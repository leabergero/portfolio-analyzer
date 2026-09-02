"""
blacklitterman.py — Combinar el equilibrio del mercado con tus opiniones.

    π      = δ Σ w_mkt                                    retornos de equilibrio
    μ_BL   = [(τΣ)⁻¹ + PᵀΩ⁻¹P]⁻¹ [(τΣ)⁻¹π + PᵀΩ⁻¹Q]      posterior
    Σ_BL   = Σ + [(τΣ)⁻¹ + PᵀΩ⁻¹P]⁻¹

Parte de los retornos que están implícitos en la cartera actual y los corrige
con las views, pesando cada una por su confianza. Sin views devuelve el punto de
partida: es la propiedad que lo hace confiable.

**Cuatro parámetros que en las apps anteriores estaban fijos y acá son
decisiones explícitas** (ver `docs/MODELOS.md`):

  · **δ** se calibra con el benchmark, `δ = (E[r_m] − r_f)/σ²_m`, en vez de 2,5
    escrito a mano.
  · **τ = 1/T** siguiendo a He y Litterman, en vez de 0,05 fijo.
  · Los pesos finales se obtienen **optimizando con la restricción w ≥ 0**, no
    recortando los negativos y renormalizando, que da otra cartera.
  · La volatilidad reportada usa **Σ_BL**, la misma matriz que el retorno. Antes
    el retorno usaba la posterior y el riesgo la previa.

Y uno que se mantiene, pero declarado: `w_mkt` son **los pesos de tu propia
cartera**, no capitalizaciones de mercado. Con eso, "el equilibrio" es la
ingeniería inversa de tu cartera y BL te dice cuánto te movés respecto de vos
mismo. Es lo único posible sin capitalizaciones de BYMA y es razonable para una
cartera personal, pero cambia la interpretación y hay que decirlo.
"""

import numpy as np

from core.models.markowitz import cap_weights, max_sharpe_weights

RUEDAS = 252


def _delta(benchmark: str, rf: float) -> tuple:
    """Aversión al riesgo implícita en el mercado: (E[r_m] − r_f)/σ²_m."""
    from core.models.capm import serie_benchmark
    serie, nombre = serie_benchmark(benchmark)
    if serie.empty or len(serie) < 60:
        return 2.5, "2,5 (valor por defecto: sin datos del índice)"
    r = serie.pct_change().dropna()
    exceso = float(r.mean()) * RUEDAS - rf
    var = float(r.var(ddof=1)) * RUEDAS
    if var <= 0 or exceso <= 0:
        return 2.5, "2,5 (por defecto: el índice no da una aversión positiva)"
    d = float(np.clip(exceso / var, 1.0, 6.0))
    return d, f"{d:.2f} calibrado con {nombre}"


def _confianza_a_omega(confianzas, tau, Sigma, P):
    """Ω diagonal: cuanta menos confianza, más incertidumbre en la view.

    El tope de confianza es 90 % aunque el usuario esté seguro: con Ω → 0 la
    solución degenera y BL concentra toda la cartera en un activo.
    """
    diag = []
    for k, conf in enumerate(confianzas):
        c = np.clip(conf, 1, 90) / 100.0
        var_view = float(P[k] @ (tau * Sigma) @ P[k])
        diag.append(max((1 - c) * var_view, 1e-10))
    return np.diag(diag)


