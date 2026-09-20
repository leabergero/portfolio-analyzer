"""
vault.py — Credenciales cifradas en disco.

Guarda usuario, contraseña y semilla 2FA del broker con AES-256-GCM, y la clave
se deriva con Scrypt de un token que solo existe en la máquina del usuario. La
contraseña del broker nunca toca el código, ni un archivo de configuración, ni
git.

    formato del blob:  \\x01 ‖ salt(32) ‖ nonce(12) ‖ ciphertext

El byte de versión al principio permite cambiar el esquema más adelante sin
romper los vaults viejos.

**El vault vive dentro del proyecto** (`data/vault/`), no en `~/.config`: esta
aplicación es independiente de Terminal Financiera y no comparte credenciales
con ella. Copiar la carpeta del proyecto se lleva el vault; borrarla lo borra.

Este módulo no sabe nada de Cocos: cifra y descifra bytes. Quién los usa es
`core.broker.cocos`.
"""

import json
import os
import secrets
from pathlib import Path

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

VAULT_DIR = Path(__file__).resolve().parents[2] / "data" / "vault"
CREDENCIALES = VAULT_DIR / "credentials.enc"
SESION = VAULT_DIR / "session.enc"
CONFIG = VAULT_DIR / "config.json"


def _rutas(broker: str):
    """Un archivo por broker. `broker=""` mantiene los nombres de siempre
    (Cocos, que llegó primero) para no invalidar los vaults ya guardados;
    cualquier broker nuevo pasa su nombre y listo."""
    sufijo = f"_{broker}" if broker else ""
    return (VAULT_DIR / f"credentials{sufijo}.enc",
            VAULT_DIR / f"session{sufijo}.enc",
            f"default_key{sufijo}")

_PREFIJO = "byma_"
_VERSION = b"\x01"

# Scrypt con N=131072: deliberadamente lento (~0,5 s por derivación) para que un
# ataque por fuerza bruta sobre el archivo cifrado sea inviable.
_SCRYPT = {"length": 32, "n": 131072, "r": 8, "p": 1}


# ── Cifrado ───────────────────────────────────────────────────────────────────

def _derivar(token: bytes, salt: bytes) -> bytes:
    return Scrypt(salt=salt, backend=default_backend(), **_SCRYPT).derive(token)


def cifrar(datos: bytes, token: bytes) -> bytes:
    salt = secrets.token_bytes(32)
    nonce = secrets.token_bytes(12)
    ct = AESGCM(_derivar(token, salt)).encrypt(nonce, datos, None)
    return _VERSION + salt + nonce + ct


def descifrar(blob: bytes, token: bytes) -> bytes:
    if not blob or blob[:1] != _VERSION:
        raise ValueError("Formato de vault desconocido.")
    clave = _derivar(token, blob[1:33])
    try:
        return AESGCM(clave).decrypt(blob[33:45], blob[45:], None)
    except Exception:
        raise ValueError("Clave incorrecta o vault dañado.") from None


def _escribir_privado(ruta: Path, datos: bytes):
    """Escribe con permisos 600: solo el dueño puede leerlo."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(datos)
    try:
        os.chmod(ruta, 0o600)
    except (AttributeError, OSError):
        pass


def _token(api_key: str) -> bytes:
    return bytes.fromhex(api_key.replace(_PREFIJO, "").strip())


# ── Credenciales ──────────────────────────────────────────────────────────────

def existe(broker: str = "") -> bool:
    credenciales, _, _ = _rutas(broker)
    return credenciales.exists()


def crear(credenciales: dict, broker: str = "") -> str:
    """Cifra las credenciales, guarda la clave que las abre y la devuelve.

    A diferencia de un vault clásico, la clave se persiste al lado del cifrado
    (`config.json`) para que el usuario no tenga que conservarla ni volver a
    tipearla: carga email/contraseña/2FA una vez y la app se conecta sola en los
    arranques siguientes. El trade-off es explícito: quien acceda a `data/vault/`
    tiene el cifrado y la clave juntos, así que esta carpeta vale tanto como las
    credenciales en claro. Es el mismo modelo que usa Terminal Financiera y es
    una máquina personal; por eso `data/vault/` nunca se versiona.

    credenciales: {"email": ..., "password": ..., "totp_secret_key": ...}
    """
    faltan = [k for k in ("email", "password") if not credenciales.get(k)]
    if faltan:
        raise ValueError(f"Faltan credenciales: {', '.join(faltan)}")
    credenciales_path, _, clave_config = _rutas(broker)
    token = secrets.token_bytes(32)
    _escribir_privado(credenciales_path, cifrar(json.dumps(credenciales).encode(), token))
    clave = _PREFIJO + token.hex()
    guardar_clave(clave, broker)
    return clave


def guardar_clave(api_key: str, broker: str = "") -> None:
    _, _, clave_config = _rutas(broker)
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    config = json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
    config[clave_config] = api_key
    CONFIG.write_text(json.dumps(config))
    try:
        os.chmod(CONFIG, 0o600)
    except OSError:
        pass


def clave_guardada(broker: str = ""):
    """La clave que abre el vault, o None. Evita pedírsela al usuario."""
    if not CONFIG.exists():
        return None
    _, _, clave_config = _rutas(broker)
    try:
        return json.loads(CONFIG.read_text()).get(clave_config)
    except Exception:
        return None


def abrir(api_key: str, broker: str = "") -> dict:
    credenciales_path, _, _ = _rutas(broker)
    if not credenciales_path.exists():
        raise FileNotFoundError("No hay vault. Cargá las credenciales primero.")
    return json.loads(descifrar(credenciales_path.read_bytes(), _token(api_key)).decode())


def rotar(api_key_vieja: str, broker: str = "") -> str:
    """Re-cifra con un token nuevo. Devuelve la API key nueva."""
    credenciales_path, _, _ = _rutas(broker)
    credenciales = abrir(api_key_vieja, broker)
    token = secrets.token_bytes(32)
    _escribir_privado(credenciales_path, cifrar(json.dumps(credenciales).encode(), token))
    return _PREFIJO + token.hex()


# ── Sesión ────────────────────────────────────────────────────────────────────
# Los JWT del broker se guardan cifrados con la misma API key. Es lo que evita
# tener que sacar el celular y tipear el código 2FA en cada arranque.

def guardar_sesion(api_key: str, sesion: dict, broker: str = "") -> bool:
    _, sesion_path, _ = _rutas(broker)
    try:
        _escribir_privado(sesion_path, cifrar(json.dumps(sesion).encode(), _token(api_key)))
        return True
    except Exception as e:
        print(f"  [vault] no se pudo guardar la sesión: {e}")
        return False


def cargar_sesion(api_key: str, broker: str = ""):
    _, sesion_path, _ = _rutas(broker)
    if not sesion_path.exists():
        return None
    try:
        return json.loads(descifrar(sesion_path.read_bytes(), _token(api_key)).decode())
    except Exception:
        return None      # sesión vieja o de otra clave: se hace login de nuevo


def borrar_sesion(broker: str = "") -> bool:
    _, sesion_path, _ = _rutas(broker)
    if sesion_path.exists():
        sesion_path.unlink()
        return True
    return False


def borrar_todo(broker: str = "") -> None:
    """Elimina credenciales, sesión y clave guardada de este broker."""
    credenciales_path, sesion_path, clave_config = _rutas(broker)
    for f in (credenciales_path, sesion_path):
        f.unlink(missing_ok=True)
    if CONFIG.exists():
        config = json.loads(CONFIG.read_text())
        config.pop(clave_config, None)
        CONFIG.write_text(json.dumps(config))
