"""
cocos.py — Cocos Capital: la única fuente de precios de bonos, ONs y letras.

Ningún otro proveedor tiene estos instrumentos: yfinance devuelve vacío o, peor,
otra especie con el mismo nombre. Por eso el ruteo de `core.data.sources` los
manda directo acá sin intentar la cascada.

Dos cosas que hay que tener presentes al leer este módulo:

  1. **Los precios llegan en pesos y cada 100 nominales**, incluso los del tramo
     en dólares. Este módulo devuelve el precio crudo tal como viene; dividir
     por 100 y convertir por MEP es responsabilidad de `sources.precios_base`,
     que es donde está la regla escrita una sola vez.

  2. **El 2FA se pide una sola vez.** Los JWT de la sesión se guardan cifrados
     con la misma API key del vault; mientras sigan vivos, arrancar no pide el
     código del autenticador.
"""

import contextvars
import hashlib
import threading
import time
from datetime import date

import pandas as pd

from core.broker import _cocos_patch, sesion, vault
from core.data import mep

# ── Uno por request, no uno por proceso ───────────────────────────────────────
# El cliente del broker y su estado eran globales de módulo, y estuvo bien
# mientras la app corría en la máquina de su dueño: un proceso, un usuario.
# Servida en la web hay muchos usuarios a la vez en el mismo intérprete, y un
# global le mostraría a uno la sesión de otro. ContextVar da una copia por
# request sin tocar ninguna de las ~30 funciones que los usan.

_LIMPIO = {"conectado": False, "detalle": "sin conectar", "cuenta": None}

_ctx_cliente = contextvars.ContextVar("cocos_cliente", default=None)
_ctx_estado = contextvars.ContextVar("cocos_estado", default=None)

# Y en modo local, uno solo para todo el proceso. Es obligatorio, no una
# comodidad: cada request de Flask corre en su propio contexto, así que un
# ContextVar se vaciaría entre una request y la siguiente y la app de escritorio
# tendría que reconectar el broker en cada clic. En la web eso no molesta porque
# el cliente se arma de nuevo en cada request a partir del sobre, que es
# justamente lo que hace que no queden tokens vivos entre medio.
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


def sesion_muerta() -> bool:
    """¿Alguna llamada de este request se comió un 401 del broker?

    No es lo mismo que un error de Cocos: significa que el token ya no vale y
    hay que volver a autenticarse. Ver `_cocos_patch._marcar`.
    """
    return _cocos_patch.hubo_401()


def cliente():
    return _c()


# ── Conexión ──────────────────────────────────────────────────────────────────

def _clase():
    """La clase de pyCocos, ya parcheada.

    pyCocos 0.2.12 apunta al login viejo con una clave caduca: se repara el
    host, la anon key y los headers de versión antes de instanciar. Ver
    core/broker/_cocos_patch.py.
    """
    from pycocos import Cocos
    _cocos_patch.aplicar()
    return Cocos


def _jwt_actual() -> dict:
    """Los JWT vivos del cliente. Es lo único que sale de este módulo hacia
    afuera: nunca la contraseña, nunca la semilla."""
    return {
        "access_token": _c().access_token,
        "refresh_token": _c().refresh_token,
        "token_expiration": _c().token_expiration,
        "account_number": getattr(_c(), "account_number", ""),
    }


# Los dos constructores de abajo parchean cosas globales —un método de clase y
# `builtins.input`— mientras instancian. Eso no es seguro con hilos: servido a
# varios usuarios, un hilo restauraba el método justo cuando otro todavía no
# había construido su cliente, y el segundo terminaba haciendo el login de
# verdad con las credenciales de relleno. Cocos contestaba "Invalid login
# credentials" y desconectaba a alguien que acababa de conectarse. Pasó de
# verdad el 2026-09-08.
#
# El lock cubre sólo la construcción, que no toca la red: son ~18 ms.
_lock_construir = threading.Lock()


