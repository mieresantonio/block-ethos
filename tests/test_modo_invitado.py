"""Modo invitado (F-BE2): una lección de muestra pública sin sesión;
el resto del contenido exige sesión. Los quizzes nunca son públicos."""

MUESTRA_TITULO = "¿Qué es una blockchain?"


def _muestra(client):
    r = client.get("/api/lessons/sample")
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def _no_muestra_id(client):
    lecciones = client.get("/api/lessons").get_json()
    otra = next(l for l in lecciones if not l["is_sample"])
    return otra["id"]


def test_muestra_publica_sin_sesion(client):
    muestra = _muestra(client)
    assert muestra["title"] == MUESTRA_TITULO
    assert muestra["content"]
    assert muestra["is_sample"] is True
    assert muestra["path_title"] == "Fundamentos de Blockchain"
    assert muestra["module_lessons"]


def test_muestra_legible_por_id_sin_sesion(client):
    muestra = _muestra(client)
    r = client.get(f"/api/lessons/{muestra['id']}")
    assert r.status_code == 200
    assert r.get_json()["content"] == muestra["content"]


def test_otra_leccion_exige_sesion(client, student_headers):
    lid = _no_muestra_id(client)
    r = client.get(f"/api/lessons/{lid}")
    assert r.status_code == 401
    assert "error" in r.get_json()
    r = client.get(f"/api/lessons/{lid}", headers=student_headers)
    assert r.status_code == 200
    assert r.get_json()["content"]


def test_quiz_exige_sesion_incluso_el_de_la_muestra(
        client, student_headers):
    muestra = _muestra(client)
    r = client.get(f"/api/quizzes/{muestra['id']}")
    assert r.status_code == 401
    r = client.get(f"/api/quizzes/{muestra['id']}",
                   headers=student_headers)
    assert r.status_code == 200
    assert len(r.get_json()["questions"]) == 4


def test_404_sigue_siendolo_para_invitados(client):
    for url in ("/api/lessons/99999", "/api/quizzes/99999"):
        r = client.get(url)
        assert r.status_code == 404, url
        assert "error" in r.get_json(), url


def test_catalogo_marca_la_muestra(client):
    paths = client.get("/api/learning-paths").get_json()
    fund = next(p for p in paths
                if p["title"] == "Fundamentos de Blockchain")
    detalle = client.get(f"/api/learning-paths/{fund['id']}").get_json()
    marcadas = [l for m in detalle["modules"] for l in m["lessons"]
                if l["is_sample"]]
    assert len(marcadas) == 1
    assert marcadas[0]["title"] == MUESTRA_TITULO
    lista = client.get("/api/lessons").get_json()
    assert sum(1 for l in lista if l["is_sample"]) == 1


def test_invitado_no_guarda_progreso(client):
    r = client.post("/api/progress", json=[])
    assert r.status_code == 401


def test_invitado_no_reclama_certificado(client):
    r = client.post("/api/certificates/claim",
                    json={"learning_path_id": 1})
    assert r.status_code == 401
