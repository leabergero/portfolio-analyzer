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
    mu, sd = finales.mean(), finales.std(ddof=1)
    normal = stats.norm.pdf(centros, mu, sd) * escala
    try:
        forma, loc, esc = stats.lognorm.fit(finales, floc=0)
        lognormal = stats.lognorm.pdf(centros, forma, loc, esc) * escala
        # `kstest(datos, "norm", args=(...))` revienta en scipy 1.18
        # (`ndtr() takes from 1 to 2 positional arguments`) y el except dejaba
        # el ajuste lognormal en cero: se dibujaba una línea plana sobre el eje
        # y el veredicto caía siempre en "normal" sin haber comparado nada.
        # Igual que en risk.py: se pasa la CDF ya evaluada.
        ks_log = stats.kstest(finales, lambda v: stats.lognorm.cdf(v, forma, loc, esc)).statistic
        ks_norm = stats.kstest(finales, lambda v: stats.norm.cdf(v, mu, sd)).statistic
        mejor = "lognormal" if ks_log <= ks_norm else "normal"
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


def por_activo(posiciones, horizonte: int = 252, n_sims: int = 4000,
               motor: str = "t") -> dict:
    """Simula cada activo por separado, además de la cartera.

    Responde qué activo puede hundir el resultado, que el agregado esconde: la
    cartera promedia, y promediar es exactamente lo que oculta el caso
    individual. Cada activo se simula con SU propio μ y σ, así que un papel
    volátil muestra su abanico real y no el suavizado del conjunto.

    Menos simulaciones que el agregado a propósito: son N activos y el objetivo
    acá es comparar formas, no afinar el tercer decimal de un percentil.
    """
    from core.models.portfolio import matriz_retornos, value_weights

    ret_df, precios = matriz_retornos(posiciones)
    if ret_df.empty:
        return {"error": "Sin datos para simular."}

    tickers = list(ret_df.columns)
    w = value_weights(posiciones, precios, tickers)
    valor_total = sum(float(p.get("qty", 0)) * precios[t]
                      for p in posiciones
                      for t in [str(p["ticker"]).upper()] if t in precios)
    rng = np.random.default_rng(_SEMILLA)

    filas = []
    for i, t in enumerate(tickers):
        r = ret_df[t].to_numpy()
        valor = float(w[i]) * valor_total
        if valor <= 0:
            continue
        finales = valor * np.exp(
            _sortear(motor, r, n_sims, horizonte, rng).sum(axis=1))
        var95 = float(np.percentile(finales, 5))
        filas.append({
            "ticker": t,
            "valor_inicial": round(valor, 2),
            "peso_pct": round(float(w[i]) * 100, 2),
            "mediana": round(float(np.median(finales)), 2),
            "p5": round(var95, 2),
            "p95": round(float(np.percentile(finales, 95)), 2),
            "perdida_var95_pct": round((valor - var95) / valor * 100, 2),
            "prob_ganancia": round(float((finales > valor).mean()) * 100, 1),
            # Rango entre el buen y el mal escenario, como múltiplo del valor de
            # hoy: cuánta incertidumbre trae este activo a la cartera.
            "amplitud": round(float(np.percentile(finales, 95) - var95) / valor, 2),
        })

    cartera = ret_df[tickers].to_numpy() @ w
    finales_c = valor_total * np.exp(
        _sortear(motor, cartera, n_sims, horizonte, rng).sum(axis=1))
    var95_c = float(np.percentile(finales_c, 5))

    suma_individual = sum(f["valor_inicial"] - f["p5"] for f in filas)
    perdida_cartera = valor_total - var95_c

    return {
        "motor": motor, "horizonte_ruedas": horizonte, "n_simulaciones": n_sims,
        "por_activo": sorted(filas, key=lambda f: -f["perdida_var95_pct"]),
        "cartera": {
            "ticker": "CARTERA", "valor_inicial": round(valor_total, 2), "peso_pct": 100.0,
            "mediana": round(float(np.median(finales_c)), 2),
            "p5": round(var95_c, 2),
            "p95": round(float(np.percentile(finales_c, 95)), 2),
            "perdida_var95_pct": round(perdida_cartera / valor_total * 100, 2),
            "prob_ganancia": round(float((finales_c > valor_total).mean()) * 100, 1),
            "amplitud": round(float(np.percentile(finales_c, 95) - var95_c) / valor_total, 2),
        },
        "ahorro_diversificacion_usd": round(suma_individual - perdida_cartera, 2),
        "nota": "Si los activos cayeran todos a la vez en su escenario malo, la pérdida "
                f"sería ${suma_individual:,.0f}. La de la cartera es ${perdida_cartera:,.0f}: "
                "la diferencia es lo que aporta que no caigan sincronizados.",
    }