def _restaurar(Cocos, kwargs: dict, sesion: dict):
    """Crea el cliente inyectando los JWT guardados, sin login ni 2FA.

    pycocos autentica dentro del constructor, así que se neutraliza `_auth`
    mientras se instancia y se restaura enseguida. Es intrusivo y hay que
    dejarlo anotado: si pycocos cambia el nombre de ese método, esto deja de
    funcionar y hay que volver al login completo (que igual sigue andando).
    """
    with _lock_construir:
        original = Cocos._auth
        Cocos._auth = lambda self: None
        try:
            c = Cocos(**kwargs)
        finally:
            Cocos._auth = original

    c.access_token = sesion["access_token"]
    c.refresh_token = sesion["refresh_token"]
    c.token_expiration = sesion["token_expiration"]
    c.account_number = sesion.get("account_number", "")
    # apikey vacío, no la anon key: es el estado que deja pyCocos tras el login
    # (_auth_phase_2). Con la anon key acá, los endpoints de cuenta responden
    # 401 "invalid signature" aunque el access_token sea válido.
    c.client.update_session_headers({
        "apikey": "",
        "authorization": f"Bearer {c.access_token}",
        "Content-Type": "application/json",
        "x-account-id": c.account_number,
    })
    return c


def _login(Cocos, kwargs: dict, codigo_2fa: str = ""):
    """Login completo. Resuelve el 2FA con la semilla (si está en kwargs) o con
    un código puntual de 6 dígitos.

    pyCocos pide ese código con `input()` cuando no hay semilla, lo que colgaría
    un servidor web. Se neutraliza `input` con el código provisto sólo durante el
    constructor; es el mismo recurso que usa Terminal Financiera.
    """
    if kwargs.get("topt_secret_key") or not codigo_2fa:
        return Cocos(**kwargs)          # semilla → pyCocos genera el código solo

    import builtins
    with _lock_construir:
        original = builtins.input
        builtins.input = lambda *a, **k: codigo_2fa
        try:
            return Cocos(**kwargs)
        finally:
            builtins.input = original


def conectar(api_key: str, forzar_login: bool = False, codigo_2fa: str = "") -> dict:
    """Conecta al broker. Reusa la sesión guardada si sigue viva.

    El 2FA admite dos formas, y no hacen falta las dos:
      · **semilla** (base32, la que se escanea una vez): pyCocos genera el código
        solo en cada login, guardada en el vault.
      · **código puntual** de 6 dígitos, el que muestra la app en el momento:
        vale ~30 s, no se guarda, se pasa sólo en esta conexión.

    Con cualquiera de las dos, tras el primer login se guarda la sesión y los
    arranques siguientes ya no piden nada hasta que caduque.

    Devuelve el estado; no lanza excepción, porque una caída del broker no debe
    tumbar la aplicación entera — el resto de la cartera se sigue valuando con
    la caché.
    """

    try:
        Cocos = _clase()
    except ImportError:
        _est().update(conectado=False, detalle="falta pycocos")
        return estado()

    try:
        credenciales = vault.abrir(api_key)
    except Exception as e:
        _est().update(conectado=False, detalle=f"vault: {e}")
        return estado()

    kwargs = {"email": credenciales["email"], "password": credenciales["password"],
              "api_key": _cocos_patch.ANON_KEY}
    if credenciales.get("totp_secret_key"):
        # pyotp exige base32 puro (A-Z, 2-7). Las apps muestran la semilla con
        # espacios o guiones y a veces en minúscula: se limpia antes de usarla,
        # o el login corta con "Non-base32 digit found".
        semilla = credenciales["totp_secret_key"].replace(" ", "").replace("-", "").upper()
        kwargs["topt_secret_key"] = semilla   # sic: typo de pycocos

    if not forzar_login:
        sesion = vault.cargar_sesion(api_key)
        if sesion:
            try:
                _poner(_restaurar(Cocos, kwargs, sesion))
                # El access_token dura ~1 h; si venció, se renueva con el
                # refresh_token (que vive mucho más) sin volver a pedir 2FA. Sin
                # esto, reconectar tras una hora daba 401 "jwt expired" en cada
                # llamada de datos aunque el login figurara conectado.
                import time
                if time.time() > sesion.get("token_expiration", 0) - 60:
                    _c().connected = True
                    _c()._refresh_access_token()
                    _guardar_sesion(api_key)
                    detalle = "sesión renovada"
                else:
                    detalle = "sesión restaurada"
                _est().update(conectado=True, detalle=detalle,
                              cuenta=getattr(_c(), "account_number", None))
                return estado()
            except Exception as e:
                print(f"  [cocos] sesión rechazada ({e}); login completo")
                vault.borrar_sesion()

    try:
        _poner(_login(Cocos, kwargs, codigo_2fa))   # acá se resuelve el 2FA
    except Exception as e:
        _est().update(conectado=False, detalle=f"login: {e}")
        return estado()

    _guardar_sesion(api_key)
    _est().update(conectado=True, detalle="login nuevo",
                  cuenta=getattr(_c(), "account_number", None))
    return estado()


