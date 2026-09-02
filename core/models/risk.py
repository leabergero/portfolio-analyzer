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


# ── Riesgo por activo ─────────────────────────────────────────────────────────

def por_activo(posiciones, benchmark: str = "SP500") -> dict:
    """VaR, CVaR, VaR 99 y peor caída de **cada activo**, no solo de la cartera.

    Una cartera puede verse tranquila y contener un activo que solo, cae 60 %.
    El agregado lo esconde: la diversificación promedia, y promediar es
    exactamente lo que oculta el caso individual.

    Todas las series se recortan a la ventana COMÚN de la cartera, así que los
    números son comparables entre sí y con el total.
    """
    from core.models.portfolio import matriz_retornos, value_weights
    from core.models.rates import risk_free_para

    ret_df, precios = matriz_retornos(posiciones)
    if ret_df.empty:
        return {"error": "Sin datos suficientes."}

    tickers = list(ret_df.columns)
    w = value_weights(posiciones, precios, tickers)
    rf, rf_label = risk_free_para(benchmark, "corto")
    valor_total = sum(float(p.get("qty", 0)) * precios[t]
                      for p in posiciones
                      for t in [str(p["ticker"]).upper()] if t in precios)

    filas = []
    for i, t in enumerate(tickers):
        r = ret_df[t].to_numpy()
        valor = float(w[i]) * valor_total
        filas.append({
            "ticker": t,
            "peso_pct": round(float(w[i]) * 100, 2),
            "valor_usd": round(valor, 2),
            "retorno_anual_pct": round(float((1 + r.mean()) ** RUEDAS - 1) * 100, 2),
            "volatilidad_pct": round(float(r.std(ddof=1)) * np.sqrt(RUEDAS) * 100, 2),
            "var95_pct": round(var_historico(r, 0.05) * 100, 3),
            "var99_pct": round(var_historico(r, 0.01) * 100, 3),
            "cvar95_pct": round(cvar_historico(r, 0.05) * 100, 3),
            "var95_usd": round(var_historico(r, 0.05) * valor, 2),
            "cvar95_usd": round(cvar_historico(r, 0.05) * valor, 2),
            "max_drawdown_pct": round(max_drawdown(r) * 100, 2),
            "sharpe": round(sharpe(r, rf), 3),
            "curtosis_exceso": round(float(stats.kurtosis(r)), 2),
        })

    cartera = ret_df[tickers].to_numpy() @ w
    total = {
        "ticker": "CARTERA", "peso_pct": 100.0, "valor_usd": round(valor_total, 2),
        "retorno_anual_pct": round(float((1 + cartera.mean()) ** RUEDAS - 1) * 100, 2),
        "volatilidad_pct": round(float(cartera.std(ddof=1)) * np.sqrt(RUEDAS) * 100, 2),
        "var95_pct": round(var_historico(cartera, 0.05) * 100, 3),
        "var99_pct": round(var_historico(cartera, 0.01) * 100, 3),
        "cvar95_pct": round(cvar_historico(cartera, 0.05) * 100, 3),
        "var95_usd": round(var_historico(cartera, 0.05) * valor_total, 2),
        "cvar95_usd": round(cvar_historico(cartera, 0.05) * valor_total, 2),
        "max_drawdown_pct": round(max_drawdown(cartera) * 100, 2),
        "sharpe": round(sharpe(cartera, rf), 3),
        "curtosis_exceso": round(float(stats.kurtosis(cartera)), 2),
    }

    # El beneficio de diversificar, en un número: cuánta volatilidad se ahorra
    # respecto de tener los mismos activos sin que se compensen entre sí.
    suma_ponderada = float(sum(w[i] * ret_df[t].std(ddof=1) for i, t in enumerate(tickers)))
    vol_cartera = float(cartera.std(ddof=1))
    ahorro = (1 - vol_cartera / suma_ponderada) * 100 if suma_ponderada > 0 else 0

    return {
        "por_activo": sorted(filas, key=lambda x: x["var95_pct"]),
        "cartera": total,
        "beneficio_diversificacion_pct": round(ahorro, 1),
        "ventana": {"desde": str(ret_df.index[0].date()),
                    "hasta": str(ret_df.index[-1].date()), "ruedas": len(ret_df)},
        "rf_label": rf_label,
        "series": {t: [{"fecha": str(f.date()), "ret": round(float(v) * 100, 3)}
                       for f, v in ret_df[t].items()] for t in tickers},
        "serie_cartera": [{"fecha": str(f.date()), "ret": round(float(v) * 100, 3)}
                          for f, v in zip(ret_df.index, cartera)],
    }


