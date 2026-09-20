"""
bonistas.py — TIR de bonistas.com, de respaldo cuando `core.models.bonds` no
tiene la ficha de cupones del papel.

`bonds.py` calcula la TIR reconstruyendo el flujo de fondos completo (cupones,
amortización) contra un catálogo propio chico: exacta cuando el papel está,
pero la mayoría de las ONs no están. Bonistas.com publica una API pública, sin
login, con la TIR ya calculada por ellos para ~900 instrumentos — no tan
auditable como la propia, pero mucho más ancha. Por eso es **respaldo**, no
reemplazo: si `bonds.py` ya tiene el papel, esa TIR manda.

API descubierta leyendo el bundle de Next.js del sitio (público, sin
autenticar) — no hay documentación oficial, así que un cambio de forma ahí
puede romper esto sin aviso. Ver `inviu-integration/` para el mismo método
aplicado a un caso más difícil.
"""

import time

import requests

from core.data import cache

_URL = "https://www.bonistas.com/api/bonds"
_HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
_CLAVE_CACHE = "bonistas:bonds"
_TTL_H = 20          # el sitio dice actualizar una vez por día


def _descargar() -> list:
    r = requests.get(_URL, headers=_HEADERS, timeout=20)
    r.raise_for_status()
    return r.json()


def _bonos() -> list:
    """La lista cruda, cacheada ~20 h. Vacía si la fuente está caída y no hay
    nada guardado — nunca excepción: es un respaldo, no puede tumbar la
    pantalla que lo pide."""
    cacheado = cache.leer_respuesta(_CLAVE_CACHE, _TTL_H)
    if cacheado is not None:
        return cacheado
    try:
        datos = _descargar()
    except Exception as e:
        print(f"  [bonistas] no se pudo bajar: {e}")
        return cache.leer_respuesta(_CLAVE_CACHE, ttl_horas=24 * 365) or []
    cache.guardar_respuesta(_CLAVE_CACHE, datos)
    return datos


def tir_pct(ticker: str, settlement: str = "24hs") -> float:
    """TIR en % (ya multiplicada por 100, como espera la UI) para ese ticker
    y plazo de liquidación, o `None` si no está."""
    ticker = ticker.upper().strip()
    for b in _bonos():
        if b.get("bond_name") == ticker and b.get("settlement") == settlement:
            tir = b.get("tir")
            return round(tir * 100, 3) if tir is not None else None
    return None


def demo():
    """Self-check sin red: pisa `_bonos` con datos fijos."""
    global _bonos
    original = _bonos
    _bonos = lambda: [{"bond_name": "AO28D", "settlement": "24hs", "tir": 0.0936},
                      {"bond_name": "AO28D", "settlement": "CI", "tir": 0.09}]
    try:
        assert tir_pct("ao28d") == 9.36              # no distingue mayúsculas
        assert tir_pct("AO28D", settlement="CI") == 9.0
        assert tir_pct("NO-EXISTE") is None
    finally:
        _bonos = original
    print("ok")


if __name__ == "__main__":
    demo()