def _guardar_sesion(api_key: str):
    """Persiste los JWT vivos del cliente para reconectar sin 2FA."""
    vault.guardar_sesion(api_key, _jwt_actual())


def desconectar():
    _poner(None)
    vault.borrar_sesion()
    _est().update(conectado=False, detalle="desconectado", cuenta=None)


# ── Modo web: sin vault, sin disco ────────────────────────────────────────────
# Las dos funciones de abajo son el camino multiusuario. No leen ni escriben
# `data/vault/`: las credenciales llegan por parámetro, se usan para el login y
# se van con el garbage collector. Lo único que persiste está en el navegador
# del usuario, firmado por `core.broker.sesion`.
#
# El cliente y el estado son por request (ver `_ctx_cliente` arriba), así que
# varios usuarios pueden estar conectados a la vez en el mismo proceso sin
# verse entre ellos.

def login(email: str, password: str, codigo_2fa: str = "") -> tuple:
    """Login con credenciales que no se guardan en ningún lado.

    El 2FA es obligatorio en este camino y tiene que ser el código de 6 dígitos,
    no la semilla: guardar la semilla dejaría al servidor generando códigos solo
    para siempre, y la caducidad diaria del sobre no valdría nada.

    Devuelve (estado, jwt). El `jwt` va firmado al navegador; acá no queda.
    """

    if not (email and password):
        return {**estado(), "detalle": "faltan credenciales"}, None
    try:
        Cocos = _clase()
    except ImportError:
        _est().update(conectado=False, detalle="falta pycocos")
        return estado(), None

    kwargs = {"email": email, "password": password, "api_key": _cocos_patch.ANON_KEY}
    try:
        _poner(_login(Cocos, kwargs, codigo_2fa))
    except Exception as e:
        _est().update(conectado=False, detalle=f"login: {e}")
        return estado(), None

    _est().update(conectado=True, detalle="login nuevo",
                   cuenta=getattr(_c(), "account_number", None))
    return estado(), _jwt_actual()


def restaurar(jwt: dict) -> tuple:
    """Reconstruye el cliente desde los JWT del sobre. Sin login, sin 2FA.

    Se llama en cada request: son ~18 ms de construcción, y a cambio entre
    request y request el proceso no tiene ningún token vivo en memoria.

    Devuelve (estado, jwt_renovado). El segundo es None si no hubo renovación;
    si no lo es, hay que reemitir el sobre y devolvérselo al navegador, **con el
    login_ts del sobre viejo** o el 2FA diario deja de pedirse.
    """
    _cocos_patch.olvidar_401()      # la marca es de este request, no del anterior
    try:
        Cocos = _clase()
    except ImportError:
        _est().update(conectado=False, detalle="falta pycocos")
        return estado(), None

    # email y password no se usan: `_restaurar` neutraliza `_auth` y le inyecta
    # los tokens. Van con valor de relleno sólo porque pyCocos los exige.
    kwargs = {"email": "-", "password": "-", "api_key": _cocos_patch.ANON_KEY}
    try:
        _poner(_restaurar(Cocos, kwargs, jwt))
    except Exception as e:
        _poner(None)
        _est().update(conectado=False, detalle=f"sesión rechazada: {e}", cuenta=None)
        return estado(), None

    renovado = None
    if time.time() > jwt.get("token_expiration", 0) - 60:
        try:
            renovado = _renovar(jwt)
        except Exception as e:
            # El refresh falló, pero el access token puede seguir sirviendo: si
            # todavía no venció, se sigue con él en vez de desconectar a alguien
            # que estaba trabajando. Si tampoco sirve, la llamada al broker dará
            # 401 y ahí sí se le pide reconectar.
            if time.time() > jwt.get("token_expiration", 0):
                _poner(None)
                _est().update(conectado=False, detalle=f"no se pudo renovar: {e}",
                              cuenta=None)
                return estado(), None
            print(f"  [cocos] refresh rechazado, sigo con el token vigente: {e}")

    _est().update(conectado=True, detalle="sesión restaurada",
                   cuenta=getattr(_c(), "account_number", None))
    return estado(), renovado


