"""Ronda 12 · 2ª tanda (16 nov 2026): la API nunca responde HTML.

Sondas de la tanda (antes de los arreglos):
- GET /api/ruta-inexistente -> 404 HTML; POST a la misma -> 405 HTML;
  POST /api/modules/1 -> 405 HTML; GET /api/users/abc -> 404 HTML.
- GET /dashboard con el token de un usuario borrado -> 404 HTML
  (db.get_or_404 sin manejador JSON).
- POST /modules, /lessons, /quizzes y /certificates/claim con un id
  dict ({'a': 1}) -> 500 HTML (InvalidRequestError en session.get()).
- learning_path_id=True se colaba como el id 1 (True == 1).
- POST /learning-paths con level=dict o description=list, y
  POST /lessons con content=dict/list -> 500 HTML (ProgrammingError
  en el INSERT); level=123 y content=123 se guardaban tal cual.

Arreglos: manejadores 404/405/500 JSON para /api/ en app.py (la SPA
conserva su HTML fuera de /api/), guarda api/ en el catch-all,
helper _es_id_valido en los cuatro endpoints, y validación de tipo
y longitud en los campos de texto de creación.
"""
import uuid

import pytest


def test_errores_http_de_api_responden_json(client, admin_headers):
    r = client.get("/api/ruta-inexistente")
    assert r.status_code == 404 and r.is_json
    assert r.get_json() == {"error": "Not Found"}

    r = client.post("/api/ruta-inexistente", json={})
    assert r.status_code == 405 and r.is_json
    assert r.get_json() == {"error": "Method Not Allowed"}

    r = client.post("/api/modules/1", headers=admin_headers, json={})
    assert r.status_code == 405 and r.is_json

    r = client.get("/api/users/abc", headers=admin_headers)
    assert r.status_code == 404 and r.is_json


def test_error_500_de_api_responde_json_sin_detalle(client, monkeypatch):
    # Se hace reventar una vista real (GET /api/lessons) parcheando
    # db.session.execute: el 500 no capturado debe llegar como JSON
    # genérico, sin fugar el detalle del error.
    from api.models import db

    def _revienta(*args, **kwargs):
        raise RuntimeError("boom de prueba ronda 12")

    monkeypatch.setattr(db.session, "execute", _revienta)
    r = client.get("/api/lessons")
    assert r.status_code == 500 and r.is_json
    assert r.get_json() == {"error": "Error interno del servidor"}
    # El detalle del error no se fuga en la respuesta.
    assert "boom de prueba" not in r.get_data(as_text=True)


def test_ruta_fuera_de_api_sigue_siendo_html(client):
    # La SPA conserva su comportamiento: fuera de /api/ no hay JSON.
    # (En la suite no existe dist/, así que el catch-all responde 404.)
    r = client.get("/pagina-que-no-existe-ronda12")
    assert r.status_code == 404
    assert not r.is_json


def test_dashboard_usuario_borrado_da_404_json(client, nuevo_usuario):
    headers, user = nuevo_usuario()
    from api.models import db, User
    with client.application.app_context():
        db.session.delete(db.session.get(User, user["id"]))
        db.session.commit()
    r = client.get("/api/dashboard", headers=headers)
    assert r.status_code == 404 and r.is_json


@pytest.mark.parametrize("mal_id", [{"a": 1}, "abc", True, 1.5, [1]])
def test_ids_no_enteros_en_creacion_dan_400(client, admin_headers, mal_id):
    r = client.post("/api/modules", headers=admin_headers, json={
        "title": "T", "level": "L", "learning_path_id": mal_id})
    assert r.status_code == 400 and r.is_json, mal_id
    r = client.post("/api/lessons", headers=admin_headers, json={
        "title": "T", "content": "c", "module_id": mal_id,
        "order_number": 1})
    assert r.status_code == 400 and r.is_json, mal_id
    r = client.post("/api/quizzes", headers=admin_headers, json={
        "lesson_id": mal_id, "questions_data": []})
    assert r.status_code == 400 and r.is_json, mal_id


@pytest.mark.parametrize("mal_id", [{"a": 1}, "abc", True, 1.5, [1]])
def test_path_id_no_entero_en_certificado_da_400(
        client, student_headers, mal_id):
    r = client.post("/api/certificates/claim", headers=student_headers,
                    json={"path_id": mal_id})
    assert r.status_code == 400 and r.is_json, mal_id
    assert "path_id" in r.get_json()["error"]


def test_user_id_booleano_en_progreso_da_400(client, admin_headers):
    # True == 1 y el admin demo ES el id 1: sin la guarda, un user_id
    # True pasaba el control de «es tu propio progreso» y llegaba al
    # INSERT como el id 1.
    r = client.post("/api/progress", headers=admin_headers, json=[{
        "user_id": True, "lesson_id": 1}])
    assert r.status_code == 400 and r.is_json


@pytest.mark.parametrize("campo,valor", [
    ("level", {"a": 1}), ("level", 123), ("level", ["x"]),
    ("description", ["x"]), ("image_url", 5), ("time_required", {"a": 1}),
])
def test_campos_opcionales_no_cadena_dan_400(
        client, admin_headers, campo, valor):
    r = client.post("/api/learning-paths", headers=admin_headers, json={
        "title": "Sondeo R12", campo: valor})
    assert r.status_code == 400 and r.is_json, (campo, valor)


@pytest.mark.parametrize("contenido", [123, {"a": 1}, ["x"], None])
def test_contenido_de_leccion_no_cadena_da_400(
        client, admin_headers, contenido):
    r = client.post("/api/lessons", headers=admin_headers, json={
        "title": "Sondeo R12", "content": contenido, "module_id": 1,
        "order_number": 1})
    assert r.status_code == 400 and r.is_json, contenido


def test_titulos_demasiado_largos_dan_400(client, admin_headers):
    r = client.post("/api/learning-paths", headers=admin_headers,
                    json={"title": "X" * 101})
    assert r.status_code == 400 and r.is_json
    r = client.post("/api/modules", headers=admin_headers, json={
        "title": "X" * 101, "level": "L", "learning_path_id": 1})
    assert r.status_code == 400 and r.is_json
    r = client.post("/api/modules", headers=admin_headers, json={
        "title": "T", "level": "L" * 51, "learning_path_id": 1})
    assert r.status_code == 400 and r.is_json
    r = client.post("/api/lessons", headers=admin_headers, json={
        "title": "X" * 201, "content": "c", "module_id": 1,
        "order_number": 1})
    assert r.status_code == 400 and r.is_json


def test_titulo_en_el_limite_si_se_crea(client, admin_headers):
    r = client.post("/api/learning-paths", headers=admin_headers,
                    json={"title": "Y" * 100})
    assert r.status_code == 201, r.get_json()


def test_correos_usan_la_marca_block_ethos(client, fake_mail):
    sufijo = uuid.uuid4().hex[:10]
    r = client.post("/api/signup", json={
        "username": f"Marca {sufijo}",
        "email": f"marca.{sufijo}@example.test",
        "password": "secret123",
    })
    assert r.status_code == 201, r.get_json()
    assert "Block Ethos" in fake_mail.sent[-1].subject
    assert "Block Ethos" in fake_mail.sent[-1].html
    assert "ALI" not in fake_mail.sent[-1].subject

    r = client.post("/api/forgot-password",
                    json={"email": "student@academy.test"})
    assert r.status_code == 200
    assert "Block Ethos" in fake_mail.sent[-1].subject
