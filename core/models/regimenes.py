"""
regimenes.py — Cuándo el mercado cambió de humor.

Marca los períodos de volatilidad alta y los cruza con un calendario de eventos
macro, para poder leer una caída de la cartera junto a lo que pasaba alrededor.

**Dos correcciones respecto de las apps anteriores.**

1. *Sin sesgo de anticipación.* El umbral que define "crisis" se calculaba como
   un cuantil sobre **toda la serie**, incluidos los datos posteriores a cada
   fecha, y después se aplicaba hacia atrás. Así, decir "en marzo de 2020
   estábamos en crisis" usaba información de 2026 para decidirlo. En un repaso
   histórico —que existe justamente para reproducir lo que se sabía en el
   momento— eso invalida el ejercicio. Acá el umbral es **expansivo**: en cada
   fecha se calcula solo con los datos disponibles hasta esa fecha.

2. *El nombre dice lo que es.* Las apps anteriores llamaban "Markov" a esto y
   exponían endpoints `historical_replay_markov`, pero no hay estados latentes,
   ni matriz de transición, ni verosimilitud: es un umbral sobre la volatilidad
   móvil. Prometer un modelo que no está es peor que no tenerlo. Un HMM real
   queda anotado en `docs/PENDIENTES.md`; mientras tanto, esto se llama
   "régimen por volatilidad" y hace exactamente eso.

La atribución a eventos es **contexto, nunca causalidad**: el calendario dice
qué pasaba, no que eso haya causado el cambio de régimen.
"""

import numpy as np
import pandas as pd

RUEDAS = 252
VENTANA_VOL = 21
PERCENTIL_CRISIS = 75
MINIMO_PARA_UMBRAL = 252     # un año antes de arriesgar una clasificación

# Calendario macro curado. Fecha, alcance y descripción. Es contexto para leer
# el gráfico, no una lista de causas.
EVENTOS = [
    ("2018-04-25", "AR", "Corrida cambiaria: empieza la crisis de 2018"),
    ("2018-06-07", "AR", "Acuerdo stand-by con el FMI"),
    ("2018-08-30", "AR", "Tasa de política monetaria al 60 %"),
    ("2019-08-11", "AR", "PASO: derrota del oficialismo"),
    ("2019-08-28", "AR", "Reperfilamiento de la deuda de corto plazo"),
    ("2019-09-01", "AR", "Vuelve el control de cambios"),
    ("2019-12-10", "AR", "Cambio de gobierno"),
    ("2020-02-20", "MUNDO", "Arranca el desplome por COVID"),
    ("2020-03-11", "MUNDO", "La OMS declara la pandemia"),
    ("2020-03-23", "MUNDO", "Piso del S&P 500; la Fed anuncia compras ilimitadas"),
    ("2020-08-31", "AR", "Cierra el canje de deuda soberana"),
    ("2021-09-12", "AR", "PASO legislativas"),
    ("2021-11-14", "AR", "Elecciones legislativas"),
    ("2022-01-28", "AR", "Principio de acuerdo con el FMI"),
    ("2022-02-24", "MUNDO", "Invasión de Ucrania"),
    ("2022-03-16", "MUNDO", "La Fed empieza a subir tasas"),
    ("2022-07-02", "AR", "Renuncia de Guzmán; salto del dólar libre"),
    ("2022-08-03", "AR", "Massa asume el ministerio de Economía"),
    ("2023-03-10", "MUNDO", "Caída de Silicon Valley Bank"),
    ("2023-05-01", "AR", "Sequía histórica: se derrumban las exportaciones"),
    ("2023-08-14", "AR", "PASO y devaluación del 22 %"),
    ("2023-11-19", "AR", "Balotaje presidencial"),
    ("2023-12-12", "AR", "Devaluación del 54 %"),
    ("2023-12-20", "AR", "DNU de desregulación"),
    ("2024-06-28", "AR", "Se aprueba la Ley Bases"),
    ("2024-07-15", "AR", "Fin del dólar blend para exportadores"),
    ("2025-04-11", "AR", "Nuevo acuerdo con el FMI; se flexibiliza el cepo"),
    ("2025-04-02", "MUNDO", "Aranceles generalizados de EE.UU."),
    ("2026-06-13", "MUNDO", "Escalada Irán–Israel; salta el petróleo"),
]


PERSISTENCIA = 5      # ruedas seguidas para dar por cambiado el régimen