# ── Renovar una sola vez, no una por request ──────────────────────────────────
# El refresh token de Cocos es de un solo uso: quien renueva lo consume y deja
# inválidos a los demás. Como el navegador dispara varias requests a la vez con
# el mismo sobre, sin esto la primera renovaba y las otras recibían
# "invalid_grant" y desconectaban al usuario recién conectado. Pasó de verdad el
# 2026-09-08.
#
# El que gana renueva; los que pierden esperan el lock y se llevan el mismo
# resultado. La caja se vacía sola a los pocos segundos.
#
#     ponytail: guarda tokens en memoria durante _VIDA_RENOVACION segundos, que
#     es lo único que este proceso retiene entre requests. Si algún día molesta,
#     la alternativa es que el navegador serialice: pedir la renovación por un
#     endpoint aparte y encolar el resto mientras tanto.

_VIDA_RENOVACION = 20
_lock_renovar = threading.Lock()
_renovados = {}


def _aplicar(jwt: dict) -> None:
    """Mete unos JWT en el cliente vivo y arregla sus cabeceras."""
    c = _c()
    c.access_token = jwt["access_token"]
    c.refresh_token = jwt["refresh_token"]
    c.token_expiration = jwt["token_expiration"]
    c.client.update_session_headers({
        "apikey": "", "authorization": f"Bearer {c.access_token}",
        "Content-Type": "application/json",
        "x-account-id": getattr(c, "account_number", ""),
    })


def _renovar(jwt: dict) -> dict:
    clave = hashlib.sha256(jwt["refresh_token"].encode()).hexdigest()[:16]
    with _lock_renovar:
        ahora = time.time()
        for k, (_, t0) in list(_renovados.items()):
            if ahora - t0 > _VIDA_RENOVACION:
                _renovados.pop(k, None)

        hecho = _renovados.get(clave)
        if hecho:
            _aplicar(hecho[0])          # perdió la carrera: usa lo que ya se sacó
            return hecho[0]

        _c().connected = True
        _c()._refresh_access_token()
        nuevo = _jwt_actual()
        _renovados[clave] = (nuevo, ahora)
        return nuevo


def olvidar():
    """Suelta el cliente al terminar el request. No toca el vault."""
    _poner(None)
    _est().update(conectado=False, detalle="sin conectar", cuenta=None)


# ── Precios ───────────────────────────────────────────────────────────────────

_CAMPOS_PRECIO = ("last", "bid", "previous_close", "close", "ask")


def _numero(valor):
    try:
        v = float(valor)
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def precio_snapshot(ticker: str):
    """Último precio conocido, en pesos y cada 100 nominales.

    Orden de preferencia: last → bid → cierre anterior → close → ask.
    `close` va tarde a propósito: durante la rueda y al cierre suele venir vacío
    o en cero, y tomarlo primero devuelve un precio inexistente.
    """
    if _c() is None:
        return None
    from core.data.symbols import base_symbol

    base = base_symbol(ticker)
    try:
        filas = _c().get_instrument_snapshot(base, _c().segments.DEFAULT)
    except Exception:
        return None
    for fila in filas or []:
        if not isinstance(fila, dict):
            continue
        for campo in _CAMPOS_PRECIO:
            v = _numero(fila.get(campo))
            if v is not None:
                return v
    return None