def correlaciones_moviles(posiciones, ventana: int = 63, pasos: int = 40) -> dict:
    """Cómo evolucionó la correlación entre los activos, para animar.

    Una matriz de correlaciones es una foto de un promedio, y esconde el hecho
    más importante del riesgo de cartera: **las correlaciones no son estables**.
    Suben en las crisis, justo cuando la diversificación tendría que proteger.
    Ver la matriz moverse muestra eso de una forma que un número promedio no
    puede.
    """
    from core.models.portfolio import matriz_retornos
    from core.models.regimenes import EVENTOS

    ret_df, _ = matriz_retornos(posiciones)
    if ret_df.shape[1] < 2 or len(ret_df) < ventana + 20:
        return {"error": "Serie demasiado corta para una correlación móvil."}

    tickers = list(ret_df.columns)

    # Primera rueda a partir de la cual TODOS los activos tienen cotización real.
    # `matriz_retornos` rellena con ceros lo que todavía no existía, así que sin
    # esto los pasos se reparten sobre un rango donde la mayoría de las ventanas
    # no son calculables y la animación queda con cuatro cuadros.
    vivos = (ret_df.abs() > 1e-12).cumsum() > 0
    primera = int(np.argmax(vivos.all(axis=1).to_numpy())) if vivos.all(axis=1).any() else 0
    arranque = max(ventana, primera + ventana)
    if arranque >= len(ret_df) - 1:
        return {"error": "No hay historia en común suficiente entre todos los activos "
                         "para una correlación móvil: probá una ventana más corta."}

    indices = np.linspace(arranque, len(ret_df) - 1,
                          min(pasos, len(ret_df) - arranque), dtype=int)

    cuadros = []
    for i in indices:
        tramo = ret_df.iloc[i - ventana:i]
        # Un activo que todavía no cotizaba llega como serie constante —
        # `matriz_retornos` rellena con ceros— y su correlación es NaN, que
        # después contamina la media y el gráfico entero. Esas ventanas se
        # descartan en vez de dibujarlas vacías: no hay correlación que mostrar
        # cuando el activo no existía.
        if (tramo.std(ddof=1) < 1e-12).any():
            continue
        m = tramo.corr()
        if m.isna().to_numpy().any():
            continue
        valores = [[round(float(m.loc[a, b]), 3) for b in tickers] for a in tickers]
        pares = [float(m.loc[a, b]) for j, a in enumerate(tickers) for b in tickers[j + 1:]]
        cuadros.append({
            "fecha": str(ret_df.index[i].date()),
            "matriz": valores,
            "media": round(float(np.mean(pares)), 3) if pares else 0.0,
        })

    if not cuadros:
        return {"error": "No hay ninguna ventana donde todos los activos tengan "
                         "cotización: probá con una ventana más corta."}

    medias = [c["media"] for c in cuadros]
    pico = max(cuadros, key=lambda c: c["media"])
    piso = min(cuadros, key=lambda c: c["media"])
    desde, hasta = cuadros[0]["fecha"], cuadros[-1]["fecha"]

    return {
        "tickers": tickers, "cuadros": cuadros, "ventana_ruedas": ventana,
        "media_global": round(float(np.mean(medias)), 3),
        "maximo": {"fecha": pico["fecha"], "media": pico["media"]},
        "minimo": {"fecha": piso["fecha"], "media": piso["media"]},
        "eventos": [{"fecha": f, "alcance": a, "descripcion": d}
                    for f, a, d in EVENTOS if desde <= f <= hasta],
        "nota": f"Correlación sobre las últimas {ventana} ruedas en cada punto. "
                "Que suba significa que los activos empiezan a moverse juntos y la "
                "diversificación deja de proteger.",
    }
