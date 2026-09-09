"""
mercado.py — Desde qué plaza se mira la cartera.

El núcleo calcula todo en dólares: los precios salen convertidos a USD y las
métricas se apoyan en esa serie. Lo que elige el usuario acá no es un formato de
pantalla, es **la moneda de medición**: un europeo que mide en euros carga
además el movimiento del EURUSD, y su volatilidad, su Sharpe y su beta cambian
con eso. Por eso la conversión pasa por los precios —fecha por fecha, igual que
el MEP— y no por el formateo de los números al final.

Tres plazas, y lo que cada una decide:

    AR  Argentina        USD (por MEP)   Merval      letra EE.UU. 13 semanas
    EU  Europa           EUR             STOXX 600   Bund
    US  Estados Unidos   USD             S&P 500     letra EE.UU. 13 semanas

El benchmark de la tabla es sólo el que abre: la regla de elegir el índice que
mejor explica la cartera (mayor R², ver `capm.comparar_benchmarks`) sigue
mandando apenas termina de medirse.

Argentina es la única que muestra MEP, Conectores y Cocos: son datos de quien
invierte **desde** Argentina, no de quien invierte en activos argentinos.

La plaza viaja en el header `X-Mercado` de cada request y vive en un
`ContextVar`, no en un global: con gunicorn hay varios hilos atendiendo a
usuarios distintos al mismo tiempo. Los modelos corren en un pool aparte, así
que `jobs.lanzar` copia el contexto explícitamente — un `ContextVar` no cruza
solo a un hilo nuevo.
"""

from contextvars import ContextVar

import pandas as pd

PLAZAS = {
    "AR": {"nombre": "Argentina", "moneda": "USD", "simbolo": "US$",
           "benchmark": "MERVAL", "rf": "US", "locales": True},
    "EU": {"nombre": "Europa", "moneda": "EUR", "simbolo": "€",
           "benchmark": "STOXX600", "rf": "EU", "locales": False},
    "US": {"nombre": "Estados Unidos", "moneda": "USD", "simbolo": "US$",
           "benchmark": "SP500", "rf": "US", "locales": False},
}

# Cuántos dólares vale una unidad de la moneda. El euro es la única que se
# convierte: el resto de las plazas europeas —Londres en peniques, Zúrich en
# francos— quedan fuera a propósito.
# ponytail: agregar una moneda es agregar su par acá y nada más.
PAR = {"EUR": "EURUSD=X"}

_actual = ContextVar("mercado", default="AR")


def poner(clave):
    _actual.set(clave if clave in PLAZAS else "AR")


def actual() -> str:
    return _actual.get()


def cfg() -> dict:
    return PLAZAS[actual()]


def moneda() -> str:
    return cfg()["moneda"]


def _par(mon: str) -> pd.Series:
    """Serie del par contra el dólar. Vacía si esa moneda no se convierte."""
    par = PAR.get(mon)
    if not par:
        return pd.Series(dtype=float)
    from core.data import sources
    df = sources.precios(par)
    if df.empty or "Close" not in df.columns:
        return pd.Series(dtype=float)
    return df["Close"].dropna()


def _fx() -> pd.Series:
    """El par de la moneda de medición. Vacía si se mide en dólares."""
    return _par(moneda())


def _alinear(s: pd.Series, fx: pd.Series) -> tuple:
    idx = s.index
    if getattr(idx, "tz", None) is not None:
        s = s.copy()
        s.index = idx.tz_localize(None)
    return s, fx.reindex(s.index, method="ffill")


def a_usd(s: pd.Series, mon: str) -> pd.Series:
    """Una serie en su moneda de cotización, pasada a dólares.

    El paso de entrada al núcleo, que calcula en dólares. Una moneda sin par
    —peniques, francos— vuelve sin tocar: es lo que la app hacía con todo lo que
    no fuera peso, y romper acá dejaría al ticker sin precio en vez de con uno
    aproximado.
    """
    if s is None or s.empty or mon == "USD":
        return s
    fx = _par(mon)
    if fx.empty:
        return s
    s, alineado = _alinear(s, fx)
    return (s * alineado).dropna()


def escalar_a_usd(monto, mon: str, fecha=None):
    """Un importe suelto en su moneda de cotización, en dólares."""
    if monto is None or mon == "USD":
        return monto
    fx = _par(mon)
    if fx.empty:
        return monto
    previos = fx.loc[:pd.Timestamp(fecha)] if fecha is not None else fx
    if not len(previos):
        previos = fx
    return float(monto) * float(previos.iloc[-1])


def desde_usd(s: pd.Series) -> pd.Series:
    """Una serie en dólares, pasada a la moneda de la plaza, fecha por fecha.

    El tipo de cambio se alinea hacia adelante: un feriado del mercado de
    cambios toma el último valor conocido, igual que hace el MEP.
    """
    if s is None or s.empty or moneda() == "USD":
        return s
    fx = _fx()
    if fx.empty:
        return s          # sin par no se inventa una conversión: queda en USD
    s, alineado = _alinear(s, fx)
    return (s / alineado).dropna()


def a_base(monto_usd, fecha=None):
    """Un importe en dólares, en la moneda de la plaza, al cambio de esa fecha.

    Sin fecha usa el último cambio conocido. Es la contracara de `desde_usd`
    para los importes sueltos —el costo de un lote, un saldo— que no vienen en
    una serie.
    """
    if monto_usd is None or moneda() == "USD":
        return monto_usd
    fx = _fx()
    if fx.empty:
        return monto_usd
    if fecha is not None:
        previos = fx.loc[:pd.Timestamp(fecha)]
        if len(previos):
            return float(monto_usd) / float(previos.iloc[-1])
    return float(monto_usd) / float(fx.iloc[-1])
