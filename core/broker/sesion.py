"""
sesion.py — El sobre firmado que reemplaza al vault en el modo web.

En la máquina del usuario, las credenciales viven cifradas en `data/vault/` y la
app se reconecta sola (ver `vault.py`). Servida a varios usuarios eso no sirve:
la contraseña de otro no puede estar en nuestro disco, ni cifrada, porque la
llave que la abre también estaría ahí.

Acá no se guarda nada. El usuario tipea email, contraseña y el código 2FA una
vez por día; el servidor hace el login, le devuelve al navegador un sobre
firmado con los JWT de Cocos adentro, y se olvida de la contraseña. El resto
del día el navegador manda el sobre en cada request y el servidor reconstruye
el cliente sin descifrar nada.

    sobre = firma(secreto, {access_token, refresh_token, ..., login_ts})

Está **firmado, no cifrado**, y es deliberado: el dueño del navegador puede leer
sus propios JWT y no le sirve de nada — ya tiene la cuenta. Lo que la firma
impide es que alguien fabrique o edite uno.

`login_ts` es el momento del login con 2FA y **no se toca nunca**. El access
token de Cocos dura una hora y se renueva solo, lo que obliga a reemitir el
sobre; si cada reemisión reiniciara el reloj, el 2FA diario no llegaría jamás
y la caducidad sería decorativa. Por eso la vigencia se mide contra `login_ts`
y no contra la firma.
"""

import os
import secrets
import time
from pathlib import Path

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

DIA = 24 * 60 * 60

_SECRETO = Path(__file__).resolve().parents[2] / "data" / "secreto_sesion"
_SAL = "cocos-sesion"


def modo_web() -> bool:
    """¿Este proceso sirve a un usuario por sobre, o al dueño de la máquina?

    Los dos caminos comparten el global `_cliente` de `cocos.py`, así que no
    pueden convivir en el mismo intérprete: una request con sobre restaura el
    cliente y al terminar lo suelta, dejando colgada la sesión del vault. En el
    despliegue nunca se cruzan —un contenedor por usuario, un modo por
    proceso— y este flag lo hace explícito en vez de dejarlo librado a que
    nadie mande la cabecera por accidente.

        modo local (por defecto)   la app de todos los días, vault en disco
        PA_MODO=web                multiusuario, sin vault, sobre por request
    """
    return os.environ.get("PA_MODO", "").strip().lower() == "web"


class SesionInvalida(Exception):
    """Sobre vencido, manipulado o firmado con un secreto que ya no rige."""


def secreto() -> str:
    """El secreto que firma los sobres. De entorno, o uno propio persistido.

    Rotarlo invalida todas las sesiones vivas de todos los usuarios de golpe:
    es el botón de pánico. No es dato de nadie, es del servidor.
    """
    if env := os.environ.get("PA_SECRETO_SESION"):
        return env
    if not _SECRETO.exists():
        _SECRETO.parent.mkdir(parents=True, exist_ok=True)
        _SECRETO.write_text(secrets.token_hex(32))
        try:
            os.chmod(_SECRETO, 0o600)
        except OSError:
            pass
    return _SECRETO.read_text().strip()


def emitir(jwt: dict, login_ts: float = None) -> str:
    """Envuelve los JWT recién obtenidos. Sin `login_ts` arranca el reloj ahora.

    Al reemitir tras renovar el access token hay que pasar el `login_ts` del
    sobre viejo, o el 2FA diario no vence nunca.
    """
    datos = dict(jwt)
    datos["login_ts"] = login_ts if login_ts is not None else time.time()
    return URLSafeTimedSerializer(secreto(), salt=_SAL).dumps(datos)


def leer(sobre: str, max_age: int = DIA) -> dict:
    """Abre y valida el sobre. Lanza `SesionInvalida` si no sirve.

    Dos vallas: la firma (nadie lo fabricó ni lo editó) y `login_ts` (no pasaron
    más de `max_age` desde que tipeó el 2FA).
    """
    if not sobre:
        raise SesionInvalida("sin sesión")
    try:
        # El max_age de itsdangerous es el cinturón; el tirante es login_ts, que
        # sobrevive a las reemisiones. Se le da margen para que la valla real
        # sea siempre la de abajo y el mensaje de error sea el correcto.
        datos = URLSafeTimedSerializer(secreto(), salt=_SAL).loads(
            sobre, max_age=max_age * 30)
    except SignatureExpired:
        raise SesionInvalida("sesión vencida") from None
    except BadSignature:
        raise SesionInvalida("sesión inválida") from None

    if time.time() - datos.get("login_ts", 0) > max_age:
        raise SesionInvalida("sesión vencida")
    return datos


def vence_en(sesion: dict, max_age: int = DIA) -> int:
    """Segundos que le quedan al sobre. Para avisar antes de cortar."""
    return max(0, int(sesion.get("login_ts", 0) + max_age - time.time()))
