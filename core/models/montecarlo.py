"""
montecarlo.py — Futuros posibles de la cartera.

Simula miles de trayectorias y muestra el abanico de resultados: no una
predicción, sino el rango de lo que puede pasar y con qué frecuencia.

Movimiento browniano geométrico:

    S_t = S₀ · exp[ Σ_k ( (μ − ½σ²) + σ·Z_k ) ]

La corrección −½σ² es correcta con μ y σ estimados sobre retornos **simples**:
es la solución exacta del GBM, no un ajuste discrecional. (Lo verifiqué contra
la literatura antes de tocarlo, porque parecía un error y no lo era.)

**Tres motores, no uno.** El problema del Monte Carlo anterior no era la
fórmula, era el supuesto: sorteaba `Z` de una normal cuando el propio módulo de
riesgo detecta que estos retornos siguen una t de Student con ~4 grados de
libertad. Una normal subestima las colas justo donde importa: en el escenario
malo.

    normal      la referencia clásica; subestima eventos extremos
    t           t de Student escalada a varianza unitaria; colas gordas
    bootstrap   remuestrea bloques del histórico real; sin supuesto de
                distribución y conserva el agrupamiento de volatilidad

El bootstrap por bloques es el más honesto de los tres: no inventa una
distribución, reordena la historia. Y al tomar bloques de ~21 ruedas en vez de
días sueltos, conserva que las crisis son rachas y no días aislados.

**Cuánto cambia elegir uno u otro, medido sobre LEANDRO** (curtosis en exceso
9,96, ν ajustado 3,82):

    a UN día      cuantil 1 %: normal −2,326 σ  ·  t −2,655 σ   (+14 % de cola)
    a 1 semana    pérdida VaR 99 %: normal 11,9 %  ·  t 12,4 %  (+0,4 pp)
    a 1 mes       normal 22,0 %  ·  t 22,3 %                     (+0,3 pp)
    a 1 año       normal 49,8 %  ·  t 49,8 %                     (+0,1 pp)

O sea: **las colas gordas pesan muchísimo en el VaR de un día y se diluyen al
componer varios**, porque sumar retornos independientes acerca el resultado a
una normal. La conclusión práctica es que la corrección por colas rinde en el
VaR diario —donde está, vía Cornish-Fisher en `risk.py`— y que acá los tres
motores dan casi lo mismo de una semana en adelante.

Se dejan los tres igual: cuestan poco, el bootstrap aporta una lectura sin
supuestos, y tener el número medido evita que alguien "arregle" más adelante
algo que no está roto.

Se simula la cartera **agregada** como un solo activo, no activo por activo con
la matriz de covarianza completa. Es una simplificación —la suma de lognormales
no es lognormal— y está declarada a propósito: a este horizonte el resultado es
muy parecido y el cálculo es órdenes de magnitud más barato.
"""

import numpy as np
from scipy import stats

RUEDAS = 252
_SEMILLA = 7


