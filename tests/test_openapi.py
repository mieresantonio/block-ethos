"""Test de contrato OpenAPI: docs/openapi.yaml contra las rutas reales.

- Cada ruta /api/* registrada en app.url_map debe estar documentada,
  con sus mismos métodos, y cada ruta documentada debe existir de
  verdad (añadir un endpoint sin documentarlo rompe la suite).
- Todos los endpoints deben estar DETALLADOS (cuerpos y respuestas
  reales, no el marcador «sin detallar todavía» del esqueleto generado).
- Todas las referencias $ref deben resolver a componentes definidos.
- GET /api/openapi.yaml sirve el mismo archivo del repo.
"""
import os
import re

import yaml

SPEC_PATH = os.path.join(os.path.dirname(__file__), "..", "docs",
                         "openapi.yaml")
PARAM_RE = re.compile(r"<(?:int|string):(\w+)>")

# Endpoints con rate limiting: deben documentar el 429.
RATE_LIMITED = ["/api/login", "/api/signup",
                "/api/forgot-password", "/api/reset-password"]


def _load_spec():
    """Carga la spec rechazando claves duplicadas: yaml.safe_load las
    sobrescribe en silencio y una ruta duplicada desaparecería sin que
    ningún test lo notara."""
    class NoDupLoader(yaml.SafeLoader):
        pass

    def _no_dup(loader, node):
        seen = set()
        for key_node, _value in node.value:
            key = loader.construct_object(key_node, deep=True)
            if key in seen:
                raise ValueError(f"clave duplicada en openapi.yaml: {key!r}")
            seen.add(key)
        return loader.construct_mapping(node, deep=True)

    NoDupLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_dup)
    with open(SPEC_PATH) as f:
        return yaml.load(f, Loader=NoDupLoader)


def _real_routes(app):
    """{(ruta OpenAPI): {métodos}} de las rutas /api/* registradas."""
    routes = {}
    for rule in app.url_map.iter_rules():
        if not rule.rule.startswith("/api/"):
            continue
        methods = {m.lower() for m in rule.methods
                   if m not in ("HEAD", "OPTIONS")}
        path = PARAM_RE.sub(r"{\1}", rule.rule)
        routes.setdefault(path, set()).update(methods)
    return routes


def test_spec_es_yaml_valido_con_estructura_openapi():
    spec = _load_spec()
    assert spec["openapi"].startswith("3.")
    assert spec["info"]["title"]
    assert isinstance(spec["paths"], dict) and spec["paths"]


def test_toda_ruta_real_esta_documentada_y_viceversa(app):
    spec = _load_spec()
    reales = _real_routes(app)
    documentadas = {
        path: {m for m in ops if m in
               ("get", "post", "put", "patch", "delete")}
        for path, ops in spec["paths"].items()
    }
    faltan = {p: sorted(reales[p] - documentadas.get(p, set()))
              for p in reales if reales[p] - documentadas.get(p, set())}
    sobran = {p: sorted(documentadas[p] - reales.get(p, set()))
              for p in documentadas
              if documentadas[p] - reales.get(p, set())}
    assert not faltan, f"rutas reales sin documentar: {faltan}"
    assert not sobran, f"rutas documentadas que no existen: {sobran}"


def test_todos_los_endpoints_detallados():
    """Ninguna operación lleva el marcador de esqueleto «sin detallar»:
    cada endpoint documenta sus respuestas reales, y cada POST su cuerpo."""
    spec = _load_spec()
    for path, ops in spec["paths"].items():
        for method, op in ops.items():
            if not isinstance(op, dict):
                continue  # p. ej. `parameters` a nivel de ruta, no operación
            assert "sin detallar" not in op.get("summary", ""), \
                f"{method.upper()} {path} sigue sin detallar"
            assert "sin detallar" not in str(op.get("responses", {})), \
                f"{method.upper()} {path} tiene respuestas sin detallar"
            assert op.get("responses"), f"{method.upper()} {path} sin responses"
            if method == "post" and path != "/api/hello":
                assert op.get("requestBody"), \
                    f"POST {path} sin requestBody"
    # Los 4 endpoints con rate limiting documentan el 429.
    for path in RATE_LIMITED:
        assert "429" in spec["paths"][path]["post"]["responses"], \
            f"{path} no documenta el 429"


def test_todas_las_referencias_resuelven():
    spec = _load_spec()
    refs = set()

    def _buscar(nodo):
        if isinstance(nodo, dict):
            ref = nodo.get("$ref")
            if isinstance(ref, str):
                refs.add(ref)
            for valor in nodo.values():
                _buscar(valor)
        elif isinstance(nodo, list):
            for item in nodo:
                _buscar(item)

    _buscar(spec)
    assert refs, "la especificación no usa ninguna $ref"
    for ref in refs:
        assert ref.startswith("#/components/schemas/"), ref
        nombre = ref.split("/")[-1]
        assert nombre in spec["components"]["schemas"], \
            f"$ref sin definir: {ref}"


def test_endpoint_sirve_la_misma_especificacion(client):
    r = client.get("/api/openapi.yaml")
    assert r.status_code == 200, r.status_code
    with open(SPEC_PATH, "rb") as f:
        assert r.data == f.read()
