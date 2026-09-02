"""
markowitz.py — Frontera eficiente y cartera óptima.

    μₚ = wᵀμ                  retorno esperado
    σₚ = √(wᵀΣw)              volatilidad

    máx Sharpe   max (wᵀμ − r_f)/√(wᵀΣw)   s.a. Σwᵢ = 1, wᵢ ≥ 0
    mín varianza min wᵀΣw                  s.a. Σwᵢ = 1, wᵢ ≥ 0
    frontera     min wᵀΣw                  s.a. wᵀμ = r*, Σwᵢ = 1, wᵢ ≥ 0

Todo se resuelve con SLSQP, que da el óptimo exacto y **determinista**. Terminal
Financiera elegía el mejor de 2.000 carteras generadas al azar: el "óptimo"
cambiaba de lugar entre corridas, y eso es lo que verifica una de las verdades.

La nube aleatoria se sigue dibujando, pero es solo ilustración de la región
factible: no entra en ninguna optimización.

Las funciones de optimización son puras —reciben μ, Σ y rf— así que se testean
sin descargar nada.
"""

import numpy as np
from scipy.optimize import minimize

RUEDAS = 252
_SEMILLA = 42


def _restricciones(n):
    return ({"type": "eq", "fun": lambda w: w.sum() - 1.0},)


def _limites(n, cap=None):
    tope = 1.0 if cap is None else min(1.0, max(cap, 1.0 / n))
    return tuple((0.0, tope) for _ in range(n))


def min_variance_weights(covarianza, cap: float = None) -> np.ndarray:
    """Cartera de mínima varianza. No depende de μ, que es lo que peor se estima."""
    cov = np.asarray(covarianza, dtype=float)
    n = len(cov)
    r = minimize(lambda w: float(w @ cov @ w), np.ones(n) / n, method="SLSQP",
                 bounds=_limites(n, cap), constraints=_restricciones(n))
    return r.x if r.success else np.ones(n) / n


def max_sharpe_weights(mu, covarianza, rf: float = 0.04, cap: float = None) -> np.ndarray:
    """Cartera tangente: la de mejor retorno ajustado por riesgo.

    Determinista: dos corridas con los mismos datos dan exactamente los mismos
    pesos. Es una de las verdades del proyecto.
    """
    mu = np.asarray(mu, dtype=float)
    cov = np.asarray(covarianza, dtype=float)
    n = len(mu)

    def negativo_sharpe(w):
        v = float(np.sqrt(w @ cov @ w))
        return -((float(w @ mu) - rf) / v) if v > 1e-12 else 1e9

    r = minimize(negativo_sharpe, np.ones(n) / n, method="SLSQP",
                 bounds=_limites(n, cap), constraints=_restricciones(n))
    return r.x if r.success else np.ones(n) / n


def frontera(mu, covarianza, puntos: int = 40, cap: float = None) -> list:
    """Frontera eficiente analítica: mínima varianza para cada retorno objetivo.

    Se barre **desde el retorno de mínima varianza hacia arriba**. Barrer desde
    el mínimo de μ arrastra la rama ineficiente —a volatilidad baja, retornos muy
    negativos— y la curva zigzaguea. Era el bug que hacía que el gráfico "se
    viera raro".
    """
    mu = np.asarray(mu, dtype=float)
    cov = np.asarray(covarianza, dtype=float)
    n = len(mu)

    w_min = min_variance_weights(cov, cap)
    ret_min = float(w_min @ mu)
    salida = []
    for objetivo in np.linspace(ret_min, float(mu.max()), puntos):
        cons = (
            {"type": "eq", "fun": lambda w: w.sum() - 1.0},
            {"type": "eq", "fun": lambda w, o=objetivo: float(w @ mu) - o},
        )
        r = minimize(lambda w: float(w @ cov @ w), np.ones(n) / n, method="SLSQP",
                     bounds=_limites(n, cap), constraints=cons)
        if r.success:
            salida.append({"vol": round(float(np.sqrt(r.x @ cov @ r.x)) * 100, 3),
                           "ret": round(float(objetivo) * 100, 3)})
    return sorted(salida, key=lambda p: p["vol"])


