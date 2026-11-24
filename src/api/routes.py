import hashlib
import math
import os
import re
import unicodedata
from collections import Counter
from datetime import timedelta, datetime, timezone

from flask import request, jsonify, Blueprint, current_app, send_from_directory
from flask_cors import CORS
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from flask_jwt_extended import (
    jwt_required,
    get_jwt_identity,
    create_access_token,
    decode_token,
    verify_jwt_in_request,
)
from flask_jwt_extended.exceptions import JWTExtendedException
from flask_mail import Message

from api.models import db, User, UserType, LearningPath, Module, Lesson, Quiz, UserProgress, Certificate
from api.mail import mail
from api.rate_limit import rate_limit

api = Blueprint('api', __name__)
CORS(api)

EMAIL_REGEX = r'^[\w\.-]+@[\w\.-]+\.\w+$'


def _texto(data, key):
    """Campo de texto seguro: '' si falta, es None o no es una cadena.

    Sin esto, un JSON como {"username": null} reventaba con AttributeError
    (500 en HTML) al hacer .strip() sobre None.
    """
    value = data.get(key)
    return value.strip() if isinstance(value, str) else ""


def _es_score_valido(value):
    """Un quiz_score válido es un número entre 0 y 100 (bool no cuenta)."""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and 0 <= value <= 100
    )


def _es_id_valido(value):
    """Un id de clave foránea válido es un entero (bool no cuenta).

    Sin esto, un dict como learning_path_id reventaba en
    db.session.get() con InvalidRequestError (500 HTML), y True se
    colaba como el id 1 (en Python, True == 1). Mismo criterio que
    ya aplicaba POST /progress a lesson_id.
    """
    return isinstance(value, int) and not isinstance(value, bool)


def _usuario_opcional_del_token():
    """Usuario del JWT si viene un token válido; None en caso contrario.

    Para endpoints públicos que se personalizan con sesión (el tutor):
    sin token, con un token caducado o con uno inválido, se responde
    como anónimo en vez de devolver 401/422. Un token viejo guardado
    en el navegador no debe romper nunca una página pública.
    """
    try:
        verify_jwt_in_request(optional=True)
    except JWTExtendedException:
        return None
    user_id = _current_user_id()
    if user_id is None:
        return None
    return db.session.get(User, user_id)


def _current_user_id():
    """Id numérico del JWT, o None si la identidad no es un id válido.

    Los tokens de verificación de correo y de recuperación llevan el
    EMAIL como identidad (claim 'type' distinto): usarlos como Bearer en
    un endpoint protegido reventaba con ValueError en int() (500 HTML).
    Con None, cada endpoint responde 403/404 en JSON, como debe ser.
    """
    try:
        return int(get_jwt_identity())
    except (TypeError, ValueError):
        return None


def _require_admin():
    """(usuario, None) si el JWT es de un admin; (None, respuesta 403) si no.

    La página Admin del frontend ya oculta la creación de contenido a los
    estudiantes, pero esa barrera era solo visual: cualquier estudiante con
    token podía crear rutas/módulos/lecciones por API. Esto lo cierra en el
    servidor, que es donde cuenta.
    """
    user_id = _current_user_id()
    user = db.session.get(User, user_id) if user_id is not None else None
    if not user or user.role != UserType.admin:
        return None, (jsonify({
            "error": "No tienes permiso para acceder a este recurso"}), 403)
    return user, None


# ============================================================================
# AUTENTICACIÓN (registro + verificación de correo)
# ============================================================================

@api.route('/signup', methods=['POST'])
@rate_limit(max_attempts=5)
def handle_signup():
    data = request.get_json(silent=True)
    # Un JSON válido pero no-objeto (p. ej. una lista) es truthy y hacía
    # que _texto reventara con AttributeError en data.get (500 HTML).
    if not isinstance(data, dict) or not data:
        return jsonify({"error": "Cuerpo de la petición inválido"}), 400

    username = _texto(data, 'username')
    email = _texto(data, 'email').lower()
    password = data.get('password')
    if not isinstance(password, str):
        password = ''

    if len(email) > 120 or len(username) > 80:
        return jsonify({"error": "El correo o el nombre de usuario son demasiado largos"}), 400
    if not email or not re.match(EMAIL_REGEX, email):
        return jsonify({"error": "Debes proporcionar un correo electrónico válido"}), 400
    if not password or len(password) < 6:
        return jsonify({"error": "La contraseña debe tener al menos 6 caracteres"}), 400

    existing = db.session.execute(
        db.select(User).filter_by(email=email)
    ).scalar_one_or_none()

    if existing and existing.is_active:
        return jsonify({"error": "El correo ya está registrado y activo. Inicia sesión."}), 400

    if existing and not existing.is_active:
        existing.username = username
        existing.set_password(password)
        user = existing
    else:
        user = User(email=email, username=username,
                    is_active=False, role=UserType.student)
        user.set_password(password)
        db.session.add(user)

    db.session.commit()

    token = create_access_token(
        identity=user.email,
        expires_delta=timedelta(hours=24),
        additional_claims={"type": "verify_email"}
    )
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    verification_link = f"{frontend_url}/verify-email?token={token}"

    try:
        msg = Message(
            subject="Verifica tu cuenta en Block Ethos",
            recipients=[user.email],
            html=f"""
            <div style="font-family:Arial,Helvetica,sans-serif;max-width:600px;
                        padding:32px 24px;line-height:1.6;color:#212529">
              <h2 style="margin:0 0 20px 0">¡Hola{f', {username}' if username else ''}!</h2>
              <p style="margin:0 0 24px 0">
                Gracias por registrarte en Block Ethos. Confirma tu correo para activar tu cuenta:
              </p>
              <p style="margin:0 0 24px 0">
                <a href="{verification_link}"
                   style="display:inline-block;background:#0d6efd;color:#fff;
                          padding:14px 32px;border-radius:6px;text-decoration:none;
                          font-weight:bold">Verificar mi cuenta</a>
              </p>
              <p style="margin:0 0 8px 0;color:#6c757d;font-size:14px">
                Este enlace vence en 24 horas.
              </p>
              <p style="margin:0;color:#6c757d;font-size:14px">
                Si no fuiste tú, ignora este correo de forma segura.
              </p>
            </div>
            """
        )
        mail.send(msg)
    except Exception as e:
        current_app.logger.error(
            "Error enviando correo de verificación: %s", e)
        return jsonify({
            "message": "Usuario registrado, pero hubo un error al enviar el correo.",
            "error": str(e)
        }), 500

    return jsonify({"message": "Usuario registrado con éxito. Revisa tu correo para verificar tu cuenta."}), 201


@api.route('/login', methods=['POST'])
@rate_limit(max_attempts=10)
def handle_login():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not data:
        return jsonify({"error": "Cuerpo de la petición inválido"}), 400

    email = _texto(data, 'email').lower()
    password = data.get('password')
    if not isinstance(password, str):
        password = ''

    user = db.session.execute(
        db.select(User).filter_by(email=email)
    ).scalar_one_or_none()

    if not user or not user.check_password(password):
        return jsonify({"error": "Credenciales inválidas"}), 401

    if not user.is_active:
        return jsonify({"error": "Debes verificar tu correo antes de iniciar sesión."}), 403

    token = create_access_token(identity=str(user.id))
    return jsonify({"token": token, "user": user.serialize()}), 200


@api.route('/verify-email', methods=['POST'])
def handle_verify_email():
    data = request.get_json(silent=True)
    token = data.get('token') if isinstance(data, dict) else None
    if not token:
        return jsonify({"error": "No se proporcionó ningún token de verificación."}), 400

    try:
        decoded = decode_token(token)
        if decoded.get('type') != 'verify_email':
            return jsonify({"error": "Tipo de token inválido"}), 400

        email = decoded.get('sub')
        user = db.session.execute(
            db.select(User).filter_by(email=email)
        ).scalar_one_or_none()

        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404
        if user.is_active:
            return jsonify({"message": "Tu cuenta ya se encuentra verificada."}), 200

        user.is_active = True
        db.session.commit()
        return jsonify({"message": "¡Cuenta verificada exitosamente! Ya puedes iniciar sesión."}), 200

    except Exception as e:
        return jsonify({"error": "El enlace de verificación es inválido o ha expirado.", "detail": str(e)}), 400


