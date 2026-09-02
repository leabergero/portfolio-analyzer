"""
momentum.py — ¿es momento de entrar, o conviene esperar?

    m_k = Π (1 + r_t) − 1        sobre las últimas k ruedas
    m_12-1                       12 meses SALTEANDO el último

**El 12−1 es la corrección respecto de las apps anteriores**, que usaban los 12
meses completos. La literatura (Jegadeesh y Titman) saltea el mes más reciente
porque en el corto plazo hay reversión: incluirlo mete ruido de signo contrario
justo en la señal que se quiere leer. Se devuelven los dos para poder comparar.

La "degradación" no es una métrica estándar sino una heurística propia: mide
cuánto se desacelera la tendencia reciente contra la de medio plazo. Se presenta
como tal, no como si fuera literatura.
"""

import numpy as np

RUEDAS_MES = 21


def _acumulado(serie, ruedas: int, saltear: int = 0) -> float:
    r = np.asarray(serie, dtype=float)
    if saltear:
        r = r[:-saltear] if len(r) > saltear else np.array([])
    if len(r) == 0:
        return 0.0
    tramo = r[-ruedas:] if len(r) >= ruedas else r
    return float(np.prod(1 + tramo) - 1)


def _veredicto(m12_1: float, m3: float, degradacion: float, reversion: bool):
    """Qué hacer, en una palabra y una frase."""
    if reversion:
        return ("ESPERAR", "Subió fuerte pero la tendencia se está desacelerando: "
                           "riesgo de reversión. No es momento de sobreponderar.")
    if m12_1 > 0.05 and m3 > 0:
        return ("FAVORABLE", "Tendencia positiva y sostenida en 12 y 3 meses. "
                             "Viento a favor para entrar o mantener.")
    if m12_1 < -0.05 and m3 < 0:
        return ("EVITAR", "Baja en 12 y 3 meses: el momentum está en contra. "
                          "Conviene esperar una señal de giro.")
    if m3 > 0 >= m12_1:
        return ("INCIPIENTE", "Posible giro al alza: 3 meses en positivo sobre "
                              "un año flojo. Vigilar, todavía no confirma.")
    return ("NEUTRAL", "Sin tendencia clara. El momentum no aporta señal de timing.")


def analizar(posiciones) -> dict:
    from core.models.portfolio import matriz_retornos

    ret_df, _ = matriz_retornos(posiciones)
    if ret_df.empty:
        return {"error": "Sin datos para calcular momentum."}

    salida = []
    for ticker in ret_df.columns:
        r = ret_df[ticker].to_numpy()
        m3 = _acumulado(r, 63)
        m6 = _acumulado(r, 126)
        m12 = _acumulado(r, 252)
        m12_1 = _acumulado(r, 252 - RUEDAS_MES, saltear=RUEDAS_MES)

        ann3 = (1 + m3) ** (252 / 63) - 1 if m3 > -1 else -1.0
        ann6 = (1 + m6) ** (252 / 126) - 1 if m6 > -1 else -1.0
        degradacion = float((ann6 - ann3) / abs(ann3)) if abs(ann3) > 1e-9 else 0.0
        reversion = m12_1 > 0.20 and degradacion > 0.50

        señal, texto = _veredicto(m12_1, m3, degradacion, reversion)
        salida.append({
            "ticker": ticker,
            "mom_3m_pct": round(m3 * 100, 2),
            "mom_6m_pct": round(m6 * 100, 2),
            "mom_12m_pct": round(m12 * 100, 2),
            "mom_12_1_pct": round(m12_1 * 100, 2),
            "degradacion": round(degradacion, 3),
            "riesgo_reversion": "alto" if reversion else "bajo",
            "señal": señal, "veredicto": texto,
        })

    return {
        "por_activo": sorted(salida, key=lambda x: -x["mom_12_1_pct"]),
        "en_reversion": [s["ticker"] for s in salida if s["riesgo_reversion"] == "alto"],
        "nota_metodo": "El momentum principal es 12−1 (doce meses salteando el "
                       "último) porque el mes más reciente tiende a revertir.",
    }
