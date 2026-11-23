"""Perfil público verificable (/u/<handle>): opt-in por estudiante,
solo campos públicos, mismo 404 para «no existe» y «no es público»,
y cada certificado comprobable en /verificar/<código>."""


def _publicar(client, headers, handle):
    r = client.put("/api/profile/me", json={"handle": handle},
                   headers=headers)
    assert r.status_code == 200, r.get_json()
    r = client.put("/api/profile/me", json={"is_public": True},
                   headers=headers)
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def _perfil_publico(client, handle):
    return client.get(f"/api/profile/{handle}")


def _primera_ruta_con_lecciones(client):
    r = client.get("/api/learning-paths")
    assert r.status_code == 200, r.get_json()
    for ruta in r.get_json():
        detalle = client.get(f"/api/learning-paths/{ruta['id']}").get_json()
        lecciones = [l for m in detalle["modules"] for l in m["lessons"]]
        if lecciones:
            return ruta["id"], lecciones
    raise AssertionError("la semilla no tiene ninguna ruta con lecciones")


def _completar_ruta(client, headers, user_id, lecciones):
    for leccion in lecciones:
        r = client.put(
            f"/api/progress/{user_id}/{leccion['id']}",
            json={"is_completed": True, "quiz_score": 100}, headers=headers)
        assert r.status_code == 200, r.get_json()


def test_handle_invalido_da_400(client, nuevo_usuario):
    headers, _user = nuevo_usuario()
    for handle in ["ab", "a b", "-abc", "abc-", "a" * 31, "me", "admin",
                   "tutor", "con espacios", "CON_MAYUSCULAS_Y_ESPACIO"]:
        r = client.put("/api/profile/me", json={"handle": handle},
                       headers=headers)
        assert r.status_code == 400, (handle, r.get_json())


def test_handle_duplicado_da_409(client, nuevo_usuario):
    headers1, _u1 = nuevo_usuario()
    headers2, _u2 = nuevo_usuario()
    r = client.put("/api/profile/me", json={"handle": "estudiante-uno"},
                   headers=headers1)
    assert r.status_code == 200, r.get_json()
    r = client.put("/api/profile/me", json={"handle": "Estudiante-Uno"},
                   headers=headers2)
    assert r.status_code == 409, r.get_json()


def test_publicar_sin_handle_da_400(client, nuevo_usuario):
    headers, _user = nuevo_usuario()
    r = client.put("/api/profile/me", json={"is_public": True},
                   headers=headers)
    assert r.status_code == 400, r.get_json()


def test_perfil_privado_da_404(client, nuevo_usuario):
    headers, _user = nuevo_usuario()
    r = client.put("/api/profile/me", json={"handle": "solo-privado"},
                   headers=headers)
    assert r.status_code == 200, r.get_json()
    r = _perfil_publico(client, "solo-privado")
    assert r.status_code == 404


def test_perfil_inexistente_da_404_igual_que_privado(client, nuevo_usuario):
    headers, _user = nuevo_usuario()
    client.put("/api/profile/me", json={"handle": "privado-dos"},
               headers=headers)
    privado = _perfil_publico(client, "privado-dos")
    inexistente = _perfil_publico(client, "nadie-existe-aqui")
    assert privado.status_code == 404
    assert inexistente.status_code == 404
    # La respuesta no distingue un caso del otro: sin oráculo.
    assert privado.get_json() == inexistente.get_json()


def test_perfil_publico_muestra_solo_campos_publicos(
        client, nuevo_usuario):
    headers, user = nuevo_usuario()
    _publicar(client, headers, "MiHandle1")
    r = _perfil_publico(client, "mihandle1")
    assert r.status_code == 200
    body = r.get_json()
    assert body["handle"] == "mihandle1"
    assert body["display_name"] == user["username"]
    assert body["level_name"]
    assert isinstance(body["xp"], int)
    assert isinstance(body["paths"], list)
    assert body["certificates_count"] == 0
    assert "email" not in body
    assert "id" not in body
    assert "quiz_score" not in str(body)
    assert "streak" not in str(body).lower()


def test_perfil_publico_muestra_avance_por_ruta(client, nuevo_usuario):
    headers, user = nuevo_usuario()
    path_id, lecciones = _primera_ruta_con_lecciones(client)
    _publicar(client, headers, "avance-ruta")
    r = client.put(
        f"/api/progress/{user['id']}/{lecciones[0]['id']}",
        json={"is_completed": True}, headers=headers)
    assert r.status_code == 200, r.get_json()
    body = _perfil_publico(client, "avance-ruta").get_json()
    ruta = [p for p in body["paths"] if p["path_id"] == path_id][0]
    assert ruta["lessons_completed"] == 1
    assert ruta["lessons_total"] == len(lecciones)
    assert 0 < ruta["percent"] < 100 or len(lecciones) == 1
    assert ruta["certificate"] is None


def test_perfil_publico_muestra_certificado_tras_reclamar(
        client, nuevo_usuario):
    headers, user = nuevo_usuario()
    path_id, lecciones = _primera_ruta_con_lecciones(client)
    _completar_ruta(client, headers, user["id"], lecciones)
    r = client.post("/api/certificates/claim", json={"path_id": path_id},
                    headers=headers)
    assert r.status_code in (200, 201), r.get_json()
    codigo = r.get_json()["code"]
    _publicar(client, headers, "con-certificado")
    body = _perfil_publico(client, "con-certificado").get_json()
    ruta = [p for p in body["paths"] if p["path_id"] == path_id][0]
    assert ruta["certificate"]["code"] == codigo
    assert body["certificates_count"] == 1
    # La verificación es independiente del perfil: el código se
    # comprueba en el endpoint público de certificados.
    r = client.get(f"/api/certificates/verify/{codigo}")
    assert r.status_code == 200
    assert r.get_json()["valid"] is True


def test_admin_no_puede_configurar_perfil(client, admin_headers):
    r = client.put("/api/profile/me", json={"handle": "el-admin"},
                   headers=admin_headers)
    assert r.status_code == 403, r.get_json()


def test_cambiar_handle_mueve_la_url(client, nuevo_usuario):
    headers, _user = nuevo_usuario()
    _publicar(client, headers, "handle-viejo")
    assert _perfil_publico(client, "handle-viejo").status_code == 200
    r = client.put("/api/profile/me", json={"handle": "handle-nuevo"},
                   headers=headers)
    assert r.status_code == 200, r.get_json()
    assert _perfil_publico(client, "handle-viejo").status_code == 404
    assert _perfil_publico(client, "handle-nuevo").status_code == 200


def test_ocultar_perfil_lo_hace_desaparecer(client, nuevo_usuario):
    headers, _user = nuevo_usuario()
    _publicar(client, headers, "ahora-me-escondo")
    assert _perfil_publico(client, "ahora-me-escondo").status_code == 200
    r = client.put("/api/profile/me", json={"is_public": False},
                   headers=headers)
    assert r.status_code == 200, r.get_json()
    assert _perfil_publico(client, "ahora-me-escondo").status_code == 404


def test_get_my_profile_devuelve_configuracion(client, nuevo_usuario):
    r = client.get("/api/profile/me")
    assert r.status_code == 401
    headers, _user = nuevo_usuario()
    r = client.get("/api/profile/me", headers=headers)
    assert r.status_code == 200
    assert r.get_json() == {
        "handle": None, "is_public": False,
        "username": _user["username"]}