@api.route('/forgot-password', methods=['POST'])
@rate_limit(max_attempts=5)
def handle_forgot_password():
    data = request.get_json(silent=True)
    email = _texto(data, 'email').lower() if isinstance(data, dict) else ''

    if not email:
        return jsonify({"error": "Debes proporcionar un correo electrónico."}), 400

    user = db.session.execute(
        db.select(User).filter_by(email=email)
    ).scalar_one_or_none()

    # Por seguridad, respondemos igual exista o no el correo (no revelamos
    # si un email está registrado).
    generic_message = "Si el correo existe, hemos enviado las instrucciones para restablecer tu contraseña."

    if not user:
        return jsonify({"message": generic_message}), 200

    token = create_access_token(
        identity=user.email,
        expires_delta=timedelta(hours=1),
        additional_claims={"type": "reset_password"}
    )
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    reset_link = f"{frontend_url}/reset-password?token={token}"

    try:
        msg = Message(
            subject="Recuperación de contraseña - Block Ethos",
            recipients=[user.email],
            html=f"""
            <div style="font-family:Arial,Helvetica,sans-serif;max-width:600px;
                        padding:32px 24px;line-height:1.6;color:#212529">
              <h2 style="margin:0 0 20px 0">Hola{f', {user.username}' if user.username else ''},</h2>
              <p style="margin:0 0 24px 0">
                Recibimos una solicitud para restablecer la contraseña de tu cuenta.
                Haz clic en el siguiente botón para continuar:
              </p>
              <p style="margin:0 0 24px 0">
                <a href="{reset_link}"
                   style="display:inline-block;background:#0d6efd;color:#fff;
                          padding:14px 32px;border-radius:6px;text-decoration:none;
                          font-weight:bold">Restablecer contraseña</a>
              </p>
              <p style="margin:0 0 8px 0;color:#6c757d;font-size:14px">
                Este enlace expirará en 1 hora.
              </p>
              <p style="margin:0;color:#6c757d;font-size:14px">
                Si no solicitaste este cambio, puedes ignorar este correo de forma segura.
              </p>
            </div>
            """
        )
        mail.send(msg)
    except Exception as e:
        current_app.logger.error(
            "Error enviando correo de recuperación: %s", e)

    return jsonify({"message": generic_message}), 200


@api.route('/reset-password', methods=['POST'])
@rate_limit(max_attempts=5)
def handle_reset_password():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        data = {}
    token = data.get('token')
    new_password = data.get('password')
    # Igual que en signup/login: una contraseña que no es cadena no es
    # válida. Sin esto, len(123456) reventaba con TypeError (500 HTML)
    # antes de llegar a cualquier validación.
    if not isinstance(new_password, str):
        new_password = ''

    if not token or not new_password:
        return jsonify({"error": "Faltan datos para restablecer la contraseña."}), 400
    if len(new_password) < 6:
        return jsonify({"error": "La contraseña debe tener al menos 6 caracteres"}), 400

    try:
        decoded = decode_token(token)
        if decoded.get('type') != 'reset_password':
            return jsonify({"error": "Tipo de token inválido"}), 400

        email = decoded.get('sub')
        user = db.session.execute(
            db.select(User).filter_by(email=email)
        ).scalar_one_or_none()

        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        user.set_password(new_password)
        db.session.commit()

        return jsonify({"message": "Tu contraseña ha sido restablecida con éxito. Ya puedes iniciar sesión."}), 200

    except Exception as e:
        return jsonify({"error": "El enlace es inválido o ha expirado.", "detail": str(e)}), 400


# ============================================================================
# RUTAS ORIGINALES DEL PROYECTO (sin cambios)
# ============================================================================

@api.route('/openapi.yaml', methods=['GET'])
def get_openapi_spec():
    """Sirve la especificación OpenAPI del repo (docs/openapi.yaml).

    Se sirve el archivo tal cual, sin parsearlo: PyYAML no es una
    dependencia declarada del backend y no hace falta para entregar el
    documento. El test de contrato (tests/test_openapi.py) audita que
    cada ruta /api/* registrada esté en la especificación y viceversa.
    """
    docs_dir = os.path.join(os.path.dirname(__file__), "..", "..", "docs")
    return send_from_directory(
        docs_dir, "openapi.yaml", mimetype="application/yaml")


@api.route('/hello', methods=['POST', 'GET'])
def handle_hello():

    response_body = {
        "message": "Hello! I'm a message that came from the backend, check the network tab on the google inspector and you will see the GET request"
    }

    return jsonify(response_body), 200

# ---- USERS ----


@api.route('/users', methods=['GET'])
@jwt_required()
def get_users():
    uid = _current_user_id()
    current_user = db.session.get(User, uid) if uid is not None else None
    if not current_user or current_user.role != UserType.admin:
        return jsonify({"error": "No tienes permiso para acceder a este recurso"}), 403
    users = db.session.execute(db.select(User)).scalars().all()
    return jsonify([u.serialize() for u in users]), 200


@api.route('/users/<int:user_id>', methods=['GET'])
@jwt_required()
def get_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    # Solo el propio usuario o un admin: antes, cualquier cuenta con token
    # podía leer el correo y el rol de cualquier otro usuario por su id.
    uid = _current_user_id()
    current_user = db.session.get(User, uid) if uid is not None else None
    if not current_user or (
        current_user.id != user_id and current_user.role != UserType.admin
    ):
        return jsonify({"error": "No tienes permiso para acceder a este recurso"}), 403
    return jsonify(user.serialize()), 200

# ---- LEARNING PATHS ----


@api.route('/learning-paths', methods=['GET'])
def get_learning_paths():
    # selectinload: sin esto, len(p.modules) lanzaba una consulta por ruta
    # (patrón N+1). La respuesta es idéntica, solo cambia cómo se carga.
    paths = db.session.execute(
        db.select(LearningPath).options(selectinload(LearningPath.modules))
    ).scalars().all()
    return jsonify([{
        "id": p.id,
        "title": p.title,
        "image_url": p.image_url,
        "description": p.description,
        "time_required": p.time_required,
        "level": p.level,
        "number_of_modules": len(p.modules),
        "modules": [{"id": m.id, "title": m.title} for m in p.modules]} for p in paths]), 200


@api.route('/learning-paths/<int:path_id>', methods=['GET'])
def get_learning_path(path_id):
    path = db.session.execute(
        db.select(LearningPath)
        .options(selectinload(LearningPath.modules)
                 .selectinload(Module.lessons))
        .filter_by(id=path_id)
    ).scalar_one_or_none()
    if not path:
        return jsonify({"error": "Learning path not found"}), 404
    return jsonify({
        "id": path.id,
        "title": path.title,
        "image_url": path.image_url,
        "description": path.description,
        "time_required": path.time_required,
        "level": path.level,
        "number_of_modules": len(path.modules),
        "modules": [{"id": m.id, "title": m.title, "lessons": [{"id": l.id, "title": l.title, "is_sample": l.is_sample} for l in m.lessons]} for m in path.modules]}), 200


