"""
vault.py — Credenciales cifradas en disco.

Guarda usuario, contraseña y semilla 2FA del broker con AES-256-GCM, y la clave
se deriva con Scrypt de un token que solo existe en la máquina del usuario. La
contraseña del broker nunca toca el código, ni un archivo de configuración, ni
git.

    formato del blob:  \\x01 ‖ salt(32) ‖ nonce(12) ‖ ciphertext

El byte de versión al principio permite cambiar el esquema más adelante sin
romper los vaults viejos.

**Compatible con el vault de Terminal Financiera**: mismo algoritmo, mismos
parámetros, mismo directorio. Si ya tenías credenciales cargadas, esta app las
lee sin que tengas que volver a ingresarlas.

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

VAULT_DIR = Path.home() / ".config" / "byma_vault"
CREDENCIALES = VAULT_DIR / "credentials.enc"
SESION = VAULT_DIR / "session.enc"

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

def existe() -> bool:
    return CREDENCIALES.exists()


def crear(credenciales: dict) -> str:
    """Cifra las credenciales y devuelve la API key que las abre.

    La API key se muestra UNA vez y no se guarda en ningún lado: es lo único
    que el usuario tiene que conservar. Sin ella, el vault es ruido.

    credenciales: {"email": ..., "password": ..., "totp_secret_key": ...}
    """
    faltan = [k for k in ("email", "password") if not credenciales.get(k)]
    if faltan:
        raise ValueError(f"Faltan credenciales: {', '.join(faltan)}")
    token = secrets.token_bytes(32)
    _escribir_privado(CREDENCIALES, cifrar(json.dumps(credenciales).encode(), token))
    return _PREFIJO + token.hex()


def abrir(api_key: str) -> dict:
    if not CREDENCIALES.exists():
        raise FileNotFoundError("No hay vault. Cargá las credenciales primero.")
    return json.loads(descifrar(CREDENCIALES.read_bytes(), _token(api_key)).decode())


def rotar(api_key_vieja: str) -> str:
    """Re-cifra con un token nuevo. Devuelve la API key nueva."""
    credenciales = abrir(api_key_vieja)
    token = secrets.token_bytes(32)
    _escribir_privado(CREDENCIALES, cifrar(json.dumps(credenciales).encode(), token))
    return _PREFIJO + token.hex()


# ── Sesión ────────────────────────────────────────────────────────────────────
# Los JWT del broker se guardan cifrados con la misma API key. Es lo que evita
# tener que sacar el celular y tipear el código 2FA en cada arranque.

def guardar_sesion(api_key: str, sesion: dict) -> bool:
    try:
        _escribir_privado(SESION, cifrar(json.dumps(sesion).encode(), _token(api_key)))
        return True
    except Exception as e:
        print(f"  [vault] no se pudo guardar la sesión: {e}")
        return False


def cargar_sesion(api_key: str):
    if not SESION.exists():
        return None
    try:
        return json.loads(descifrar(SESION.read_bytes(), _token(api_key)).decode())
    except Exception:
        return None      # sesión vieja o de otra clave: se hace login de nuevo


def borrar_sesion() -> bool:
    if SESION.exists():
        SESION.unlink()
        return True
    return False
