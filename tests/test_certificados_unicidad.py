"""Unicidad de certificados a nivel de base de datos + detector de deriva.

- La restricción única uq_certificate_user_path impide dos certificados
  para el mismo (usuario, ruta) aunque dos reclamaciones lleguen a la
  vez; el endpoint ya devolvía el existente en el camino normal, pero
  solo la BD cierra la carrera.
- La migración 195659629ab0 crea esa restricción (y corrige la deriva
  de certificates.issued_at a NOT NULL, como ya declaraba el modelo).
- El test de deriva corre `flask db check`: si modelo y migraciones
  vuelven a divergir, la suite lo caza antes de llegar a producción.
"""
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from api.models import Certificate, db
from test_progreso_gamificacion import _lecciones_ruta

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_SRC_DIR = os.path.join(_REPO_ROOT, "src")


def _flask_env(db_file):
    env = dict(os.environ)
    env["DATABASE_URL"] = f"sqlite:///{db_file}"
    env["FLASK_APP_KEY"] = "test-secret-key"
    env["PYTHONPATH"] = _SRC_DIR
    env.pop("FLASK_DEBUG", None)
    env.pop("ENABLE_ADMIN", None)
    env.pop("SEED_DEMO_USERS", None)
    return env


def _flask(*args, db_file):
    res = subprocess.run(
        [sys.executable, "-m", "flask", "--app", "src.app", "db", *args],
        env=_flask_env(db_file), cwd=_REPO_ROOT,
        capture_output=True, text=True, timeout=600,
    )
    return res


def test_doble_certificado_directo_da_integrity_error(
        app, client, nuevo_usuario):
    """Dos inserts directos con el mismo (usuario, ruta) chocan en la BD."""
    _, user = nuevo_usuario()
    path_id, _ = _lecciones_ruta(client, "Fundamentos de Blockchain")
    ahora = datetime.now(timezone.utc)
    with app.app_context():
        primero = Certificate(
            user_id=user["id"], learning_path_id=path_id,
            code="BK-TEST1-11111-AAAAA", issued_at=ahora)
        db.session.add(primero)
        db.session.commit()
        try:
            duplicado = Certificate(
                user_id=user["id"], learning_path_id=path_id,
                code="BK-TEST2-22222-BBBBB", issued_at=ahora)
            db.session.add(duplicado)
            with pytest.raises(IntegrityError):
                db.session.commit()
        finally:
            db.session.rollback()
            db.session.delete(
                db.session.get(Certificate, primero.id))
            db.session.commit()


def test_migracion_crea_la_restriccion_unica(tmp_path):
    """`flask db upgrade` sobre una BD nueva deja la restricción única y
    el NOT NULL de issued_at en el esquema resultante."""
    db_file = tmp_path / "migracion.db"
    res = _flask("upgrade", db_file=db_file)
    assert res.returncode == 0, res.stderr or res.stdout
    con = sqlite3.connect(db_file)
    try:
        # La restricción única aparece como índice único automático
        # sobre (user_id, learning_path_id).
        unico = False
        for (nombre, es_unico, _origen) in con.execute(
                "SELECT name, \"unique\", origin FROM pragma_index_list("
                "'certificates')"):
            if not es_unico:
                continue
            columnas = [r[2] for r in con.execute(
                f"PRAGMA index_info({nombre})")]
            if columnas == ["user_id", "learning_path_id"]:
                unico = True
        assert unico, "falta el índice único (user_id, learning_path_id)"
        issued_at = [r for r in con.execute(
            "PRAGMA table_info(certificates)") if r[1] == "issued_at"][0]
        assert issued_at[3] == 1, "issued_at debería ser NOT NULL"
    finally:
        con.close()


def test_sin_deriva_entre_modelos_y_migraciones(tmp_path):
    """Tras `flask db upgrade`, `flask db check` no detecta operaciones
    pendientes: modelo y migraciones están en sync."""
    db_file = tmp_path / "deriva.db"
    res = _flask("upgrade", db_file=db_file)
    assert res.returncode == 0, res.stderr or res.stdout
    res = _flask("check", db_file=db_file)
    assert res.returncode == 0, (
        "deriva esquema↔modelo: el autogenerate detecta cambios "
        f"pendientes:\n{res.stdout}\n{res.stderr}")