@api.route('/learning-paths', methods=['POST'])
@jwt_required()
def create_learning_path():
    _, error = _require_admin()
    if error:
        return error
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or not _texto(body, "title"):
        return jsonify({"error": "Debes proporcionar un título válido"}), 400
    if len(body["title"]) > 100:
        return jsonify({"error": "El título es demasiado largo (máximo 100 caracteres)"}), 400
    # Los campos opcionales deben ser cadenas o null: un dict o una lista
    # llegaba al INSERT y reventaba con ProgrammingError (500 HTML). Las
    # longitudes son las del modelo (String(300/50/50)): SQLite no las
    # impone, pero Postgres sí, y allí un valor largo reventaba igual
    # en el commit.
    for campo, maximo in (("image_url", 300), ("description", None),
                          ("time_required", 50), ("level", 50)):
        valor = body.get(campo)
        if valor is not None and not isinstance(valor, str):
            return jsonify({"error": f"{campo} debe ser una cadena de texto"}), 400
        if maximo is not None and isinstance(valor, str) and len(valor) > maximo:
            return jsonify({"error": f"{campo} es demasiado largo (máximo {maximo} caracteres)"}), 400
    path = LearningPath(title=body["title"], image_url=body.get("image_url"), description=body.get(
        "description"), time_required=body.get("time_required"), level=body.get("level"))
    db.session.add(path)
    db.session.commit()
    return jsonify({"id": path.id, "title": path.title, "image_url": path.image_url, "description": path.description, "time_required": path.time_required, "level": path.level}), 201

# ---- MODULES ----


@api.route('/modules', methods=['GET'])
def get_modules():
    # selectinload: sin esto, m.lessons lanzaba una consulta por módulo
    # (N+1 medido: 6 SQL para 5 módulos; con eager loading son 2).
    modules = db.session.execute(
        db.select(Module).options(selectinload(Module.lessons))
    ).scalars().all()
    return jsonify([{
        "id": m.id,
        "title": m.title,
        "level": m.level,
        "learning_path_id": m.learning_path_id,
        "lessons": [{"id": l.id, "title": l.title, "order_number": l.order_number, "is_sample": l.is_sample} for l in m.lessons]} for m in modules]), 200


@api.route('/modules/<int:module_id>', methods=['GET'])
def get_module(module_id):
    module = db.session.get(Module, module_id)
    if not module:
        return jsonify({"error": "Module not found"}), 404
    return jsonify({"id": module.id, "title": module.title, "level": module.level}), 200


@api.route('/modules', methods=['POST'])
@jwt_required()
def create_module():
    _, error = _require_admin()
    if error:
        return error
    body = request.get_json(silent=True)
    # level es NOT NULL en el modelo (Mapped[str] sin Optional) y no se
    # validaba: sin level (o null) el commit reventaba con IntegrityError
    # y Flask devolvía un 500 en HTML, contra el patrón 400 JSON del resto
    # de la API de creación. Se valida como el título, con _texto (cadena
    # no vacía), en la misma guarda y antes del 404 de la ruta padre.
    if not isinstance(body, dict) or not _texto(body, "title") \
            or not _texto(body, "level") \
            or not _es_id_valido(body.get("learning_path_id")):
        return jsonify({"error": "Debes proporcionar título, level y learning_path_id"}), 400
    if len(body["title"]) > 100 or len(body["level"]) > 50:
        return jsonify({"error": "El título o el level son demasiado largos (máximo 100 y 50 caracteres)"}), 400
    if not db.session.get(LearningPath, body["learning_path_id"]):
        return jsonify({"error": "Learning path not found"}), 404
    module = Module(title=body["title"], level=body.get(
        "level"), learning_path_id=body["learning_path_id"])
    db.session.add(module)
    db.session.commit()
    return jsonify({"id": module.id, "title": module.title, "lessons": []}), 201

# ---- LESSONS ----


@api.route('/lessons', methods=['GET'])
def get_lessons():
    lessons = db.session.execute(db.select(Lesson)).scalars().all()
    return jsonify([{"id": l.id, "title": l.title, "module_id": l.module_id, "order_number": l.order_number, "is_sample": l.is_sample} for l in lessons]), 200


@api.route('/lessons/sample', methods=['GET'])
def get_sample_lesson():
    """La lección de muestra (modo invitado, F-BE2): pública, sin sesión.

    La marca la pone la semilla (is_sample en Lesson); si ninguna
    lección la tiene (semilla sin correr tras la migración), 404 en JSON.
    Si algún día hay más de una muestra, se sirve la de menor id.
    """
    lesson = db.session.execute(
        db.select(Lesson).filter_by(is_sample=True)
        .order_by(Lesson.id)).scalars().first()
    if not lesson:
        return jsonify({"error": "No hay lección de muestra"}), 404
    return jsonify({
        "id": lesson.id,
        "title": lesson.title,
        "module_id": lesson.module_id,
        "path_id": lesson.module.learning_path_id,
        "path_title": lesson.module.learning_path.title,
        "module_title": lesson.module.title,
        "content": lesson.content,
        "order_number": lesson.order_number,
        "is_sample": True,
        "module_lessons": [{"id": l.id, "order": l.order_number} for l in lesson.module.lessons]}), 200


@api.route('/lessons/<int:lesson_id>', methods=['GET'])
def get_lesson(lesson_id):
    lesson = db.session.get(Lesson, lesson_id)
    if not lesson:
        return jsonify({"error": "Lesson not found"}), 404
    # Modo invitado (F-BE2): la lección de muestra es pública; el resto
    # exige sesión. El 404 va primero a propósito: la existencia de la
    # lección ya es pública (los títulos están en el catálogo), así que
    # no se filtra nada y el test de 404 sigue en verde para invitados.
    # _usuario_opcional_del_token (el mismo ayudante del tutor) devuelve
    # None sin token, con token caducado o con token inválido.
    if not lesson.is_sample and _usuario_opcional_del_token() is None:
        return jsonify({"error": "Inicia sesión para ver esta lección"}), 401
    return jsonify({
        "id": lesson.id,
        "title": lesson.title,
        "module_id": lesson.module_id,
        "path_id": lesson.module.learning_path_id,
        "content": lesson.content,
        "order_number": lesson.order_number,
        "is_sample": lesson.is_sample,
        "module_lessons": [{"id": l.id, "order": l.order_number} for l in lesson.module.lessons]}), 200


@api.route('/lessons', methods=['POST'])
@jwt_required()
def create_lesson():
    _, error = _require_admin()
    if error:
        return error
    body = request.get_json(silent=True)
    # content es NOT NULL y la guarda solo comprobaba que la CLAVE
    # existiera: con "content": null pasaba la validación y el commit
    # reventaba igual que en create_module (500 HTML). Se exige que el
    # valor no sea None, como module_id en la misma guarda.
    # Ronda 12: además debe ser una cadena: un dict o una lista pasaba
    # el «no es None» y reventaba en el INSERT con ProgrammingError
    # (500 HTML), y un entero se guardaba tal cual en la columna Text.
    if not isinstance(body, dict) or not _texto(body, "title") \
            or not isinstance(body.get("content"), str) \
            or not _es_id_valido(body.get("module_id")) \
            or not isinstance(body.get("order_number"), int) \
            or isinstance(body.get("order_number"), bool):
        return jsonify({"error": "Debes proporcionar título, contenido, module_id y order_number"}), 400
    if len(body["title"]) > 200:
        return jsonify({"error": "El título es demasiado largo (máximo 200 caracteres)"}), 400
    if not db.session.get(Module, body["module_id"]):
        return jsonify({"error": "Module not found"}), 404
    if "is_sample" in body and not isinstance(body["is_sample"], bool):
        return jsonify({"error": "is_sample debe ser verdadero o falso"}), 400
    lesson = Lesson(
        title=body["title"],
        content=body["content"],
        module_id=body["module_id"],
        order_number=body["order_number"],
        is_sample=body.get("is_sample", False)
    )
    db.session.add(lesson)
    db.session.commit()
    return jsonify({"id": lesson.id, "title": lesson.title}), 201

# ---- QUIZZES ----


