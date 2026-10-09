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

    ret_df, precios = matriz_retornos(posiciones, larga=False)
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
    return {"motor": motor, **_salida(trayectorias, valor_inicial, horizonte, rng)}


def _salida(trayectorias, valor_inicial, horizonte, rng, n_muestra: int = 50) -> dict:
    """Abanico, percentiles finales e histograma de un juego de trayectorias.

    La comparten los dos modelos (`simular` y `simular_fhs`) para que el panel
    de la app dibuje cualquiera de los dos sin saber cuál es.
    """
    n_sims = len(trayectorias)
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
            for s in rng.choice(n_sims, size=min(n_muestra, n_sims), replace=False)
        ],
    }


# ── Modelo propuesto (lab 11): simulación histórica filtrada ────────────────
#
# Elegido por backtest (2026-10): 47.500 pronósticos a un año, orígenes
# mensuales 2006–2025, 300 carteras (índices, CEDEARs, acciones argentinas,
# europeas, latinas en EE. UU., bonos y las carteras reales). En cada fecha se
# calibró sólo con el pasado y se comparó contra lo que pasó (CRPS). Le gana al
# modelo actual en todos los grupos, Argentina y las carteras reales incluidas.
# Las decisiones, cada una medida:
#
#   1. HISTORIA LARGA. Un CEDEAR se calibra con su subyacente (AAPLD.BA desde
#      2021 → AAPL desde 2005), y una acción argentina pasa a dólares con el MEP
#      y, antes de 2019, con el CCL implícito de GGAL (`mep.serie_larga`).
#
#   2. VOLATILIDAD CONDICIONAL (FHS, Barone-Adesi 1999). Cada retorno se divide
#      por su vol EWMA del día; esos shocks se remuestrean en bloques de 21
#      ruedas, TODOS los activos de la misma fecha juntos (conserva las
#      correlaciones reales, también las de crisis, sin Cholesky ni normalidad),
#      y se reescalan con una vol que arranca en la de hoy y vuelve a la de largo
#      plazo con vida media de 120 ruedas. Es el que reacciona cuando el mercado
#      ya está nervioso: en 2007–2012 el error bajó 11 %.
#
#   3. DERIVA ENCOGIDA (bayesiana). La media histórica de unos años tiene un
#      error estándar de ±7 a ±25 pp anuales; usada tal cual, la app le daba
#      95 % de chances de ganar a MAMI. Se combina con el CAPM pesando cada una
#      por su precisión (τ = 8 %: el CAPM ± 8 pp de duda a priori).
#
#   4. CADA ACTIVO CONTRA SU MERCADO. CAPM = rf + β·(5 % + CRP del país): la
#      prima de riesgo país de Damodaran (`riesgo_pais`) es lo que más sumó
#      (t ≈ 2,3), sobre todo en Argentina y en las latinas que cotizan en EE. UU.
#      La β se mide contra el índice local cuando el activo cotiza en su plaza
#      (BYMA, Europa, ETF de país) y contra SPY cuando es una extranjera que
#      forman inversores globales (NU, MELI, TSM); medida así o toda contra SPY
#      dio lo mismo, la diferencia la hace la prima. β semanal: en diario la
#      asincronía horaria (Taiwán cierra antes de que abra Nueva York) daba β ≈ 0.
#
# Lo que NO arregla: ningún modelo previó el piso de las crisis que empiezan en
# calma (2007–2012: 16 % de los resultados bajo el percentil 5), las acciones
# argentinas sueltas tienen colas más gordas que las simuladas (12 % bajo el
# p5), y China queda optimista: su riesgo es regulatorio, no de default, y el
# spread soberano no lo mide.

_ERP, _TAU, _VIDA_MEDIA, _BLOQUE, _LAMBDA = 0.05, 0.08, 120, 21, 0.94

# Empresas que facturan en varios países: la prima país va ponderada por
# ingresos (Damodaran), no por la sede — yfinance da Uruguay para MELI.
# ponytail: a mano, revisar con los balances una vez por año.
_PAIS_POR_INGRESOS = {"MELI": {"Brazil": .55, "Argentina": .25, "Mexico": .20}}
_EUROPA = ("Germany", "France", "Netherlands", "Spain", "Italy", "Belgium", "Austria",
           "Ireland", "Finland", "Portugal", "Europe", "Eurozone")
