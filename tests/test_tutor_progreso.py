"""Tutor con progreso: con sesión, el tutor conoce dónde va el
estudiante y guía su siguiente paso; sin sesión responde igual que
siempre. Las lecciones y los ids se derivan de la API, sin suponer
contenido de la semilla (salvo «Proof of Work», ya probado en
test_tutor.py)."""


def _preguntar(client, pregunta, headers=None):
    return client.post("/api/tutor", json={"question": pregunta},
                       headers=headers or {})


def _lecciones(client):
    r = client.get("/api/lessons")
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def _completar(client, headers, user_id, lesson_id, quiz_score=None):
    body = {"is_completed": True}
    if quiz_score is not None:
        body["quiz_score"] = quiz_score
    r = client.put(f"/api/progress/{user_id}/{lesson_id}",
                   json=body, headers=headers)
    assert r.status_code == 200, r.get_json()


def _leccion_con_quiz(client, headers):
    """Primera lección que tiene quiz, o None si la semilla no tiene.

    Los quizzes exigen sesión (modo invitado): sin headers, el
    endpoint responde 401 y el bucle no encontraría ninguna.
    """
    for leccion in _lecciones(client):
        r = client.get(f"/api/quizzes/{leccion['id']}", headers=headers)
        if r.status_code == 200:
            return leccion
    return None


def test_tutor_anonimo_no_recibe_next_step(client):
    """Sin sesión el tutor responde igual que antes: next_step null y
    sin marca de respuesta de progreso."""
    r = _preguntar(client, "¿Qué es el proof of work?")
    assert r.status_code == 200
    body = r.get_json()
    assert body["found"] is True
    assert body["next_step"] is None
    assert body["progress_answer"] is False


def test_tutor_con_sesion_devuelve_siguiente_paso(client, nuevo_usuario):
    headers, user = nuevo_usuario()
    r = _preguntar(client, "¿Qué es el proof of work?", headers)
    assert r.status_code == 200
    body = r.get_json()
    paso = body["next_step"]
    assert paso is not None
    assert paso["all_done"] is False
    assert paso["lessons_total"] > 0
    assert paso["lessons_completed"] == 0
    siguiente = paso["next_lesson"]
    assert siguiente["lesson_id"] in [l["id"] for l in _lecciones(client)]
    assert siguiente["lesson_title"]
    assert siguiente["path_id"]
    assert siguiente["path_title"]


def test_siguiente_paso_avanza_al_completar(client, nuevo_usuario):
    headers, user = nuevo_usuario()
    primero = _preguntar(
        client, "¿Qué es el proof of work?", headers).get_json()
    primera = primero["next_step"]["next_lesson"]
    _completar(client, headers, user["id"], primera["lesson_id"])
    segundo = _preguntar(
        client, "¿Qué es el proof of work?", headers).get_json()
    paso = segundo["next_step"]
    assert paso["lessons_completed"] == 1
    if paso["all_done"]:
        assert paso["next_lesson"] is None
    else:
        assert paso["next_lesson"]["lesson_id"] != primera["lesson_id"]


def test_quiz_pendiente_aparece_en_next_step(client, nuevo_usuario):
    import pytest
    headers, user = nuevo_usuario()
    leccion = _leccion_con_quiz(client, headers)
    if leccion is None:
        pytest.skip("la semilla no tiene ninguna lección con quiz")
    # Lección completada SIN nota: el quiz queda pendiente de aprobar.
    _completar(client, headers, user["id"], leccion["id"])
    body = _preguntar(
        client, "¿Qué es el proof of work?", headers).get_json()
    pendientes = body["next_step"]["quizzes_pending"]
    assert any(p["lesson_id"] == leccion["id"] for p in pendientes)


def test_pregunta_progreso_con_sesion_responde_desde_progreso(
        client, nuevo_usuario):
    headers, user = nuevo_usuario()
    r = _preguntar(
        client, "¿Qué me falta para terminar mi ruta?", headers)
    assert r.status_code == 200
    body = r.get_json()
    assert body["found"] is True
    assert body["progress_answer"] is True
    assert "siguiente paso" in body["answer"]
    siguiente = body["next_step"]["next_lesson"]
    assert siguiente["lesson_title"] in body["answer"]
    # La fuente es la siguiente lección: el enlace lleva a seguir.
    assert body["sources"]
    assert body["sources"][0]["lesson_id"] == siguiente["lesson_id"]


def test_pregunta_progreso_anonima_pide_sesion(client):
    r = _preguntar(client, "¿Qué me falta para terminar mi ruta?")
    assert r.status_code == 200
    body = r.get_json()
    assert body["found"] is False
    assert "inicia sesión" in body["answer"]
    assert body["next_step"] is None


def test_token_invalido_no_rompe_el_tutor(client):
    """Un token caducado o inválido guardado en el navegador no debe
    romper una página pública: el tutor responde como anónimo."""
    r = _preguntar(client, "¿Qué es el proof of work?",
                   {"Authorization": "Bearer token-invalido"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["found"] is True
    assert body["next_step"] is None


def test_todo_completo_all_done(client, nuevo_usuario):
    headers, user = nuevo_usuario()
    for leccion in _lecciones(client):
        _completar(client, headers, user["id"], leccion["id"],
                   quiz_score=100)
    body = _preguntar(
        client, "¿Qué me falta para terminar mi ruta?", headers).get_json()
    assert body["next_step"]["all_done"] is True
    assert body["next_step"]["next_lesson"] is None
    assert body["next_step"]["quizzes_pending"] == []
    assert "todas las lecciones" in body["answer"]