def analizar(posiciones, views=None, benchmark: str = "SP500",
             max_weight: float = None) -> dict:
    """views: [{"ticker", "ret" (% anual esperado), "confidence" (1-90)}]"""
    from core.models.portfolio import matriz_retornos, value_weights
    from core.models.rates import risk_free_para

    ret_df, precios = matriz_retornos(posiciones)
    if ret_df.shape[1] < 2:
        return {"error": "Hacen falta al menos dos activos con historia."}

    tickers = list(ret_df.columns)
    n, T = len(tickers), len(ret_df)
    Sigma = ret_df.cov().to_numpy() * RUEDAS
    rf, rf_label = risk_free_para(benchmark, "corto")
    delta, delta_label = _delta(benchmark, rf)
    tau = 1.0 / T                       # He-Litterman

    w_mkt = value_weights(posiciones, precios, tickers)
    pi = delta * Sigma @ w_mkt

    valor_total = sum(float(p.get("qty", 0)) * precios[t]
                      for p in posiciones
                      for t in [str(p["ticker"]).upper()] if t in precios)

    base = {
        "tickers": tickers, "valor_total": round(valor_total, 2),
        "equilibrio_pct": {t: round(float(pi[i]) * 100, 2) for i, t in enumerate(tickers)},
        "rf": round(rf, 4), "rf_label": rf_label,
        "delta": round(delta, 3), "delta_label": delta_label,
        "tau": round(tau, 6), "tau_label": f"1/T con T = {T} ruedas",
        "equilibrio_nota": "El equilibrio se calcula sobre los pesos de esta cartera, "
                           "no sobre capitalizaciones de mercado: mide cuánto te movés "
                           "respecto de tu propia posición.",
    }

    validas = [v for v in (views or []) if str(v.get("ticker", "")).upper() in tickers]
    if not validas:
        w = cap_weights(w_mkt, max_weight) if max_weight else w_mkt
        return {**base, "views_aplicadas": [],
                "pesos_bl_pct": {t: round(float(w[i]) * 100, 2) for i, t in enumerate(tickers)},
                "acciones": [],
                "nota": "Sin views, Black-Litterman devuelve el punto de partida."}

    P = np.zeros((len(validas), n))
    Q = np.zeros(len(validas))
    for k, v in enumerate(validas):
        P[k, tickers.index(str(v["ticker"]).upper())] = 1.0
        Q[k] = float(v["ret"]) / 100.0
    Omega = _confianza_a_omega([v.get("confidence", 50) for v in validas], tau, Sigma, P)

    inv_tau_sigma = np.linalg.inv(tau * Sigma)
    inv_omega = np.linalg.inv(Omega)
    M = np.linalg.inv(inv_tau_sigma + P.T @ inv_omega @ P)
    mu_bl = M @ (inv_tau_sigma @ pi + P.T @ inv_omega @ Q)
    Sigma_bl = Sigma + M

    # Optimización con restricción, no recorte de negativos.
    w_bl = max_sharpe_weights(mu_bl, Sigma_bl, rf, max_weight)

    ret_bl = float(w_bl @ mu_bl)
    vol_bl = float(np.sqrt(w_bl @ Sigma_bl @ w_bl))

    acciones = []
    for i, t in enumerate(tickers):
        delta_w = float(w_bl[i] - w_mkt[i])
        acciones.append({
            "ticker": t,
            "peso_actual_pct": round(float(w_mkt[i]) * 100, 2),
            "peso_bl_pct": round(float(w_bl[i]) * 100, 2),
            "delta_pct": round(delta_w * 100, 2),
            "delta_usd": round(delta_w * valor_total, 2),
            "ret_equilibrio_pct": round(float(pi[i]) * 100, 2),
            "ret_bl_pct": round(float(mu_bl[i]) * 100, 2),
            "accion": "COMPRAR" if delta_w > 0.005 else ("VENDER" if delta_w < -0.005 else "MANTENER"),
        })

    return {
        **base,
        "retornos_bl_pct": {t: round(float(mu_bl[i]) * 100, 2) for i, t in enumerate(tickers)},
        "pesos_bl_pct": {t: round(float(w_bl[i]) * 100, 2) for i, t in enumerate(tickers)},
        "ret_bl_pct": round(ret_bl * 100, 2),
        "vol_bl_pct": round(vol_bl * 100, 2),
        "sharpe_bl": round((ret_bl - rf) / vol_bl, 3) if vol_bl > 0 else 0,
        "views_aplicadas": validas,
        "acciones": acciones,
    }


def views_desde_objetivos(resultado_objetivos, resultado_momentum=None) -> list:
    """Convierte precios objetivo en views, ajustando por momentum.

    La confianza sale de la cobertura de analistas, y se **recorta 35 puntos si
    el momentum está en contra**: sin eso, BL sobreasigna a un activo que viene
    cayendo solo porque los analistas le ven recorrido. Es el problema de
    "agarrar el cuchillo cayendo", trasladado a la optimización.
    """
    momentos = {m["ticker"]: m.get("señal")
                for m in (resultado_momentum or {}).get("por_activo", [])}
    views = []
    for a in resultado_objetivos.get("por_activo", []):
        if not a.get("disponible") or a.get("upside_pct") is None:
            continue
        if a.get("es_futuro"):
            # La curva de futuros refleja costo de acarreo, no dirección.
            confianza = 55
        else:
            n = a.get("n_analistas") or 1
            confianza = min(85, 35 + 8 * n)
        if momentos.get(a["ticker"]) in ("EVITAR", "ESPERAR"):
            confianza = max(10, confianza - 35)
        views.append({"ticker": a["ticker"], "ret": a["upside_pct"],
                      "confidence": confianza, "n_analistas": a.get("n_analistas"),
                      "momentum": momentos.get(a["ticker"])})
    return views
