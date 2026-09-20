"""
inviu.py — InvIU: bonos, CEDEARs, cauciones y la cuenta completa con gestión
discrecional. Fuente probada contra una cuenta real, no adivinada de un
bundle JS (ver `inviu-integration/` en la raíz del repo para el detalle de
cómo se descubrió cada endpoint).

Dos cosas hay que tener presentes al leer este módulo:

  1. **El login no se puede hacer con `requests` solo.** El primer paso exige
     un `g-recaptcha-response` de Google reCAPTCHA v3, que solo se genera
     ejecutando el JS real de Google en un navegador de verdad. Por eso
     `conectar()` abre un Chrome real (Playwright) la primera vez, pero solo
     para el login — una vez adentro, el resto de este módulo es `requests`
     puro con el `idToken`/`refreshToken` que salen de esa sesión.

  2. **Cloudflare, no el token, es la causa más común de un 403.** La API está
     detrás de un WAF que bloquea el user-agent por defecto de `requests`
     antes de mirar el `Authorization`. `_headers()` ya manda lo necesario
     para pasarlo; si un endpoint nuevo empieza a devolver 403 con un token
     que se sabe válido, revisar los headers antes que el token.

Este módulo devuelve los datos crudos del broker, como ya hace `cocos.py`: la
interpretación (qué pata de una renta es plata real, cómo separar cauciones
de compra/venta) se hace en el importador, no acá — ver
`inviu-integration/MAPEO_A_PORTFOLIO.md`.
"""

import contextvars
import threading
import time

import requests

from core.broker import sesion, vault

BASE_API_URL = "https://inviuxy.inviu.com.ar/investor"
LOGIN_URL = "https://inversor.inviu.com.ar/login"
BROKER = "inviu"

# Marca de importación, igual que `cocos.LOTE_OPERACIONES` — permite
# reemplazar solo lo que trajo esta fuente sin tocar lo cargado a mano.
LOTE_OPERACIONES = "inviu-ops"
LOTE_RENTAS = "inviu-rentas"
LOTE_CAUCION = "inviu-caucion"


def clave_operacion(x: dict) -> str:
    """Identifica una fila del preview sin mandar sus números de ida y vuelta.
    Igual que `cocos.clave_operacion`."""
    return "|".join(str(x.get(c, "")) for c in
                    ("ticker", "buy_date", "sell_date", "qty"))

# El idToken dura ~5 minutos (visto en el `exp` del JWT); el refreshToken
# parece durar mucho más (patrón Cognito estándar), así que la reconexión de
# todos los días pasa por `refresh()`, no por abrir el navegador de nuevo.

_LIMPIO = {"conectado": False, "detalle": "sin conectar", "cuenta": None}

_ctx_cliente = contextvars.ContextVar("inviu_cliente", default=None)
_ctx_estado = contextvars.ContextVar("inviu_estado", default=None)
_local = {"cliente": None, "estado": dict(_LIMPIO)}


def _c():
    return _ctx_cliente.get() if sesion.modo_web() else _local["cliente"]


def _poner(cliente) -> None:
    if sesion.modo_web():
        _ctx_cliente.set(cliente)
    else:
        _local["cliente"] = cliente


def _est() -> dict:
    if not sesion.modo_web():
        return _local["estado"]
    e = _ctx_estado.get()
    if e is None:
        e = dict(_LIMPIO)
        _ctx_estado.set(e)
    return e


def estado() -> dict:
    return dict(_est())


# ── El cliente: tokens + cuenta, nada de sesión de navegador ──────────────────
# A diferencia de Cocos (que guarda el objeto de pyCocos), acá no hay nada que
# mantener vivo entre requests salvo un dict con los tokens: todo lo demás es
# un GET/POST de `requests`.

class _Cliente:
    def __init__(self, id_token, refresh_token, account_id=None, client_id=None):
        self.id_token = id_token
        self.refresh_token = refresh_token
        self.account_id = account_id
        self.client_id = client_id
        self.session = requests.Session()

    def jwt(self) -> dict:
        return {"idToken": self.id_token, "refreshToken": self.refresh_token}