@api.route('/quizzes/<int:lesson_id>', methods=['GET'])
def get_quiz(lesson_id):
    # .first() en vez de .scalar(): si alguna vez hubiera dos quizzes para
    # una lección, .scalar() lanzaba MultipleResultsFound (500).
    quiz = db.session.execute(
        db.select(Quiz).filter_by(lesson_id=lesson_id)).scalars().first()
    if not quiz:
        return jsonify({"error": "Quiz not found"}), 404
    # Modo invitado (F-BE2): ningún quiz es público, ni el de la lección
    # de muestra: el quiz es la razón para registrarse. El 404 va
    # primero, como en get_lesson, por la misma razón.
    if _usuario_opcional_del_token() is None:
        return jsonify({"error": "Inicia sesión para hacer este quiz"}), 401
    return jsonify({"id": quiz.id, "questions": quiz.questions_data}), 200


@api.route('/quizzes', methods=['POST'])
@jwt_required()
def create_quiz():
    _, error = _require_admin()
    if error:
        return error
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or not _es_id_valido(body.get("lesson_id")) \
            or "questions_data" not in body:
        return jsonify({"error": "Debes proporcionar lesson_id y questions_data"}), 400
    if not db.session.get(Lesson, body["lesson_id"]):
        return jsonify({"error": "Lesson not found"}), 404
    quiz = Quiz(lesson_id=body["lesson_id"],
                questions_data=body["questions_data"])
    db.session.add(quiz)
    db.session.commit()
    return jsonify({"id": quiz.id}), 201

# ---- USER PROGRESS ----


@api.route('/progress/<int:user_id>', methods=['GET'])
@jwt_required()
def get_user_progress(user_id):

    current_user_id = _current_user_id()
    if current_user_id != user_id:
        return jsonify({"error": "No tienes permiso para acceder a este recurso"}), 403

    progress = db.session.execute(
        db.select(UserProgress).filter_by(user_id=user_id)
        .options(selectinload(UserProgress.lesson)
                 .selectinload(Lesson.module))).scalars().all()

    if not progress:
        return jsonify([]), 200

    return jsonify([{"lesson_id": p.lesson_id, "lesson_title": p.lesson.title, "path_id": p.lesson.module.learning_path_id, "is_completed": p.is_completed, "quiz_score": p.quiz_score} for p in progress]), 200


@api.route('/progress/<int:user_id>/<int:lesson_id>', methods=['GET'])
@jwt_required()
def get_lesson_progress(user_id, lesson_id):
    current_user_id = _current_user_id()
    if current_user_id != user_id:
        return jsonify({"error": "No tienes permiso para acceder a este recurso"}), 403

    progress = db.session.execute(db.select(UserProgress).filter_by(
        user_id=user_id, lesson_id=lesson_id)).scalars().one_or_none()

    if not progress:
        return jsonify({"lesson_id": lesson_id, "is_completed": False, "quiz_score": None}), 200

    return jsonify({"lesson_id": progress.lesson_id,
                    "is_completed": progress.is_completed,
                    "quiz_score": progress.quiz_score}), 200


@api.route('/progress', methods=['POST'])
@jwt_required()
def create_initial_progress():
    current_user_id = _current_user_id()
    body = request.get_json(silent=True)

    if not isinstance(body, list):
        return jsonify({"error": "Se esperaba una lista de objetos JSON"}), 400

    if any(not isinstance(item, dict) or "user_id" not in item
           or "lesson_id" not in item for item in body):
        return jsonify({"error": "Cada elemento debe incluir user_id y lesson_id"}), 400

    if any(item.get("user_id") != current_user_id for item in body):
        return jsonify({"error": "No tienes permiso para crear progreso de otro usuario"}), 403

    if any(item.get("quiz_score") is not None
           and not _es_score_valido(item["quiz_score"]) for item in body):
        return jsonify({"error": "quiz_score debe ser un número entre 0 y 100"}), 400

    if any(item.get("is_completed") is not None
           and not isinstance(item.get("is_completed"), bool)
           for item in body):
        return jsonify({"error": "is_completed debe ser true o false"}), 400

    # Las lecciones deben existir: sin esta comprobación se creaba
    # progreso huérfano y GET /progress/<user> reventaba después al
    # leer p.lesson.title sobre None (500). Mismo criterio que
    # create_module/create_lesson/create_quiz con su padre (404).
    if any(not isinstance(item["lesson_id"], int)
           or isinstance(item["lesson_id"], bool) for item in body):
        return jsonify({"error": "lesson_id debe ser un entero"}), 400
    # Igual que lesson_id: un user_id True se colaba como el id 1
    # (True == 1) y uno no entero llegaba al INSERT.
    if any(not isinstance(item["user_id"], int)
           or isinstance(item["user_id"], bool) for item in body):
        return jsonify({"error": "user_id debe ser un entero"}), 400
    lesson_ids = {item["lesson_id"] for item in body}
    known_lessons = {l.id for l in db.session.execute(
        db.select(Lesson).where(Lesson.id.in_(lesson_ids))).scalars().all()}
    if lesson_ids - known_lessons:
        return jsonify({"error": "Lesson not found"}), 404

    # Sin duplicados: repetir esta inicialización creaba una fila nueva por
    # lección en cada llamada, y la XP de la gamificación sumaba doble.
    existing = {p.lesson_id for p in db.session.execute(
        db.select(UserProgress).filter_by(user_id=current_user_id)
    ).scalars().all()}

    initial_progress = []

    try:
        for item in body:
            if item["lesson_id"] in existing:
                continue
            existing.add(item["lesson_id"])
            progress = UserProgress(
                user_id=item["user_id"],
                lesson_id=item["lesson_id"],
                quiz_score=item.get("quiz_score", 0),
                is_completed=item.get("is_completed", False)
            )
            initial_progress.append(progress)

        db.session.add_all(initial_progress)
        db.session.commit()
        return jsonify({"message": "Progress created"}), 201

    except Exception as error:
        db.session.rollback()
        return jsonify({"error": str(error)}), 500


@api.route('/progress/<int:user_id>/<int:lesson_id>', methods=['PUT'])
@jwt_required()
def update_progress(user_id, lesson_id):
    current_user_id = _current_user_id()
    if current_user_id != user_id:
        return jsonify({"error": "No tienes permiso para modificar este recurso"}), 403

    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return jsonify({"error": "Cuerpo de la petición inválido"}), 400
    # Sin esta validación se aceptaban notas como 99999, y la XP de la
    # gamificación (que suma quiz_score tal cual) se inflaba sin límite.
    if body.get("quiz_score") is not None \
            and not _es_score_valido(body["quiz_score"]):
        return jsonify({"error": "quiz_score debe ser un número entre 0 y 100"}), 400
    # Un is_completed no booleano (p. ej. la cadena "false") llegaba a
    # SQLAlchemy y devolvía un 500 con el error SQL en la respuesta.
    if body.get("is_completed") is not None \
            and not isinstance(body.get("is_completed"), bool):
        return jsonify({"error": "is_completed debe ser true o false"}), 400
    progress = db.session.execute(db.select(UserProgress).filter_by(
        user_id=user_id, lesson_id=lesson_id)).scalars().one_or_none()
    # Crear progreso de una lección inexistente dejaba una fila
    # huérfana que rompía GET /progress/<user> (p.lesson es None).
    if not progress and not db.session.get(Lesson, lesson_id):
        return jsonify({"error": "Lesson not found"}), 404

    try:
        if not progress:
            progress = UserProgress(user_id=user_id, lesson_id=lesson_id)
            db.session.add(progress)

        # is_completed: null significa «sin cambio» (y el default
        # False del modelo si la fila se está creando), la misma
        # semántica que ya tiene POST /progress: allí null supera su
        # validación, al crear se guarda el default False y las filas
        # ya existentes se saltan sin tocarlas. Asignar None tal cual
        # solo reventaba en las filas EXISTENTES: la columna es
        # NOT NULL (Mapped[bool] en models.py), el UPDATE lanzaba un
        # IntegrityError y el except respondía 500 JSON con el SQL en
        # el cuerpo (observación de la ronda 10). Por eso solo se
        # asigna cuando viene un booleano de verdad; la guarda de
        # arriba ya rechazó con 400 cualquier otro valor no nulo.
        if body.get("is_completed") is not None:
            progress.is_completed = body["is_completed"]
        progress.quiz_score = body.get("quiz_score", progress.quiz_score)
        # La fecha de finalización alimenta las rachas de la gamificación.
        # Solo se sella la primera vez que la lección queda completada.
        if progress.is_completed and progress.completed_at is None:
            progress.completed_at = datetime.now(timezone.utc)
        db.session.commit()
        return jsonify({"message": "Progress updated"})

    except Exception as error:
        db.session.rollback()
        return jsonify({"error": str(error)}), 500


