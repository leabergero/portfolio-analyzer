"""
comparacion.py — Cuál de estas carteras es mejor, y si la diferencia es real.

El modo Comparación de las apps anteriores coronaba un ganador contando cuántos
de ocho criterios ganaba cada cartera. Eso responde **cuál se ve mejor**, no
cuál es mejor: con tres años de datos, un Sharpe de 1,2 contra uno de 0,9 puede
ser enteramente ruido. Este módulo agrega las tres piezas que faltaban.

**1. Período común.** Antes cada cartera se medía sobre su propia historia: una
con 1.268 ruedas contra otra con 1.724 no compara estrategias, compara épocas
distintas del mercado. Acá se recorta al tramo que todas comparten y se informa
cuánto se recortó.

**2. ¿La diferencia de Sharpe es real?** Jobson-Korkie con la corrección de
Memmel:

    θ = 2(1−ρ) + ½(S_A² + S_B²) − S_A·S_B(1+ρ²)
    z = (S_A − S_B) / √(θ/T)

Devuelve un valor p. "A supera a B por 0,31 de Sharpe, p = 0,18" es una
afirmación honesta; "A gana 5 de 8 criterios" no lo es.

**3. Sharpe deflactado.** Comparar muchas variantes garantiza encontrar una
buena por azar. Bailey y López de Prado corrigen por cuántas probaste y por que
los retornos no son normales. Es directamente pertinente a una herramienta cuyo
propósito es comparar configuraciones: sin esto, empuja a sobreajustar.

**4. Intervalos por remuestreo.** Una barra de error en cada número. Si los
intervalos de dos carteras se superponen, no hay ganador y hay que decirlo.
"""

import numpy as np
from scipy import stats

from core.models import risk

RUEDAS = 252
_SEMILLA = 11
EULER = 0.5772156649015329


# ── Pruebas estadísticas ──────────────────────────────────────────────────────

def _sharpe_periodo(r, rf_periodo=0.0) -> float:
    r = np.asarray(r, dtype=float)
    exceso = r - rf_periodo
    s = exceso.std(ddof=1)
    return float(exceso.mean() / s) if s > 0 else 0.0


def test_diferencia_sharpe(retornos_a, retornos_b, rf_anual: float = 0.0) -> dict:
    """¿La diferencia de Sharpe entre dos carteras es estadísticamente real?

    Jobson-Korkie con corrección de Memmel, sobre las series **alineadas**: la
    correlación entre ambas entra en el estadístico, y dos carteras que comparten
    activos están muy correlacionadas — ignorarlo sobrestima la significancia.
    """
    a = np.asarray(retornos_a, dtype=float)
    b = np.asarray(retornos_b, dtype=float)
    n = min(len(a), len(b))
    if n < 60:
        return {"concluyente": False, "motivo": "menos de 60 ruedas en común"}
    a, b = a[-n:], b[-n:]

    rf_d = rf_anual / RUEDAS
    sa, sb = _sharpe_periodo(a, rf_d), _sharpe_periodo(b, rf_d)
    rho = float(np.corrcoef(a, b)[0, 1]) if a.std() > 0 and b.std() > 0 else 0.0

    base = {
        "sharpe_a_anual": round(sa * np.sqrt(RUEDAS), 3),
        "sharpe_b_anual": round(sb * np.sqrt(RUEDAS), 3),
        "diferencia_anual": round((sa - sb) * np.sqrt(RUEDAS), 3),
        "correlacion": round(rho, 3),
        "n_ruedas": int(n),
    }

    theta = (2 * (1 - rho) + 0.5 * (sa ** 2 + sb ** 2) - sa * sb * (1 + rho ** 2))

    # Caso degenerado: dos series iguales (o casi) hacen θ ≤ 0, porque el
    # estadístico de Jobson-Korkie no está definido cuando no hay nada que
    # distinguir. La respuesta correcta no es "no se puede calcular" sino "no hay
    # diferencia": una cartera comparada consigo misma empata, y decirlo así
    # evita que la interfaz muestre un error donde hay una respuesta clara.
    if theta <= 0:
        if abs(sa - sb) < 1e-9:
            return {**base, "concluyente": False, "z": 0.0, "p_valor": 1.0,
                    "lectura": "Son la misma serie: no hay diferencia que probar."}
        return {**base, "concluyente": False, "p_valor": None,
                "lectura": "Las series son casi idénticas: la prueba no puede "
                           "separarlas, así que la diferencia no es demostrable."}

    z = (sa - sb) / np.sqrt(theta / n)
    p = float(2 * (1 - stats.norm.cdf(abs(z))))

    if p < 0.05:
        lectura = "La diferencia es estadísticamente significativa."
    elif p < 0.10:
        lectura = "La diferencia es débil: sugestiva, no concluyente."
    else:
        lectura = ("La diferencia NO es concluyente con los datos disponibles: "
                   "puede ser azar.")

    return {**base, "concluyente": p < 0.05, "z": round(float(z), 3),
            "p_valor": round(p, 4), "lectura": lectura}