def _headers(id_token: str) -> dict:
    # Cloudflare delante de la API devuelve 403 ("Just a moment...") al
    # user-agent por defecto de `requests`, sin mirar siquiera el token. Con
    # un user-agent de navegador y el origin/referer reales, pasa. Confirmado
    # contra la cuenta real: sin esto, TODOS los endpoints de acá abajo caen.
    return {
        "Authorization": f"Bearer {id_token}",
        "Content-Type": "application/json", "Accept": "application/json",
        "X-Platform": "web", "X-Client-Version": "1.0.0",
        "Origin": "https://inversor.inviu.com.ar",
        "Referer": "https://inversor.inviu.com.ar/",
        "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
    }


def _get(ruta: str, **params):
    """Envoltorio fino: devuelve el JSON crudo o `{"error": ...}`, nunca tumba
    la app. Igual que `cocos._llamar`.

    El idToken dura ~5 minutos —se ve larga la sesión porque `conectar()`
    refresca al arrancar, pero cualquier pantalla abierta más que eso pega
    con un token vencido—. Un 401 dispara un `refresh()` y un solo reintento;
    si el refresh también falla (el refreshToken venció de verdad), se
    devuelve el error tal cual para que se note que hace falta reconectar.
    """
    c = _c()
    if c is None:
        return {"error": "sin conectar"}
    try:
        r = c.session.get(f"{BASE_API_URL}{ruta}", headers=_headers(c.id_token),
                           params=params or None, timeout=15)
        if r.status_code == 401:
            if "error" in (refresh() or {}):
                r.raise_for_status()
            r = c.session.get(f"{BASE_API_URL}{ruta}", headers=_headers(c.id_token),
                               params=params or None, timeout=15)
        r.raise_for_status()
        return r.json() if r.content else None
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def _post(ruta: str, body: dict, id_token: str = None):
    c = _c()
    token = id_token if id_token is not None else (c.id_token if c else None)
    try:
        r = requests.post(f"{BASE_API_URL}{ruta}", headers=_headers(token),
                           json=body, timeout=15)
        r.raise_for_status()
        return r.json() if r.content else None
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


# ── Login (necesita navegador) ────────────────────────────────────────────────

def _login_navegador(timeout_segundos: int = 300) -> dict:
    """Abre un Chrome real, deja que el usuario se loguee a mano (contraseña +
    el código que le llega por mail) y devuelve los tokens que quedan en el
    `localStorage` al terminar.

    Por qué a mano y no tipeando nosotros el formulario: el primer paso exige
    un reCAPTCHA v3 válido, que un navegador de verdad resuelve solo con la
    interacción real del usuario — automatizar el tipeo no cambia eso, solo
    agrega selectores frágiles para ahorrar diez segundos. Ver
    `inviu-integration/lab_server.py` si en algún momento hace falta esa
    versión (ahí está probada, con sus selectores y sus riesgos anotados).
    """
    import json
    from playwright.sync_api import sync_playwright

    def _tokens_en(page):
        pares = page.evaluate(
            "() => Object.entries(localStorage)"
            ".filter(([k]) => /token/i.test(k))"
        )
        for _, valor in pares:
            try:
                datos = json.loads(valor)
            except (TypeError, ValueError):
                continue
            if isinstance(datos, dict) and "idToken" in datos and "refreshToken" in datos:
                return datos
        return None

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(LOGIN_URL)

        # Se espera a que aparezcan los tokens en el localStorage, no a que
        # cambie la URL: la SPA pasa por un par de redirects transitorios al
        # cargar (incluso sin loguearse) que salen de "/login" un instante y
        # vuelven — mirar la URL corta el login antes de que el usuario
        # llegue a tipear nada.
        limite = time.time() + timeout_segundos
        tokens = None
        while time.time() < limite:
            tokens = _tokens_en(page)
            if tokens:
                break
            page.wait_for_timeout(1000)
        browser.close()

    if not tokens:
        raise TimeoutError("no se completó el login a tiempo")
    return tokens


def refresh() -> dict:
    """POST /auth/refresh — inferido del JS de la app, no capturado en vivo
    todavía (el idToken de la sesión de prueba no llegó a vencer dentro de la
    ventana de captura). Si esto empieza a fallar con 400/422, es lo primero
    a re-verificar contra tráfico real."""
    c = _c()
    if c is None:
        return {"error": "sin conectar"}
    datos = _post("/auth/refresh", c.jwt())
    if "error" in (datos or {}):
        return datos
    c.id_token = datos["idToken"]
    c.refresh_token = datos.get("refreshToken", c.refresh_token)
    return datos


