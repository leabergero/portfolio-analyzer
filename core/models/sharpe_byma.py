"""
sharpe_byma.py — Sharpe y liquidez de las acciones y CEDEARs de BYMA.

Es un buscador de papeles, no un modelo de la cartera: recorre ~680 especies y
baja una serie por cada una, algo que la VM no aguanta en un request. Por eso se
calcula de noche (`python -m core.models.sharpe_byma`, timer de systemd) y la
web sólo lee el JSON que deja.

Una especie por papel, la de pesos, medida en dólares MEP del último año con la
tasa libre de 4 %. El volumen es el promedio diario en dólares —acciones ×
cierre ÷ MEP—: las acciones operadas solas no comparan papeles de precios
distintos. La beta, contra el mercado de cada papel: una acción argentina
contra el Merval en dólares MEP, un CEDEAR contra el S&P 500 (SPY); el alfa
es lo que rindió por encima de lo que esa beta explica, anualizado.

De paso deja el diccionario de especies de BYMA (`symbols.ESPECIES`): ya
tiene los paneles en la mano y es la misma rueda de todos los días.
"""

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np

from core.data import sources, symbols
from core.models import risk

SALIDA = Path(__file__).resolve().parents[2] / "data" / "sharpe_byma.json"
RF = 0.04
MIN_RUEDAS = 60
# Un CEDEAR que cambia de ratio sin que la serie lo ajuste salta así en un día
# (MRNA +175 % el 2026-08-19). No se descarta: se marca, para no creerle el Sharpe.
SALTO = 0.40


def universo() -> dict:
    """{símbolo: "accion" | "cedear"}, sólo la especie en pesos. Guarda además
    el diccionario de especies (todas las monedas) para `symbols`."""
    import pandas as pd
    from pyobd import BymaData
    b = BymaData()
    # BYMA liquida a 24 h desde 2024; el default de la librería (48 h) da vacío.
    df = pd.concat([b.get_bluechips(settlement_t2=False, settlement_t1=True),
                    b.get_general_board(settlement_t2=False, settlement_t1=True),
                    b.get_cedears()])
    if df.empty:
        return {}
    especies = {s: {"moneda": m, "tipo": t}
                for s, m, t in zip(df.symbol, df.denominationCcy, df.securityType)
                if m in ("ARS", "USD", "EXT") and t in ("CD", "CS")}
    # Un panel que vino a medias (BYMA a veces devuelve vacío fuera de hora) no
    # pisa al de ayer: un diccionario corto haría volver a la regla de la D.
    if len(especies) >= 0.8 * len(symbols.especies()):
        # Acumula: lo que BYMA deja de listar (vendido, vencido, deslistado)
        # conserva su moneda y no vuelve a la regla de la D.
        tmp = symbols.ESPECIES.with_suffix(".tmp")
        tmp.write_text(json.dumps({**symbols.especies(), **especies}, sort_keys=True))
        tmp.replace(symbols.ESPECIES)
    return {s: "accion" if e["tipo"] == "CS" else "cedear"
            for s, e in especies.items() if e["moneda"] == "ARS"}


def _mercados(desde: str) -> dict:
    """{tipo: retornos diarios del mercado contra el que se mide la beta}."""
    from core.models.montecarlo import _indice
    return {"accion": _indice("^MERV").loc[desde:].pct_change().dropna(),
            "cedear": sources.precios_base("SPY", desde).pct_change().dropna()}


def _beta_alfa(r, m):
    """(β, α anual %) sobre las ruedas en común; None sin un semestre en común."""
    x, y = r.align(m, join="inner")
    if len(x) < 120 or y.var() == 0:
        return None, None
    beta = float(np.cov(x, y)[0, 1] / y.var())
    rf = RF / 252
    alfa = ((x.mean() - rf) - beta * (y.mean() - rf)) * 252 * 100
    return round(beta, 2), round(float(alfa), 1)


def _fila(sym: str, tipo: str, desde: str, mercados: dict):
    t = f"{sym}.BA"
    try:
        crudo = sources.precios(t, desde)
        usd = sources.precios_base(t, desde)
    except Exception:
        return None
    if crudo.empty or len(usd) < MIN_RUEDAS:
        return None
    vol = crudo["Volume"].reindex(usd.index).fillna(0)
    r = usd.pct_change().dropna()
    r = r[np.isfinite(r)]
    beta, alfa = _beta_alfa(r, mercados[tipo])
    # El nombre de un CEDEAR es el de la empresa en EE.UU.: la ficha del .BA
    # suele faltar en yfinance. La ficha queda en caché una semana.
    ficha = sources.info(symbols.CEDEAR_EEUU.get(sym, sym) if tipo == "cedear" else t) or {}
    if not (ficha.get("longName") or ficha.get("shortName")):
        ficha = sources.info(t) or {}          # PETR3, BAYN: no hay símbolo igual en EE.UU.
    return {"ticker": t, "tipo": tipo, "ruedas": len(usd), "beta": beta, "alfa_pct": alfa,
            "nombre": ficha.get("longName") or ficha.get("shortName") or "",
            "sharpe": round(risk.sharpe(r.values, RF), 2),
            "retorno_pct": round(((usd.iloc[-1] / usd.iloc[0]) ** (252 / len(usd)) - 1) * 100, 1),
            "vol_pct": round(float(r.std() * np.sqrt(252)) * 100, 1),
            "volumen_usd": round(float((vol * usd).mean())),
            "sin_operar_pct": round(float((vol == 0).mean()) * 100, 1),
            "salto": bool((r.abs() > SALTO).any())}


def calcular(hilos: int = 2) -> dict:
    import contextvars
    desde = (date.today() - timedelta(days=365)).isoformat()
    papeles = universo()
    mercados = _mercados(desde)
    ctx = contextvars.copy_context()
    with ThreadPoolExecutor(hilos) as ex:
        filas = [f for f in ex.map(lambda x: ctx.copy().run(_fila, *x, desde, mercados),
                                   papeles.items()) if f]
    filas.sort(key=lambda f: -f["sharpe"])
    datos = {"fecha": datetime.now(sources.TZ_BYMA).isoformat(timespec="minutes"),
             "rf": RF, "desde": desde, "listados": len(papeles), "filas": filas}
    tmp = SALIDA.with_suffix(".tmp")
    tmp.write_text(json.dumps(datos))
    tmp.replace(SALIDA)
    return datos


def leer() -> dict:
    try:
        return json.loads(SALIDA.read_text())
    except (OSError, ValueError):
        return {"filas": []}


if __name__ == "__main__":
    d = calcular(int(sys.argv[1]) if len(sys.argv) > 1 else 2)
    print(f"{len(d['filas'])} de {d['listados']} papeles → {SALIDA}")
