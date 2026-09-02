"""
mep.py — Dólar MEP: la serie que convierte toda la cartera a dólares.

Es la pieza más crítica del núcleo después de `symbols.py`: cada precio en pesos
se divide por el MEP **de la fecha de ese precio**, nunca por el de hoy. Usar el
MEP de hoy para una compra de 2024 no es una aproximación, es un error de varios
cientos por ciento.

Cascada de fuentes, en orden:
  1. ArgentinaDatos — API pública, serie diaria desde 2020, es la primaria.
  2. Cocos — MEP implícito con AL30/AL30D, si el broker está conectado.
Lo que se descarga se guarda en la caché, así que la app sirve con la serie
guardada aunque las dos fuentes estén caídas.

(yfinance no sirve como respaldo: AL30.BA y AL30D.BA figuran como delistados.)
"""

from datetime import date, timedelta

import pandas as pd
import requests

from core.data import cache

INICIO = "2020-01-01"
_URL_ARGDATOS = "https://api.argentinadatos.com/v1/cotizaciones/dolares/bolsa"

_memoria = {"serie": None, "fuente": None}


# ── Descarga ──────────────────────────────────────────────────────────────────

def _filtrar_outliers(s: pd.Series) -> pd.Series:
    """Descarta valores fuera de ±40 % de la mediana móvil de 30 ruedas.

    Un solo dato malo en el MEP corrompe la valuación de toda la cartera para
    esa fecha, y las APIs públicas publican ceros y saltos de vez en cuando.
    """
    if len(s) < 5:
        return s
    med = s.rolling(30, min_periods=5).median().ffill().bfill()
    return s[(s > med * 0.60) & (s < med * 1.40)]


def _desde_argentinadatos() -> pd.Series:
    r = requests.get(_URL_ARGDATOS, timeout=20,
                     headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    r.raise_for_status()
    datos = r.json()
    if not isinstance(datos, list):
        return pd.Series(dtype=float)
    filas = {}
    for d in datos:
        f, v = d.get("fecha"), d.get("venta") or d.get("compra")
        if f and v and float(v) > 50:
            filas[f] = float(v)
    if not filas:
        return pd.Series(dtype=float)
    s = pd.Series(filas)
    s.index = pd.to_datetime(s.index)
    return _filtrar_outliers(s.sort_index())


def _desde_cocos() -> pd.Series:
    """MEP implícito = precio en pesos del AL30 sobre su tramo en dólares."""
    from core.broker import cocos
    if cocos.cliente() is None:
        return pd.Series(dtype=float)
    ars = cocos.historico("AL30", INICIO)
    usd = cocos.historico("AL30D", INICIO)
    if ars.empty or usd.empty or "Close" not in ars.columns:
        return pd.Series(dtype=float)
    a, u = ars["Close"].dropna(), usd["Close"].dropna()
    mep = (a / u.reindex(a.index, method="ffill")).dropna()
    return _filtrar_outliers(mep[(mep > 50) & (mep < 100_000)])


def sincronizar(forzar: bool = False) -> dict:
    """Trae lo que falta y lo guarda. Devuelve un resumen de lo que hizo."""
    ultima = cache.ultima_fecha_mep()
    hoy = date.today().isoformat()
    if not forzar and ultima and ultima >= (date.today() - timedelta(days=1)).isoformat():
        return {"estado": "al dia", "ultima": ultima, "nuevas": 0}

    for nombre, fn in (("ArgentinaDatos", _desde_argentinadatos),
                       ("Cocos (AL30/AL30D)", _desde_cocos)):
        try:
            s = fn()
        except Exception as e:
            print(f"  [mep] {nombre} falló: {e}")
            continue
        if s is not None and not s.empty:
            n = cache.guardar_mep(s, nombre)
            _memoria["serie"] = None            # invalida el cacheado en memoria
            _memoria["fuente"] = nombre
            return {"estado": "sincronizado", "fuente": nombre,
                    "nuevas": n, "ultima": str(s.index[-1].date()), "hasta": hoy}

    return {"estado": "sin fuentes", "ultima": ultima, "nuevas": 0}


# ── Lectura ───────────────────────────────────────────────────────────────────

def serie() -> pd.Series:
    """La serie completa, cacheada en memoria (se lee muchas veces por request)."""
    if _memoria["serie"] is None:
        _memoria["serie"] = cache.leer_mep()
    return _memoria["serie"]


def fuente() -> str:
    return _memoria["fuente"] or "caché local"


def valor(fecha, mep: pd.Series = None) -> float:
    """MEP de una fecha. Si ese día no cotizó, usa el último anterior.

    Devuelve None si la fecha es previa al inicio de la serie: es preferible un
    None explícito a convertir con un número inventado.
    """
    s = serie() if mep is None else mep
    if s is None or s.empty:
        return None
    ts = pd.Timestamp(fecha)
    previos = s.loc[:ts]
    return float(previos.iloc[-1]) if len(previos) else None


def a_usd(monto_ars: float, fecha, mep: pd.Series = None) -> float:
    """Convierte un monto en pesos usando el MEP de esa fecha exacta."""
    v = valor(fecha, mep)
    if not v or v <= 0:
        return None
    return float(monto_ars) / v


def serie_a_usd(precios_ars: pd.Series, mep: pd.Series = None) -> pd.Series:
    """Convierte una serie de precios en pesos a dólares, fecha por fecha.

    El MEP se alinea hacia adelante: un feriado toma el último valor conocido.
    """
    s = serie() if mep is None else mep
    if s is None or s.empty or precios_ars.empty:
        return pd.Series(dtype=float)
    idx = precios_ars.index
    if getattr(idx, "tz", None) is not None:
        precios_ars = precios_ars.copy()
        precios_ars.index = idx.tz_localize(None)
    alineado = s.reindex(precios_ars.index, method="ffill")
    return (precios_ars / alineado).dropna()
