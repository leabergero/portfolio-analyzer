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

from core.broker import vault

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
    c.client.update_session_headers({
        "apikey": c.api_key,
        "authorization": f"Bearer {c.access_token}",
        "Content-Type": "application/json",
        "x-account-id": c.account_number,
    })
    return c


def conectar(api_key: str, forzar_login: bool = False) -> dict:
    """Conecta al broker. Reusa la sesión guardada si sigue viva.

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

    try:
        credenciales = vault.abrir(api_key)
    except Exception as e:
        _estado.update(conectado=False, detalle=f"vault: {e}")
        return estado()

    kwargs = {"email": credenciales["email"], "password": credenciales["password"]}
    if credenciales.get("totp_secret_key"):
        kwargs["topt_secret_key"] = credenciales["totp_secret_key"]   # sic: typo de pycocos

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
        _cliente = Cocos(**kwargs)          # acá puede pedir el código 2FA
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