def cotizaciones(tickers: list) -> pd.DataFrame:
    """Snapshot de varios instrumentos. Funciona con el mercado cerrado."""
    if _c() is None:
        return pd.DataFrame()
    filas = []
    for t in tickers:
        try:
            snap = _c().get_instrument_snapshot(t, _c().segments.DEFAULT)
            if snap:
                filas.extend(snap)
        except Exception:
            continue
    if not filas:
        return pd.DataFrame()
    df = pd.DataFrame(filas)
    for c in ("last", "bid", "ask", "open", "high", "low", "close",
              "previous_close", "volume"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.reset_index(drop=True)


def historico(ticker: str, desde: str, hasta: str = None) -> pd.DataFrame:
    """Serie diaria OHLCV, en el formato que espera la caché.

    Devuelve vacío en vez de fallar: si el broker no responde, `sources` cae a
    lo que ya esté guardado.
    """
    if _c() is None:
        return pd.DataFrame()
    from core.data.symbols import base_symbol

    hasta = hasta or date.today().isoformat()
    base = base_symbol(ticker)
    try:
        largo = _c().long_ticker(base, _c().settlements.T2,
                                     _c().currencies.PESOS)
        crudo = _c().get_daily_history(largo, desde)
    except Exception as e:
        print(f"  [cocos] histórico de {ticker}: {e}")
        return pd.DataFrame()

    registros = crudo.get("prices") if isinstance(crudo, dict) else crudo
    if not registros:
        return pd.DataFrame()

    df = pd.DataFrame(registros)
    col_fecha = next((c for c in ("date", "fecha", "datetime") if c in df.columns), None)
    if not col_fecha:
        return pd.DataFrame()
    df.index = pd.to_datetime(df.pop(col_fecha))
    if getattr(df.index, "tz", None) is not None:
        df.index = df.index.tz_localize(None)
    df.columns = [c.capitalize() for c in df.columns]
    for c in ("Open", "High", "Low", "Close", "Volume"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.sort_index().loc[desde:hasta]


# ── Datos personales de la cuenta (solo lectura) ───────────────────────────────
# Envoltorios finos sobre pyCocos: cada uno devuelve los datos crudos del broker
# o {"error": ...}, sin tumbar la app si el endpoint cambió. Se sondean tal cual
# vienen; la interpretación (mapear a la cartera, valuar en USD) se hace arriba.

def _llamar(nombre: str, *args):
    if _c() is None:
        return {"error": "sin conectar"}
    try:
        return getattr(_c(), nombre)(*args)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def _rendimiento(timeframe: str):
    if _c() is None:
        return {"error": "sin conectar"}
    try:
        tf = getattr(_c().performance_timeframes, timeframe, timeframe)
        return _c().portfolio_performance(tf, "", "")
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


# Cocos cotiza los FCI **en pesos y cada 1000 cuotapartes**, incluso los fondos
# cuya cuotaparte es en dólares (esos los pasa a pesos con su propio MEP). Sin
# dividir, la tenencia sale mil veces más grande. Verificado contra los propios
# movimientos del broker: COCOSPPA suscribió 2331,23929815 cuotapartes por
# $3.371 (cuotaparte 1,446012) y el broker informa `average_price` 1446,012.
_FACTOR_FCI = 1000


def _normalizar_fci(pos: list) -> list:
    """Deja los precios de los FCI referidos a UNA cuotaparte.

    `result` ya viene en la escala buena (es cantidad × (last − ppc) / 1000), así
    que se toca sólo el par de precios.
    """
    for p in pos:
        if p.get("instrument_type") != "FCI":
            continue
        for campo in ("last", "average_price"):
            if p.get(campo):
                p[campo] = p[campo] / _FACTOR_FCI
    return pos


def posiciones():
    """Tenencias con precio promedio de compra y resultado total, en pesos.

    Sale de wallet/performance/historic: `my_portfolio()` de pyCocos apunta a un
    endpoint que Cocos dio de baja (404). Devuelve una lista de instrumentos.
    """
    pos = _rendimiento("HISTORICAL")
    return _normalizar_fci(pos) if isinstance(pos, list) else pos


def posiciones_dia():
    """Las mismas tenencias con la variación del día (previo vs. último)."""
    d = _rendimiento("DAILY")
    return d.get("tickers", d) if isinstance(d, dict) else d


# El broker agrupa el detalle por `movementType`; acá se traduce a una categoría
# estable con la que filtrar. Un tipo que no esté en el mapa cae en "Otros" y
# sigue apareciendo: preferible a esconderlo.
_CATEGORIAS = {
    "COCOS_CARD": "Tarjeta",
    "SUBSCRIPTION": "FCI · suscripción",
    "REDEMPTION": "FCI · rescate",
    "BUY": "Compra",
    "SELL": "Venta",
    "DEPOSIT": "Depósito",
    "WITHDRAWAL": "Retiro",
    "DIVIDEND": "Dividendo",
    "OTHERS": "Otros",
}


def _categoria(m: dict) -> str:
    if m.get("side") == "CHARGEBACK":
        return "Reintegro"
    return _CATEGORIAS.get(m.get("movementType"), "Otros")


def _pagina_movimientos(limite: int, offset: int):
    """Una página cruda del endpoint nuevo `api/movements` (sin v1)."""
    if _c() is None:
        return {"error": "sin conectar"}
    try:
        r = _c().client.session.get(
            "https://api.cocos.capital/api/movements",
            params={"limit": limite, "offset": offset}, timeout=25).json()
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
    if isinstance(r, dict) and r.get("success") is False:
        return {"error": r.get("message", "sin datos")}

    lista = []
    for grupo in r.get("data", []):
        fecha = grupo.get("date")
        for m in grupo.get("movements", []):
            lista.append({**m, "fecha": fecha, "categoria": _categoria(m)})
    pag = r.get("pagination", {})
    return {"movimientos": lista, "hay_mas": not pag.get("lastPage", True),
            "offset": pag.get("offset", offset), "limite": pag.get("limit", limite)}


def movimientos(limite: int = 40, offset: int = 0):
    """Movimientos de la cuenta (dinero y operaciones), del más nuevo al más viejo.

    Cocos los entrega agrupados por día; se aplanan a una lista con la fecha y la
    categoría en cada ítem, y se conserva la paginación para pedir más.
    """
    return _pagina_movimientos(limite, offset)


# El barrido de liquidez (COCORMA) genera muchísimos movimientos: se recorre el
# historial hasta este tope para el tracking. Si se corta acá, se avisa arriba.
_TOPE_HISTORIAL = 3000


def _historial_completo():
    """Todos los movimientos hasta el tope, paginando. Lista + flag de corte."""
    todos, offset = [], 0
    while offset < _TOPE_HISTORIAL:
        pag = _pagina_movimientos(200, offset)
        if isinstance(pag, dict) and pag.get("error"):
            return {"error": pag["error"]}
        todos.extend(pag["movimientos"])
        if not pag["hay_mas"] or not pag["movimientos"]:
            return {"movimientos": todos, "cortado": False}
        offset += 200
    return {"movimientos": todos, "cortado": True}


def fci_tracking():
    """Seguimiento por FCI: cuánto suscribiste, cuánto rescataste, qué tenés hoy
    y el resultado que dio.

    Un FCI se detecta por su ticker: cualquiera que aparezca en un movimiento de
    suscripción o rescate. Así, si el broker suma un fondo nuevo, aparece solo.
    Cada FCI queda en su moneda (no se mezclan pesos con dólares).

    resultado = valor de la tenencia hoy + lo rescatado − lo suscrito
    (flujo de caja: lo que sacaste más lo que aún tenés, contra lo que pusiste).
    """
    hist = _historial_completo()
    if hist.get("error"):
        return {"error": hist["error"]}
    movs = hist["movimientos"]

    # Valor actual de cada tenencia, por ticker.
    pos = posiciones()
    tenencia = {}
    if isinstance(pos, list):
        for p in pos:
            t = p.get("short_ticker") or p.get("instrument_code")
            # `last` viene nulo mientras el fondo no publicó la cuotaparte del
            # día (típico de una suscripción de ayer): el PPC es la mejor
            # aproximación disponible y evita valuar la tenencia en cero.
            tenencia[t] = {"cantidad": p.get("quantity"),
                           "ultimo": p.get("last") or p.get("average_price")}

    fondos = {}
    for m in movs:
        tipo = m.get("movementType")
        if tipo not in ("SUBSCRIPTION", "REDEMPTION"):
            continue
        tk = m.get("ticker")
        if not tk:
            continue
        f = fondos.setdefault(tk, {
            "ticker": tk, "moneda": m.get("currency"),
            "suscrito": 0.0, "rescatado": 0.0, "n_susc": 0, "n_resc": 0,
            "desde": m.get("fecha"), "hasta": m.get("fecha")})
        imp = m.get("amount") or 0
        if tipo == "SUBSCRIPTION":
            f["suscrito"] += abs(imp); f["n_susc"] += 1
        else:
            f["rescatado"] += abs(imp); f["n_resc"] += 1
        f["desde"] = min(f["desde"], m.get("fecha"))
        f["hasta"] = max(f["hasta"], m.get("fecha"))

    salida = []
    hoy = date.today()
    for tk, f in fondos.items():
        ten = tenencia.get(tk, {})
        precio = ten.get("ultimo") or 0
        # El broker cotiza en pesos también los fondos en dólares; las
        # suscripciones y rescates de este bloque están en la moneda del fondo,
        # así que el precio tiene que venir a la misma moneda antes de valuar.
        # Se convierte con el MEP de la app, igual que el resto de la cartera.
        # Cocos armó el precio con el suyo, y está bien que así sea: la
        # diferencia entre fuentes (~0,3 %) es una decisión tomada, no una
        # deuda — no cablear `get_dolar_mep_info()` para emparejarlas.
        if precio and f["moneda"] and f["moneda"] != "ARS":
            precio = mep.a_usd(precio, hoy) or 0
        valor = (ten.get("cantidad") or 0) * precio
        resultado = valor + f["rescatado"] - f["suscrito"]
        f.update({
            "cantidad": ten.get("cantidad"),
            "ultimo": precio or None,
            "valor_actual": valor,
            "neto": f["suscrito"] - f["rescatado"],
            "resultado": resultado,
            "resultado_pct": (resultado / f["suscrito"] * 100) if f["suscrito"] else None,
        })
        salida.append(f)

    cerradas = _resultados_realizados(movs)
    for f in salida:
        f["resultado_usd"] = (cerradas["por_fondo"].get(f["ticker"]) or {}).get("pnl")

    salida.sort(key=lambda x: x["valor_actual"], reverse=True)
    return {"fci": salida, "cortado": hist["cortado"], "total_movs": len(movs),
            "trades": cerradas["trades"], "total_usd": cerradas["total_usd"],
            "cuenta": _est().get("cuenta")}


# ── El resultado de los FCI, como operaciones cerradas ────────────────────────
# Suscribir es comprar y rescatar es vender, así que el resultado realizado sale
# del mismo apareo FIFO que usa el importador de CSV: lo que todavía tenés no
# entra, y lo que rescataste entra contra el costo de las cuotapartes más viejas.
#
# Dos cosas que no se pueden saltear:
#
#   1. **Cada movimiento se pasa a dólares con el MEP de SU fecha.** Convertir
#      el neto al MEP de hoy no es una aproximación, es otro número: COCOSPPA da
#      +$217.815 en pesos y −170 dólares, porque las suscripciones se hicieron
#      con un MEP y los rescates con otro bastante más alto. Hasta el signo
#      cambia.
#
#   2. **Sale un registro por fondo, no uno por movimiento.** El barrido diario
#      de COCORMA son 239 rescates de centavos; volcados uno a uno inundan las
#      operaciones cerradas sin decir nada que el total no diga mejor.

LOTE_RESULTADOS_FCI = "cocos-fci"


def _resultados_realizados(movs: list) -> dict:
    """Aparea suscripciones contra rescates y devuelve un cerrado por fondo."""
    from core.io.csv_yahoo import _netear_fifo

    # Los movimientos llegan del más nuevo al más viejo; `orden` tiene que
    # crecer con el tiempo para desempatar bien dos operaciones del mismo día.
    ops = {}
    for orden, m in enumerate(reversed(movs)):
        tipo = m.get("movementType")
        if tipo not in ("SUBSCRIPTION", "REDEMPTION"):
            continue
        tk, fecha = m.get("ticker"), m.get("fecha")
        # En un rescate el broker informa las cuotapartes en negativo. La
        # dirección ya la dice el tipo de movimiento: en signo, acá sólo
        # dejaría precios negativos y un apareo que no cierra nunca.
        cuotapartes = abs((m.get("quantity") or {}).get("executed") or 0)
        importe = abs(m.get("amount") or 0)
        if not tk or not cuotapartes or not importe:
            continue
        usd = (importe if (m.get("currency") or "ARS").upper() != "ARS"
               else mep.a_usd(importe, fecha))
        if not usd:
            continue
        # El precio se saca del importe, no del `price` del movimiento: así da
        # igual en qué escala venga la cuotaparte.
        compras, ventas = ops.setdefault(tk, ([], []))
        (compras if tipo == "SUBSCRIPTION" else ventas).append(
            {"fecha": fecha, "orden": orden, "precio": usd / cuotapartes,
             "qty": cuotapartes, "comision": 0.0})

    trades, por_fondo, total = [], {}, 0.0
    for tk, (compras, ventas) in ops.items():
        if not ventas:
            continue
        _, cerrados = _netear_fifo(compras, ventas)
        if not cerrados:
            continue
        costo = sum(c["qty"] * c["buy_price"] for c in cerrados)
        ingreso = sum(c["qty"] * c["sell_price"] for c in cerrados)
        pnl = ingreso - costo
        # Cantidad 1 y los importes como precios: el registro representa el
        # resultado del fondo, no una cuotaparte. `moneda` va explícita porque
        # acá ya está convertido y nadie tiene que volver a convertirlo.
        trades.append({
            "ticker": tk,
            "buy_date": min(c["buy_date"] for c in cerrados),
            "sell_date": max(c["sell_date"] for c in cerrados),
            "buy_price": round(costo, 4), "sell_price": round(ingreso, 4),
            "qty": 1, "buy_comm": 0.0, "sell_comm": 0.0,
            "moneda": "USD", "pnl": round(pnl, 4), "n_ops": len(cerrados),
            # Marca lo que este registro es: un resultado agregado, no una
            # operación. La evolución mira esto para no leer el saldo de dos
            # años de barrido como un aporte y un retiro de golpe.
            "tipo": "fci",
        })
        por_fondo[tk] = {"pnl": round(pnl, 4), "n_ops": len(cerrados)}
        total += pnl

    trades.sort(key=lambda t: t["pnl"], reverse=True)
    return {"trades": trades, "por_fondo": por_fondo, "total_usd": round(total, 4)}


# ── Participaciones en FCI, como lotes de cartera ─────────────────────────────

def precio_fci(ticker: str):
    """Última cuotaparte de un FCI, en pesos (que es como la informa Cocos).

    Es la de T-1: los fondos se valúan al cierre anterior. Quien la fecha es
    `sources._fci_usd`, y la fecha importa porque define con qué MEP se convierte.

    None si no hay posición en ese fondo o el broker no publicó precio: la
    posición sale marcada «sin precio», que es mejor que valuarla mal.
    """
    pos = posiciones()
    if not isinstance(pos, list):
        return None
    t = ticker.upper().strip()
    for p in pos:
        if (p.get("short_ticker") or p.get("instrument_code")) == t:
            return p.get("last") or p.get("average_price")
    return None


def tenencias_fci():
    """Las participaciones en FCI de la cuenta, como lotes listos para importar.

    Una tenencia de FCI es una foto —cuotapartes y precio promedio de compra—,
    no un historial de suscripciones. Alcanza para la posición y el resultado,
    que es lo único que se le pide.

    La moneda sale de los movimientos del fondo: las posiciones vienen todas en
    pesos y ahí el broker no la dice. Un fondo en dólares se guarda con su PPC
    en dólares, si no el resultado mezcla el movimiento del tipo de cambio con
    el del fondo.
    """
    from core.data.symbols import SOURCE_FCI

    pos = posiciones()
    if not isinstance(pos, list):
        return {"error": (pos or {}).get("error", "sin datos")}
    seguimiento = fci_tracking()
    if seguimiento.get("error"):
        return seguimiento
    fondos = {f["ticker"]: f for f in seguimiento["fci"]}

    lotes = []
    for p in pos:
        if p.get("instrument_type") != "FCI":
            continue
        tk = p.get("short_ticker") or p.get("instrument_code")
        cantidad, ppc = p.get("quantity"), p.get("average_price")
        if not cantidad or not ppc:
            continue
        f = fondos.get(tk, {})
        moneda = (f.get("moneda") or "ARS").upper()
        fecha = f.get("hasta") or date.today().isoformat()
        precio = ppc if moneda == "ARS" else mep.a_usd(ppc, fecha)
        if not precio:
            continue
        lotes.append({
            "ticker": tk, "buy_date": fecha, "buy_price": round(precio, 6),
            "qty": cantidad, "commissions": 0.0, "source": SOURCE_FCI,
            "currency": moneda, "asset_type": "FCI",
            "notes": p.get("instrument_short_name") or "",
        })
    return {"lotes": lotes, "cuenta": _est().get("cuenta")}


def fondos_disponibles():
    return _llamar("funds_available")


def mis_datos():
    return _llamar("my_data")


def cuentas_bancarias():
    return _llamar("my_bank_accounts")
