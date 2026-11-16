"""Tests del rate limiting de auth (api/rate_limit.py).

La suite entera corre con el limitador APAGADO (conftest.py pone
RATE_LIMIT_DISABLED=1, porque decenas de logins salen de la misma IP
de test). Estos tests lo encienden en caliente tocando app.config y
lo devuelven a su estado al terminar; cada test empieza con el estado
del limitador vacío.
"""
import time
import uuid

import pytest

from api.rate_limit import clear_rate_limit_state

LOGIN_LIMIT = 10
OTHER_LIMIT = 5
EXPECTED_ERROR = "Demasiados intentos, inténtalo más tarde"


@pytest.fixture()
def rate_limit_on(app):
    """Enciende el limitador con la ventana por defecto (60 s)."""
    app.config["RATE_LIMIT_DISABLED"] = False
    clear_rate_limit_state()
    yield
    clear_rate_limit_state()
    app.config["RATE_LIMIT_DISABLED"] = True
    app.config["RATE_LIMIT_WINDOW_SECONDS"] = 60


@pytest.fixture()
def rate_limit_short_window(app):
    """Enciende el limitador con una ventana de 2 s (para probar la recuperación)."""
    app.config["RATE_LIMIT_DISABLED"] = False
    app.config["RATE_LIMIT_WINDOW_SECONDS"] = 2
    clear_rate_limit_state()
    yield
    clear_rate_limit_state()
    app.config["RATE_LIMIT_DISABLED"] = True
    app.config["RATE_LIMIT_WINDOW_SECONDS"] = 60


def _bad_login(client):
    return client.post("/api/login", json={
        "email": "nadie@example.test", "password": "incorrecta"})


def _assert_429(response):
    assert response.status_code == 429, response.get_json()
    assert response.get_json() == {"error": EXPECTED_ERROR}
    retry_after = response.headers.get("Retry-After")
    assert retry_after is not None, "falta la cabecera Retry-After"
    assert int(retry_after) >= 1


def test_login_429_tras_umbral(client, rate_limit_on):
    """10 logins fallidos → 401; el 11º → 429 JSON con Retry-After."""
    for _ in range(LOGIN_LIMIT):
        r = _bad_login(client)
        assert r.status_code == 401, r.get_json()
    _assert_429(_bad_login(client))


def test_login_se_recupera_tras_la_ventana(client, rate_limit_short_window):
    """Tras esperar la ventana, un login correcto vuelve a funcionar."""
    for _ in range(LOGIN_LIMIT):
        assert _bad_login(client).status_code == 401
    _assert_429(_bad_login(client))
    time.sleep(2.5)
    r = client.post("/api/login", json={
        "email": "student@academy.test", "password": "Student123!"})
    assert r.status_code == 200, r.get_json()
    assert "token" in r.get_json()


def test_signup_429_tras_umbral(client, rate_limit_on):
    """5 registros → 201; el 6º → 429 (límite propio de signup)."""
    for i in range(OTHER_LIMIT):
        r = client.post("/api/signup", json={
            "username": f"RL {i}",
            "email": f"rl.{uuid.uuid4().hex[:10]}@example.test",
            "password": "secret123",
        })
        assert r.status_code == 201, r.get_json()
    r = client.post("/api/signup", json={
        "username": "RL extra",
        "email": f"rl.{uuid.uuid4().hex[:10]}@example.test",
        "password": "secret123",
    })
    _assert_429(r)


def test_forgot_password_429_tras_umbral(client, rate_limit_on):
    """5 solicitudes de recuperación → 200; la 6ª → 429."""
    for _ in range(OTHER_LIMIT):
        r = client.post("/api/forgot-password", json={
            "email": "nadie@example.test"})
        assert r.status_code == 200, r.get_json()
    _assert_429(client.post("/api/forgot-password", json={
        "email": "nadie@example.test"}))


def test_reset_password_429_tras_umbral(client, rate_limit_on):
    """5 intentos de reseteo con token inválido → 400; el 6º → 429."""
    for _ in range(OTHER_LIMIT):
        r = client.post("/api/reset-password", json={
            "token": "token-invalido", "password": "nueva123"})
        assert r.status_code == 400, r.get_json()
    _assert_429(client.post("/api/reset-password", json={
        "token": "token-invalido", "password": "nueva123"}))


def test_limite_por_endpoint_y_por_ip(client, rate_limit_on):
    """Agotar el login no bloquea otro endpoint ni a otra IP."""
    for _ in range(LOGIN_LIMIT):
        assert _bad_login(client).status_code == 401
    _assert_429(_bad_login(client))
    # Otro endpoint desde la misma IP: sigue respondiendo normal.
    r = client.post("/api/forgot-password", json={
        "email": "nadie@example.test"})
    assert r.status_code == 200, r.get_json()
    # Otra IP: el login sigue respondiendo normal (401, no 429).
    r = client.post("/api/login", json={
        "email": "nadie@example.test", "password": "incorrecta"},
        environ_base={"REMOTE_ADDR": "203.0.113.9"})
    assert r.status_code == 401, r.get_json()


def test_limitador_apagado_no_bloquea(client):
    """Con RATE_LIMIT_DISABLED (estado de la suite), 12 logins fallidos
    seguidos son todos 401: nunca aparece el 429."""
    clear_rate_limit_state()
    for _ in range(LOGIN_LIMIT + 2):
        r = _bad_login(client)
        assert r.status_code == 401, r.get_json()