_INDICE = {"Argentina": "^MERV", "Brazil": "^BVSP", "China": "MCHI", "Japan": "EWJ",
           "Taiwan": "EWT", **{p: "^STOXX" for p in _EUROPA}}
_SUFIJOS_EU = (".AS", ".PA", ".DE", ".MC", ".MI", ".BR", ".LS", ".VI", ".HE", ".IR")


def _limpiar(s):
    """Sin fines de semana (los bonos de Cocos traen ruedas de domingo con un
    precio de otra moneda) y sin picos de un día que se revierten al siguiente."""
    import pandas as pd
    s = s[pd.DatetimeIndex(s.index).dayofweek < 5]
    l = np.log(s.to_numpy(dtype=float))
    malo = np.zeros(len(l), bool)
    for i in range(1, len(l) - 1):
        if abs(l[i] - l[i - 1]) > 0.2 and abs(l[i + 1] - l[i - 1]) < 0.06:
            malo[i] = True
    return s[~malo]


def _serie_larga(ticker, source):
    """(serie propia, serie para calibrar, de dónde salió la historia o None)."""
    from core import mercado
    from core.data import mep, sources, symbols
    propia = sources.precios_base(ticker, source=source)
    if symbols.is_bond(ticker, source):
        return propia, propia, None
    base = symbols.base_symbol(ticker)
    larga, origen = None, None
    try:
        if base != symbols.strip_ba(ticker):                    # CEDEAR → subyacente
            larga, origen = sources.precios_base(base), base
        elif symbols.ticker_currency(ticker) == "ARS":          # acción local
            crudo = sources.precios(ticker, source=source)["Close"].dropna()
            larga, origen = mercado.desde_usd(mep.serie_a_usd(crudo, mep.serie_larga())), "MEP + CCL"
    except Exception:
        larga = None
    if larga is not None and len(larga) > len(propia) + 252:
        return propia, larga, origen
    return propia, propia, None


def _pais_y_mercado(ticker, source):
    """(país o mezcla por ingresos, índice local contra el que medir β o None
    para medirla contra SPY)."""
    from core.data import sources
    from core.models import composicion
    base = sources.base_symbol(ticker)
    if base in _PAIS_POR_INGRESOS:
        return _PAIS_POR_INGRESOS[base], None
    tipo, ficha = composicion._clasificar_tipo(ticker, base, source)
    pais = composicion._clasificar_pais(ticker, base, tipo, ficha)
    en_su_plaza = (sources.is_bond(ticker, source) or ticker.endswith(_SUFIJOS_EU)
                   or base in composicion.PAISES_ETF
                   or (ticker.endswith(".BA") and base == sources.strip_ba(ticker)))
    return pais, (_INDICE.get(pais) if en_su_plaza else None)


def _indice(simbolo):
    """Índice local en la moneda de medición, fecha por fecha."""
    from core import mercado
    from core.data import mep, sources
    if simbolo not in ("^MERV", "^BVSP", "^STOXX"):
        return sources.precios_base(simbolo)                    # ETFs en dólares
    crudo = sources.precios(simbolo)["Close"].dropna()
    if simbolo == "^MERV":
        usd = mep.serie_a_usd(crudo, mep.serie_larga())
    elif simbolo == "^BVSP":
        brl = sources.precios("BRL=X")["Close"].dropna()
        usd = (crudo / brl.reindex(crudo.index, method="ffill")).dropna()
    else:
        usd = mercado.a_usd(crudo, "EUR")
    return mercado.desde_usd(usd)


def _beta_semanal(x, m):
    """β con retornos semanales; neutra (1) con menos de un año en común."""
    n = len(x) // 5 * 5
    if n < 252:
        return 1.0
    x, m = x[-n:].reshape(-1, 5).sum(1), m[-n:].reshape(-1, 5).sum(1)
    return float(np.cov(x, m)[0, 1] / m.var(ddof=1))