def cap_weights(pesos, cap: float, max_iter: int = 50) -> np.ndarray:
    """Topea cada peso y reparte el excedente por ESPACIO LIBRE.

    El excedente se distribuye proporcional a `cap − wⱼ`, no al peso actual.
    Repartir por peso actual dejaría fuera a los activos en 0 % (0 × factor = 0)
    y el tope terminaría violado igual.

    Requiere `cap · n ≥ 1` para ser factible; si no lo es, devuelve lo más
    parejo posible en vez de colgarse.
    """
    w = np.asarray(pesos, dtype=float).copy()
    n = len(w)
    if cap is None or cap >= 1.0 or n == 0:
        return w
    if cap * n < 1.0:
        return np.ones(n) / n           # imposible respetar el tope: equiponderar

    for _ in range(max_iter):
        excedidos = w > cap + 1e-12
        if not excedidos.any():
            break
        excedente = float((w[excedidos] - cap).sum())
        w[excedidos] = cap
        libres = ~excedidos
        espacio = np.clip(cap - w, 0, None) * libres
        total_espacio = float(espacio.sum())
        if total_espacio <= 1e-12:
            break
        w = w + excedente * espacio / total_espacio

    return w / w.sum() if w.sum() > 0 else np.ones(n) / n


def nube_factible(mu, covarianza, rf: float, n_carteras: int = 2000) -> dict:
    """Nube de carteras aleatorias: SOLO para dibujar la región factible.

    Semilla fija, así que el gráfico no cambia entre corridas. Se agregan las
    esquinas (un activo al 100 %) porque una Dirichlet casi nunca las alcanza y
    sin ellas la región se ve más chica de lo que es.
    """
    mu = np.asarray(mu, dtype=float)
    cov = np.asarray(covarianza, dtype=float)
    n = len(mu)
    rng = np.random.default_rng(_SEMILLA)

    pesos = list(rng.dirichlet(np.ones(n), n_carteras)) + list(np.eye(n))
    ret = np.array([float(w @ mu) for w in pesos])
    vol = np.array([float(np.sqrt(w @ cov @ w)) for w in pesos])
    with np.errstate(divide="ignore", invalid="ignore"):
        shr = np.where(vol > 0, (ret - rf) / vol, 0.0)

    return {"ret": np.round(ret * 100, 3).tolist(),
            "vol": np.round(vol * 100, 3).tolist(),
            "sharpe": np.round(shr, 3).tolist()}


# ── Optimización de una cartera concreta ──────────────────────────────────────

def optimizar(posiciones, benchmark: str = "SP500", cap: float = None) -> dict:
    """Frontera, óptimos y qué habría que comprar o vender para llegar."""
    from core.models.portfolio import matriz_retornos, value_weights
    from core.models.rates import risk_free_para

    ret_df, precios = matriz_retornos(posiciones)
    if ret_df.shape[1] < 2:
        return {"error": "Hacen falta al menos dos activos con historia."}

    tickers = list(ret_df.columns)
    mu = ret_df.mean().to_numpy() * RUEDAS          # aritmética: es el insumo de media-varianza
    cov = ret_df.cov().to_numpy() * RUEDAS
    rf, rf_label = risk_free_para(benchmark, "corto")

    w_actual = value_weights(posiciones, precios, tickers)
    w_sharpe = max_sharpe_weights(mu, cov, rf, cap)
    w_minvar = min_variance_weights(cov, cap)

    valor_total = sum(float(p.get("qty", 0)) * precios[t]
                      for p in posiciones
                      for t in [str(p["ticker"]).upper()] if t in precios)

    def punto(w):
        r = float(w @ mu)
        v = float(np.sqrt(w @ cov @ w))
        return {"pesos": [round(float(x) * 100, 2) for x in w],
                "ret_pct": round(r * 100, 3), "vol_pct": round(v * 100, 3),
                "sharpe": round((r - rf) / v, 3) if v > 0 else 0}

    def acciones(objetivo):
        salida = []
        for i, t in enumerate(tickers):
            delta = float(objetivo[i] - w_actual[i])
            usd = delta * valor_total
            salida.append({
                "ticker": t,
                "peso_actual_pct": round(float(w_actual[i]) * 100, 2),
                "peso_objetivo_pct": round(float(objetivo[i]) * 100, 2),
                "delta_pct": round(delta * 100, 2),
                "delta_usd": round(usd, 2),
                "delta_unidades": round(usd / precios[t], 3) if precios.get(t) else None,
                "accion": "COMPRAR" if delta > 0.005 else ("VENDER" if delta < -0.005 else "MANTENER"),
            })
        return salida

    return {
        "tickers": tickers,
        "valor_total": round(valor_total, 2),
        "rf": round(rf, 4), "rf_label": rf_label, "benchmark": benchmark,
        "cap": cap,
        "frontera": frontera(mu, cov, cap=cap),
        "nube": nube_factible(mu, cov, rf),
        "actual": punto(w_actual),
        "max_sharpe": punto(w_sharpe),
        "min_varianza": punto(w_minvar),
        "acciones_max_sharpe": acciones(w_sharpe),
        "acciones_min_varianza": acciones(w_minvar),
    }


