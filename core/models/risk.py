"""
risk.py — Cuánto puedo perder, y qué activo trae ese riesgo.

Todas las funciones de cálculo son **puras**: reciben números y devuelven
números, sin tocar la red ni la base. Por eso se pueden verificar con casos
resueltos a mano en `tests/test_verdades.py`, que es como se detectaron los
errores del código anterior.

Correcciones respecto de las apps viejas (ver `docs/MODELOS.md`):

  · La desviación a la baja se promedia sobre TODAS las observaciones, no solo
    sobre las negativas. El error inflaba la desviación ~√2 y subestimaba el
    Sortino de forma sistemática.
  · La descomposición del riesgo usa la identidad de Euler, que suma exacto.
    La anterior ponderaba varianzas por cantidad de nominales, ignoraba las
    covarianzas y sus porcentajes no sumaban 100 %.
  · La tasa libre es la de corto plazo (ver `rates.py`).
  · El stress test usa los pesos reales, no un equiponderado de emergencia.

Convención de signo: el VaR es un cuantil, o sea un número **negativo**. Se
guarda así y se muestra como pérdida positiva. Fijarlo evita restar dos veces.
"""

import numpy as np
from scipy import stats

RUEDAS = 252


# ── Medidas puras ─────────────────────────────────────────────────────────────

def max_drawdown(retornos) -> float:
    """Peor caída desde un máximo previo. Negativo (−0,20 = cayó 20 %)."""
    r = np.asarray(retornos, dtype=float)
    if r.size == 0:
        return 0.0
    acumulado = np.cumprod(1 + r)
    pico = np.maximum.accumulate(acumulado)
    return float((acumulado / pico - 1).min())


def downside_deviation(retornos, objetivo: float = 0.0) -> float:
    """Desviación de lo que quedó por debajo del objetivo.

        DD = √( (1/N) · Σ_{t=1..N} [ min(r_t − τ, 0) ]² )

    El promedio va sobre **N total**, no sobre la cantidad de observaciones
    negativas. Dividir por N_neg (aproximadamente la mitad) infla la desviación
    en torno a √2 y hunde el Sortino: era el bug de QuantFolio, y como el
    Sortino es uno de los criterios que eligen la cartera ganadora, el error se
    propagaba hasta la decisión.
    """
    r = np.asarray(retornos, dtype=float)
    if r.size == 0:
        return 0.0
    bajo = np.minimum(r - objetivo, 0.0)
    return float(np.sqrt((bajo ** 2).sum() / r.size))


def sharpe(retornos, rf_anual: float) -> float:
    """Exceso de retorno por unidad de volatilidad, anualizado.

    Divide por la desviación del retorno **en exceso**, que es la definición
    canónica. Con rf casi constante la diferencia es mínima, pero fijarlo evita
    discutirlo cada vez.
    """
    r = np.asarray(retornos, dtype=float)
    if r.size < 2:
        return 0.0
    exceso = r - rf_anual / RUEDAS
    s = exceso.std(ddof=1)
    return float(exceso.mean() / s * np.sqrt(RUEDAS)) if s > 0 else 0.0


def sortino(retornos, rf_anual: float) -> float:
    """Como el Sharpe, pero castigando solo la volatilidad a la baja."""
    r = np.asarray(retornos, dtype=float)
    objetivo = rf_anual / RUEDAS
    dd = downside_deviation(r, objetivo)
    if dd <= 0:
        return 0.0
    return float((r.mean() - objetivo) * RUEDAS / (dd * np.sqrt(RUEDAS)))


def calmar(retornos) -> float:
    """Retorno compuesto anual sobre la peor caída.

    Usa CAGR, no la media aritmética anualizada: es lo que efectivamente se
    ganó, que es con lo que corresponde comparar una caída real.
    """
    r = np.asarray(retornos, dtype=float)
    mdd = max_drawdown(r)
    if r.size == 0 or mdd == 0:
        return 0.0
    cagr = (1 + r.mean()) ** RUEDAS - 1
    return float(cagr / abs(mdd))


def var_historico(retornos, alfa: float = 0.05) -> float:
    """Cuantil empírico. Sin supuesto de distribución, pero no puede
    extrapolar más allá de la peor pérdida observada."""
    r = np.asarray(retornos, dtype=float)
    return float(np.percentile(r, alfa * 100)) if r.size else 0.0