def calibrar(posiciones, horizonte: int = 252, hasta=None) -> dict:
    """Todo lo que el modelo propuesto sabe de cada activo, sin simular nada.

    Lo comparten el Monte Carlo (`simular_fhs`, `por_activo_fhs`,
    `motores_fhs`) y Markowitz en el lab 11 (`esperados`): los mismos
    rendimientos esperados, volatilidades y correlaciones de los dos lados, o
    la optimización y el abanico contarían dos historias de la misma cartera.
    `hasta` corta la historia en esa fecha (para probar fuera de muestra).
    """
    import pandas as pd
    from core.data import riesgo_pais, sources
    from core.models import rates

    qty, origen = {}, {}
    for p in posiciones:
        if p.get("source") == sources.SOURCE_FCI:      # la caja no se simula
            continue
        t = str(p["ticker"]).upper()
        qty[t] = qty.get(t, 0.0) + float(p.get("qty", 0))
        origen.setdefault(t, p.get("source") or None)

    precio, calib, proxy = {}, {}, {}
    for t in qty:
        propia, larga, sub = _serie_larga(t, origen[t])
        if hasta is not None:
            larga = larga[larga.index <= pd.Timestamp(hasta)]
        if len(propia) == 0 or len(larga) < 30:
            continue
        precio[t] = float(propia.iloc[-1])
        calib[t], proxy[t] = _limpiar(larga.dropna()), sub
    tickers = [t for t in calib if qty[t] * precio[t] > 0]
    if not tickers:
        return {"error": "Sin datos para simular."}
    valor = np.array([qty[t] * precio[t] for t in tickers])
    valor_inicial = float(valor.sum())
    w = valor / valor_inicial

    # Precios (no retornos) alineados: un día sin rueda repite el precio. La
    # ventana común la fija el activo más nuevo; sirve para los shocks
    # conjuntos (las correlaciones). Deriva y vol de largo plazo salen de la
    # historia COMPLETA de cada activo: AAPL no pierde 13 años porque NU nació
    # en 2021.
    todo = pd.DataFrame(calib).sort_index().ffill()
    px = todo.dropna()
    X = np.log(px[tickers]).diff().iloc[1:].to_numpy()
    T, N = X.shape
    if T < 60:
        return {"error": "Hace falta al menos tres meses de historia común para simular."}
    indices = {}

    def indice(simbolo):
        if simbolo not in indices:
            try:
                s_ = _indice(simbolo)
                indices[simbolo] = s_[s_.index <= pd.Timestamp(hasta)] if hasta is not None else s_
            except Exception:
                indices[simbolo] = None
        return indices[simbolo]

    # Deriva: media histórica encogida hacia el CAPM de su mercado.
    rf, rf_txt = rates.risk_free_para()
    m, v, largo, beta, Ts, crp = (np.empty(N) for _ in range(6))
    paises, mercados = [], []
    bono = np.array([sources.is_bond(t, origen[t]) for t in tickers])
    for i, t in enumerate(tickers):
        x = np.log(calib[t]).diff().dropna()
        Ts[i], m[i], v[i] = len(x), np.expm1(x).mean(), x.var(ddof=1)
        largo[i] = np.sqrt(v[i])
        try:
            pais, local = _pais_y_mercado(t, origen[t])
        except Exception:
            pais, local = None, None
        mk = indice(local) if local else None
        if mk is None:
            local, mk = "SPY", indice("SPY")
        par = pd.DataFrame({"x": calib[t], "m": mk}).sort_index().ffill().dropna() if mk is not None else None
        r_ = np.log(par).diff().dropna() if par is not None else None
        beta[i] = _beta_semanal(r_["x"].to_numpy(), r_["m"].to_numpy()) if r_ is not None else 1.0
        crp[i] = (riesgo_pais.spread_default if bono[i] else riesgo_pais.prima)(pais) if pais else 0.0
        paises.append(pais if isinstance(pais, str) or pais is None
                      else " + ".join(f"{p} {w:.0%}" for p, w in pais.items()))
        mercados.append(local)
    beta = 0.33 + 0.67 * beta                          # Blume: vuelven hacia 1
    # Un bono no cobra prima de acciones: su prior es la tasa libre más el
    # spread de default del país (un CAPM de acciones les daba 20 % anual a
    # ONs que rinden 8 %). ponytail: el ideal es la TIR de cada bono, cuando
    # `analizar_bono` la dé para todos los de la cartera.
    capm = np.where(bono, rf + crp, rf + beta * (_ERP + crp)) / 252
    prec_dato, prec_prior = Ts / np.maximum(v, 1e-12), 1 / (_TAU / 252) ** 2
    peso_dato = prec_dato / (prec_dato + prec_prior)
    a = peso_dato * m + (1 - peso_dato) * capm         # aritmética diaria

    # Shocks filtrados por su vol EWMA, y la vol de hoy hacia la de largo plazo.
    Y = X - X.mean(0)
    var_ewma = np.empty_like(Y)
    var_ewma[0] = Y[:21].var(0) + 1e-12
    for i in range(1, T):
        var_ewma[i] = _LAMBDA * var_ewma[i - 1] + (1 - _LAMBDA) * Y[i - 1] ** 2
    hoy = np.sqrt(_LAMBDA * var_ewma[-1] + (1 - _LAMBDA) * Y[-1] ** 2)
    Z = Y / np.sqrt(var_ewma)
    Z = Z / Z.std(0, ddof=1)
    phi = 0.5 ** (1 / _VIDA_MEDIA)
    var_k = largo ** 2 + (hoy ** 2 - largo ** 2) * phi ** np.arange(horizonte)[:, None]

    anual = lambda x: float(np.expm1(x * 252) * 100)
    activos = [{
        "ticker": t, "peso_pct": round(float(w[i]) * 100, 1), "calibrado_con": proxy[t] or t,
        "anios": round(float(Ts[i]) / 252, 1), "beta": round(float(beta[i]), 2),
        "pais": paises[i], "mercado": mercados[i], "crp_pct": round(float(crp[i]) * 100, 2),
        "deriva_historica_pct": round(anual(m[i]), 1), "deriva_capm_pct": round(anual(capm[i]), 1),
        "deriva_usada_pct": round(anual(a[i]), 1), "peso_historia_pct": round(float(peso_dato[i]) * 100),
        "vol_hoy_pct": round(float(hoy[i] * np.sqrt(252) * 100), 1),
        "vol_largo_pct": round(float(largo[i] * np.sqrt(252) * 100), 1),
    } for i, t in enumerate(tickers)]
    return {"tickers": tickers, "valor": valor, "w": w, "valor_inicial": valor_inicial,
            "precios": {t: precio[t] for t in tickers}, "px": px, "X": X, "Y": Y, "Z": Z,
            "a": a, "largo": largo, "var_k": var_k, "activos": activos,
            "modelo": {"nombre": "Simulación histórica filtrada · deriva bayesiana",
                       "desde": str(px.index[0].date()), "anios": round(T / 252, 1), "rf": rf_txt,
                       "historia_corta": T < 252,
                       "erp_pct": _ERP * 100, "tau_pct": _TAU * 100, "vida_media_vol": _VIDA_MEDIA,
                       "activos": activos}}