@api.route('/dashboard', methods=['GET'])
@jwt_required()
def handle_dashboard():
    user_id = _current_user_id()
    if user_id is None:
        return jsonify({"error": "No tienes permiso para acceder a este recurso"}), 403
    user = db.get_or_404(User, user_id)
    return jsonify({"message": "Bienvenido", "user": user.serialize()}), 200


# ============================================================================
# GAMIFICACIÓN (XP, niveles, rachas) y CERTIFICADOS VERIFICABLES — Fase 2
# El XP y las rachas se DERIVAN del progreso ya guardado (sin tablas nuevas):
#   XP = 100 por lección completada + la nota de cada quiz registrado.
#   Racha = días consecutivos con al menos una lección completada
#   (usa UserProgress.completed_at; las filas antiguas sin fecha no cuentan).
# Los certificados sí se persisten (tabla certificates) para poder
# verificarlos públicamente por su código.
# ============================================================================

LEVELS = [
    (0, "Explorador"),
    (300, "Aprendiz de bloques"),
    (700, "Constructor"),
    (1200, "Validador"),
    (2000, "Nodo completo"),
    (3200, "Arquitecto Web3"),
]


def _calcular_xp(progress_rows):
    xp = 0
    for p in progress_rows:
        if p.is_completed:
            xp += 100
        if p.quiz_score is not None:
            xp += p.quiz_score
    return xp


def _nivel_desde_xp(xp):
    actual = LEVELS[0]
    siguiente = None
    for i, nivel in enumerate(LEVELS):
        if xp >= nivel[0]:
            actual = nivel
            siguiente = LEVELS[i + 1] if i + 1 < len(LEVELS) else None
    return actual, siguiente


def _calcular_rachas(fechas):
    """Devuelve (racha actual, mejor racha, días activos) desde completed_at."""
    dias = sorted({f.date() for f in fechas if f is not None})
    if not dias:
        return 0, 0, 0
    mejor = 1
    racha = 1
    for i in range(1, len(dias)):
        racha = racha + 1 if (dias[i] - dias[i - 1]).days == 1 else 1
        mejor = max(mejor, racha)
    hoy = datetime.now(timezone.utc).date()
    actual = 0
    if dias[-1] in (hoy, hoy - timedelta(days=1)):
        actual = 1
        j = len(dias) - 1
        while j > 0 and (dias[j] - dias[j - 1]).days == 1:
            actual += 1
            j -= 1
    return actual, mejor, len(dias)


@api.route('/gamification/me', methods=['GET'])
@jwt_required()
def gamification_me():
    user_id = _current_user_id()
    if user_id is None:
        return jsonify({"error": "No tienes permiso para acceder a este recurso"}), 403
    rows = db.session.execute(
        db.select(UserProgress).filter_by(user_id=user_id)).scalars().all()

    xp = _calcular_xp(rows)
    (minimo, nombre), siguiente = _nivel_desde_xp(xp)
    actual, mejor, dias_activos = _calcular_rachas(
        [p.completed_at for p in rows])

    if siguiente:
        progreso_nivel = round((xp - minimo) / (siguiente[0] - minimo), 2)
        faltan = siguiente[0] - xp
    else:
        progreso_nivel = 1.0
        faltan = 0

    return jsonify({
        "xp": xp,
        "level_name": nombre,
        "level_min_xp": minimo,
        "next_level_name": siguiente[1] if siguiente else None,
        "next_level_xp": siguiente[0] if siguiente else None,
        "xp_to_next": faltan,
        "progress_to_next": progreso_nivel,
        "streak_current": actual,
        "streak_best": mejor,
        "active_days": dias_activos,
        "lessons_completed": sum(1 for p in rows if p.is_completed),
        "quizzes_passed": sum(
            1 for p in rows if p.quiz_score is not None and p.quiz_score >= 70),
    }), 200


def _resumen_ruta(user_id, path):
    """(total lecciones, completadas, títulos con quiz sin aprobar ≥70)."""
    lessons = [lesson for module in path.modules for lesson in module.lessons]
    ids = [lesson.id for lesson in lessons]
    rows = {}
    if ids:
        rows = {p.lesson_id: p for p in db.session.execute(
            db.select(UserProgress).filter_by(user_id=user_id)
            .where(UserProgress.lesson_id.in_(ids))).scalars().all()}
    completadas = sum(
        1 for lid in ids if rows.get(lid) and rows[lid].is_completed)
    pendientes_quiz = []
    for lesson in lessons:
        if lesson.quiz is not None:
            row = rows.get(lesson.id)
            if not row or row.quiz_score is None or row.quiz_score < 70:
                pendientes_quiz.append(lesson.title)
    return len(lessons), completadas, pendientes_quiz


@api.route('/certificates/claim', methods=['POST'])
@jwt_required()
def claim_certificate():
    uid = _current_user_id()
    user = db.session.get(User, uid) if uid is not None else None
    if not user:
        return jsonify({"error": "Usuario no encontrado"}), 404
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        body = {}
    path_id = body.get("path_id")
    # Un path_id no entero (dict, cadena, bool) reventaba en
    # db.session.get() con InvalidRequestError (500 HTML), o se colaba
    # como otro id (True == 1). Ausente sigue siendo 404, como antes.
    if path_id is not None and not _es_id_valido(path_id):
        return jsonify({"error": "path_id debe ser un entero"}), 400
    path = db.session.get(LearningPath, path_id) if path_id is not None else None
    if not path:
        return jsonify({"error": "Ruta no encontrada"}), 404

    total, completadas, pendientes_quiz = _resumen_ruta(user.id, path)
    if total == 0 or completadas < total:
        return jsonify({
            "error": "Aún no completas todas las lecciones de esta ruta",
            "lessons_total": total,
            "lessons_completed": completadas,
        }), 400
    if pendientes_quiz:
        return jsonify({
            "error": "Te falta aprobar estos quizzes con 70% o más",
            "quizzes_pending": pendientes_quiz,
        }), 400

    existing = db.session.execute(
        db.select(Certificate).filter_by(
            user_id=user.id, learning_path_id=path.id)).scalars().one_or_none()
    if existing:
        return jsonify(existing.serialize()), 200

    issued = datetime.now(timezone.utc)
    digest = hashlib.sha256(
        f"{user.id}:{path.id}:{user.email}:{issued.isoformat()}".encode()
    ).hexdigest()[:15].upper()
    cert = Certificate(
        user_id=user.id,
        learning_path_id=path.id,
        code=f"BK-{digest[0:5]}-{digest[5:10]}-{digest[10:15]}",
        issued_at=issued,
    )
    db.session.add(cert)
    try:
        db.session.commit()
    except IntegrityError:
        # Carrera con otra reclamación simultánea de la misma ruta: la
        # restricción única uq_certificate_user_path rechazó el segundo
        # certificado. Se devuelve el existente (200) en vez de un 500.
        db.session.rollback()
        existing = db.session.execute(
            db.select(Certificate).filter_by(
                user_id=user.id, learning_path_id=path.id)
        ).scalars().one_or_none()
        if existing:
            return jsonify(existing.serialize()), 200
        raise
    return jsonify(cert.serialize()), 201