def cvar_historico(retornos, alfa: float = 0.05) -> float:
    """Pérdida media en el peor α % de los días. Lo que el VaR no dice: qué tan
    malo es el día malo cuando llega."""
    r = np.asarray(retornos, dtype=float)
    if r.size == 0:
        return 0.0
    v = var_historico(r, alfa)
    cola = r[r <= v]
    return float(cola.mean()) if cola.size else v


def var_cornish_fisher(retornos, alfa: float = 0.05) -> float:
    """VaR ajustado por asimetría y curtosis.

        z_CF = z + (z²−1)·S/6 + (z³−3z)·K/24 − (2z³−5z)·S²/36

    El VaR normal supone campana simétrica sin colas gordas. Estas carteras
    tienen curtosis en exceso de más de 10, así que ese supuesto subestima la
    pérdida. Cornish-Fisher corrige el cuantil con los momentos reales y se
    muestra junto al histórico: la diferencia entre ambos es, literalmente,
    cuánto riesgo esconde suponer normalidad.
    """
    r = np.asarray(retornos, dtype=float)
    if r.size < 4:
        return 0.0
    s = float(stats.skew(r))
    k = float(stats.kurtosis(r))          # en exceso: normal = 0
    z = float(stats.norm.ppf(alfa))
    z_cf = (z
            + (z ** 2 - 1) * s / 6
            + (z ** 3 - 3 * z) * k / 24
            - (2 * z ** 3 - 5 * z) * s ** 2 / 36)
    return float(r.mean() + z_cf * r.std(ddof=1))


def risk_contributions(pesos, covarianza) -> np.ndarray:
    """Cuánto de la volatilidad de la cartera aporta cada activo.

        MCRᵢ = (Σw)ᵢ / σₚ        contribución marginal
        CRᵢ  = wᵢ · MCRᵢ         contribución absoluta
        Σ CRᵢ = σₚ               exacto, por la identidad de Euler

    Que sumen exactamente la volatilidad no es un detalle: es la prueba de que
    la descomposición está bien planteada. La versión anterior ponderaba
    varianzas por cantidad de nominales —5.817 acciones de COME contra 30 de
    QQQD, que no son comparables—, ignoraba las covarianzas y omitía el término
    cruzado, así que sus porcentajes no sumaban 100 %.

    Revela el caso que importa: un activo con 10 % de peso que aporta 40 % del
    riesgo.
    """
    w = np.asarray(pesos, dtype=float)
    cov = np.asarray(covarianza, dtype=float)
    sigma = float(np.sqrt(w @ cov @ w))
    if sigma <= 0:
        return np.zeros_like(w)
    return w * (cov @ w) / sigma


def concentracion_riesgo(pesos, covarianza) -> list:
    """Contribución al riesgo por activo, en porcentaje y comparada con el peso."""
    w = np.asarray(pesos, dtype=float)
    cr = risk_contributions(w, covarianza)
    total = cr.sum()
    if total <= 0:
        return []
    return [{"peso_pct": round(float(w[i]) * 100, 2),
             "riesgo_pct": round(float(cr[i]) / total * 100, 2),
             "ratio": round(float(cr[i]) / total / float(w[i]), 2) if w[i] > 1e-9 else None}
            for i in range(len(w))]


# ── Resumen de riesgo de una cartera ──────────────────────────────────────────

