"""
capm.py — La cartera contra su índice de referencia.

    β  = Cov(rₚ, r_b) / Var(r_b)                    cuánto amplifica al mercado
    α  = r̄ₚ − [ r_f + β(r̄_b − r_f) ]                lo que rindió de más
    R² = corr(rₚ, r_b)²                             cuánto explica el benchmark
    Treynor = (rₚ − r_f) / β                        retorno por unidad de β
    IR = media(rₚ − r_b)·252 / (sd(rₚ − r_b)·√252)  consistencia del exceso

**El R² decide si el resto de los números significan algo.** Para una cartera
argentina, el R² contra el Merval da ~0,52 y contra el S&P 500 ~0,05. Con 0,05
el benchmark no explica nada de lo que hace la cartera, así que su beta y su
alpha son ruido con formato de número — y la interfaz tiene que decirlo, no
mostrarlos como si tal cosa. Ese aviso es la función `diagnostico_r2()`.

Los tres benchmarks se llevan a dólares antes de comparar, porque la cartera se
mide en dólares: el STOXX 600 vía EURUSD, el Merval vía MEP. Comparar un índice
en su moneda contra una cartera en otra mide el tipo de cambio.
"""

import numpy as np
import pandas as pd

RUEDAS = 252

BENCHMARKS = {
    "SP500":    {"ticker": "SPY",    "moneda": "USD", "nombre": "S&P 500"},
    "STOXX600": {"ticker": "^STOXX", "moneda": "EUR", "nombre": "STOXX 600"},
    "MERVAL":   {"ticker": "^MERV",  "moneda": "ARS", "nombre": "Merval (en USD)"},
}


def _cierres(ticker: str, desde: str = None) -> pd.Series:
    try:
        import yfinance as yf
        s = yf.Ticker(ticker).history(start=desde or "2005-01-01")["Close"].dropna()
    except Exception:
        return pd.Series(dtype=float)
    if getattr(s.index, "tz", None) is not None:
        s.index = s.index.tz_localize(None)
    return s


def serie_benchmark(clave: str, desde: str = None):
    """(serie en USD, nombre para mostrar)."""
    cfg = BENCHMARKS.get(clave, BENCHMARKS["SP500"])
    s = _cierres(cfg["ticker"], desde)
    if s.empty:
        return s, cfg["nombre"]

    if cfg["moneda"] == "EUR":
        fx = _cierres("EURUSD=X", desde).reindex(s.index, method="ffill")
        s = (s * fx).dropna()
    elif cfg["moneda"] == "ARS":
        from core.data import mep
        s = mep.serie_a_usd(s)

    return s, cfg["nombre"]


def diagnostico_r2(r2: float) -> dict:
    """Si el benchmark no explica la cartera, hay que decirlo antes que el beta.

    Los umbrales son de lectura, no de teoría: por debajo de 0,20 el beta de una
    regresión con este R² no sostiene ninguna conclusión.
    """
    if r2 >= 0.50:
        return {"nivel": "alto", "texto": "El índice explica buena parte de lo que hace "
                                          "la cartera: beta y alpha son informativos."}
    if r2 >= 0.20:
        return {"nivel": "medio", "texto": "El índice explica solo una parte. Leé beta y "
                                           "alpha con reservas."}
    return {"nivel": "bajo", "texto": "El índice casi no explica a esta cartera. Beta y "
                                      "alpha no son concluyentes: probá otro benchmark."}


