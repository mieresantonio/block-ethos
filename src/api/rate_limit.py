"""Rate limiting en memoria para los endpoints de autenticación.

Sin dependencias: solo la librería estándar. Ventana deslizante por
(IP, endpoint): cada intento queda registrado con su instante y solo
cuentan los intentos dentro de la ventana. Al superar el máximo, la
petición se rechaza con 429 JSON y cabecera Retry-After.

Límites (intentos por ventana por IP): login 10, signup /
forgot-password / reset-password 5. La ventana por defecto es de 60 s
y se configura con la variable de entorno RATE_LIMIT_WINDOW_SECONDS;
el limitador se desactiva del todo con RATE_LIMIT_DISABLED=1 (la
suite de tests lo usa: hace decenas de logins desde la misma IP).

Ambas opciones se leen al arrancar en app.py y quedan en
app.config; el decorador las consulta en cada petición, así que los
tests pueden activar/desactivar el limitador y acortar la ventana
tocando app.config sin reiniciar la app.

Límites conocidos: el estado vive en memoria del proceso. En
PythonAnywhere (un solo proceso) funciona tal cual; con varios
procesos o réplicas cada uno limitaría por separado. La IP es
request.remote_addr, que app.py resuelve con ProxyFix (x_for=1)
desde el único proxy de confianza: detrás de PythonAnywhere es la
IP real de cada cliente, no la del proxy. Un cliente no puede
falsificarla escribiendo en X-Forwarded-For: ProxyFix solo toma la
última entrada, la que añade el proxy.
"""
import threading
import time
from collections import deque
from functools import wraps

from flask import current_app, jsonify, request

# Tope de cubos (IP, endpoint) guardados: sin él, un atacante podría
# inflar la memoria con IPs falsificadas. Al llegar al tope se descartan
# primero los cubos vacíos y después los de inserción más antigua.
_MAX_BUCKETS = 5000

_lock = threading.Lock()
# {(ip, endpoint): deque([instante, ...])} — solo intentos dentro de
# la ventana; los expirados se podan en cada comprobación.
_attempts = {}


def _window_seconds():
    try:
        return max(1, int(current_app.config.get(
            "RATE_LIMIT_WINDOW_SECONDS", 60)))
    except (TypeError, ValueError):
        return 60


def _is_disabled():
    return bool(current_app.config.get("RATE_LIMIT_DISABLED", False))


def clear_rate_limit_state():
    """Vacía el estado del limitador. Solo para tests."""
    with _lock:
        _attempts.clear()


def rate_limit(max_attempts):
    """Decorador: rechaza con 429 si la IP supera max_attempts en la ventana."""
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if _is_disabled():
                return view(*args, **kwargs)
            window = _window_seconds()
            now = time.monotonic()
            key = (request.remote_addr or "unknown", request.endpoint)
            with _lock:
                bucket = _attempts.setdefault(key, deque())
                while bucket and bucket[0] <= now - window:
                    bucket.popleft()
                if len(bucket) >= max_attempts:
                    retry_after = max(1, int(bucket[0] + window - now) + 1)
                    response = jsonify({
                        "error": "Demasiados intentos, inténtalo más tarde"})
                    response.status_code = 429
                    response.headers["Retry-After"] = str(retry_after)
                    return response
                bucket.append(now)
                if len(_attempts) > _MAX_BUCKETS:
                    # Descarta cubos vacíos primero; si no basta, los más viejos.
                    for old_key in list(_attempts):
                        if not _attempts[old_key]:
                            del _attempts[old_key]
                    while len(_attempts) > _MAX_BUCKETS:
                        _attempts.pop(next(iter(_attempts)))
            return view(*args, **kwargs)
        return wrapped
    return decorator