def sharpe_deflactado(retornos, n_pruebas: int, varianza_sharpes: float = None,
                      rf_anual: float = 0.0) -> dict:
    """Probabilidad de que el Sharpe observado NO sea producto del azar.

        DSR = Φ[ (Ŝ − S₀)·√(T−1) / √(1 − γ₃Ŝ + (γ₄−1)/4·Ŝ²) ]

    S₀ es el Sharpe que uno *esperaría* encontrar como máximo probando
    `n_pruebas` variantes aunque ninguna tuviera habilidad. Corrige a la vez por
    multiplicidad de pruebas y por no-normalidad de los retornos, que es
    exactamente la situación de este producto: comparar varias carteras con
    retornos de colas gordas.
    """
    r = np.asarray(retornos, dtype=float)
    T = len(r)
    if T < 60 or n_pruebas < 1:
        return {"disponible": False, "motivo": "serie corta o número de pruebas inválido"}

    rf_d = rf_anual / RUEDAS
    s = _sharpe_periodo(r, rf_d)
    skew = float(stats.skew(r))
    kurt = float(stats.kurtosis(r)) + 3.0          # no-excedente, como pide la fórmula

    # Umbral esperado del máximo de N pruebas independientes.
    var_s = varianza_sharpes if varianza_sharpes is not None else (1.0 / T)
    if n_pruebas > 1:
        s0 = np.sqrt(var_s) * ((1 - EULER) * stats.norm.ppf(1 - 1.0 / n_pruebas)
                               + EULER * stats.norm.ppf(1 - 1.0 / (n_pruebas * np.e)))
    else:
        s0 = 0.0

    denominador = 1 - skew * s + (kurt - 1) / 4 * s ** 2
    if denominador <= 0:
        return {"disponible": False, "motivo": "momentos incompatibles con la fórmula"}

    dsr = float(stats.norm.cdf((s - s0) * np.sqrt(T - 1) / np.sqrt(denominador)))

    if dsr >= 0.95:
        lectura = "El resultado se sostiene aun considerando cuántas variantes probaste."
    elif dsr >= 0.80:
        lectura = "Probablemente real, pero con margen: convendría más historia."
    else:
        lectura = ("Con este número de pruebas, un Sharpe así aparece por azar con "
                   "frecuencia. No lo tomes como habilidad.")

    return {
        "disponible": True,
        "sharpe_anual": round(s * np.sqrt(RUEDAS), 3),
        "umbral_azar_anual": round(float(s0) * np.sqrt(RUEDAS), 3),
        "dsr": round(dsr, 4),
        "n_pruebas": n_pruebas,
        "lectura": lectura,
    }