def _cargar_cuenta(c: "_Cliente") -> dict:
    info = _get("/user/info")
    if "error" in (info or {}):
        return info
    c.account_id = info["accounts"][0]["id"]
    c.client_id = info["accounts"][0]["userId"]
    return info


def _intentar_refresh(api_key: str) -> bool:
    """La sesión guardada sirve para reconectar sin navegador. `True` si
    quedó conectado."""
    sesion_guardada = vault.cargar_sesion(api_key, BROKER)
    if not sesion_guardada:
        return False
    c = _Cliente(sesion_guardada["idToken"], sesion_guardada["refreshToken"])
    _poner(c)
    r = refresh()
    if "error" not in (r or {}):
        info = _cargar_cuenta(c)
        if "error" not in (info or {}):
            vault.guardar_sesion(api_key, c.jwt(), BROKER)
            _est().update(conectado=True, detalle="sesión renovada",
                          cuenta=c.account_id)
            return True
    _poner(None)
    return False


def _completar_login(api_key: str):
    """La parte que abre el navegador. Bloquea hasta 5 minutos — quien la
    llama decide si eso corre en este hilo (`conectar`) o en uno aparte
    (`conectar_async`, para no colgar un request de la API)."""
    try:
        tokens = _login_navegador()
    except Exception as e:
        _est().update(conectado=False, detalle=f"login: {e}")
        return

    c = _Cliente(tokens["idToken"], tokens["refreshToken"])
    _poner(c)
    info = _cargar_cuenta(c)
    if "error" in (info or {}):
        _poner(None)
        _est().update(conectado=False, detalle=f"login ok pero {info['error']}")
        return

    vault.guardar_sesion(api_key, c.jwt(), BROKER)
    _est().update(conectado=True, detalle="login nuevo", cuenta=c.account_id)


def conectar(api_key: str, forzar_login: bool = False) -> dict:
    """Reusa la sesión guardada si el refresh todavía sirve; si no, abre el
    navegador y **bloquea** hasta que el usuario termine (o hasta 5 minutos).
    Para un caller que no puede quedarse colgado (un endpoint HTTP), usar
    `conectar_async`. Nunca lanza excepción — un login que falla no debe
    tumbar la app, igual que en `cocos.conectar`."""
    if forzar_login or not _intentar_refresh(api_key):
        _completar_login(api_key)
    return estado()


_lock_login_async = threading.Lock()
_login_en_curso = False


def conectar_async(api_key: str, forzar_login: bool = False) -> dict:
    """Como `conectar`, pero si hace falta navegador lo abre en un hilo
    aparte y devuelve al toque. El caller sondea `estado()` (ver
    `login_en_curso()`) hasta que `conectado` se resuelva en `True`/`False`."""
    global _login_en_curso
    if not forzar_login and _intentar_refresh(api_key):
        return estado()

    with _lock_login_async:
        if not _login_en_curso:
            _login_en_curso = True
            _est().update(conectado=False, detalle="esperando login en el navegador")

            def _correr():
                global _login_en_curso
                try:
                    _completar_login(api_key)
                finally:
                    _login_en_curso = False

            threading.Thread(target=_correr, daemon=True).start()
    return estado()


def login_en_curso() -> bool:
    return _login_en_curso


def desconectar():
    _poner(None)
    vault.borrar_sesion(BROKER)
    _est().update(conectado=False, detalle="desconectado", cuenta=None)


# ── Datos de cuenta (solo lectura) — todo lo que se puede ver ─────────────────
# Uno por endpoint confirmado en `inviu-integration/DATOS_DISPONIBLES.md`.
# `account_id`/`client_id` los completa `_cargar_cuenta` al conectar.

def user_info() -> dict:
    return _get("/user/info")


def cartera(plazo: str = "24HS") -> dict:
    """Posiciones abiertas: tenencias, PPC en ARS y en USD por separado, P&L,
    patrimonio total por categoría. `plazo`: 0HS/24HS/48HS."""
    c = _c()
    if c is None or not c.account_id:
        return {"error": "sin conectar"}
    return _get(f"/managed-portfolio/v4/account/{c.account_id}", term=plazo)