@api.route('/certificates/mine', methods=['GET'])
@jwt_required()
def my_certificates():
    user_id = _current_user_id()
    if user_id is None:
        return jsonify({"error": "No tienes permiso para acceder a este recurso"}), 403
    # selectinload: serialize() lee c.user y c.learning_path; sin eager
    # loading, cada certificado lanzaba su propia consulta de ruta (N+1
    # medido: 4 SQL con 2 certificados; con eager loading son 3 fijos).
    certs = db.session.execute(
        db.select(Certificate).filter_by(user_id=user_id)
        .options(selectinload(Certificate.user),
                 selectinload(Certificate.learning_path))
        .order_by(Certificate.issued_at.desc())).scalars().all()
    return jsonify([c.serialize() for c in certs]), 200


@api.route('/certificates/verify/<string:code>', methods=['GET'])
def verify_certificate(code):
    cert = db.session.execute(
        db.select(Certificate).filter_by(
            code=code.strip().upper())).scalars().one_or_none()
    if not cert:
        return jsonify({"valid": False}), 404
    return jsonify({
        "valid": True,
        "code": cert.code,
        "holder": cert.user.username or cert.user.email,
        "path": cert.learning_path.title,
        "issued_at": cert.issued_at.isoformat() if cert.issued_at else None,
    }), 200


# ============================================================================
# PERFIL PÚBLICO VERIFICABLE — /u/<handle>
# ============================================================================
# Opt-in por estudiante: solo lo que el usuario elige hacer público se
# ve desde fuera, y solo lo que la plataforma puede verificar (rutas
# completadas con su certificado, comprobable en /verificar/<código>).
# Nada de correo, ids internos, notas de quiz ni rachas: el perfil es
# una credencial, no un informe de actividad.

_HANDLE_RE = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{1,28}[a-z0-9])?$")
_HANDLE_RESERVADOS = {
    "me", "admin", "api", "tutor", "login", "register", "dashboard",
    "courses", "certificado", "verificar", "laboratorio", "lesson",
    "course", "quizzes", "u", "root", "blockethos", "support",
    "ayuda", "perfil", "profile", "settings", "ajustes",
}


def _handle_valido(handle):
    """Handle de perfil: 3-30 caracteres, minúsculas, dígitos y . _ -
    dentro (nunca al principio ni al final); nada de reservados."""
    if not isinstance(handle, str):
        return False
    handle = handle.strip().lower()
    if len(handle) < 3 or len(handle) > 30:
        return False
    if handle in _HANDLE_RESERVADOS:
        return False
    return bool(_HANDLE_RE.match(handle))


def _perfil_publico_serialize(user):
    """Lo único que sale por la API pública de un perfil: nombre para
    mostrar, nivel y XP, rutas con su avance y sus certificados.
    Sin correo, sin id interno, sin notas de quiz, sin rachas."""
    paths = db.session.execute(
        db.select(LearningPath)
        .options(selectinload(LearningPath.modules)
                 .selectinload(Module.lessons))
        .order_by(LearningPath.id)).scalars().all()
    certs = {c.learning_path_id: c for c in db.session.execute(
        db.select(Certificate).filter_by(user_id=user.id)).scalars().all()}
    rows = db.session.execute(
        db.select(UserProgress).filter_by(user_id=user.id)).scalars().all()
    xp = _calcular_xp(rows)
    (_minimo, nombre_nivel), _siguiente = _nivel_desde_xp(xp)
    rutas = []
    for path in paths:
        total, completadas, _pend = _resumen_ruta(user.id, path)
        if total == 0:
            continue
        cert = certs.get(path.id)
        rutas.append({
            "path_id": path.id,
            "title": path.title,
            "lessons_total": total,
            "lessons_completed": completadas,
            "percent": round(completadas / total * 100) if total else 0,
            "certificate": (
                {"code": cert.code,
                 "issued_at": cert.issued_at.isoformat()
                 if cert.issued_at else None}
                if cert else None),
        })
    return {
        "handle": user.public_handle,
        "display_name": user.username or user.public_handle,
        "level_name": nombre_nivel,
        "xp": xp,
        "member_since": user.created_at.strftime("%Y-%m")
        if user.created_at else None,
        "paths": rutas,
        "certificates_count": len(certs),
    }


@api.route('/profile/me', methods=['GET'])
@jwt_required()
def get_my_profile():
    uid = _current_user_id()
    user = db.session.get(User, uid) if uid is not None else None
    if not user:
        return jsonify({"error": "Usuario no encontrado"}), 404
    return jsonify({
        "handle": user.public_handle,
        "is_public": bool(user.is_profile_public),
        "username": user.username,
    }), 200


@api.route('/profile/me', methods=['PUT'])
@jwt_required()
def update_my_profile():
    uid = _current_user_id()
    user = db.session.get(User, uid) if uid is not None else None
    if not user:
        return jsonify({"error": "Usuario no encontrado"}), 404
    # El perfil público es una credencial de estudiante: el admin no
    # tiene progreso que mostrar (y la demo ADMIN nunca está activa).
    if user.role != UserType.student:
        return jsonify({
            "error": "El perfil público es solo para estudiantes"}), 403
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "Cuerpo de la petición inválido"}), 400
    if "handle" in body and body["handle"] is not None:
        handle = body["handle"].strip().lower() \
            if isinstance(body["handle"], str) else ""
        if not _handle_valido(handle):
            return jsonify({"error": (
                "El handle debe tener 3-30 caracteres, solo minúsculas, "
                "dígitos y puntos, guiones o guiones bajos, y no puede ser "
                "una palabra reservada")}), 400
        otro = db.session.execute(
            db.select(User).filter_by(public_handle=handle)
            .where(User.id != user.id)).scalars().one_or_none()
        if otro:
            return jsonify({"error": "Ese handle ya está en uso"}), 409
        user.public_handle = handle
    if "is_public" in body:
        if not isinstance(body["is_public"], bool):
            return jsonify({"error": "is_public debe ser true o false"}), 400
        if body["is_public"] and not user.public_handle:
            return jsonify({"error": (
                "Elige primero un handle para tu perfil público")}), 400
        user.is_profile_public = body["is_public"]
    db.session.commit()
    return jsonify({
        "handle": user.public_handle,
        "is_public": bool(user.is_profile_public),
        "username": user.username,
    }), 200


@api.route('/profile/<string:handle>', methods=['GET'])
@rate_limit(max_attempts=30)
def get_public_profile(handle):
    # El mismo 404 para «no existe», «no es público» y «no es
    # estudiante»: la respuesta no debe decir cuál de las tres es,
    # para no convertir el endpoint en un oráculo de usuarios.
    # El rate limit es por IP de cliente: exige P-02 (ProxyFix)
    # aplicado; sin él, detrás del proxy todos comparten un cubo.
    user = db.session.execute(
        db.select(User).filter_by(
            public_handle=handle.strip().lower())
    ).scalars().one_or_none()
    if not user or not user.is_profile_public \
            or user.role != UserType.student:
        return jsonify({"error": "Perfil no encontrado"}), 404
    return jsonify(_perfil_publico_serialize(user)), 200


# ============================================================================
# TUTOR DE BLOCK ETHOS — responde SOLO desde el contenido de las lecciones
# ============================================================================
# Sin servicios externos, sin claves y sin modelos de lenguaje: la
# búsqueda es TF-IDF (solo librería estándar) sobre los fragmentos del
# contenido Markdown de las lecciones guardadas en la base de datos.
# La respuesta es EXTRACTIVA: se compone con los fragmentos más
# relevantes, citando siempre la lección de origen. Si ningún fragmento
# supera el umbral, el tutor lo dice honestamente y sugiere la lección
# más cercana en vez de inventar una respuesta.

_TUTOR_STOPWORDS = {
    "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del",
    "en", "y", "o", "a", "con", "por", "para", "que", "es", "se", "su",
    "al", "lo", "como", "mas", "más", "pero", "sus", "le", "ya", "este",
    "esta", "esto", "si", "sí", "no", "qué", "cuál", "cuáles", "cómo",
    "cuándo", "dónde", "quién", "porque", "cuando", "puede", "puedo",
    "quiero", "hace", "hacer", "tiene", "tienen", "son", "sobre",
    "entre", "muy", "sin", "también", "me", "te", "mi", "tu", "nos",
    "hay", "ser", "estar", "está", "están", "eso", "esa", "ese",
    # Verbos típicos de la pregunta, sin contenido temático propio:
    "sirve", "sirven", "funciona", "funcionan", "significa",
    "quiero", "saber", "explicame", "cuentame", "dime",
}