def intervalo_bootstrap(retornos, metrica="sharpe", rf_anual: float = 0.0,
                        n_muestras: int = 1000, bloque: int = 21) -> dict:
    """Intervalo de confianza al 95 % por remuestreo de bloques.

    Bloques y no días sueltos: conserva el agrupamiento de volatilidad, que un
    remuestreo día a día destruye y que haría parecer las métricas más precisas
    de lo que son.
    """
    r = np.asarray(retornos, dtype=float)
    T = len(r)
    if T < 120:
        return {"disponible": False, "motivo": "serie demasiado corta"}

    funciones = {
        "sharpe": lambda x: risk.sharpe(x, rf_anual),
        "sortino": lambda x: risk.sortino(x, rf_anual),
        "max_drawdown": lambda x: risk.max_drawdown(x) * 100,
        "retorno_anual": lambda x: ((1 + x.mean()) ** RUEDAS - 1) * 100,
        "volatilidad": lambda x: x.std(ddof=1) * np.sqrt(RUEDAS) * 100,
    }
    f = funciones.get(metrica)
    if f is None:
        return {"disponible": False, "motivo": f"métrica desconocida: {metrica}"}

    rng = np.random.default_rng(_SEMILLA)
    n_bloques = int(np.ceil(T / bloque))
    valores = []
    for _ in range(n_muestras):
        inicios = rng.integers(0, T - bloque + 1, size=n_bloques)
        muestra = np.concatenate([r[i:i + bloque] for i in inicios])[:T]
        valores.append(f(muestra))

    v = np.array(valores, dtype=float)
    return {
        "disponible": True, "metrica": metrica,
        "observado": round(float(f(r)), 3),
        "ic95_bajo": round(float(np.percentile(v, 2.5)), 3),
        "ic95_alto": round(float(np.percentile(v, 97.5)), 3),
        "n_muestras": n_muestras,
    }


# ── Comparación de carteras ───────────────────────────────────────────────────

def _series(carteras: dict):
    """{nombre: retornos diarios} recortados al período que TODAS comparten."""
    from core.models.portfolio import matriz_retornos, value_weights
    import pandas as pd

    series, propias = {}, {}
    for nombre, posiciones in carteras.items():
        ret_df, precios = matriz_retornos(posiciones)
        if ret_df.empty:
            continue
        tickers = list(ret_df.columns)
        w = value_weights(posiciones, precios, tickers)
        s = pd.Series(ret_df[tickers].to_numpy() @ w, index=ret_df.index)
        series[nombre] = s
        propias[nombre] = len(s)

    if len(series) < 2:
        return None, {}, {}

    alineadas = pd.concat(series, axis=1).dropna()
    return alineadas, propias, {n: len(alineadas) for n in series}


CRITERIOS = [
    ("retorno_anual_pct", "más retorno", 1),
    ("sharpe", "mejor Sharpe", 1),
    ("sortino", "mejor Sortino", 1),
    ("calmar", "mejor Calmar", 1),
    ("volatilidad_anual_pct", "menos volatilidad", -1),
    ("max_drawdown_pct", "menor caída máxima", 1),
    ("var95_pct", "menor pérdida en un día malo", 1),
    ("curtosis_exceso", "colas más livianas", -1),
]