def _log_trayectorias(cal, n_sims, horizonte, rng, motor="fhs"):
    """De a mil escenarios: log-precio acumulado de cada activo (s × H × N).

    fhs        shocks filtrados por su EWMA, remuestreados en bloques conjuntos,
               con la vol de hoy volviendo a la de largo plazo (el propuesto)
    bootstrap  bloques conjuntos de los retornos tal cual, vol de largo plazo
    normal     normal multivariante (Cholesky de la correlación), vol de largo
    Los tres con la MISMA deriva: lo que los separe es el supuesto de
    distribución, no cuánto se espera ganar.
    """
    Z, Y, a, largo = cal["Z"], cal["Y"], cal["a"], cal["largo"]
    T, N = Z.shape
    if motor == "fhs":
        var_k = cal["var_k"][:horizonte]
        shocks, escala, deriva = Z, np.sqrt(var_k), a - 0.5 * var_k
    else:
        shocks = Y / Y.std(0, ddof=1)
        escala, deriva = largo, a - 0.5 * largo ** 2
    chol = np.linalg.cholesky(np.corrcoef(shocks.T).reshape(N, N) + 1e-10 * np.eye(N))
    n_bloques = -(-horizonte // _BLOQUE)
    for desde in range(0, n_sims, 1000):               # de a mil: memoria acotada
        s_ = min(1000, n_sims - desde)
        if motor == "normal":
            z = rng.standard_normal((s_, horizonte, N)) @ chol.T
        else:
            ini = rng.integers(0, T - _BLOQUE + 1, size=(s_, n_bloques))
            z = shocks[(ini[:, :, None] + np.arange(_BLOQUE)).reshape(s_, -1)[:, :horizonte]]
        yield np.cumsum(z * escala + deriva, axis=1)


def esperados(posiciones, hasta=None) -> dict:
    """Insumos de media-varianza del modelo propuesto, anuales.

    μ es la deriva bayesiana (CAPM de su mercado + riesgo país, encogida con
    la historia); Σ = D·ρ·D con la vol de largo plazo de cada activo (su
    historia completa) y la correlación de la ventana común. Backtest de
    2026-10 (12.000 carteras óptimas mantenidas un año, 2007–2025): con esta
    μ el máximo Sharpe rindió Sharpe 0,79 contra 0,74 con la histórica, con
    menos caída (−21 % vs −24 %) y más diversificado. Usar la vol del Monte
    Carlo (de la de hoy a la de largo plazo) no mejoró nada y duplicaba la
    rotación trimestral (17 % vs 9 % de la cartera): para decidir pesos
    conviene la de largo plazo, que no se mueve con cada semana nerviosa.
    """
    cal = calibrar(posiciones, hasta=hasta)
    if "error" in cal:
        return cal
    N = len(cal["tickers"])
    d = cal["largo"] * np.sqrt(252)
    rho = np.corrcoef(cal["Y"].T).reshape(N, N)
    return {**cal, "mu": cal["a"] * 252, "cov": rho * np.outer(d, d)}


def _ajustar(cal, deriva_anual=None, vol_anual=None):
    """Reemplaza en la calibración la deriva y/o la vol de algunos activos."""
    if "error" in cal:
        return cal
    tk = cal["tickers"]
    for t, mu in (deriva_anual or {}).items():
        if t in tk:
            cal["a"][tk.index(t)] = mu / 252
    for t, sd in (vol_anual or {}).items():
        if t in tk:
            cal["var_k"][:, tk.index(t)] = (sd / np.sqrt(252)) ** 2
    return cal


def simular_fhs(posiciones, horizonte: int = 252, n_sims: int = 10_000,
                deriva_anual: dict = None, vol_anual: dict = None) -> dict:
    """Abanico a `horizonte` ruedas con el modelo propuesto (ver arriba).

    `deriva_anual` y `vol_anual` ({ticker: fracción}) reemplazan lo que el
    modelo calibró para esos activos: es como corre el escenario "según los
    analistas" (`escenario_analistas`). El resto —shocks, correlaciones— no
    cambia, así los dos abanicos se comparan con la misma suerte.
    """
    cal = _ajustar(calibrar(posiciones, horizonte), deriva_anual, vol_anual)
    if "error" in cal:
        return cal
    rng = np.random.default_rng(_SEMILLA)
    trayectorias = np.concatenate([np.exp(L) @ cal["valor"]
                                   for L in _log_trayectorias(cal, n_sims, horizonte, rng)])
    # 200 trayectorias de muestra: el abanico se dibuja con ellas (lab 11), y
    # con 50 se ven sueltas en vez de una nube.
    return {"motor": "fhs", "modelo": cal["modelo"],
            **_salida(trayectorias, cal["valor_inicial"], horizonte, rng, n_muestra=200)}


def escenario_analistas(posiciones, opiniones: dict = None, horizonte: int = 252) -> dict:
    """El Monte Carlo con el rendimiento esperado de Black-Litterman.

    BL parte del rendimiento esperado de este modelo y lo corrige con los
    precios objetivo de los analistas y con los precios que el usuario fijó a
    mano (`store.opiniones`). Es "lo que dicen los analistas" —sus objetivos
    suelen ser optimistas y no hay historia para probarlos—; el escenario de
    siempre es el del modelo.

    Un evento con fecha (modo B2: una OPA, un canje) no se proyecta como la
    tasa anualizada que usa BL: una OPA que paga 10 % en 3 meses no rinde 46 %
    en el año, rinde ese 10 % y después la tasa libre sobre la plata cobrada.
    Y el rango que fijó el usuario es su incertidumbre: se toma como el 90 %
    central del resultado, en lugar de la volatilidad de toda la historia del
    papel, que ya no es la del activo una vez anunciada la oferta.
    """
    aj = ajustes_analistas(posiciones, opiniones)
    if "error" in aj:
        return aj
    salida = simular_fhs(posiciones, horizonte, deriva_anual=aj["deriva"], vol_anual=aj["vol"])
    if "error" in salida:
        return salida
    salida["escenario"] = aj["escenario"]
    return salida


def ajustes_analistas(posiciones, opiniones: dict = None) -> dict:
    """La deriva de Black-Litterman y la vol de los eventos fijados, por activo
    (ver `escenario_analistas`). La comparten el abanico y `por_activo_fhs`."""
    from core.models import blacklitterman, momentum, rates, targets

    rf, _ = rates.risk_free_para()
    views = blacklitterman.views_combinadas(targets.analizar(posiciones),
                                            momentum.analizar(posiciones), opiniones)
    vol, eventos = {}, []
    for v in views:
        if v.get("modo") != "B2" or not v.get("rango") or not v.get("precio_referencia"):
            continue
        bajo, alto = v["rango"]
        medio, m = (bajo + alto) / 2, max(1, int(v.get("meses") or 12))
        bruto = medio / v["precio_referencia"] - 1
        anio = (1 + bruto) * (1 + rf) ** (max(0, 12 - m) / 12) - 1 if m <= 12 else (1 + bruto) ** (12 / m) - 1
        v["ret"] = round(anio * 100, 2)
        # El rango es el 90 % central del precio al que se resuelve: ésa es toda
        # la incertidumbre del año, repartida pareja (después hay plata cobrada).
        vol[v["ticker"]] = max((alto - bajo) / medio / (2 * 1.645), 0.01)
        eventos.append({"ticker": v["ticker"], "meses": m, "precio": round(medio, 2),
                        "ret_12m_pct": v["ret"], "vol_pct": round(vol[v["ticker"]] * 100, 1)})
    bl = blacklitterman.analizar(posiciones, views, lab=True)
    if "error" in bl:
        return bl
    deriva = {t: r / 100 for t, r in bl["retornos_bl_pct"].items()}
    return {"deriva": deriva, "vol": vol, "escenario": {
        "nombre": "Según los analistas (Black-Litterman)",
        "views": [{"ticker": v["ticker"], "ret_pct": v["ret"], "confianza": v["confidence"],
                   "manual": bool(v.get("manual")), "modo": v.get("modo")} for v in views],
        "eventos": eventos,
        "deriva_pct": {t: round(r * 100, 2) for t, r in deriva.items()},
    }}


def motores_fhs(posiciones, horizonte: int = 252, n_sims: int = 10_000) -> dict:
    """Lab 11: los tres motores con la deriva del propuesto (ver `_log_trayectorias`)."""
    cal = calibrar(posiciones, horizonte)
    if "error" in cal:
        return cal
    v0, salida = cal["valor_inicial"], {}
    nombres = {"normal": "Normal multivariante (Cholesky)", "bootstrap": "Bootstrap por bloques",
               "fhs": "Simulación histórica filtrada (el de la app)"}
    for motor, nombre in nombres.items():
        rng = np.random.default_rng(_SEMILLA)
        fin = np.concatenate([np.exp(L[:, -1]) @ cal["valor"]
                              for L in _log_trayectorias(cal, n_sims, horizonte, rng, motor)])
        var95, var99 = float(np.percentile(fin, 5)), float(np.percentile(fin, 1))
        salida[nombre] = {
            "var95": round(var95, 2), "perdida_var95_pct": round((v0 - var95) / v0 * 100, 2),
            "var99": round(var99, 2), "perdida_var99_pct": round((v0 - var99) / v0 * 100, 2),
            "mediana": round(float(np.median(fin)), 2),
            "prob_ganancia": round(float((fin > v0).mean()) * 100, 1)}
    return salida


def por_activo_fhs(posiciones, horizonte: int = 252, n_sims: int = 4000,
                   deriva_anual: dict = None, vol_anual: dict = None) -> dict:
    """Lab 11: `por_activo` con el modelo propuesto. Los activos se simulan
    JUNTOS (los mismos escenarios), así que la suma de sus peores casos contra
    el de la cartera mide la diversificación con correlaciones reales."""
    cal = _ajustar(calibrar(posiciones, horizonte), deriva_anual, vol_anual)
    if "error" in cal:
        return cal
    rng = np.random.default_rng(_SEMILLA)
    fin = np.concatenate([np.exp(L[:, -1]) * cal["valor"]
                          for L in _log_trayectorias(cal, n_sims, horizonte, rng)])   # s × N
    return _armar_por_activo(cal["tickers"], cal["valor"], fin, fin.sum(1),
                             "fhs", horizonte, n_sims)


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

    ret_df, precios = matriz_retornos(posiciones, larga=False)
    if ret_df.empty:
        return {"error": "Sin datos para simular."}

    tickers = list(ret_df.columns)
    w = value_weights(posiciones, precios, tickers)
    valor_total = sum(float(p.get("qty", 0)) * precios[t]
                      for p in posiciones
                      for t in [str(p["ticker"]).upper()] if t in precios)
    rng = np.random.default_rng(_SEMILLA)
    cols, valores = [], []
    for i, t in enumerate(tickers):
        valor = float(w[i]) * valor_total
        if valor <= 0:
            continue
        cols.append(valor * np.exp(_sortear(motor, ret_df[t].to_numpy(), n_sims, horizonte, rng).sum(axis=1)))
        valores.append((t, valor))
    cartera = ret_df[tickers].to_numpy() @ w
    finales_c = valor_total * np.exp(_sortear(motor, cartera, n_sims, horizonte, rng).sum(axis=1))
    return _armar_por_activo([t for t, _ in valores], np.array([v for _, v in valores]),
                             np.column_stack(cols), finales_c, motor, horizonte, n_sims)


def _armar_por_activo(tickers, valores, finales, finales_c, motor, horizonte, n_sims) -> dict:
    """La tabla por activo y la de la cartera, desde los valores finales
    simulados (`finales`: escenarios × activos)."""
    valor_total = float(valores.sum())

    def fila(t, valor, fin):
        var95 = float(np.percentile(fin, 5))
        return {
            "ticker": t,
            "valor_inicial": round(valor, 2),
            "peso_pct": round(valor / valor_total * 100, 2),
            "mediana": round(float(np.median(fin)), 2),
            "p5": round(var95, 2),
            "p95": round(float(np.percentile(fin, 95)), 2),
            "perdida_var95_pct": round((valor - var95) / valor * 100, 2),
            "prob_ganancia": round(float((fin > valor).mean()) * 100, 1),
            # Rango entre el buen y el mal escenario, como múltiplo del valor de
            # hoy: cuánta incertidumbre trae este activo a la cartera.
            "amplitud": round(float(np.percentile(fin, 95) - var95) / valor, 2),
        }

    filas = [fila(t, float(valores[i]), finales[:, i]) for i, t in enumerate(tickers)]
    cart = fila("CARTERA", valor_total, finales_c)
    suma_individual = sum(f["valor_inicial"] - f["p5"] for f in filas)
    perdida_cartera = valor_total - float(np.percentile(finales_c, 5))

    return {
        "motor": motor, "horizonte_ruedas": horizonte, "n_simulaciones": n_sims,
        "por_activo": sorted(filas, key=lambda f: -f["perdida_var95_pct"]),
        "cartera": cart,
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