# Umbral mínimo de similitud coseno (TF-IDF) para afirmar que las
# lecciones cubren la pregunta. Ajustado con preguntas reales de prueba.
_TUTOR_UMBRAL = 0.08


def _tutor_tokens(texto):
    """Normaliza (minúsculas, sin acentos) y tokeniza para el TF-IDF."""
    texto = unicodedata.normalize("NFD", (texto or "").lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return [
        t for t in re.findall(r"[a-z0-9]+", texto)
        if len(t) > 2 and t not in _TUTOR_STOPWORDS
    ]


def _tutor_limpiar(fragmento):
    """Quita la sintaxis Markdown de un fragmento para mostrarlo en texto."""
    texto = re.sub(r"```[a-z]*", " ", fragmento)
    texto = re.sub(r"[#>*`]", " ", texto)
    texto = re.sub(r"^\s*[-•]\s+", "", texto, flags=re.MULTILINE)
    texto = re.sub(r"^\s*\d+\.\s+", "", texto, flags=re.MULTILINE)
    texto = re.sub(r"\s+", " ", texto).strip()
    return re.sub(r"\s+([:;,.])", r"\1", texto)


def _tutor_fragmentos(contenido):
    """Divide el contenido de una lección en fragmentos comparables.

    Corta por líneas en blanco y fusiona los trozos muy cortos (títulos
    sueltos) con el fragmento siguiente, para que cada fragmento tenga
    suficiente texto para puntuar y para citar.
    """
    bloques = [b.strip() for b in re.split(r"\n\s*\n", contenido or "")]
    fragmentos = []
    pendiente = ""
    for bloque in bloques:
        limpio = _tutor_limpiar(bloque)
        if not limpio:
            continue
        if pendiente:
            limpio = pendiente + " " + limpio
            pendiente = ""
        if len(limpio) < 60:
            pendiente = limpio
            continue
        fragmentos.append(limpio)
    if pendiente:
        if fragmentos:
            fragmentos[-1] = fragmentos[-1] + " " + pendiente
        else:
            fragmentos.append(pendiente)
    return fragmentos


def _tutor_clave_indice():
    """Huella del contenido del que depende el índice TF-IDF.

    Incluye, por lección y en orden de id: su id, su módulo, su título
    y su contenido íntegro, más el título del módulo y el id y título
    de la ruta (todo ello alimenta los fragmentos, los tokens de
    contexto y las fuentes que devuelve el tutor). No hay columna de
    «última modificación» en el modelo, así que la huella se calcula
    con un hash SHA-256 sobre una sola consulta de columnas (sin
    cargar objetos ORM): cualquier alta, baja o edición de ese
    contenido cambia la huella y obliga a reconstruir; si no cambia,
    el índice se reutiliza tal cual.
    """
    filas = db.session.execute(
        db.select(Lesson.id, Lesson.module_id, Lesson.title,
                  Lesson.content, Module.id, Module.title,
                  LearningPath.id, LearningPath.title)
        .join(Module, Module.id == Lesson.module_id)
        .join(LearningPath, LearningPath.id == Module.learning_path_id)
        .order_by(Lesson.id)).all()
    huella = hashlib.sha256()
    for fila in filas:
        huella.update(repr(tuple(fila)).encode("utf-8"))
        huella.update(b"\n")
    return huella.hexdigest()


# Índice TF-IDF cacheado: construirlo cuesta ~8-15 ms y 3 consultas
# (medido con la semilla: 71 fragmentos, 863 términos), y antes se
# rehacía en CADA petición al tutor. La huella de arriba es la única
# invalidación: se recalcula en cada petición (1 consulta ligera) y
# el índice solo se reconstruye cuando el contenido cambia.
_TUTOR_CACHE = {"clave": None, "docs": None, "idf": None}


def _tutor_indice():
    """Índice TF-IDF reutilizable: se reconstruye solo si cambia el contenido."""
    clave = _tutor_clave_indice()
    if _TUTOR_CACHE["clave"] == clave and _TUTOR_CACHE["docs"] is not None:
        # Copias superficiales: tutor_pregunta anota «score» y ordena
        # los documentos; así no muta lo cacheado (los vectores y los
        # textos compartidos solo se leen, nunca se escriben).
        return [dict(d) for d in _TUTOR_CACHE["docs"]], _TUTOR_CACHE["idf"]
    docs, idf = _tutor_construir_indice()
    _TUTOR_CACHE.update(clave=clave, docs=docs, idf=idf)
    return [dict(d) for d in docs], idf


def _tutor_construir_indice():
    """Construye el índice TF-IDF de fragmentos de todas las lecciones."""
    # selectinload: sin esto, lesson.module y module.learning_path se
    # cargaban en perezoso, una consulta por módulo/ruta (8 SQL en
    # total por construcción; con eager loading son 3).
    lessons = db.session.execute(
        db.select(Lesson)
        .options(selectinload(Lesson.module)
                 .selectinload(Module.learning_path))
        .order_by(Lesson.id)).scalars().all()
    docs = []
    for lesson in lessons:
        contexto = (
            f"{lesson.module.learning_path.title} "
            f"{lesson.module.title} {lesson.title}"
        )
        tokens_ctx = _tutor_tokens(contexto)
        for fragmento in _tutor_fragmentos(lesson.content):
            docs.append({
                "lesson": lesson,
                "texto": fragmento,
                # Los tokens del título cuentan doble: si la pregunta
                # nombra el tema de la lección, sus fragmentos pesan más.
                "tokens": _tutor_tokens(fragmento) + tokens_ctx,
            })
    df = Counter()
    for doc in docs:
        df.update(set(doc["tokens"]))
    n = max(len(docs), 1)
    idf = {t: math.log((1 + n) / (1 + c)) + 1.0 for t, c in df.items()}
    for doc in docs:
        tf = Counter(doc["tokens"])
        # TF sublineal (1 + log tf): repetir una palabra en un fragmento
        # suma, pero con rendimiento decreciente; así un fragmento que
        # repite un término genérico no tapa al que trata el tema.
        doc["vector"] = {
            t: (1.0 + math.log(c)) * idf[t] for t, c in tf.items()}
        doc["norma"] = math.sqrt(sum(v * v for v in doc["vector"].values()))
    return docs, idf


def _tutor_coseno(tokens_pregunta, idf, doc):
    if not tokens_pregunta or not doc["norma"]:
        return 0.0
    tf = Counter(tokens_pregunta)
    qvec = {t: (1.0 + math.log(c)) * idf.get(t, 0.0)
            for t, c in tf.items()}
    qnorm = math.sqrt(sum(v * v for v in qvec.values()))
    if not qnorm:
        return 0.0
    punto = sum(v * doc["vector"].get(t, 0.0) for t, v in qvec.items())
    return punto / (qnorm * doc["norma"])


def _tutor_fuente(doc):
    lesson = doc["lesson"]
    return {
        "lesson_id": lesson.id,
        "lesson_title": lesson.title,
        "module_title": lesson.module.title,
        "path_id": lesson.module.learning_path_id,
        "path_title": lesson.module.learning_path.title,
        "excerpt": doc["texto"][:400],
        "score": round(doc["score"], 3),
    }


# Preguntas sobre el propio progreso («¿qué me falta?», «¿qué sigue?»):
# no se responden desde los fragmentos de las lecciones sino desde el
# progreso guardado del estudiante. La detección es por expresiones
# normalizadas (sin acentos, en minúsculas); una pregunta temática
# normal («¿qué es la mempool?») no casa con ninguna.
_TUTOR_INTENCION_PROGRESO = (
    "que me falta",
    "cuanto me falta",
    "que me queda",
    "que sigue",
    "que sigo",
    "mi progreso",
    "mi avance",
    "donde voy",
    "donde estoy",
    "que estudiar",
    "por donde sigo",
    "por donde continuar",
    "terminar mi ruta",
    "terminar la ruta",
    "completar mi ruta",
)


def _tutor_es_pregunta_progreso(pregunta):
    normalizada = unicodedata.normalize(
        "NFD", (pregunta or "").lower())
    normalizada = "".join(
        c for c in normalizada if unicodedata.category(c) != "Mn")
    normalizada = re.sub(r"\s+", " ", normalizada).strip()
    return any(expresion in normalizada
               for expresion in _TUTOR_INTENCION_PROGRESO)


def _tutor_siguiente_paso(user_id):
    """Siguiente paso del estudiante, derivado de su progreso guardado.

    Recorre las rutas en orden de id (módulos por id, lecciones por
    order_number) y devuelve la primera lección sin completar, más
    los quizzes pendientes (lecciones con quiz sin aprobar con 70).
    Si no queda nada pendiente, all_done es True. No crea filas de
    progreso: una lección sin fila cuenta como no empezada.
    """
    paths = db.session.execute(
        db.select(LearningPath)
        .options(selectinload(LearningPath.modules)
                 .selectinload(Module.lessons)
                 .selectinload(Lesson.quiz))
        .order_by(LearningPath.id)).scalars().all()
    rows = {p.lesson_id: p for p in db.session.execute(
        db.select(UserProgress).filter_by(user_id=user_id)).scalars().all()}
    quizzes_pendientes = []
    total = 0
    completadas = 0
    siguiente = None
    for path in paths:
        for modulo in sorted(path.modules, key=lambda m: m.id):
            for leccion in sorted(modulo.lessons,
                                  key=lambda l: l.order_number):
                total += 1
                fila = rows.get(leccion.id)
                if fila and fila.is_completed:
                    completadas += 1
                    if leccion.quiz is not None and (
                            fila.quiz_score is None
                            or fila.quiz_score < 70):
                        quizzes_pendientes.append({
                            "lesson_id": leccion.id,
                            "lesson_title": leccion.title,
                            "path_id": path.id,
                            "path_title": path.title,
                        })
                elif siguiente is None:
                    siguiente = {
                        "path_id": path.id,
                        "path_title": path.title,
                        "module_title": modulo.title,
                        "lesson_id": leccion.id,
                        "lesson_title": leccion.title,
                    }
    return {
        "all_done": siguiente is None,
        "next_lesson": siguiente,
        "lessons_total": total,
        "lessons_completed": completadas,
        "quizzes_pending": quizzes_pendientes,
    }


def _tutor_respuesta_progreso(paso):
    """Texto de la respuesta a «¿qué me falta?», solo con datos propios
    del estudiante. Plantilla determinista, sin fragmentos ni inventos."""
    if paso["all_done"]:
        texto = (
            "Ya completaste todas las lecciones de tus rutas "
            f"({paso['lessons_completed']} de {paso['lessons_total']})."
        )
        if paso["quizzes_pending"]:
            titulos = ", ".join(
                f"«{q['lesson_title']}»" for q in paso["quizzes_pending"])
            texto += (
                " Te falta aprobar con 70% o más el quiz de "
                f"{titulos} para poder reclamar el certificado."
            )
        else:
            texto += (" Si aún no lo hiciste, puedes reclamar tu "
                      "certificado desde el panel.")
        return texto
    siguiente = paso["next_lesson"]
    texto = (
        f"Llevas {paso['lessons_completed']} de {paso['lessons_total']} "
        f"lecciones. Tu siguiente paso es «{siguiente['lesson_title']}» "
        f"({siguiente['path_title']} · {siguiente['module_title']})."
    )
    if paso["quizzes_pending"]:
        titulos = ", ".join(
            f"«{q['lesson_title']}»" for q in paso["quizzes_pending"])
        texto += f" Además tienes pendiente aprobar el quiz de {titulos}."
    return texto


@api.route('/tutor', methods=['POST'])
def tutor_pregunta():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        body = {}
    # _texto devuelve '' si question falta o no es cadena (antes, un
    # question numérico o un cuerpo-lista reventaban con 500 HTML).
    pregunta = _texto(body, "question")
    if not pregunta:
        return jsonify({"error": "Escribe una pregunta para el tutor"}), 400
    if len(pregunta) > 500:
        return jsonify({"error": "La pregunta es demasiado larga"}), 400

    # Progreso opcional: con sesión de estudiante, el tutor conoce
    # dónde va y guía el siguiente paso; sin sesión (o con un token
    # caducado), responde igual que siempre, sin personalizar. El
    # admin cae en la vía anónima: no tiene progreso que guiar.
    usuario = _usuario_opcional_del_token()
    paso = None
    if usuario is not None and usuario.role == UserType.student:
        paso = _tutor_siguiente_paso(usuario.id)

    es_progreso = _tutor_es_pregunta_progreso(pregunta)
    if es_progreso and usuario is None:
        return jsonify({
            "found": False,
            "answer": (
                "Para decirte qué te falta necesito ver tu progreso: "
                "inicia sesión y pregúntame de nuevo."
            ),
            "sources": [],
            "next_step": None,
            "progress_answer": False,
        }), 200
    if es_progreso and paso is not None:
        respuesta = _tutor_respuesta_progreso(paso)
        fuentes = []
        if paso["next_lesson"]:
            siguiente = paso["next_lesson"]
            fuentes.append({
                "lesson_id": siguiente["lesson_id"],
                "lesson_title": siguiente["lesson_title"],
                "module_title": siguiente["module_title"],
                "path_id": siguiente["path_id"],
                "path_title": siguiente["path_title"],
                "excerpt": "",
                "score": None,
            })
        return jsonify({
            "found": True,
            "answer": respuesta,
            "sources": fuentes,
            "next_step": paso,
            "progress_answer": True,
        }), 200

    tokens = _tutor_tokens(pregunta)
    docs, idf = _tutor_indice()
    if not docs:
        return jsonify({
            "found": False,
            "answer": "Todavía no hay lecciones cargadas en la plataforma.",
            "sources": [],
            "next_step": paso,
            "progress_answer": False,
        }), 200

    for doc in docs:
        doc["score"] = _tutor_coseno(tokens, idf, doc)
    docs.sort(key=lambda d: d["score"], reverse=True)
    mejor = docs[0]

    if mejor["score"] < _TUTOR_UMBRAL:
        # Honestidad ante todo: no está en las lecciones. Se sugiere la
        # lección con mejor puntuación como punto de partida.
        sugerencia = _tutor_fuente(mejor)
        return jsonify({
            "found": False,
            "answer": (
                "Eso no aparece en las lecciones de Block Ethos, así que no "
                "quiero inventarte una respuesta. La lección más cercana "
                f"a tu pregunta es «{sugerencia['lesson_title']}» "
                f"({sugerencia['path_title']} · {sugerencia['module_title']}); "
                "puede ser un buen punto de partida."
            ),
            "sources": [sugerencia],
            "next_step": paso,
            "progress_answer": False,
        }), 200

    # Hasta 3 fragmentos, de lecciones distintas si es posible, que
    # superen el 60% de la mejor puntuación.
    corte = max(_TUTOR_UMBRAL, mejor["score"] * 0.6)
    elegidos = []
    lecciones_vistas = set()
    for doc in docs:
        if doc["score"] < corte or len(elegidos) >= 3:
            break
        if doc["lesson"].id in lecciones_vistas and len(docs) > 3:
            continue
        elegidos.append(doc)
        lecciones_vistas.add(doc["lesson"].id)

    respuesta = " ".join(d["texto"] for d in elegidos)
    return jsonify({
        "found": True,
        "answer": respuesta,
        "sources": [_tutor_fuente(d) for d in elegidos],
        "next_step": paso,
        "progress_answer": False,
    }), 200