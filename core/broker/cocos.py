"""
cocos.py — Cocos Capital: la única fuente de precios de bonos, ONs y letras.

Ningún otro proveedor tiene estos instrumentos: yfinance devuelve vacío o, peor,
otra especie con el mismo nombre. Por eso el ruteo de `core.data.sources` los
manda directo acá sin intentar la cascada.

Dos cosas que hay que tener presentes al leer este módulo:

  1. **Los precios llegan en pesos y cada 100 nominales**, incluso los del tramo
     en dólares. Este módulo devuelve el precio crudo tal como viene; dividir
     por 100 y convertir por MEP es responsabilidad de `sources.precios_usd`,
     que es donde está la regla escrita una sola vez.

  2. **El 2FA se pide una sola vez.** Los JWT de la sesión se guardan cifrados
     con la misma API key del vault; mientras sigan vivos, arrancar no pide el
     código del autenticador.
"""

from datetime import date

import pandas as pd

from core.broker import _cocos_patch, vault

_cliente = None
_estado = {"conectado": False, "detalle": "sin conectar", "cuenta": None}


def estado() -> dict:
    return dict(_estado)


def cliente():
    return _cliente


# ── Conexión ──────────────────────────────────────────────────────────────────

def _restaurar(Cocos, kwargs: dict, sesion: dict):
    """Crea el cliente inyectando los JWT guardados, sin login ni 2FA.

    pycocos autentica dentro del constructor, así que se neutraliza `_auth`
    mientras se instancia y se restaura enseguida. Es intrusivo y hay que
    dejarlo anotado: si pycocos cambia el nombre de ese método, esto deja de
    funcionar y hay que volver al login completo (que igual sigue andando).
    """
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
    global _cliente

    try:
        from pycocos import Cocos
    except ImportError:
        _estado.update(conectado=False, detalle="falta pycocos")
        return estado()

    # pyCocos 0.2.12 apunta al login viejo con una clave caduca: se repara el
    # host, la anon key y los headers de versión antes de instanciar. Ver
    # core/broker/_cocos_patch.py.
    _cocos_patch.aplicar()

    try:
        credenciales = vault.abrir(api_key)
    except Exception as e:
        _estado.update(conectado=False, detalle=f"vault: {e}")
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
                _cliente = _restaurar(Cocos, kwargs, sesion)
                _estado.update(conectado=True, detalle="sesión restaurada",
                               cuenta=getattr(_cliente, "account_number", None))
                return estado()
            except Exception as e:
                print(f"  [cocos] sesión rechazada ({e}); login completo")
                vault.borrar_sesion()

    try:
        _cliente = _login(Cocos, kwargs, codigo_2fa)   # acá se resuelve el 2FA
    except Exception as e:
        _estado.update(conectado=False, detalle=f"login: {e}")
        return estado()

    vault.guardar_sesion(api_key, {
        "access_token": _cliente.access_token,
        "refresh_token": _cliente.refresh_token,
        "token_expiration": _cliente.token_expiration,
        "account_number": getattr(_cliente, "account_number", ""),
    })
    _estado.update(conectado=True, detalle="login nuevo",
                   cuenta=getattr(_cliente, "account_number", None))
    return estado()


def desconectar():
    global _cliente
    _cliente = None
    vault.borrar_sesion()
    _estado.update(conectado=False, detalle="desconectado", cuenta=None)


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
    if _cliente is None:
        return None
    from core.data.symbols import base_symbol

    base = base_symbol(ticker)
    try:
        filas = _cliente.get_instrument_snapshot(base, _cliente.segments.DEFAULT)
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
    if _cliente is None:
        return pd.DataFrame()
    filas = []
    for t in tickers:
        try:
            snap = _cliente.get_instrument_snapshot(t, _cliente.segments.DEFAULT)
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
    if _cliente is None:
        return pd.DataFrame()
    from core.data.symbols import base_symbol

    hasta = hasta or date.today().isoformat()
    base = base_symbol(ticker)
    try:
        largo = _cliente.long_ticker(base, _cliente.settlements.T2,
                                     _cliente.currencies.PESOS)
        crudo = _cliente.get_daily_history(largo, desde)
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
    if _cliente is None:
        return {"error": "sin conectar"}
    try:
        return getattr(_cliente, nombre)(*args)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def _rendimiento(timeframe: str):
    if _cliente is None:
        return {"error": "sin conectar"}
    try:
        tf = getattr(_cliente.performance_timeframes, timeframe, timeframe)
        return _cliente.portfolio_performance(tf, "", "")
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def posiciones():
    """Tenencias con precio promedio de compra y resultado total, en pesos.

    Sale de wallet/performance/historic: `my_portfolio()` de pyCocos apunta a un
    endpoint que Cocos dio de baja (404). Devuelve una lista de instrumentos.
    """
    return _rendimiento("HISTORICAL")


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
    if _cliente is None:
        return {"error": "sin conectar"}
    try:
        r = _cliente.client.session.get(
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
            tenencia[t] = {"cantidad": p.get("quantity"),
                           "valor": (p.get("quantity") or 0) * (p.get("last") or 0),
                           "ultimo": p.get("last")}

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
    for tk, f in fondos.items():
        ten = tenencia.get(tk, {})
        valor = ten.get("valor", 0) or 0
        resultado = valor + f["rescatado"] - f["suscrito"]
        f.update({
            "cantidad": ten.get("cantidad"),
            "ultimo": ten.get("ultimo"),
            "valor_actual": valor,
            "neto": f["suscrito"] - f["rescatado"],
            "resultado": resultado,
            "resultado_pct": (resultado / f["suscrito"] * 100) if f["suscrito"] else None,
        })
        salida.append(f)

    salida.sort(key=lambda x: x["valor_actual"], reverse=True)
    return {"fci": salida, "cortado": hist["cortado"], "total_movs": len(movs)}


def fondos_disponibles():
    return _llamar("funds_available")


def mis_datos():
    return _llamar("my_data")


def cuentas_bancarias():
    return _llamar("my_bank_accounts")
