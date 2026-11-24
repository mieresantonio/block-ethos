# Caso de estudio: Block Ethos — Web3 Space

**Plataforma educativa en español para aprender blockchain haciendo.**
Demo en vivo: <https://BC123.pythonanywhere.com> · Código: <https://github.com/mieresantonio/block-ethos>

Block Ethos nació como proyecto final del bootcamp Full Stack de 4Geeks Academy
(Grupo 3) y siguió evolucionando como producto propio: rutas guiadas con
lecciones en Markdown, quizzes con nota real, progreso persistente en el
servidor, un tutor que responde citando el contenido del curso, gamificación y
certificados verificables. Este documento cuenta cómo se construyó: las
decisiones de arquitectura, los errores reales que aparecieron y cómo se
resolvieron, con enlaces al código y a los tests que lo demuestran.

> Todos los enlaces al código apuntan al commit `b136008` (17 nov 2026), el
> estado revisado para este caso. Los números de línea corresponden a ese
> commit. La demo pública corresponde a un despliegue anterior al renombre
> desde Blockali y muestra la marca anterior hasta el próximo redespliegue.

## El proyecto en cifras

| Dato | Valor | Fuente |
| --- | --- | --- |
| Rutas / módulos / lecciones | 2 / 5 / 9 | Semilla de contenido y README |
| Quizzes / preguntas | 9 / 36 | Semilla (`commands.py`: 9 bloques de preguntas, 36 `question_text`) |
| Pruebas automatizadas | 166 (144 en verde; 22 nuevas: 2 de ProxyFix verificadas y 20 del tutor y el perfil público, aún sin correr) | Suite completa (`pytest tests/`, 23 nov 2026) |
| Archivos de tests (backend) | 17 | `tests/` |
| Commits del repo original | 93 (Antonio 48 · Luis 23 · Iván 22) | Historial del repo original |
| Commits del repo independiente | 5 | Historial de `block-ethos` |
| Stack | React 18 + Vite · Flask · SQLAlchemy 2 · JWT · SQLite | `README.md` |
| Despliegue | PythonAnywhere | `README.md` |

## Línea de tiempo

