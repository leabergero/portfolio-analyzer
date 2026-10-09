"""
hrp.py — Hierarchical Risk Parity: pesos sin invertir la matriz de covarianza.

Markowitz (`markowitz.py`) invierte Σ para resolver el óptimo — y esa inversión
es lo que lo hace frágil: con activos muy correlacionados o pocas ruedas de
historia frente a la cantidad de activos, un error chico de estimación se
amplifica en pesos que cambian bruscamente entre corridas. HRP (López de Prado,
2016) evita el problema entero con tres pasos que nunca invierten nada:

    1. Tree clustering       agrupar los activos más correlacionados primero
                              (ya está: `portfolio._orden_jerarquico`)
    2. Quasi-diagonalización reordenar la matriz según ese árbol
                              (mismo lugar — es lo que ya se usa en el
                              "Agrupar por correlación" de la matriz)
    3. Bisección recursiva   repartir el peso bajando por el árbol de a dos
                              ramas por vez, más al lado de menor varianza
                              (lo que agrega este archivo)

A cambio de esa estabilidad, HRP no busca explícitamente el mejor Sharpe ni
incorpora una vista de retorno esperado como Black-Litterman — reparte el
riesgo de forma pareja, no persigue un objetivo. Son preguntas distintas, no
un reemplazo del otro.
"""

import numpy as np

RUEDAS = 252


def _pesos_ivp(cov: np.ndarray) -> np.ndarray:
    """Inverse-Variance Portfolio: peso inversamente proporcional a la varianza
    propia de cada activo, sin mirar la covarianza cruzada. Es el reparto que
    se usa DENTRO de cada rama en la bisección — ahí sí hay que invertir algo,
    pero solo la diagonal, nunca la matriz completa."""
    ivp = 1.0 / np.diag(cov)
    return ivp / ivp.sum()


def _var_cluster(cov: np.ndarray, idx: list) -> float:
    """Varianza de un cluster si sus miembros se ponderan por IVP entre sí."""
    sub = cov[np.ix_(idx, idx)]
    w = _pesos_ivp(sub)
    return float(w @ sub @ w)


def _bisección_recursiva(cov: np.ndarray) -> np.ndarray:
    """Pesos de HRP, en el mismo orden que las filas/columnas de `cov`.

    `cov` ya tiene que venir con los activos en el orden de la
    quasi-diagonalización —correlacionados contiguos— porque bisecar a la
    mitad de la lista es lo que separa un cluster del otro. Bisecar una
    matriz en orden alfabético cortaría clusters por la mitad y el reparto
    no significaría nada.
    """
    n = cov.shape[0]
    pesos = np.ones(n)
    clusters = [list(range(n))]
    while clusters:
        # Cada cluster de 2+ elementos se parte en mitades y compite con su
        # propia mitad — no con el resto del árbol— así el reparto es
        # puramente binario, sin optimizar nada de punta a punta.
        clusters = [c[i:j] for c in clusters
                    for i, j in ((0, len(c) // 2), (len(c) // 2, len(c))) if len(c) > 1]
        for i in range(0, len(clusters), 2):
            izq, der = clusters[i], clusters[i + 1]
            v_izq, v_der = _var_cluster(cov, izq), _var_cluster(cov, der)
            alfa = 1.0 - v_izq / (v_izq + v_der) if (v_izq + v_der) > 0 else 0.5
            pesos[izq] *= alfa
            pesos[der] *= (1.0 - alfa)
    return pesos


def optimizar(posiciones, benchmark: str = None, lab: bool = False) -> dict:
    """Pesos de HRP para esta cartera, comparables con los de Markowitz.

    lab (`?lab=11`): Σ y ρ del modelo propuesto (`montecarlo.esperados`):
    historia larga de cada activo y ventana común sin ceros inventados; μ, que
    HRP no usa para los pesos, es el del modelo propuesto.
    """
    import pandas as pd
    from core.models.portfolio import matriz_retornos, value_weights, _orden_jerarquico
    from core.models.rates import risk_free_para

    if lab:
        from core.models.montecarlo import esperados
        e = esperados(posiciones)
        if "error" in e or len(e["tickers"]) < 2:
            return {"error": "Hacen falta al menos dos activos con historia."}
        tickers, precios, mu, cov = e["tickers"], e["precios"], e["mu"], e["cov"]
        d = np.sqrt(np.diag(cov))
        corr = pd.DataFrame(cov / np.outer(d, d), index=tickers, columns=tickers)
    else:
        ret_df, precios = matriz_retornos(posiciones)
        if ret_df.shape[1] < 2:
            return {"error": "Hacen falta al menos dos activos con historia."}

        tickers = list(ret_df.columns)
        mu = ret_df.mean().to_numpy() * RUEDAS
        cov = ret_df.cov().to_numpy() * RUEDAS
        corr = ret_df.corr()
    rf, rf_label = risk_free_para(benchmark, "corto")

    orden, _grupo = _orden_jerarquico(corr)
    idx = [tickers.index(tk) for tk in orden]
    cov_orden = cov[np.ix_(idx, idx)]
    pesos_orden = _bisección_recursiva(cov_orden)
    # Volver al orden original de `tickers`: todo lo que sigue (acciones,
    # comparación con la cartera actual) trabaja en ese orden.
    pesos = np.empty(len(tickers))
    for pos_orden, i_original in enumerate(idx):
        pesos[i_original] = pesos_orden[pos_orden]

    w_actual = value_weights(posiciones, precios, tickers)
    valor_total = sum(float(p.get("qty", 0)) * precios[t]
                      for p in posiciones
                      for t in [str(p["ticker"]).upper()] if t in precios)

    ret_pct = float(pesos @ mu)
    vol_pct = float(np.sqrt(pesos @ cov @ pesos))

    def punto(w):
        r, v = float(w @ mu), float(np.sqrt(w @ cov @ w))
        return {"pesos": [round(float(x) * 100, 2) for x in w],
                "ret_pct": round(r * 100, 3), "vol_pct": round(v * 100, 3),
                "sharpe": round((r - rf) / v, 3) if v > 0 else 0}

    acciones = []
    for i, tk in enumerate(tickers):
        delta = float(pesos[i] - w_actual[i])
        usd = delta * valor_total
        acciones.append({
            "ticker": tk,
            "peso_actual_pct": round(float(w_actual[i]) * 100, 2),
            "peso_objetivo_pct": round(float(pesos[i]) * 100, 2),
            "delta_pct": round(delta * 100, 2),
            "delta_usd": round(usd, 2),
            "delta_unidades": round(usd / precios[tk], 3) if precios.get(tk) else None,
            "accion": "COMPRAR" if delta > 0.005 else ("VENDER" if delta < -0.005 else "MANTENER"),
        })

    return {
        "tickers": tickers,
        "valor_total": round(valor_total, 2),
        "rf": round(rf, 4), "rf_label": rf_label, "benchmark": benchmark,
        "orden_hrp": orden,
        "actual": punto(w_actual),
        "hrp": punto(pesos),
        "acciones_hrp": acciones,
    }
