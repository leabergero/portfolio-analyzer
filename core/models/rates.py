"""
rates.py — Tasa libre de riesgo.

**Corrección respecto de las apps anteriores.** Usaban el Treasury a 10 años
(`^TNX`) como tasa libre de riesgo para Sharpe, Sortino, alpha de Jensen y
Treynor. Un bono a 10 años **no es libre de riesgo a horizonte diario**: tiene
riesgo de duración y su precio se mueve todos los días. La tasa libre de una
métrica calculada sobre retornos diarios es la de **corto plazo**.

    métricas sobre retornos diarios  →  letra a 13 semanas (^IRX)
    descuento a largo plazo          →  Treasury 10Y (^TNX)

La diferencia no es cosmética: con ^TNX ≈ 4,4 % y ^IRX ≈ 4,0 %, el exceso de
retorno de una cartera cambia y con él todos los ratios que se comparan entre
carteras.

La región la fija la plaza elegida (`core.mercado`), que es la que fija la
moneda de medición: midiendo en dólares, la letra del Tesoro; midiendo en euros,
el Bund. El Bund es una estimación —no tiene ticker confiable en yfinance— y la
interfaz lo dice.
"""

import time

CORTO = "^IRX"      # letra del Tesoro EE.UU. a 13 semanas
LARGO = "^TNX"      # Treasury EE.UU. a 10 años

# Si la descarga falla, valores de referencia razonables antes que romper el
# cálculo. La etiqueta siempre aclara que es estimación.
_RESPALDO = {"corto": 0.040, "largo": 0.043, "bund": 0.024}
_TTL = 3600
_memoria = {}


def _ultimo(ticker: str):
    """Rendimiento en decimal. yfinance publica estos índices en porcentaje."""
    try:
        from core.data import yahoo
        s = yahoo.ticker(ticker).history(period="5d")["Close"].dropna()
        if len(s):
            return float(s.iloc[-1]) / 100.0
    except Exception:
        pass
    return None


def risk_free(plazo: str = "corto", region: str = "US"):
    """(tasa anual en decimal, etiqueta para mostrar).

    plazo: "corto" para todo lo que se mide sobre retornos diarios (Sharpe,
    Sortino, CAPM); "largo" para descuento a largo plazo.
    """
    clave = (plazo, region)
    ahora = time.time()
    if clave in _memoria and ahora - _memoria[clave][2] < _TTL:
        return _memoria[clave][0], _memoria[clave][1]

    if region == "EU":
        # El Bund 10Y no tiene ticker confiable en yfinance. Es una estimación y
        # se muestra como tal, en vez de aparentar un dato que no tenemos.
        valor, etiqueta = _RESPALDO["bund"], "Bund 10Y (estimado)"
    else:
        ticker = CORTO if plazo == "corto" else LARGO
        v = _ultimo(ticker)
        if v is not None:
            nombre = "Letra EE.UU. 13 semanas" if plazo == "corto" else "Treasury EE.UU. 10Y"
            valor, etiqueta = round(v, 4), f"{nombre} ({v * 100:.2f} %)"
        else:
            valor = _RESPALDO[plazo]
            etiqueta = f"EE.UU. {plazo} plazo (estimado {valor * 100:.2f} %)"

    _memoria[clave] = (valor, etiqueta, ahora)
    return valor, etiqueta


def risk_free_para(benchmark: str = None, plazo: str = "corto"):
    """La tasa libre de riesgo de la plaza desde la que se mira la cartera.

    La región la fija la **moneda de medición**, no el índice elegido: la tasa
    libre de riesgo de un retorno medido en euros es una tasa en euros, aunque
    ese día se esté comparando contra el S&P 500. Medir en euros y descontar con
    la letra del Tesoro americano mezcla dos monedas dentro del mismo Sharpe.

    El argumento `benchmark` queda por compatibilidad con las llamadas viejas;
    ya no decide nada.
    """
    from core import mercado
    return risk_free(plazo, mercado.cfg()["rf"])