# ── VaR rolling ───────────────────────────────────────────────────────────────

def var_rolling(posiciones, ventana: int = 21) -> dict:
    """VaR y CVaR 95 % en ventana móvil, con los eventos macro superpuestos.

    Un VaR único resume toda la historia en un número y esconde que el riesgo
    de la cartera cambió: la serie muestra cuándo se disparó y —con el
    calendario al lado— qué estaba pasando.
    """
    from core.models.portfolio import matriz_retornos, value_weights
    from core.models.regimenes import EVENTOS

    ret_df, precios = matriz_retornos(posiciones)
    if ret_df.empty or len(ret_df) < ventana + 10:
        return {"error": "Serie demasiado corta para una ventana móvil."}

    tickers = list(ret_df.columns)
    w = value_weights(posiciones, precios, tickers)
    cartera = ret_df[tickers].to_numpy() @ w
    valor_total = sum(float(p.get("qty", 0)) * precios[t]
                      for p in posiciones
                      for t in [str(p["ticker"]).upper()] if t in precios)

    serie = []
    for i in range(ventana, len(cartera)):
        v = cartera[i - ventana:i]
        var95 = float(np.percentile(v, 5))
        cola = v[v <= var95]
        serie.append({
            "fecha": str(ret_df.index[i].date()),
            "var95_pct": round(var95 * 100, 3),
            "cvar95_pct": round(float(cola.mean()) * 100, 3) if cola.size else round(var95 * 100, 3),
            "var95_usd": round(var95 * valor_total, 2),
        })

    desde, hasta = serie[0]["fecha"], serie[-1]["fecha"]
    return {
        "serie": serie, "ventana_ruedas": ventana,
        "valor_total": round(valor_total, 2),
        "eventos": [{"fecha": f, "alcance": a, "descripcion": d}
                    for f, a, d in EVENTOS if desde <= f <= hasta],
        "nota": f"VaR 95 % calculado sobre las últimas {ventana} ruedas en cada punto. "
                "Los eventos son contexto, no causa.",
    }


# ── Riesgo cambiario ──────────────────────────────────────────────────────────

def riesgo_cambiario(posiciones) -> dict:
    """Cuánto del riesgo viene del activo y cuánto del tipo de cambio.

    Para un activo que cotiza en pesos, el retorno en dólares es
    aproximadamente `r_local − r_mep`, así que:

        Var(r_usd) = Var(local) + Var(MEP) − 2·Cov(local, MEP)

    El término cruzado es la parte que la versión anterior omitía, y por eso sus
    porcentajes no sumaban 100. Acá la descomposición es exacta: se reparte la
    covarianza a la mitad entre las dos fuentes, que es la convención habitual
    cuando dos factores comparten un término.
    """
    import pandas as pd

    from core.data import mep as mep_mod
    from core.data import sources

    serie_mep = mep_mod.serie()
    if serie_mep.empty:
        return {"error": "Sin serie de MEP."}
    r_mep = serie_mep.pct_change().dropna()

    detalle, en_pesos, en_dolares = [], 0.0, 0.0
    for p in posiciones:
        ticker = str(p["ticker"]).upper()
        origen = p.get("source") or None
        moneda = (p.get("currency") or sources.ticker_currency(ticker)).upper()
        s_usd = sources.precios_usd(ticker, source=origen)
        if len(s_usd) < 60:
            continue
        precio = float(s_usd.iloc[-1])
        valor = float(p.get("qty", 0)) * precio

        if moneda != "ARS":
            en_dolares += valor
            detalle.append({"ticker": ticker, "moneda": moneda, "valor_usd": round(valor, 2),
                            "fx_pct": 0.0, "activo_pct": 100.0,
                            "vol_total_pct": round(float(s_usd.pct_change().std()) * np.sqrt(RUEDAS) * 100, 2)})
            continue

        en_pesos += valor
        bruto = sources.precios(ticker, source=origen)["Close"].dropna()
        if sources.is_bond(ticker, origen):
            bruto = bruto / 100.0
        r_local = bruto.pct_change().dropna()
        par = pd.concat([r_local, r_mep], axis=1, keys=["a", "m"]).dropna()
        if len(par) < 60:
            continue

        var_a = float(par["a"].var(ddof=1))
        var_m = float(par["m"].var(ddof=1))
        cov = float(par["a"].cov(par["m"]))
        # Reparto simétrico del término cruzado: cada fuente carga con la mitad.
        aporte_activo = var_a - cov
        aporte_fx = var_m - cov
        total = aporte_activo + aporte_fx
        if total <= 0:
            continue

        detalle.append({
            "ticker": ticker, "moneda": "ARS", "valor_usd": round(valor, 2),
            "fx_pct": round(aporte_fx / total * 100, 1),
            "activo_pct": round(aporte_activo / total * 100, 1),
            "vol_total_pct": round(np.sqrt(total * RUEDAS) * 100, 2),
            "correlacion_con_mep": round(cov / np.sqrt(var_a * var_m), 3) if var_a * var_m > 0 else None,
        })

    if not detalle:
        return {"error": "Sin datos para descomponer el riesgo cambiario."}

    valor = sum(d["valor_usd"] for d in detalle)
    fx = sum(d["valor_usd"] * d["fx_pct"] for d in detalle) / valor if valor else 0
    return {
        "por_activo": sorted(detalle, key=lambda d: -d["valor_usd"]),
        "fx_pct": round(fx, 1), "activo_pct": round(100 - fx, 1),
        "valor_en_pesos": round(en_pesos, 2), "valor_en_dolares": round(en_dolares, 2),
        "pct_expuesto_al_peso": round(en_pesos / (en_pesos + en_dolares) * 100, 1)
                                if (en_pesos + en_dolares) else 0,
        "nota": "Para un activo que cotiza en pesos, su retorno en dólares mezcla lo que "
                "hizo el activo con lo que hizo el MEP. La descomposición reparte el "
                "término cruzado por igual entre las dos fuentes.",
    }