def analizar(posiciones, benchmark: str = "SP500") -> dict:
    """Panel de riesgo completo, en dólares.

    Devuelve además de cada número la etiqueta de qué tasa libre se usó: sin eso
    dos corridas con distinta tasa parecen un error de cálculo.
    """
    from core.models.portfolio import matriz_retornos, value_weights
    from core.models.rates import risk_free_para

    ret_df, precios = matriz_retornos(posiciones)
    if ret_df.empty:
        return {"error": "Sin datos suficientes para calcular riesgo."}

    tickers = list(ret_df.columns)
    w = value_weights(posiciones, precios, tickers)
    cartera = ret_df[tickers].to_numpy() @ w
    valor_total = sum(float(p.get("qty", 0)) * precios[t]
                      for p in posiciones
                      for t in [str(p["ticker"]).upper()] if t in precios)

    rf, rf_label = risk_free_para(benchmark, "corto")
    cov = np.cov(ret_df[tickers].to_numpy(), rowvar=False) * RUEDAS
    if cov.ndim == 0:
        cov = cov.reshape(1, 1)

    var95 = var_historico(cartera, 0.05)
    var99 = var_historico(cartera, 0.01)
    cvar95 = cvar_historico(cartera, 0.05)
    var95_cf = var_cornish_fisher(cartera, 0.05)

    contribuciones = concentracion_riesgo(w, cov)
    for i, t in enumerate(tickers):
        contribuciones[i]["ticker"] = t

    return {
        "tickers": tickers,
        "pesos": [round(float(x) * 100, 2) for x in w],
        "valor_total": round(valor_total, 2),
        "n_ruedas": int(len(cartera)),

        "retorno_anual_pct": round(float((1 + cartera.mean()) ** RUEDAS - 1) * 100, 2),
        "volatilidad_anual_pct": round(float(cartera.std(ddof=1)) * np.sqrt(RUEDAS) * 100, 2),

        "var95_pct": round(var95 * 100, 3),
        "var99_pct": round(var99 * 100, 3),
        "cvar95_pct": round(cvar95 * 100, 3),
        "var95_cornish_fisher_pct": round(var95_cf * 100, 3),
        "var95_usd": round(var95 * valor_total, 2),
        "var99_usd": round(var99 * valor_total, 2),
        "cvar95_usd": round(cvar95 * valor_total, 2),
        "var95_cornish_fisher_usd": round(var95_cf * valor_total, 2),

        "sharpe": round(sharpe(cartera, rf), 3),
        "sortino": round(sortino(cartera, rf), 3),
        "calmar": round(calmar(cartera), 3),
        "max_drawdown_pct": round(max_drawdown(cartera) * 100, 2),

        "asimetria": round(float(stats.skew(cartera)), 3),
        "curtosis_exceso": round(float(stats.kurtosis(cartera)), 3),

        "contribucion_riesgo": sorted(contribuciones,
                                      key=lambda x: -(x["riesgo_pct"] or 0)),
        "rf": round(rf, 4),
        "rf_label": rf_label,
        "moneda": "USD",
    }


# ── Stress testing ────────────────────────────────────────────────────────────

ESCENARIOS = [
    {"nombre": "PASO 2019", "desde": "2019-08-12", "hasta": "2019-08-16",
     "descripcion": "Derrota del oficialismo: acciones −40 %, MEP +30 %"},
    {"nombre": "Crash COVID", "desde": "2020-03-09", "hasta": "2020-03-23",
     "descripcion": "S&P 500 −34 %, Merval −50 %"},
    {"nombre": "Reestructuración 2020", "desde": "2020-04-06", "hasta": "2020-08-31",
     "descripcion": "Bonos en default técnico hasta el canje"},
    {"nombre": "Ajuste de la Fed 2022", "desde": "2022-06-01", "hasta": "2022-10-15",
     "descripcion": "Suba agresiva de tasas; caen los bonos emergentes"},
    {"nombre": "Devaluación diciembre 2023", "desde": "2023-12-12", "hasta": "2023-12-18",
     "descripcion": "Devaluación del 54 %; los bonos en dólares suben"},
]


def stress_test(posiciones) -> dict:
    """Qué habría pasado con ESTA cartera en cinco crisis reales.

    Usa los pesos reales por valor. La versión anterior había quedado con el
    cálculo frágil que ya se corrigió en el resto de los modelos: si el número
    de posiciones no coincidía con el de tickers con datos, caía a equiponderado
    y el resultado dejaba de corresponder a la cartera del usuario.
    """
    from core.models.portfolio import matriz_retornos, value_weights

    ret_df, precios = matriz_retornos(posiciones)
    if ret_df.empty:
        return {"error": "Sin datos para el stress test."}

    tickers = list(ret_df.columns)
    w = value_weights(posiciones, precios, tickers)
    valor_total = sum(float(p.get("qty", 0)) * precios[t]
                      for p in posiciones
                      for t in [str(p["ticker"]).upper()] if t in precios)

    salida = []
    for e in ESCENARIOS:
        ventana = ret_df.loc[(ret_df.index >= e["desde"]) & (ret_df.index <= e["hasta"])]
        if len(ventana) < 2:
            salida.append({**e, "pnl_pct": None, "pnl_usd": None, "ruedas": len(ventana),
                           "nota": "la cartera no tenía historia en esa fecha"})
            continue
        acumulado = float(np.prod(1 + ventana[tickers].to_numpy() @ w) - 1)
        salida.append({**e, "pnl_pct": round(acumulado * 100, 2),
                       "pnl_usd": round(acumulado * valor_total, 2),
                       "ruedas": len(ventana)})

    return {"escenarios": salida, "valor_total": round(valor_total, 2), "moneda": "USD"}
