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

from datetime import date, timedelta

import pandas as pd

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
        import yfinance as yf
    except ImportError:
        return pd.DataFrame()
    try:
        df = yf.Ticker(ticker).history(start=desde, end=hasta, auto_adjust=False)
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

    usar_cocos = source == "cocos" or (source is None and is_cocos_only(ticker))
    fuentes = [_de_cocos] if usar_cocos else [_de_yfinance, _de_byma]

    for fn in fuentes:
        try:
            df = fn(ticker, desde, hasta)
        except Exception as e:
            print(f"  [precios] {ticker}: {fn.__name__} falló — {e}")
            continue
        if df is not None and not df.empty and "Close" in df.columns:
            cache.guardar_precios(ticker, df)
            return df.loc[desde:hasta]

    # Sin fuente disponible: lo que haya en la caché es mejor que nada.
    return cache.leer_precios(ticker, desde, hasta)


def _suficiente(df: pd.DataFrame, hasta: str) -> bool:
    """¿La caché alcanza, o hay que salir a buscar?

    Alcanza si tiene datos y el último es de los últimos 3 días hábiles. Evita
    reescribir la caché entera en cada request — el otro 77 % del tiempo que se
    iba en el análisis.
    """
    if df is None or df.empty:
        return False
    ultimo = df.index[-1].date()
    return (date.fromisoformat(hasta) - ultimo).days <= 3


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
        import yfinance as yf
        crudo = yf.Ticker(ticker).info or {}
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
    precios (AL30D ~64 USD), por eso `precios_usd` divide por 100. Pero el
    precio que carga el usuario no siempre está en esa escala: el CSV exportado
    del broker trae AL30D a 0,643 —ya por nominal— y volver a dividirlo hace que
    una operación de 1.572 dólares figure como una de 15,72, que fue lo que pasó
    en MAMI. Ninguna paridad real anda por debajo de 5, así que ese es el corte
    entre las dos escalas.
    """
    return 100.0 if is_bond(ticker, source) and abs(precio or 0) >= 5 else 1.0


def _fci_usd(ticker: str) -> pd.Series:
    """Un solo punto: la cuotaparte de hoy del FCI, en dólares.

    Un FCI no tiene serie —Cocos no publica histórico de cuotapartes— y no se
    inventa una. Con un punto alcanza para valuar la posición y calcular el
    resultado, que es todo lo que se le pide; los modelos que necesitan
    retornos descartan solos las series de menos de 30 ruedas, así que el fondo
    queda fuera del riesgo y de la optimización sin ningún caso especial.

    Tampoco se cachea: es el precio de hoy, y mañana es otro.
    """
    from core.broker import cocos
    from core.data import mep as mep_mod

    hoy = date.today()
    # Cocos informa la cuotaparte en pesos, también la de los fondos en dólares.
    usd = mep_mod.a_usd(cocos.precio_fci(ticker) or 0, hoy)
    if not usd:
        return pd.Series(dtype=float)
    return pd.Series([usd], index=[pd.Timestamp(hoy)])


def precios_usd(ticker: str, desde: str = None, hasta: str = None,
                source: str = None) -> pd.Series:
    """Serie de cierres YA convertida a dólares, lista para calcular retornos.

    Acá se juntan las tres reglas que más errores causaron:
      1. bonos y ONs se dividen por 100 (cotizan cada 100 nominales),
      2. lo que cotiza en pesos se divide por el MEP **de cada fecha**,
      3. lo que ya viene en dólares no se toca.
    """
    from core.data import mep as mep_mod

    if source == SOURCE_FCI:
        return _fci_usd(ticker)

    df = precios(ticker, desde, hasta, source=source)
    if df.empty or "Close" not in df.columns:
        return pd.Series(dtype=float)

    s = df["Close"].dropna()
    if is_bond(ticker, source):
        s = s / 100.0
    if ticker_currency(ticker) == "ARS":
        s = mep_mod.serie_a_usd(s)
    return s