def comparar(carteras: dict, benchmark: str = "SP500") -> dict:
    """Compara dos o más carteras sobre el mismo período, con estadística.

    carteras: {nombre: [posiciones]}
    """
    from core.models.rates import risk_free_para

    alineadas, propias, comunes = _series(carteras)
    if alineadas is None or alineadas.empty:
        return {"error": "Hacen falta al menos dos carteras con datos."}

    nombres = list(alineadas.columns)
    rf, rf_label = risk_free_para(benchmark, "corto")
    T = len(alineadas)

    metricas = {}
    for n in nombres:
        r = alineadas[n].to_numpy()
        metricas[n] = {
            "retorno_anual_pct": round(float((1 + r.mean()) ** RUEDAS - 1) * 100, 2),
            "volatilidad_anual_pct": round(float(r.std(ddof=1)) * np.sqrt(RUEDAS) * 100, 2),
            "sharpe": round(risk.sharpe(r, rf), 3),
            "sortino": round(risk.sortino(r, rf), 3),
            "calmar": round(risk.calmar(r), 3),
            "max_drawdown_pct": round(risk.max_drawdown(r) * 100, 2),
            "var95_pct": round(risk.var_historico(r, 0.05) * 100, 3),
            "curtosis_exceso": round(float(stats.kurtosis(r)), 3),
            "asimetria": round(float(stats.skew(r)), 3),
        }

    # Conteo de criterios: se conserva porque es legible, pero ya no decide solo.
    puntos = {n: 0 for n in nombres}
    ganados = {n: [] for n in nombres}
    for campo, etiqueta, direccion in CRITERIOS:
        valores = {n: metricas[n][campo] for n in nombres}
        mejor = max(valores, key=valores.get) if direccion > 0 else min(valores, key=valores.get)
        puntos[mejor] += 1
        ganados[mejor].append(etiqueta)

    lider = max(puntos, key=puntos.get)

    # La prueba que decide de verdad: el líder contra cada rival.
    pruebas = []
    for n in nombres:
        if n == lider:
            continue
        t = test_diferencia_sharpe(alineadas[lider].to_numpy(),
                                   alineadas[n].to_numpy(), rf)
        pruebas.append({"contra": n, **t})

    concluyentes = [p for p in pruebas if p.get("concluyente")]
    if not pruebas:
        veredicto = "Sin rivales para comparar."
    elif len(concluyentes) == len(pruebas):
        veredicto = (f"{lider} gana, y la diferencia es estadísticamente "
                     f"significativa contra todas las demás.")
    elif concluyentes:
        otras = ", ".join(p["contra"] for p in pruebas if not p.get("concluyente"))
        veredicto = (f"{lider} lidera el conteo de criterios, pero su ventaja "
                     f"sobre {otras} no es concluyente: puede ser azar.")
    else:
        veredicto = (f"{lider} lidera el conteo, pero NINGUNA de las diferencias "
                     f"es estadísticamente significativa. Con estos datos no hay "
                     f"un ganador demostrable.")

    # Sharpe deflactado: cuántas variantes se están comparando.
    sharpes = np.array([_sharpe_periodo(alineadas[n].to_numpy(), rf / RUEDAS)
                        for n in nombres])
    var_sharpes = float(sharpes.var(ddof=1)) if len(sharpes) > 1 else 1.0 / T
    deflactado = {n: sharpe_deflactado(alineadas[n].to_numpy(), len(nombres),
                                       var_sharpes, rf)
                  for n in nombres}

    intervalos = {n: {m: intervalo_bootstrap(alineadas[n].to_numpy(), m, rf)
                      for m in ("sharpe", "retorno_anual", "max_drawdown")}
                  for n in nombres}

    recorte = {n: {"ruedas_propias": propias[n], "ruedas_comparadas": T,
                   "descartadas": propias[n] - T} for n in nombres}

    return {
        "carteras": nombres,
        "metricas": metricas,
        "criterios_ganados": {n: {"puntos": puntos[n], "cuales": ganados[n]} for n in nombres},
        "lider_por_criterios": lider,
        "pruebas_sharpe": pruebas,
        "veredicto": veredicto,
        "sharpe_deflactado": deflactado,
        "intervalos_confianza": intervalos,
        "periodo_comun": {
            "desde": str(alineadas.index[0].date()),
            "hasta": str(alineadas.index[-1].date()),
            "ruedas": T,
            "recorte_por_cartera": recorte,
            "nota": "Todas las carteras se miden sobre el mismo período. Comparar "
                    "sobre historias de distinta longitud compara épocas del "
                    "mercado, no estrategias.",
        },
        "rf": round(rf, 4), "rf_label": rf_label,
        "curva_valor": [
            {"fecha": str(f.date()),
             **{n: round(float(v), 2) for n, v in zip(nombres, fila)}}
            for f, fila in zip(alineadas.index,
                               (100 * (1 + alineadas).cumprod()).to_numpy())
        ],
    }
