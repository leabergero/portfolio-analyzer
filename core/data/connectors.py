"""
connectors.py — Claves de las fuentes externas que piden credencial.

Dos fuentes de la aplicación necesitan credencial y las dos son **opcionales**:

    Cocos Capital   cuenta de broker      → precios de bonos, ONs y letras
    FMP             API key (free tier)   → precios objetivo de analistas

Sin ellas la aplicación funciona igual, con menos cobertura. Ver la tabla de
fuentes en `docs/DECISIONES.md`.

Las credenciales del broker van cifradas en el vault (`core.broker.vault`),
porque son las que pueden mover dinero. Las API keys de datos van acá, en un
JSON con permisos 600 y fuera de git: son de solo lectura, tienen plan gratuito
y meterlas en el vault obligaría a desbloquear el broker para consultar un
precio objetivo.

El archivo NUNCA se versiona y la key no se escribe en logs ni en el código.
"""

import json
import os
from pathlib import Path

ARCHIVO = Path(__file__).resolve().parents[2] / "data" / "connectors.json"


def _leer() -> dict:
    if not ARCHIVO.exists():
        return {}
    try:
        return json.loads(ARCHIVO.read_text())
    except Exception:
        return {}


def guardar(nombre: str, config: dict) -> None:
    datos = _leer()
    datos[nombre] = config
    ARCHIVO.parent.mkdir(parents=True, exist_ok=True)
    ARCHIVO.write_text(json.dumps(datos, indent=2))
    try:
        os.chmod(ARCHIVO, 0o600)
    except OSError:
        pass


def clave(nombre: str):
    """API key del conector, o None si no está configurado."""
    return (_leer().get(nombre) or {}).get("api_key") or None


def configurados() -> list:
    """Nombres de los conectores que tienen clave cargada. No devuelve las claves."""
    return [n for n, c in _leer().items() if (c or {}).get("api_key")]


def borrar(nombre: str) -> bool:
    datos = _leer()
    if nombre not in datos:
        return False
    del datos[nombre]
    ARCHIVO.write_text(json.dumps(datos, indent=2))
    return True


# ── Qué cartera es cada comitente ─────────────────────────────────────────────
# No es una credencial, pero vive acá por lo mismo: es configuración local que no
# se versiona. Cada cartera es una cuenta distinta de Cocos y el vault guarda una
# sesión por vez, así que sin este mapa no hay forma de saber si las tenencias
# que estás mirando son las de la cartera a la que las querés importar.

_CARTERAS = "cocos_carteras"


def cartera_de_cuenta(cuenta: str):
    """Nombre de la cartera asociada a ese número de comitente, o None."""
    return (_leer().get(_CARTERAS) or {}).get(str(cuenta)) if cuenta else None


def asociar_cuenta(cuenta: str, cartera: str) -> None:
    mapa = dict(_leer().get(_CARTERAS) or {})
    mapa[str(cuenta)] = cartera
    guardar(_CARTERAS, mapa)
