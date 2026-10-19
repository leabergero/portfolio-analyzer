"""
sharpe_byma.py — Sharpe y liquidez de las acciones y CEDEARs de BYMA (lab).

Es un buscador de papeles, no un modelo de la cartera: recorre ~680 especies y
baja una serie por cada una, algo que la VM no aguanta en un request. Por eso se
calcula de noche (`python -m core.models.sharpe_byma`, timer de systemd) y la
web sólo lee el JSON que deja.

Una especie por papel, la de pesos, medida en dólares MEP del último año con la
tasa libre de 4 %. El volumen es el promedio diario en dólares —acciones ×
cierre ÷ MEP—: las acciones operadas solas no comparan papeles de precios
distintos.
"""

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np

from core.data import sources
from core.data.symbols import ticker_currency
from core.models import risk

SALIDA = Path(__file__).resolve().parents[2] / "data" / "sharpe_byma.json"
RF = 0.04
MIN_RUEDAS = 60
# Un CEDEAR que cambia de ratio sin que la serie lo ajuste salta así en un día
# (MRNA +175 % el 2026-08-19). No se descarta: se marca, para no creerle el Sharpe.
SALTO = 0.40


def universo() -> dict:
    """{símbolo: "accion" | "cedear"}, sólo la especie en pesos."""
    from pyobd import BymaData
    b = BymaData()
    # BYMA liquida a 24 h desde 2024; el default de la librería (48 h) da vacío.
    paneles = (("accion", b.get_bluechips(settlement_t2=False, settlement_t1=True)),
               ("accion", b.get_general_board(settlement_t2=False, settlement_t1=True)),
               ("cedear", b.get_cedears()))
    salida = {}
    for tipo, df in paneles:
        if df.empty:
            continue
        for s in df[df.denominationCcy == "ARS"].symbol:
            # ponytail: los CEDEARs en pesos que terminan en D (MCD, HD, JD…) la
            # app los toma por dólares; hasta arreglar la regla, afuera.
            if ticker_currency(f"{s}.BA") == "ARS":
                salida.setdefault(s, tipo)
    return salida


def _fila(sym: str, tipo: str, desde: str):
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
    return {"ticker": t, "tipo": tipo, "ruedas": len(usd),
            "sharpe": round(risk.sharpe(r.values, RF), 2),
            "retorno_pct": round(((usd.iloc[-1] / usd.iloc[0]) ** (252 / len(usd)) - 1) * 100, 1),
            "vol_pct": round(float(r.std() * np.sqrt(252)) * 100, 1),
            "volumen_usd": round(float((vol * usd).mean())),
            "sin_operar_pct": round(float((vol == 0).mean()) * 100, 1),
            "salto": bool((r.abs() > SALTO).any())}


def calcular(hilos: int = 2) -> dict:
    desde = (date.today() - timedelta(days=365)).isoformat()
    papeles = universo()
    with ThreadPoolExecutor(hilos) as ex:
        filas = [f for f in ex.map(lambda x: _fila(*x, desde), papeles.items()) if f]
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