# ── Ajuste a un VaR objetivo ──────────────────────────────────────────────────

def ajustar_a_var(posiciones, var_objetivo_pct: float, benchmark: str = "SP500") -> dict:
    """Cuánto habría que desarmar para que la pérdida de un día malo no supere X.

    No reoptimiza la cartera: calcula la fracción a mantener invertida —el resto
    queda en dólares— y qué se vende de cada posición. Es la respuesta directa a
    "no quiero perder más de tanto en un día".

    Escalar funciona porque el VaR es homogéneo de grado 1 en el capital
    invertido: la mitad de la cartera tiene la mitad del VaR en dólares.
    """
    from core.models.portfolio import matriz_retornos, value_weights

    objetivo = -abs(float(var_objetivo_pct)) / 100.0
    ret_df, precios = matriz_retornos(posiciones)
    if ret_df.empty:
        return {"error": "Sin datos suficientes."}

    tickers = list(ret_df.columns)
    w = value_weights(posiciones, precios, tickers)
    cartera = ret_df[tickers].to_numpy() @ w
    var_actual = var_historico(cartera, 0.05)
    valor_total = sum(float(p.get("qty", 0)) * precios[t]
                      for p in posiciones
                      for t in [str(p["ticker"]).upper()] if t in precios)

    if var_actual >= objetivo:
        return {"ya_cumple": True, "var_actual_pct": round(var_actual * 100, 3),
                "var_objetivo_pct": round(objetivo * 100, 3),
                "valor_total": round(valor_total, 2),
                "mensaje": "La cartera ya está por debajo de ese límite: no hace falta "
                           "vender nada."}

    fraccion = objetivo / var_actual        # < 1
    liquidez = 1 - fraccion
    ajustes = [{
        "ticker": t,
        "peso_actual_pct": round(float(w[i]) * 100, 2),
        "peso_nuevo_pct": round(float(w[i]) * fraccion * 100, 2),
        "vender_usd": round(float(w[i]) * valor_total * liquidez, 2),
        "vender_unidades": round(float(w[i]) * valor_total * liquidez / precios[t], 3)
                           if precios.get(t) else None,
    } for i, t in enumerate(tickers)]

    return {
        "ya_cumple": False,
        "var_actual_pct": round(var_actual * 100, 3),
        "var_objetivo_pct": round(objetivo * 100, 3),
        "var_actual_usd": round(var_actual * valor_total, 2),
        "var_objetivo_usd": round(objetivo * valor_total, 2),
        "invertido_pct": round(fraccion * 100, 1),
        "liquidez_pct": round(liquidez * 100, 1),
        "a_liquidar_usd": round(liquidez * valor_total, 2),
        "valor_total": round(valor_total, 2),
        "ajustes": sorted(ajustes, key=lambda a: -a["vender_usd"]),
        "nota": "Se reduce la exposición de forma proporcional y el resto queda en "
                "dólares. No cambia la composición relativa: para eso está Markowitz.",
    }