def _sortear(motor: str, retornos, n_sims: int, horizonte: int, rng):
    """Matriz (n_sims × horizonte) de retornos logarítmicos simulados."""
    r = np.asarray(retornos, dtype=float)
    mu, sigma = float(r.mean()), float(r.std(ddof=1))
    deriva = mu - 0.5 * sigma ** 2

    if motor == "bootstrap":
        # Bloques solapados de ~un mes bursátil: conserva rachas de volatilidad
        # y autocorrelación, que un sorteo día a día destruye.
        bloque = min(21, max(2, len(r) // 10))
        n_bloques = int(np.ceil(horizonte / bloque))
        inicios = rng.integers(0, len(r) - bloque + 1, size=(n_sims, n_bloques))
        muestras = np.concatenate(
            [r[i:i + bloque] for fila in inicios for i in fila]
        ).reshape(n_sims, n_bloques * bloque)[:, :horizonte]
        return np.log1p(muestras)

    if motor == "t":
        gl = max(2.5, float(stats.t.fit(r)[0]))          # ν estimado de los datos
        escala = np.sqrt((gl - 2) / gl)                  # a varianza unitaria
        z = rng.standard_t(gl, size=(n_sims, horizonte)) * escala
    else:
        z = rng.standard_normal((n_sims, horizonte))

    return deriva + sigma * z


def simular(posiciones, horizonte: int = 252, n_sims: int = 10_000,
            motor: str = "t") -> dict:
    """Abanico de trayectorias a `horizonte` ruedas.

    motor: "normal" · "t" (por defecto) · "bootstrap".
    Semilla fija: dos corridas con los mismos datos dan lo mismo.
    """
    from core.models.portfolio import matriz_retornos, value_weights

    ret_df, precios = matriz_retornos(posiciones)
    if ret_df.empty:
        return {"error": "Sin datos para simular."}

    tickers = list(ret_df.columns)
    w = value_weights(posiciones, precios, tickers)
    cartera = ret_df[tickers].to_numpy() @ w
    valor_inicial = sum(float(p.get("qty", 0)) * precios[t]
                        for p in posiciones
                        for t in [str(p["ticker"]).upper()] if t in precios)
    if valor_inicial <= 0:
        return {"error": "Valor inicial de la cartera inválido."}

    rng = np.random.default_rng(_SEMILLA)
    log_ret = _sortear(motor, cartera, n_sims, horizonte, rng)
    trayectorias = valor_inicial * np.exp(np.cumsum(log_ret, axis=1))
    finales = trayectorias[:, -1]

    # Se submuestrea el eje temporal: 252 puntos por serie × 5 series es más de
    # lo que cualquier gráfico puede mostrar.
    paso = max(1, horizonte // 100)
    cortes = sorted(set(list(range(0, horizonte, paso)) + [horizonte - 1]))
    dias = [i + 1 for i in cortes]

    def percentil(q):
        return [round(float(np.percentile(trayectorias[:, i], q)), 2) for i in cortes]

    var95 = float(np.percentile(finales, 5))
    var99 = float(np.percentile(finales, 1))
    cola = finales[finales <= var95]

    # Distribución de valores finales: histograma + los dos ajustes teóricos.
    conteo, bordes = np.histogram(finales, bins=60)
    centros = (bordes[:-1] + bordes[1:]) / 2
    ancho = float(centros[1] - centros[0]) if len(centros) > 1 else 1.0
    escala = n_sims * ancho
    normal = stats.norm.pdf(centros, finales.mean(), finales.std(ddof=1)) * escala
    try:
        forma, loc, esc = stats.lognorm.fit(finales, floc=0)
        lognormal = stats.lognorm.pdf(centros, forma, loc, esc) * escala
        mejor = ("lognormal"
                 if stats.kstest(finales, "lognorm", args=(forma, loc, esc)).statistic
                 <= stats.kstest(finales, "norm",
                                 args=(finales.mean(), finales.std(ddof=1))).statistic
                 else "normal")
    except Exception:
        lognormal, mejor = np.zeros_like(centros), "normal"

    return {
        "motor": motor,
        "horizonte_ruedas": horizonte,
        "n_simulaciones": n_sims,
        "valor_inicial": round(valor_inicial, 2),

        "abanico": {
            "dias": dias,
            "p5": percentil(5), "p25": percentil(25), "p50": percentil(50),
            "p75": percentil(75), "p95": percentil(95),
        },

        "final": {
            "mediana": round(float(np.median(finales)), 2),
            "p5": round(float(np.percentile(finales, 5)), 2),
            "p95": round(float(np.percentile(finales, 95)), 2),
            "var95": round(var95, 2),
            "var99": round(var99, 2),
            "cvar95": round(float(cola.mean()) if cola.size else var95, 2),
            # Cuánto de la cartera está comprometido en el escenario malo: es la
            # lectura que le sirve a alguien que mira su propio dinero.
            "perdida_var95_pct": round((valor_inicial - var95) / valor_inicial * 100, 2),
            "perdida_var99_pct": round((valor_inicial - var99) / valor_inicial * 100, 2),
            "prob_ganancia": round(float((finales > valor_inicial).mean()) * 100, 1),
        },

        "distribucion": {
            "x": [round(float(v), 2) for v in centros],
            "y": [int(c) for c in conteo],
            "normal": [round(float(v), 2) for v in normal],
            "lognormal": [round(float(v), 2) for v in lognormal],
            "mejor_ajuste": mejor,
        },

        "trayectorias_muestra": [
            [round(float(trayectorias[s, i]), 2) for i in cortes]
            for s in rng.choice(n_sims, size=min(50, n_sims), replace=False)
        ],
    }


def comparar_motores(posiciones, horizonte: int = 252, n_sims: int = 10_000) -> dict:
    """Los tres motores sobre la misma cartera.

    Es el argumento visible de por qué el supuesto importa: la diferencia entre
    el VaR normal y el de colas gordas es cuánto riesgo esconde suponer que los
    retornos se portan bien.
    """
    salida = {}
    for motor in ("normal", "t", "bootstrap"):
        r = simular(posiciones, horizonte, n_sims, motor)
        if "error" not in r:
            salida[motor] = {
                "var95": r["final"]["var95"],
                "perdida_var95_pct": r["final"]["perdida_var95_pct"],
                "var99": r["final"]["var99"],
                "perdida_var99_pct": r["final"]["perdida_var99_pct"],
                "mediana": r["final"]["mediana"],
                "prob_ganancia": r["final"]["prob_ganancia"],
            }
    return salida