def analizar(posiciones, benchmark: str = "SP500") -> dict:
    from core.models.portfolio import matriz_retornos, value_weights
    from core.models.rates import risk_free_para

    ret_df, precios = matriz_retornos(posiciones)
    if ret_df.empty:
        return {"error": "Sin datos de la cartera."}

    tickers = list(ret_df.columns)
    w = value_weights(posiciones, precios, tickers)
    cartera = pd.Series(ret_df[tickers].to_numpy() @ w, index=ret_df.index)

    serie, nombre = serie_benchmark(benchmark, desde=str(ret_df.index[0].date()))
    if serie.empty:
        return {"error": f"Sin datos de {nombre}."}
    bench = serie.pct_change().dropna()

    par = pd.concat([cartera, bench], axis=1, keys=["p", "b"]).dropna()
    if len(par) < 30:
        return {"error": "Menos de 30 ruedas en común con el índice."}

    p = par["p"].to_numpy()
    b = par["b"].to_numpy()
    rf, rf_label = risk_free_para(benchmark, "corto")
    rf_d = rf / RUEDAS

    cov = np.cov(p, b)
    if cov[1, 1] <= 0:
        return {"error": "El índice no tiene varianza en el período."}
    beta = float(cov[0, 1] / cov[1, 1])

    alpha_d = float(p.mean() - (rf_d + beta * (b.mean() - rf_d)))
    r2 = float(np.corrcoef(p, b)[0, 1] ** 2)
    ret_cartera = float((1 + p.mean()) ** RUEDAS - 1)
    activo = p - b
    te = float(activo.std(ddof=1)) * np.sqrt(RUEDAS)

    # Beta móvil: un beta único sobre años oculta que la exposición cambió.
    sp, sb = pd.Series(p, index=par.index), pd.Series(b, index=par.index)
    rolling = {}
    for v in (60, 120, 252):
        if len(par) >= v:
            serie_beta = (sp.rolling(v).cov(sb) / sb.rolling(v).var()).dropna()
            rolling[f"beta_{v}"] = [{"fecha": str(d.date()), "beta": round(float(x), 3)}
                                    for d, x in serie_beta.items()]

    # Recta característica: la nube de retornos diarios y la regresión cuya
    # pendiente ES el beta. Deja ver si el beta viene de la nube o de dos outliers.
    paso = max(1, len(p) // 300)
    nube = [{"b": round(float(b[i]) * 100, 3), "p": round(float(p[i]) * 100, 3)}
            for i in range(0, len(p), paso)]
    b_min, b_max = float(b.min()), float(b.max())
    recta = [{"b": round(b_min * 100, 3), "p": round((alpha_d + beta * b_min) * 100, 3)},
             {"b": round(b_max * 100, 3), "p": round((alpha_d + beta * b_max) * 100, 3)}]

    return {
        "benchmark": benchmark, "benchmark_nombre": nombre,
        "n_ruedas": int(len(par)),
        "beta": round(beta, 3),
        "alpha_anual_pct": round(((1 + alpha_d) ** RUEDAS - 1) * 100, 2),
        "r2": round(r2, 3),
        "diagnostico_r2": diagnostico_r2(r2),
        "treynor": round((ret_cartera - rf) / beta, 3) if beta else None,
        "information_ratio": round(float(activo.mean()) * RUEDAS / te, 3) if te > 0 else None,
        "tracking_error_pct": round(te * 100, 2),
        "retorno_cartera_pct": round(ret_cartera * 100, 2),
        "retorno_benchmark_pct": round(((1 + float(b.mean())) ** RUEDAS - 1) * 100, 2),
        "beta_movil": rolling,
        "nube": nube, "recta": recta,
        "historia_benchmark": [{"fecha": str(d.date()), "valor": round(float(v), 4)}
                               for d, v in serie.items()],
        "rf": round(rf, 4), "rf_label": rf_label,
    }


def comparar_benchmarks(posiciones) -> dict:
    """Corre los tres índices y dice cuál es el comparable legítimo.

    Es la forma honesta de elegir: en vez de que el usuario adivine, se muestra
    el R² de cada uno y se recomienda el más alto.
    """
    salida = {}
    for clave in BENCHMARKS:
        r = analizar(posiciones, clave)
        if "error" not in r:
            salida[clave] = {"nombre": r["benchmark_nombre"], "r2": r["r2"],
                             "beta": r["beta"], "alpha_anual_pct": r["alpha_anual_pct"]}
    if not salida:
        return {"error": "No se pudo comparar contra ningún índice."}
    mejor = max(salida, key=lambda k: salida[k]["r2"])
    return {"benchmarks": salida, "recomendado": mejor,
            "motivo": f"{salida[mejor]['nombre']} es el que mejor explica a esta cartera "
                      f"(R² {salida[mejor]['r2']})."}