def backtest(posiciones, meses: int = 6, benchmark: str = "SP500") -> dict:
    """¿La cartera óptima habría funcionado de verdad?

    Se optimiza con los datos ANTERIORES a la ventana de prueba y se mide qué
    hizo después. Es la única forma honesta de evaluar Markowitz: optimizar y
    medir sobre el mismo período siempre da un resultado espectacular y no
    significa nada.

    Se compara contra dos referencias que no requieren modelo: mantener la
    cartera como está, y equiponderar.
    """
    from core.models.portfolio import matriz_retornos, value_weights

    ret_df, precios = matriz_retornos(posiciones)
    if ret_df.shape[1] < 2:
        return {"error": "Hacen falta al menos dos activos."}

    ruedas_prueba = int(meses * 21)
    if len(ret_df) < ruedas_prueba + 252:
        return {"error": f"Hace falta al menos un año más de historia para probar "
                         f"{meses} meses fuera de muestra."}

    entrenamiento = ret_df.iloc[:-ruedas_prueba]
    prueba = ret_df.iloc[-ruedas_prueba:]
    tickers = list(ret_df.columns)

    mu = entrenamiento.mean().to_numpy() * RUEDAS
    cov = entrenamiento.cov().to_numpy() * RUEDAS
    from core.models.rates import risk_free_para
    rf, rf_label = risk_free_para(benchmark, "corto")

    estrategias = {
        "Máximo Sharpe": max_sharpe_weights(mu, cov, rf),
        "Mínima varianza": min_variance_weights(cov),
        "Tu cartera": value_weights(posiciones, precios, tickers),
        "Equiponderada": np.ones(len(tickers)) / len(tickers),
    }

    from core.models import risk as risk_mod
    salida, curvas = [], {}
    for nombre, w in estrategias.items():
        r = prueba[tickers].to_numpy() @ w
        acumulado = float(np.prod(1 + r) - 1)
        salida.append({
            "estrategia": nombre,
            "retorno_pct": round(acumulado * 100, 2),
            "volatilidad_pct": round(float(r.std(ddof=1)) * np.sqrt(RUEDAS) * 100, 2),
            "sharpe": round(risk_mod.sharpe(r, rf), 3),
            "max_drawdown_pct": round(risk_mod.max_drawdown(r) * 100, 2),
            "pesos": {t: round(float(w[i]) * 100, 1) for i, t in enumerate(tickers)},
        })
        curvas[nombre] = [round(float(v) * 100, 2) for v in np.cumprod(1 + r)]

    ganadora = max(salida, key=lambda s: s["sharpe"])
    optima = next(s for s in salida if s["estrategia"] == "Máximo Sharpe")
    actual = next(s for s in salida if s["estrategia"] == "Tu cartera")

    if ganadora["estrategia"] == "Máximo Sharpe":
        veredicto = (f"La cartera optimizada habría funcionado: {optima['retorno_pct']} % "
                     f"contra {actual['retorno_pct']} % de la tuya en estos {meses} meses.")
    else:
        veredicto = (f"La optimización NO habría ayudado en este período: ganó "
                     f"«{ganadora['estrategia']}». Es lo habitual — Markowitz optimiza "
                     f"sobre retornos pasados, que son el peor insumo del modelo.")

    return {
        "meses": meses, "ruedas_prueba": len(prueba),
        "entrenamiento": {"desde": str(entrenamiento.index[0].date()),
                          "hasta": str(entrenamiento.index[-1].date()),
                          "ruedas": len(entrenamiento)},
        "prueba": {"desde": str(prueba.index[0].date()),
                   "hasta": str(prueba.index[-1].date())},
        "fechas": [str(f.date()) for f in prueba.index],
        "curvas": curvas, "resultados": salida,
        "ganadora": ganadora["estrategia"], "veredicto": veredicto,
        "rf_label": rf_label,
        "nota": "Los pesos se calcularon SOLO con datos anteriores al período de prueba. "
                "Optimizar y medir sobre el mismo período no prueba nada.",
    }
