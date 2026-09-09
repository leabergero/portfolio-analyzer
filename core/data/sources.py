"""
sources.py — De dónde sale el precio de cada instrumento.

Cara pública de la capa de datos: el resto del núcleo pide precios acá y no
necesita saber de dónde salieron.

Regla de ruteo, en una línea: **lo que solo existe en Cocos va a Cocos y nunca
se intenta en otro lado.** Pedir un AL30 o una ON a yfinance no devuelve datos
malos, devuelve otra especie o nada, y esa confusión ya costó cara.

    source="cocos"                       → Cocos, directo
    source=None y es bono/ON/letra       → Cocos, directo
    en cualquier otro caso               → caché → yfinance → BYMA Open Data

La caché va primero siempre: es la única fuente que no se cae ni tiene límite de
consultas.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from core import mercado
from core.data import cache
from core.data.symbols import (  # noqa: F401  — API pública de la capa de datos
    D_FALSOS_POSITIVOS,
    base_symbol,
    d_ticker,
    is_bond,
    is_cocos_only,
    is_d_variant,
    SOURCE_FCI,
    strip_ba,
    ticker_currency,
)

INICIO_HISTORIA = "2005-01-01"
INICIO_COCOS = "2022-01-01"      # Cocos no tiene histórico anterior


def inicio_historia() -> str:
    return INICIO_HISTORIA


# ── Fuentes individuales ──────────────────────────────────────────────────────

def _de_yfinance(ticker: str, desde: str, hasta: str) -> pd.DataFrame:
    try:
        from core.data import yahoo
    except ImportError:
        return pd.DataFrame()
    try:
        # Yahoo trata `end` como exclusivo: con end=hoy la rueda de hoy no viene
        # ni corriendo después del cierre, y la caché queda una rueda atrás para
        # siempre (KOD.BA mostraba 18,50 del viernes contra 18,46 del lunes).
        fin = (date.fromisoformat(hasta) + timedelta(days=1)).isoformat()
        df = yahoo.ticker(ticker).history(start=desde, end=fin, auto_adjust=False)
    except Exception:
        return pd.DataFrame()
    if df is None or df.empty:
        return pd.DataFrame()
    if getattr(df.index, "tz", None) is not None:
        df.index = df.index.tz_localize(None)
    return df


def _de_byma(ticker: str, desde: str, hasta: str) -> pd.DataFrame:
    """BYMA Open Data vía PyOBD. Pide de a 90 días."""
    try:
        from pyobd import BymaData
    except ImportError:
        return pd.DataFrame()
    try:
        d0 = date.fromisoformat(desde)
        d1 = date.fromisoformat(hasta)
    except ValueError:
        return pd.DataFrame()

    cliente = BymaData()
    partes, cur = [], d0
    while cur < d1:
        fin = min(cur + timedelta(days=90), d1)
        try:
            df = cliente.get_daily_history(symbol=strip_ba(ticker),
                                           from_date=cur.isoformat(),
                                           to_date=fin.isoformat())
            if df is not None and not df.empty:
                if "date" in df.columns:
                    df = df.set_index(pd.to_datetime(df["date"])).drop(columns=["date"])
                df.columns = [c.capitalize() for c in df.columns]
                partes.append(df)
        except Exception:
            pass
        cur = fin
    if not partes:
        return pd.DataFrame()
    out = pd.concat(partes)
    out = out[~out.index.duplicated(keep="last")].sort_index()
    if getattr(out.index, "tz", None) is not None:
        out.index = out.index.tz_localize(None)
    return out


def _de_cocos(ticker: str, desde: str, hasta: str) -> pd.DataFrame:
    from core.broker import cocos
    return cocos.historico(ticker, max(desde, INICIO_COCOS), hasta)


# ── Ruteo ─────────────────────────────────────────────────────────────────────

# Cuánto se espera antes de volver a preguntar por un ticker que no devolvió
# nada. Un papel recién listado tarda a lo sumo eso en aparecer; `refrescar=True`
# no pasa por acá.
TTL_SIN_SERIE_H = 6.0

# Cuánto se espera antes de volver a salir por un ticker cuya caché no llega a
# la última rueda. Acota el costo de los feriados, que `_ultima_rueda` no conoce.
TTL_FRESCO_H = 2.0

# Hora de Buenos Aires a partir de la cual se da por publicada la rueda del día.
# BYMA cierra a las 17 y yfinance viene con 20 minutos de delay. La zona es
# explícita porque el server de producción corre en UTC: con la hora de la
# máquina, las 18 caían 15:00 ART y la rueda se daba por cerrada dos horas antes.
CIERRE_BYMA_H = 18
TZ_BYMA = ZoneInfo("America/Argentina/Buenos_Aires")


def precios(ticker: str, desde: str = None, hasta: str = None,
            source: str = None, refrescar: bool = False) -> pd.DataFrame:
    """Serie histórica del ticker, en su moneda de cotización.

    NO convierte a dólares: eso lo hace quien la consume, con el MEP de cada
    fecha (ver `core.data.mep`). Devolver el precio crudo mantiene una sola
    responsabilidad por función y hace la caché reutilizable.
    """
    ticker = ticker.upper().strip()
    desde = desde or INICIO_HISTORIA
    hasta = hasta or date.today().isoformat()

    if not refrescar:
        cacheado = cache.leer_precios(ticker, desde, hasta)
        if _suficiente(cacheado, hasta):
            return cacheado
        # Le falta la última rueda, pero si ya se intentó hace poco no se vuelve
        # a salir. Un feriado de BYMA deja a los ~60 tickers "atrasados" sin que
        # exista el dato que falta, y sin esto cada request los reintenta todos.
        if not cacheado.empty and cache.leer_respuesta(
                f"fresco:{ticker}", TTL_FRESCO_H) is True:
            return cacheado
        # Un ticker que ya dio vacío no se vuelve a preguntar por unas horas.
        # Sin esto, cada panel reintenta yfinance y BYMA por los mismos tickers
        # muertos —un FCI, un CEDEAR de otra plaza— y paga ~9 segundos por cada
        # uno, en cada pedido. Es la espera más cara de la app y no aporta nada.
        if cache.leer_respuesta(f"sin-serie:{ticker}", TTL_SIN_SERIE_H) is True:
            return pd.DataFrame()

    usar_cocos = source == "cocos" or (source is None and is_cocos_only(ticker))
    fuentes = [_de_cocos] if usar_cocos else [_de_yfinance, _de_byma]

    fallo_red = False
    for fn in fuentes:
        try:
            df = fn(ticker, desde, hasta)
        except Exception as e:
            fallo_red = True
            print(f"  [precios] {ticker}: {fn.__name__} falló — {e}")
            continue
        if df is not None and not df.empty and "Close" in df.columns:
            cache.guardar_precios(ticker, df)
            cache.guardar_respuesta(f"fresco:{ticker}", True)
            return df.loc[desde:hasta]

    # Sin fuente disponible: lo que haya en la caché es mejor que nada.
    cacheado = cache.leer_precios(ticker, desde, hasta)
    if not cacheado.empty or usar_cocos:
        return cacheado
    spot = _spot_yfinance(ticker)
    # Solo se anota como muerto el que contestó y no tenía nada. Si la fuente
    # se cayó, el ticker puede estar perfecto y silenciarlo por horas sería
    # peor que reintentar.
    if spot.empty and not fallo_red:
        cache.guardar_respuesta(f"sin-serie:{ticker}", True)
    return spot


def _spot_yfinance(ticker: str, ttl_horas: float = 1.0) -> pd.DataFrame:
    """Último precio suelto, para lo que no tiene ni una rueda de historia.

    Un CEDEAR recién listado —DELLD.BA, septiembre de 2026— no devuelve nada ni
    en yfinance ni en BYMA, pero sí tiene cotización de hoy. Sin esto el lote
    quedaba sin precio y, peor, **fuera del total de la cartera**: la tenencia
    mostraba menos plata de la que había.

    Un punto no es una serie y no pretende serlo: los modelos descartan solos
    todo lo que tenga menos de 30 ruedas, así que el papel sigue quedando fuera
    del riesgo, de la optimización y del momentum, que es lo que corresponde.
    Mismo criterio que los FCI (ver `_fci_usd`).

    No entra a la caché de precios: es una cotización de hoy, posiblemente
    intradiaria, y mezclarla con cierres reales ensuciaría los retornos el día
    que el papel empiece a tener historia de verdad.
    """
    clave = f"yf:spot:{ticker.upper()}"
    precio = cache.leer_respuesta(clave, ttl_horas, default="__falta__")
    if precio == "__falta__":
        try:
            from core.data import yahoo
            i = yahoo.ticker(ticker).info or {}
            precio = (i.get("currentPrice") or i.get("regularMarketPrice")
                      or i.get("previousClose"))
        except Exception:
            precio = None
        cache.guardar_respuesta(clave, precio)
    if not precio:
        return pd.DataFrame()
    return pd.DataFrame({"Close": [float(precio)]},
                        index=[pd.Timestamp(date.today())])


def _ultima_rueda(hasta: str) -> date:
    """Última rueda que ya debería estar publicada a la fecha `hasta`.

    El fin de semana no cuenta, y la rueda de hoy tampoco hasta que cierre. Los
    feriados de BYMA quedan afuera a propósito: meterlos pide un calendario que
    hay que mantener, y el único costo de no tenerlos es un reintento por ticker
    cada `TTL_FRESCO_H`, que es justo lo que ese TTL acota.
    """
    ahora = datetime.now(TZ_BYMA)
    # `min` porque `hasta` sale de `date.today()`, que en un server UTC ya es
    # mañana durante la noche argentina: sin recortar, la "última rueda" caía en
    # un día que todavía no existe y la caché nunca alcanzaba.
    d = min(date.fromisoformat(hasta), ahora.date())
    if d == ahora.date() and ahora.hour < CIERRE_BYMA_H:
        d -= timedelta(days=1)
    while d.weekday() >= 5:          # 5 sábado, 6 domingo
        d -= timedelta(days=1)
    return d


def _suficiente(df: pd.DataFrame, hasta: str) -> bool:
    """¿La caché alcanza, o hay que salir a buscar?

    Alcanza si llega a la última rueda publicada. Antes toleraba 3 días y esa
    holgura se comía justo la rueda que `end` exclusivo no bajaba: la corrida del
    día D guardaba hasta D-1 y al día siguiente la tolerancia lo perdonaba, así
    que el agujero no se cerraba nunca y la app vivía una rueda atrás.
    """
    if df is None or df.empty:
        return False
    return df.index[-1].date() >= _ultima_rueda(hasta)


def info(ticker: str, ttl_horas: float = 24 * 7):
    """Ficha del instrumento en yfinance (sector, industria, tipo, categoría).

    Cacheada una semana. Sector, industria y tipo de instrumento cambian una vez
    al año como mucho, y en las apps anteriores se pedían **en cada request**:
    la pantalla de composición tardaba 12 segundos, casi todos gastados en
    volver a preguntar lo mismo.
    """
    clave = f"yf:info:{ticker.upper()}"
    guardado = cache.leer_respuesta(clave, ttl_horas, default="__falta__")
    if guardado != "__falta__":
        return guardado or {}

    datos = {}
    try:
        from core.data import yahoo
        crudo = yahoo.ticker(ticker).info or {}
        # Solo lo que se usa: el .info completo son cientos de campos y no tiene
        # sentido guardarlos ni arrastrarlos.
        datos = {k: crudo.get(k) for k in
                 ("quoteType", "sector", "industry", "category",
                  "longName", "shortName", "currency", "marketCap")
                 if crudo.get(k) is not None}
    except Exception:
        datos = {}

    cache.guardar_respuesta(clave, datos)
    return datos


def divisor_nominal(ticker: str, precio: float, source: str = None) -> float:
    """100 si ese precio viene por lámina de 100 nominales, 1 si viene por nominal.

    Los bonos y ONs cotizan cada 100 nominales y así los publica la fuente de
    precios (AL30D ~64 USD), por eso `precios_base` divide por 100. Pero el
    precio que carga el usuario no siempre está en esa escala: el CSV exportado
    del broker trae AL30D a 0,643 —ya por nominal— y volver a dividirlo hace que
    una operación de 1.572 dólares figure como una de 15,72, que fue lo que pasó
    en MAMI. Ninguna paridad real anda por debajo de 5, así que ese es el corte
    entre las dos escalas.
    """
    return 100.0 if is_bond(ticker, source) and abs(precio or 0) >= 5 else 1.0


def _fci_usd(ticker: str) -> pd.Series:
    """Un solo punto: la última cuotaparte del FCI (T-1), en dólares.

    Un FCI no tiene serie —Cocos no publica histórico de cuotapartes— y no se
    inventa una. Con un punto alcanza para valuar la posición y calcular el
    resultado, que es todo lo que se le pide; los modelos que necesitan
    retornos descartan solos las series de menos de 30 ruedas, así que el fondo
    queda fuera del riesgo y de la optimización sin ningún caso especial.

    **La última cuotaparte vista se guarda en la caché**, y es lo que se devuelve
    cuando el broker no está disponible. Antes no se cacheaba —"es el precio de
    hoy, y mañana es otro"— y el resultado era que sin sesión de Cocos el fondo
    aparecía «sin precio» y quedaba fuera del total de la cartera: una tenencia
    que existe, valuada en nada. Un valor de ayer es una aproximación; cero es
    un error.
    """
    from core.broker import cocos
    from core.data import cache
    from core.data import mep as mep_mod

    hoy = date.today()
    # Cocos informa la cuotaparte en pesos, también la de los fondos en dólares.
    ars = cocos.precio_fci(ticker)
    # Un FCI se valúa a T-1: la cuotaparte que publica el broker es la del cierre
    # anterior, no la de hoy. Fecharla hoy la convertía con el MEP de hoy —pesos
    # de un día, tipo de cambio de otro— y dejaba el punto cacheado un día
    # adelantado, que es el mismo error que traía la app con los cierres.
    fecha = _ultima_rueda((hoy - timedelta(days=1)).isoformat())

    if ars:
        cache.guardar_precios(ticker, pd.DataFrame({"Close": [float(ars)]},
                                                   index=[pd.Timestamp(fecha)]))
    else:
        # Sin broker: la última que se llegó a ver, con su fecha real.
        df = cache.leer_precios(ticker, "1900-01-01", hoy.isoformat())
        s = df["Close"].dropna() if "Close" in df.columns else pd.Series(dtype=float)
        if s.empty:
            return pd.Series(dtype=float)
        ars, fecha = float(s.iloc[-1]), s.index[-1].date()

    # Se convierte con el MEP de la fecha del precio, no con el de hoy: son los
    # pesos de ese día.
    usd = mep_mod.a_usd(ars, fecha)
    if not usd:
        return pd.Series(dtype=float)
    return pd.Series([usd], index=[pd.Timestamp(fecha)])


def precios_base(ticker: str, desde: str = None, hasta: str = None,
                 source: str = None) -> pd.Series:
    """Serie de cierres en la moneda de medición, lista para calcular retornos.

    Acá se juntan las tres reglas que más errores causaron:
      1. bonos y ONs se dividen por 100 (cotizan cada 100 nominales),
      2. lo que cotiza en pesos se divide por el MEP **de cada fecha**,
      3. lo que cotiza en euros se multiplica por el EURUSD de cada fecha,
      4. lo que ya viene en dólares no se toca.

    El dólar es el paso obligado de las tres, no el destino: si la plaza elegida
    mide en euros, el último paso pasa la serie a euros con el EURUSD de cada
    fecha (ver `core.mercado`). Convertir acá y no al mostrar es lo que hace que
    la volatilidad del tipo de cambio entre a las métricas, que es justamente lo
    que ve un inversor europeo.
    """
    from core.data import mep as mep_mod

    if source == SOURCE_FCI:
        return mercado.desde_usd(_fci_usd(ticker))

    df = precios(ticker, desde, hasta, source=source)
    if df.empty or "Close" not in df.columns:
        return pd.Series(dtype=float)

    s = df["Close"].dropna()
    if is_bond(ticker, source):
        s = s / 100.0

    cotiza = ticker_currency(ticker)
    if cotiza == mercado.moneda():
        return s          # ya cotiza en la moneda de medición: nada que convertir
    if cotiza == "ARS":
        s = mep_mod.serie_a_usd(s)
    else:
        s = mercado.a_usd(s, cotiza)
    return mercado.desde_usd(s)
