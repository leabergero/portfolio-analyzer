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

La cartera se mide en dólares, así que la tasa natural es siempre la de EE.UU.
Para el benchmark europeo se ofrece el Bund por convención regional, pero es una
aproximación y la interfaz lo dice.
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
        import yfinance as yf
        s = yf.Ticker(ticker).history(period="5d")["Close"].dropna()
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


# El benchmark define la región de la tasa, no la moneda de la cartera.
_REGION = {"SP500": "US", "MERVAL": "US", "STOXX600": "EU"}


def risk_free_para(benchmark: str, plazo: str = "corto"):
    return risk_free(plazo, _REGION.get(benchmark, "US"))
