"""
_cocos_patch.py — Reparación en caliente del login de pyCocos 0.2.12.

pyCocos quedó sin mantenimiento (último release jun-2024) y Cocos movió su
autenticación. La librería sigue sirviendo para el flujo completo —token, 2FA
por TOTP, órdenes, precios— pero pega contra tres cosas que cambiaron:

  1. El login vive en `auth.cocos.capital`, no en `api.cocos.capital`. Sólo el
     tramo `auth/v1/*` se mudó; los datos de mercado (`api/v1/*`) siguen igual.
  2. La `apikey` pública (anon key de Supabase) que traía hardcodeada caducó;
     la vigente se lee del bundle web de la app (rol "anon", exp año 2095).
  3. El gateway ahora exige el header `x-store-version` presente (aunque vacío
     en web) o responde 426 APP_VERSION_HEADER_MISSING.

Este módulo parchea esos tres puntos sobre la clase del cliente HTTP, sin tocar
el paquete instalado y de forma idempotente. Si Cocos vuelve a cambiar el
esquema, es acá donde hay que mirar.

    ponytail: parche de host+clave+headers sobre pyCocos. Si algún día publican
    una versión que hable con el gateway nuevo, borrar este módulo y su llamada
    en cocos.py, y volver a `pip install -U pyCocos`.
"""

# Anon key pública de Supabase, extraída del bundle web de app.cocos.capital
# (2026-09). Es la misma clave que el navegador manda sin autenticar; no es un
# secreto y no abre ninguna cuenta por sí sola.
ANON_KEY = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyAgCiAgICAicm9sZSI6ICJhbm9u"
            "IiwKICAgICJhdWRpZW5jZSI6ICJjb2NvcyIsCiAgICAiaXNzIjogInN1cGFiYXNl"
            "IiwKICAgICJpYXQiOiAxNjQxOTU2NDAwLAogICAgImV4cCI6IDM5NDgzNDE1MzEK"
            "fQ.Q5ZiL7KCUKP7iSM_LHWd3gffZ0k5Ce6CemOX9CUfEdM")

_AUTH_HOST = "https://auth.cocos.capital/"
_API_HOST = "https://api.cocos.capital/"
# Presentes aunque vacíos: en web la app manda x-store-version="" y el gateway
# sólo exige que el header exista.
_HEADERS_VERSION = {"x-store-version": "", "x-update-id": "", "x-platform": "web"}


def aplicar() -> None:
    from pycocos.components import client as _c

    if getattr(_c.RestClient, "_pa_parcheado", False):
        return

    from requests.structures import CaseInsensitiveDict

    _init = _c.RestClient.__init__

    def __init__(self):
        _init(self)
        # cloudscraper deja session.headers como OrderedDict case-sensitive, así
        # que "Authorization" y "authorization" conviven como dos headers. pyCocos
        # setea el token con distinta capitalización en pasos sucesivos, y el
        # gateway toma el primero —la anon key— y responde 401 "invalid signature"
        # en todo endpoint de cuenta. Con un dict case-insensitive colapsan en uno.
        self.session.headers = CaseInsensitiveDict(self.session.headers)
        self.session.headers.update(_HEADERS_VERSION)

    def _api_url(self, path: str) -> str:
        base = _AUTH_HOST if path.startswith("auth/") else _API_HOST
        return base + path

    _c.RestClient.__init__ = __init__
    _c.RestClient._api_url = _api_url
    _c.RestClient._pa_parcheado = True


if __name__ == "__main__":
    # Chequeo sin red: el parche enruta por prefijo y no se aplica dos veces.
    aplicar()
    from pycocos.components import client as _c
    r = _c.RestClient()
    assert r._api_url("auth/v1/token") == _AUTH_HOST + "auth/v1/token"
    assert r._api_url("api/v1/markets/types") == _API_HOST + "api/v1/markets/types"
    for h in _HEADERS_VERSION:
        assert h in r.session.headers, h
    n = _c.RestClient.__init__
    aplicar()
    assert _c.RestClient.__init__ is n, "doble parche"
    print("ok")
