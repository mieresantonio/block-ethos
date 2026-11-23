"""
This module takes care of starting the API Server, Loading the DB and Adding the endpoints
"""
import os
from flask import Flask, jsonify, send_from_directory, request, abort
from flask_cors import CORS
from flask_migrate import Migrate
from werkzeug.exceptions import InternalServerError
from werkzeug.middleware.proxy_fix import ProxyFix
from api.utils import APIException, generate_sitemap
from api.models import db
from api.routes import api
from api.admin import setup_admin
from api.commands import setup_commands
from flask_jwt_extended import JWTManager
from api.mail import mail

# from models import Person

ENV = "development" if os.getenv("FLASK_DEBUG") == "1" else "production"
static_file_dir = os.path.join(os.path.dirname(
    os.path.realpath(__file__)), '../dist/')

app = Flask(__name__)
# H-001: PythonAnywhere pone un proxy delante de la app. Sin ProxyFix,
# request.remote_addr es la IP del proxy y el rate limiting de auth
# (10 logins/min) se comparte entre TODOS los usuarios: diez logins
# de cualquiera bloquean el login de todo el mundo. Con un solo proxy
# de confianza (x_for=1), remote_addr pasa a ser la IP del cliente
# que el proxy añade al final de X-Forwarded-For; lo que un cliente
# escriba antes en esa cabecera se ignora. Sin cabecera (desarrollo
# local, tests), remote_addr queda tal cual.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)
app.config["JWT_SECRET_KEY"] = os.getenv(
    "FLASK_APP_KEY", "super-secret-fallback")
# Rate limiting de auth (ver api/rate_limit.py): ventana en segundos y
# conmutador de apagado, ambos por entorno. Los tests activan
# RATE_LIMIT_DISABLED=1 en conftest.py y lo encienden solo en los
# tests que lo prueban, tocando app.config en caliente.
app.config["RATE_LIMIT_WINDOW_SECONDS"] = 60
try:
    app.config["RATE_LIMIT_WINDOW_SECONDS"] = max(
        1, int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60")))
except ValueError:
    pass  # Valor no numérico: se queda el defecto de 60 s.
app.config["RATE_LIMIT_DISABLED"] = os.getenv(
    "RATE_LIMIT_DISABLED", "").lower() in ("1", "true", "yes")
jwt = JWTManager(app)
CORS(app)
app.url_map.strict_slashes = False

# ---- Flask-Mail config (debe ir después de crear `app`) ----
app.config["MAIL_SERVER"] = os.getenv("MAIL_SERVER", "smtp.gmail.com")
app.config["MAIL_PORT"] = int(os.getenv("MAIL_PORT", 587))
app.config["MAIL_USE_TLS"] = os.getenv("MAIL_USE_TLS", "True") == "True"
app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")
app.config["MAIL_DEFAULT_SENDER"] = os.getenv("MAIL_DEFAULT_SENDER")
mail.init_app(app)

# database condiguration
db_url = os.getenv("DATABASE_URL")
if db_url is not None:
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url.replace(
        "postgres://", "postgresql://")
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = "sqlite:////tmp/test.db"

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
MIGRATE = Migrate(app, db, compare_type=True)
db.init_app(app)

# add the admin
setup_admin(app)

# add the CLI commands (flask insert-test-data, etc.)
setup_commands(app)

# Add all endpoints form the API with a "api" prefix
# (aquí viven /api/signup, /api/login, /api/verify-email, etc. - ver routes.py)
app.register_blueprint(api, url_prefix='/api')

# Handle/serialize errors like a JSON object


@app.errorhandler(APIException)
def handle_invalid_usage(error):
    return jsonify(error.to_dict()), error.status_code


# Los errores HTTP de la API responden JSON, nunca el HTML por defecto
# de Flask: sin estos manejadores, una ruta /api inexistente (404), un
# método no permitido (405, p. ej. POST a /api/modules/1) o un 500 no
# capturado llegaban al cliente como una página HTML, rompiendo el
# contrato JSON que el resto de la API sí cumple. Fuera de /api/ se
# conserva el comportamiento por defecto (la SPA y sus páginas).
@app.errorhandler(404)
@app.errorhandler(405)
def handle_api_http_error(error):
    if request.path.startswith("/api/"):
        return jsonify({"error": error.name}), error.code
    return error


@app.errorhandler(500)
def handle_api_server_error(error):
    if request.path.startswith("/api/"):
        # Genérico a propósito: el detalle queda en el log del servidor,
        # no en la respuesta (un 500 con el SQL dentro es una fuga).
        return jsonify({"error": "Error interno del servidor"}), 500
    return InternalServerError()

# generate sitemap with all your endpoints


@app.route('/')
def sitemap():
    if ENV == "development":
        return generate_sitemap(app)
    return send_from_directory(static_file_dir, 'index.html')

# any other endpoint will try to serve it like a static file


@app.route('/<path:path>', methods=['GET'])
def serve_any_other_file(path):
    # Las rutas /api/* que no casaron con ningún endpoint son errores de
    # la API (404 JSON), no páginas de la SPA: sin esta guarda, con el
    # frontend compilado servían index.html con 200.
    if path.startswith("api/"):
        abort(404)
    if not os.path.isfile(os.path.join(static_file_dir, path)):
        path = 'index.html'
    response = send_from_directory(static_file_dir, path)
    response.cache_control.max_age = 0  # avoid cache memory
    return response


# this only runs if `$ python src/main.py` is executed
if __name__ == '__main__':
    PORT = int(os.environ.get('PORT', 3001))
    app.run(host='0.0.0.0', port=PORT, debug=True)