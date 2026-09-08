"""
usuarios.py — Quién es el que está usando la web. Sin contraseñas.

La identidad la pone Google y nosotros no guardamos ninguna clave. El motivo no
es comodidad: los usuarios de esta app tienen cuenta en Cocos, y una parte va a
reusar ahí la contraseña del broker. Una base de hashes nuestra sería, para esa
gente, una copia de la llave de su cuenta comitente. La única forma de no tener
ese problema es no tener contraseñas.

De Google llega el `sub`: un identificador estable que no cambia aunque el
usuario cambie de email. Ese es el dueño de la carpeta de carteras. El email se
guarda sólo para mostrarlo en pantalla.

    ingreso   →  Google  →  vuelve con un `code`  →  se canjea server-a-server
                            por un id_token       →  sobre de sesión (cookie)

Se usa el flujo de código, no el botón de Google en JavaScript, por una razón
concreta: el botón mete un script de terceros con acceso total a la página, y
esta página maneja sesiones de broker. Con la redirección, el navegador se va a
Google y vuelve; no corre código ajeno acá.

**No se verifica la firma del id_token, y es correcto**: viene de una respuesta
directa de Google sobre TLS a una petición autenticada con nuestro client
secret, no del navegador. Es la excepción que la propia documentación de Google
marca para este flujo. Igual se chequean `aud` e `iss`, que es gratis y caza un
error de configuración.

Dos sesiones que no se mezclan:

    la de acá        quién sos. Semanas. No abre la cuenta de nadie.
    la de Cocos      opcional, 24 h, en `core.broker.sesion`. Si el usuario no
                     conecta el broker, no existe y la app anda igual.
"""

import base64
import json
import os
import time
import urllib.parse
import urllib.request

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from core.broker.sesion import secreto
from core.data import connectors

MES = 30 * 24 * 60 * 60
_VIDA_ESTADO = 10 * 60          # lo que puede tardar alguien en elegir su cuenta

_AUTORIZAR = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN = "https://oauth2.googleapis.com/token"
_EMISORES = ("accounts.google.com", "https://accounts.google.com")

COOKIE = "pa_usuario"


class NoAutenticado(Exception):
    """No hay sesión de usuario, o la que hay no sirve."""


# ── Configuración ─────────────────────────────────────────────────────────────
# El client_id no es secreto (viaja en la URL de ingreso). El client_secret sí:
# va en connectors.json, que tiene permisos 600 y está fuera de git, o en el
# entorno, que es lo que conviene en el despliegue.

def _config() -> dict:
    c = connectors._leer().get("google") or {}
    return {
        "client_id": os.environ.get("GOOGLE_CLIENT_ID") or c.get("client_id") or "",
        "client_secret": os.environ.get("GOOGLE_CLIENT_SECRET") or c.get("client_secret") or "",
    }


def configurado() -> bool:
    c = _config()
    return bool(c["client_id"] and c["client_secret"])


def guardar_config(client_id: str, client_secret: str) -> None:
    connectors.guardar("google", {"client_id": client_id.strip(),
                                  "client_secret": client_secret.strip()})


# ── Ida y vuelta con Google ───────────────────────────────────────────────────

def _firmante(sal: str):
    return URLSafeTimedSerializer(secreto(), salt=sal)


def url_de_ingreso(redirect_uri: str, destino: str = "/") -> str:
    """A dónde mandar el navegador para que Google pregunte quién es.

    El `state` va firmado por nosotros y vuelve intacto: es lo que impide que
    alguien fabrique una vuelta de callback desde otro lado (CSRF sobre el
    login). Lleva adentro a qué página volver.
    """
    return _AUTORIZAR + "?" + urllib.parse.urlencode({
        "client_id": _config()["client_id"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": _firmante("ingreso-estado").dumps(destino),
        "access_type": "online",
        "prompt": "select_account",
    })


def leer_estado(state: str) -> str:
    """El destino que viajó en el `state`. Lanza si no lo firmamos nosotros."""
    try:
        return _firmante("ingreso-estado").loads(state or "", max_age=_VIDA_ESTADO)
    except (BadSignature, SignatureExpired):
        raise NoAutenticado("el ingreso no salió de acá o tardó demasiado") from None


def _payload(id_token: str) -> dict:
    cuerpo = id_token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(cuerpo + "=" * (-len(cuerpo) % 4)))


def canjear(code: str, redirect_uri: str) -> dict:
    """Cambia el `code` por la identidad. Devuelve {sub, email, nombre, foto}."""
    cfg = _config()
    datos = urllib.parse.urlencode({
        "code": code, "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"], "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }).encode()
    pedido = urllib.request.Request(
        _TOKEN, data=datos,
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(pedido, timeout=20) as r:
            token = json.loads(r.read())
    except Exception as e:
        raise NoAutenticado(f"Google no aceptó el ingreso: {e}") from None

    if not token.get("id_token"):
        raise NoAutenticado("Google no devolvió identidad.")
    p = _payload(token["id_token"])

    if p.get("aud") != cfg["client_id"]:
        raise NoAutenticado("el token es de otra aplicación")
    if p.get("iss") not in _EMISORES:
        raise NoAutenticado("el token no lo emitió Google")
    if not p.get("sub"):
        raise NoAutenticado("el token no trae identidad")
    if p.get("email") and not p.get("email_verified", False):
        raise NoAutenticado("ese email todavía no está verificado en Google")

    return {"sub": p["sub"], "email": p.get("email", ""),
            "nombre": p.get("name") or p.get("email", ""), "foto": p.get("picture", "")}


# ── La sesión de la app ───────────────────────────────────────────────────────
# Va en cookie httpOnly y no en localStorage, a diferencia del sobre de Cocos:
# un XSS no la puede leer. El de Cocos tiene que ser legible por el JavaScript
# porque viaja como cabecera; este no, así que se protege mejor y sale gratis.

def emitir(usuario: dict) -> str:
    return _firmante("usuario").dumps(
        {**{k: usuario.get(k, "") for k in ("sub", "email", "nombre", "foto")},
         "desde": time.time()})


def leer(sobre: str, max_age: int = MES) -> dict:
    if not sobre:
        raise NoAutenticado("sin sesión")
    try:
        return _firmante("usuario").loads(sobre, max_age=max_age)
    except SignatureExpired:
        raise NoAutenticado("la sesión venció") from None
    except BadSignature:
        raise NoAutenticado("sesión inválida") from None


def carpeta(usuario: dict) -> str:
    """El identificador que nombra la carpeta de datos del usuario.

    Es el `sub` de Google tal cual: son dígitos, estable de por vida, y no
    cambia si el usuario cambia de email. Se valida igual antes de usarlo como
    nombre de directorio — nunca se confía en algo que vino de afuera para
    construir una ruta.
    """
    sub = str(usuario.get("sub", ""))
    if not sub.isalnum():
        raise NoAutenticado("identificador de usuario inválido")
    return sub