def operaciones() -> list:
    """Historial de órdenes: status (FILLED/CANCELLED/...), cantidad pedida vs
    ejecutada, canal. Incluye cauciones — no son compra/venta de un ticker,
    hay que separarlas al importar (ver MAPEO_A_PORTFOLIO.md)."""
    c = _c()
    if c is None or not c.account_id:
        return {"error": "sin conectar"}
    return _get(f"/investor/accounts/{c.account_id}/operations")


def movimientos() -> dict:
    """Asientos de cartera con saldo acumulado después de cada uno. También
    trae depósitos/retiros (CASH_IN/CASH_OUT), amortizaciones y rentas."""
    c = _c()
    if c is None or not c.account_id:
        return {"error": "sin conectar"}
    return _get(f"/clients/{c.client_id}/account/{c.account_id}/movements")


def movimientos_efectivo() -> dict:
    c = _c()
    if c is None or not c.account_id:
        return {"error": "sin conectar"}
    return _get("/investor/cash-movements", accountId=c.account_id)


def performance() -> list:
    c = _c()
    if c is None or not c.account_id:
        return {"error": "sin conectar"}
    return _get(f"/account/{c.account_id}/performance",
                custodian="CVAL", clientId=c.client_id)


def evolucion_patrimonio(desde: str, hasta: str, moneda: str = "USD") -> dict:
    """Serie diaria de AUM, flujos in/out separados de la ganancia, y TIR ya
    calculada por InvIU — evaluar usar esto antes de recalcular rendimiento a
    mano como se hace para Cocos. Fechas ISO (`AAAA-MM-DD`)."""
    c = _c()
    if c is None or not c.account_id:
        return {"error": "sin conectar"}
    return _get(f"/performance/aum-evolution/account/{c.account_id}",
                **{"from": desde, "to": hasta, "custodian": "cval",
                   "clientId": c.client_id, "currency": moneda})


def flujo_proyectado() -> dict:
    """Próximos pagos de los bonos en cartera, más duration modificada,
    convexidad, DV01 y TIR por moneda."""
    c = _c()
    if c is None or not c.account_id:
        return {"error": "sin conectar"}
    return _get(f"/account/{c.account_id}/projected-cashflows/v2",
                clientId=c.client_id)


def poder_compra() -> dict:
    c = _c()
    if c is None or not c.account_id:
        return {"error": "sin conectar"}
    return _get(f"/account/{c.account_id}/buying-power")


def balances() -> dict:
    """Disponible, poder de compra y capacidad de caución, por plazo de
    liquidación y moneda."""
    c = _c()
    if c is None or not c.account_id:
        return {"error": "sin conectar"}
    return _get(f"/account/{c.account_id}/balances", clientId=c.client_id)


def account_details() -> list:
    c = _c()
    if c is None or not c.account_id:
        return {"error": "sin conectar"}
    return _get(f"/{c.client_id}/account-details-v2/{c.account_id}")


def productos(mercado: str = "BYMA", limite: int = 5000) -> dict:
    """Catálogo de instrumentos operables: ticker, ISIN, tipo, moneda."""
    return _get(f"/products/v3/{mercado}", limit=limite)


def settings() -> dict:
    return _get("/settings")


def notifications() -> dict:
    return _get("/notifications")


def demo():
    """Self-check sin red: session state y armado de headers. No hay
    credenciales ni tokens reales acá."""
    assert estado() == _LIMPIO
    h = _headers("fake-token")
    assert h["Authorization"] == "Bearer fake-token"
    assert h["Origin"] == "https://inversor.inviu.com.ar"

    c = _Cliente("id", "refresh", account_id="acc-1", client_id="cli-1")
    assert c.jwt() == {"idToken": "id", "refreshToken": "refresh"}

    # Sin cliente conectado, cada función corta antes de tocar la red.
    assert cartera().get("error") == "sin conectar"
    assert operaciones().get("error") == "sin conectar"
    assert movimientos().get("error") == "sin conectar"
    print("ok")


if __name__ == "__main__":
    demo()