def clasificar(retornos: pd.Series, persistencia: int = PERSISTENCIA):
    """Serie 0/1 (calma/tensión) con umbral EXPANSIVO, sin mirar el futuro.

    **Con persistencia.** Comparar la volatilidad contra el umbral día a día,
    sin más, produce un régimen que cambia de estado cada dos o tres ruedas: 57
    transiciones en cuatro años, con secuencias calma → tensión → calma en días
    consecutivos. Eso no es un régimen, es la serie oscilando alrededor del
    umbral. Se exige que la condición se sostenga `persistencia` ruedas seguidas
    para declarar el cambio.

    Es el sustituto barato de lo que un modelo de Markov haría bien: en un HMM
    la persistencia sale de la matriz de transición, que penaliza cambiar de
    estado. Acá se impone a mano y se declara.

    Devuelve (régimen, volatilidad anualizada, umbral).
    """
    vol = retornos.rolling(VENTANA_VOL).std() * np.sqrt(RUEDAS)
    # El umbral en t usa solo datos hasta t. `expanding` con mínimo de un año
    # evita clasificar con tres datos.
    umbral = vol.expanding(min_periods=MINIMO_PARA_UMBRAL).quantile(PERCENTIL_CRISIS / 100)
    crudo = (vol > umbral)

    regimen = pd.Series(np.nan, index=retornos.index)
    estado, seguidas, previo = 0, 0, None
    for f in retornos.index:
        if pd.isna(umbral.get(f)) or pd.isna(vol.get(f)):
            continue
        actual = bool(crudo[f])
        seguidas = seguidas + 1 if actual == previo else 1
        previo = actual
        if seguidas >= persistencia and int(actual) != estado:
            estado = int(actual)
        regimen[f] = estado

    return regimen, vol, umbral


def _vix(indice):
    try:
        import yfinance as yf
        s = yf.Ticker("^VIX").history(start=str(indice[0].date()))["Close"]
        if getattr(s.index, "tz", None) is not None:
            s.index = s.index.tz_localize(None)
        return s.reindex(indice, method="ffill")
    except Exception:
        return pd.Series(index=indice, dtype=float)


def _vol_merval(indice):
    """No existe un VIX del Merval gratis: se usa volatilidad realizada.

    Se verificaron nueve tickers candidatos (^VXMERV, ^VIXMERVAL y variantes) y
    todos vienen vacíos. La volatilidad realizada a 21 ruedas es el sustituto
    honesto: mide miedo local realizado, no implícito, y se etiqueta como tal.
    """
    try:
        import yfinance as yf
        s = yf.Ticker("^MERV").history(start=str(indice[0].date()))["Close"]
        if getattr(s.index, "tz", None) is not None:
            s.index = s.index.tz_localize(None)
        rv = s.pct_change().rolling(VENTANA_VOL).std() * np.sqrt(RUEDAS) * 100
        return rv.reindex(indice, method="ffill")
    except Exception:
        return pd.Series(index=indice, dtype=float)


def analizar(posiciones) -> dict:
    from core.models.portfolio import matriz_retornos, value_weights

    ret_df, precios = matriz_retornos(posiciones)
    if ret_df.empty or len(ret_df) < 90:
        return {"error": "Serie demasiado corta para identificar regímenes."}

    tickers = list(ret_df.columns)
    w = value_weights(posiciones, precios, tickers)
    cartera = pd.Series(ret_df[tickers].to_numpy() @ w, index=ret_df.index)

    regimen, vol, umbral = clasificar(cartera)
    vix = _vix(cartera.index)
    vol_local = _vol_merval(cartera.index)

    linea = []
    for f in cartera.index:
        r = regimen.get(f)
        linea.append({
            "fecha": str(f.date()),
            "regimen": (None if pd.isna(r) else int(r)),
            "vol_cartera": (None if pd.isna(vol.get(f)) else round(float(vol[f]) * 100, 2)),
            "umbral": (None if pd.isna(umbral.get(f)) else round(float(umbral[f]) * 100, 2)),
            "vix": (None if pd.isna(vix.get(f, np.nan)) else round(float(vix[f]), 2)),
            "vol_merval": (None if pd.isna(vol_local.get(f, np.nan)) else round(float(vol_local[f]), 1)),
        })

    # Transiciones: dónde cambió el humor.
    validos = regimen.dropna()
    cambios = []
    for i in range(1, len(validos)):
        if validos.iloc[i] != validos.iloc[i - 1]:
            f = validos.index[i]
            cambios.append({"fecha": str(f.date()),
                            "hacia": "tensión" if validos.iloc[i] == 1 else "calma"})

    # Eventos dentro del período, para superponer al gráfico.
    desde, hasta = str(cartera.index[0].date()), str(cartera.index[-1].date())
    eventos = [{"fecha": f, "alcance": a, "descripcion": d}
               for f, a, d in EVENTOS if desde <= f <= hasta]

    dias_tension = int(validos.sum())
    return {
        "linea_tiempo": linea,
        "transiciones": cambios,
        "eventos": eventos,
        "dias_clasificados": int(len(validos)),
        "dias_tension": dias_tension,
        "pct_tension": round(dias_tension / len(validos) * 100, 1) if len(validos) else 0,
        "regimen_actual": ("tensión" if len(validos) and validos.iloc[-1] == 1 else "calma"),
        "metodo": f"Régimen por volatilidad realizada a {VENTANA_VOL} ruedas, con "
                  f"umbral en el percentil {PERCENTIL_CRISIS} calculado de forma "
                  f"expansiva (solo con datos anteriores a cada fecha) y "
                  f"persistencia de {PERSISTENCIA} ruedas. No es un modelo de Markov.",
        "nota_eventos": "El calendario es contexto para leer el gráfico. Que un "
                        "evento coincida con un cambio de régimen no significa "
                        "que lo haya causado.",
    }