| Fecha | Hito | Commit |
| --- | --- | --- |
| 6 ago 2026 | Inicio del proyecto final (Grupo 3) | [2a84331](https://github.com/mieresantonio/mieresantonio-ProyectoFinal-grupo3-ALI/commit/2a84331) |
| 13 ago 2026 | Autenticación JWT y endpoints base | [98cff5c](https://github.com/mieresantonio/mieresantonio-ProyectoFinal-grupo3-ALI/commit/98cff5c) |
| 20 ago 2026 | Contraseñas con hash (Werkzeug) | [36ccb56](https://github.com/mieresantonio/mieresantonio-ProyectoFinal-grupo3-ALI/commit/36ccb56) |
| 8 sep 2026 | Seguridad y bugs críticos en progreso, roles y sesión | [1efc944](https://github.com/mieresantonio/mieresantonio-ProyectoFinal-grupo3-ALI/commit/1efc944) |
| 8 sep 2026 | Registro con verificación por correo y recuperación de contraseña | [8ba4cde](https://github.com/mieresantonio/mieresantonio-ProyectoFinal-grupo3-ALI/commit/8ba4cde) |
| 23 oct 2026 | Rediseño web3 oscuro y laboratorio interactivo | [cc6380d](https://github.com/mieresantonio/mieresantonio-ProyectoFinal-grupo3-ALI/commit/cc6380d) |
| 23 oct 2026 | Gamificación (XP, niveles, rachas) y certificados verificables | [8811870](https://github.com/mieresantonio/mieresantonio-ProyectoFinal-grupo3-ALI/commit/8811870) |
| 26 oct 2026 | Despliegue en PythonAnywhere | [4a733e5](https://github.com/mieresantonio/mieresantonio-ProyectoFinal-grupo3-ALI/commit/4a733e5) |
| 2 nov 2026 | Contenido completo (9 lecciones) y tutor TF-IDF integrado | [027c38e](https://github.com/mieresantonio/mieresantonio-ProyectoFinal-grupo3-ALI/commit/027c38e) |
| 2 nov 2026 | Backend: orden, validación y suite de pruebas | [dbf9e86](https://github.com/mieresantonio/mieresantonio-ProyectoFinal-grupo3-ALI/commit/dbf9e86) |
| 2 nov 2026 | Cuenta demo de estudiante pública; admin demo solo en local | [d33d35b](https://github.com/mieresantonio/mieresantonio-ProyectoFinal-grupo3-ALI/commit/d33d35b) |
| 10 nov 2026 | Revisión profunda: errores y seguridad en la API | [b7d12f5](https://github.com/mieresantonio/mieresantonio-ProyectoFinal-grupo3-ALI/commit/b7d12f5) |
| 16 nov 2026 | Repo independiente `block-ethos` (renombre desde Blockali) | [298844c](https://github.com/mieresantonio/block-ethos/commit/298844c) |
| 16 nov 2026 | Rate limiting, OpenAPI, unicidad de certificados; 144 tests | [3ef7bf1](https://github.com/mieresantonio/block-ethos/commit/3ef7bf1) |

Desde noviembre de 2026 el proyecto lo mantiene y evoluciona una sola persona.

## Decisiones de arquitectura

### Una app completa en un solo repositorio

Frontend React con Vite y backend Flask en el mismo repo, sobre la plantilla
react-flask de 4Geeks, muy modificada. La API vive en `src/api/` (modelos,
rutas, comandos, correo); el frontend en `src/front/` (páginas, componentes,
servicios). El despliegue es un solo servicio en PythonAnywhere que sirve la
API y el frontend compilado.

### SQLite en producción, por decisión, no por defecto

La base de datos es SQLite en producción y desarrollo, accedida siempre a
través de SQLAlchemy 2 con migraciones Alembic. Para una plataforma educativa
con un solo proceso, SQLite elimina una pieza de infraestructura sin coste
real; el día que el volumen lo pida, el cambio es la URL de conexión, no el
código. El modelo es: rutas → módulos → lecciones → quizzes, con progreso por
usuario y lección, certificados y gamificación encima
([`src/api/models.py`](https://github.com/mieresantonio/block-ethos/blob/b136008/src/api/models.py)).

### El tutor no usa ningún modelo de lenguaje

El tutor (`POST /api/tutor`) responde con búsqueda TF-IDF escrita con solo la
librería estándar de Python sobre los fragmentos de las lecciones guardadas en
la base de datos. Sin servicios externos, sin claves de API, sin coste por
pregunta. La respuesta es extractiva: se compone con los fragmentos más
relevantes y cita la lección de origen, con enlace directo. Si ningún fragmento
supera el umbral de similitud (0,08, ajustado con preguntas reales de prueba),
el tutor lo dice y sugiere la lección más cercana en vez de inventar una
respuesta
([`src/api/routes.py` L1015-L1040](https://github.com/mieresantonio/block-ethos/blob/b136008/src/api/routes.py#L1015-L1040),
[endpoint L1205-L1206](https://github.com/mieresantonio/block-ethos/blob/b136008/src/api/routes.py#L1205-L1206)).

El índice TF-IDF se cachea en memoria y solo se reconstruye cuando cambia el
contenido (una huella ligera lo detecta en cada petición): antes se reconstruía
en cada pregunta
([L1117-L1135](https://github.com/mieresantonio/block-ethos/blob/b136008/src/api/routes.py#L1117-L1135)).

### Rate limiting sin dependencias

El limitador de los endpoints de autenticación es memoria del proceso con
ventana deslizante por (IP, endpoint): 10 logins y 5 registros/recuperaciones
por minuto, con 429 JSON y cabecera `Retry-After`. Sin Redis ni servicios:
en PythonAnywhere corre un solo proceso, así que el estado en memoria basta, y
el propio código documenta ese límite
([`src/api/rate_limit.py`](https://github.com/mieresantonio/block-ethos/blob/b136008/src/api/rate_limit.py)).

### Certificados verificables, no PDFs decorativos

Al completar una ruta al 100% con todos los quizzes aprobados (≥ 70%), el
estudiante reclama un certificado con código único `BK-XXXXX-XXXXX-XXXXX`.
Cualquiera puede comprobarlo en `/verificar/:code`, sin cuenta. La unicidad
del código se garantiza en la base de datos, no solo en la aplicación.
La semilla crea además un certificado de ejemplo con código público
`BK-DEMO` (estudiante demo, «Fundamentos de Blockchain»): quien evalúa la
plataforma prueba la verificación en `/verificar/BK-DEMO` sin registrarse.

### Gamificación sobre el progreso real

XP (100 por lección completada, más los puntos de los quizzes), 6 niveles
(Explorador → Arquitecto Web3) y rachas de días consecutivos calculadas desde
el progreso registrado. La fecha de finalización de cada lección se sella solo
la primera vez que se completa: es el dato del que dependen las rachas.

## Errores reales y cómo se resolvieron

Cada corrección lleva su comentario en el código explicando el bug que la
pidió, y su test. Son los errores que enseñaron a construir la API que existe
hoy.

### 1. Una nota de 99999 inflaba la XP sin límite

`PUT /progress` aceptaba cualquier número como `quiz_score`, y la gamificación
suma ese valor tal cual a la XP. Una nota de 99999 daba 99999 XP. La
corrección valida que la nota sea un número entre 0 y 100 (y que un booleano
no cuele como número)
([`routes.py` L724-L738](https://github.com/mieresantonio/block-ethos/blob/b136008/src/api/routes.py#L724-L738)).
Test: `test_quiz_score_fuera_de_rango_da_400` en
[`tests/test_progreso_gamificacion.py`](https://github.com/mieresantonio/block-ethos/blob/b136008/tests/test_progreso_gamificacion.py).

### 2. La cadena "false" devolvía un 500 con el error SQL

Un `is_completed` no booleano (por ejemplo, la cadena `"false"`) llegaba a
SQLAlchemy y la respuesta era un 500 con el error SQL en el cuerpo. Ahora el
endpoint rechaza con 400 cualquier valor no booleano y no nulo
([`routes.py` L739-L743](https://github.com/mieresantonio/block-ethos/blob/b136008/src/api/routes.py#L739-L743)).
Test: `test_progreso_validaciones`.

### 3. El progreso huérfano rompía la lectura con un 500

Crear progreso de una lección inexistente dejaba una fila huérfana; después,
`GET /progress/<usuario>` reventaba al leer `p.lesson.title` sobre `None`.
La creación ahora comprueba que todas las lecciones existan y responde 404
([`routes.py` L676-L692](https://github.com/mieresantonio/block-ethos/blob/b136008/src/api/routes.py#L676-L692)).
La misma guarda rechaza un `user_id` no entero: `True` se colaba como el id 1
(`True == 1`) y llegaba al INSERT.

### 4. Inicializar el progreso dos veces duplicaba la XP

Repetir la inicialización creaba una fila nueva por lección en cada llamada,
y la XP sumaba doble. Ahora las lecciones ya inicializadas se saltan
([`routes.py` L694-L698](https://github.com/mieresantonio/block-ethos/blob/b136008/src/api/routes.py#L694-L698)).
Test: `test_inicializar_progreso_sin_duplicados`.

### 5. Un `null` en `is_completed` rompía las filas existentes

Asignar `None` a `is_completed` en una fila existente lanzaba un
`IntegrityError` (la columna es `NOT NULL`) y el 500 resultante llevaba el
SQL en el cuerpo. La semántica quedó fijada: `null` significa «sin cambio» y
solo se asigna cuando llega un booleano de verdad
([`routes.py` L756-L768](https://github.com/mieresantonio/block-ethos/blob/b136008/src/api/routes.py#L756-L768)).
Este bug lo encontró la ronda 10 de revisión, y el comentario lo dice.

### 6. Cualquier cuenta podía leer el correo y el rol de otro usuario

`GET /users/<id>` solo pedía un token válido: cualquier cuenta con sesión
podía leer el correo y el rol de cualquier usuario por su id. Ahora solo el
propio usuario o un administrador
([`routes.py` L383-L397](https://github.com/mieresantonio/block-ethos/blob/b136008/src/api/routes.py#L383-L397)).
Test: `test_perfil_de_usuario_solo_dueno_o_admin`. El mismo principio rige
todo el progreso: cada endpoint comprueba que quien llama es el dueño del
recurso (403 en caso contrario), y el listado de usuarios es solo para
administradores (`test_lista_usuarios_solo_admin`).

### 7. Recuperar la contraseña no revela si el correo existe

La recuperación de contraseña responde igual exista o no el correo, para no
revelar qué cuentas existen
([`routes.py` L251](https://github.com/mieresantonio/block-ethos/blob/b136008/src/api/routes.py#L251)).
Test: `test_recuperacion_de_contrasena` en
[`tests/test_auth.py`](https://github.com/mieresantonio/block-ethos/blob/b136008/tests/test_auth.py).

### 8. El índice del tutor se reconstruía en cada pregunta

Construir el índice TF-IDF cuesta unos milisegundos y varias consultas; antes
se hacía en cada petición al tutor. Ahora se cachea y se reconstruye solo
cuando cambia el contenido, detectado por una huella
([`routes.py` L1117-L1135](https://github.com/mieresantonio/block-ethos/blob/b136008/src/api/routes.py#L1117-L1135)).
Test: `test_pregunta_en_temario_encuentra_fuente` y
`test_pregunta_fuera_de_temario_lo_dice` en
[`tests/test_tutor.py`](https://github.com/mieresantonio/block-ethos/blob/b136008/tests/test_tutor.py).

### 9. Cuatro defectos visuales corregidos en el código

La revisión visual encontró cuatro defectos en la demo en vivo; los cuatro
están corregidos en el código (la demo desplegada es anterior a las
correcciones):

- **Header translúcido** que dejaba ver las tarjetas al hacer scroll: la
  barra es sólida ahora (`.navbar` con fondo opaco,
  [`index.css` L192-L196](https://github.com/mieresantonio/block-ethos/blob/b136008/src/front/index.css#L192-L196);
  el único `backdrop-filter` del CSS está en las estadísticas, no en la barra).
- **El botón «Preguntar» parecía activo estando deshabilitado**: el estado
  deshabilitado ya no tiene gradiente ni sombra
  ([`index.css` L141-L150](https://github.com/mieresantonio/block-ethos/blob/b136008/src/front/index.css#L141-L150)).
- **El hero se veía tenue un instante al cargar**: el hero no usa animación de
  aparición; el comentario en el código explica por qué
  ([`Hero.jsx` L15-L17](https://github.com/mieresantonio/block-ethos/blob/b136008/src/front/components/Hero.jsx#L15-L17)).
  La cabecera del Dashboard tenía el mismo defecto y se corrigió igual en la
  publicación del 23 nov 2026.
- **Franja oscura bajo el footer en `/tutor`**: el layout es flex a 100vh con
  el contenido principal creciendo para empujar el footer al pie
  ([`index.css` L657-L664](https://github.com/mieresantonio/block-ethos/blob/b136008/src/front/index.css#L657-L664)).

### 10. El rate limiting era global detrás del proxy (hallazgo en revisión)

En la revisión del 23 nov 2026 se detectó que el limitador usa
`request.remote_addr`, y detrás del proxy de PythonAnywhere esa IP es la del
proxy: el límite de 10 logins por minuto se compartía entre todos los
usuarios, así que diez logins de cualquiera bloqueaban el login de todo el
mundo. La corrección es `ProxyFix` con un solo proxy de confianza (`x_for=1`),
con dos tests que demuestran el límite por cliente y que la cabecera
`X-Forwarded-For` no se puede falsificar para esquivarlo. Estado: corregido
en la publicación del 23 nov 2026
([c52f86b](https://github.com/mieresantonio/block-ethos/commit/c52f86b8a20cb8a50d03801f935199e3bb74fe9d)),
en la misma entrega que este documento.
El limitador en sí está cubierto por 9 tests en
[`tests/test_rate_limit.py`](https://github.com/mieresantonio/block-ethos/blob/b136008/tests/test_rate_limit.py).

### 11. La cuenta de administrador demo no debe existir en público

La semilla creaba una cuenta de administrador demo con contraseña conocida.
Desde el 2 nov 2026, el estudiante demo es el único ingreso público de
prueba y el administrador demo solo se crea con `SEED_DEMO_USERS=1`, nunca en
un despliegue público
([d33d35b](https://github.com/mieresantonio/mieresantonio-ProyectoFinal-grupo3-ALI/commit/d33d35b)).

## Cómo se verifica

- **166 pruebas automatizadas** en 17 archivos (`tests/`), que cubren auth,
  catálogo, progreso, gamificación, certificados (incluida su unicidad),
  tutor (incluido el tutor con progreso), perfil público, rate limiting y
  regresiones de las rondas de revisión 2, 3, 9, 10, 11 y 12 — los nombres
  de los archivos guardan la historia de esas rondas. 144 en verde en la
  suite completa del 23 nov 2026; las 22 pruebas nuevas de esta entrega
  (2 de ProxyFix, verificadas en su archivo, y 20 del tutor y el perfil
  público) quedan pendientes de corrida completa.
- **2 archivos de tests del frontend** (`pricesService`, store global).
- **Especificación OpenAPI** servida por la propia API (`GET /api/openapi.yaml`).
- **Verificación antes de cada publicación**: la suite completa en verde y,
  en el despliegue, comprobación de que el bundle compilado contiene la URL
  del backend (un build sin la variable de entorno muestra una pantalla de
  error en vez de la aplicación).

## Qué demuestra este proyecto

- **Vertical completo**: de la interfaz al despliegue — React, API Flask,
  base de datos, autenticación JWT, correo, despliegue en producción.
- **Seguridad pensada en capas**: permisos por dueño y rol, validación de
  entradas con respuestas de error limpias, cuentas demo controladas,
  rate limiting.
- **Testing como hábito**: cada bug real terminó en un test de regresión; la
  suite crece con las rondas de revisión.
- **Decisiones con criterio de coste**: TF-IDF sin dependencias en vez de un
  modelo externo, SQLite en vez de un servidor de base de datos, rate
  limiting en memoria — cada pieza es la más simple que resuelve el problema.

---

*La evolución posterior de Block Ethos se desarrolló con apoyo de herramientas
de IA como par de programación, bajo mi dirección y revisión: cada cambio de
arquitectura, seguridad y despliegue fue verificado antes de publicarse.*
