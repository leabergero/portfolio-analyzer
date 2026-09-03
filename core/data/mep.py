"""
mep.py — Dólar MEP: la serie que convierte toda la cartera a dólares.

Es la pieza más crítica del núcleo después de `symbols.py`: cada precio en pesos
se divide por el MEP **de la fecha de ese precio**, nunca por el de hoy. Usar el
MEP de hoy para una compra de 2024 no es una aproximación, es un error de varios
cientos por ciento.

**Las fuentes del MEP son siempre públicas y sin cuenta.** El MEP lo necesita
cualquiera que use la aplicación, así que no puede depender de estar conectado a
un broker: Cocos queda reservado para bonos, ONs y letras, que no existen en
ninguna fuente pública (ver `docs/DECISIONES.md`).

Cascada:
  1. ArgentinaDatos — serie diaria completa desde 2018 y también el día de hoy.
     Es la primaria. API pública, sin credenciales.
  2. dolarapi.com — solo el valor de hoy, por si la primaria está caída o
     todavía no publicó la rueda. Pública, sin credenciales.
  3. La caché — siempre es la base. Con la serie guardada la aplicación valúa
     igual aunque las dos APIs estén caídas.

Descartadas y por qué, para no volver a intentarlas:
  · PyOBD (BYMA Open Data) — hoy devuelve vacío para todos los símbolos.
  · yfinance con AL30/AL30D — los da por delistados.
  · Cocos — funciona, pero exige cuenta de broker. No es aceptable para un dato
    que necesita todo el mundo.
"""

import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

from core.data import cache

INICIO = "2018-01-01"
EVENTOS = Path(__file__).resolve().parents[2] / "data" / "eventos_mep.json"
_URL_ARGDATOS = "https://api.argentinadatos.com/v1/cotizaciones/dolares/bolsa"
_URL_DOLARAPI = "https://dolarapi.com/v1/dolares/bolsa"
_HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

_memoria = {"serie": None, "fuente": None}


# ── Descarga ──────────────────────────────────────────────────────────────────

def _filtrar_outliers(s: pd.Series) -> pd.Series:
    """Descarta dos cosas distintas: valores fuera de nivel y picos de una rueda.

    Un solo dato malo en el MEP corrompe la valuación de toda la cartera para
    esa fecha, y las APIs públicas publican ceros y saltos de vez en cuando.

    El nivel lo agarra la mediana móvil de 30 ruedas (±40 %). Pero un pico
    aislado no sale del nivel y pasaba entero: el 2025-05-02 ArgentinaDatos
    publicó $1.363,60 entre $1.182 y $1.170, un +15 % que al día siguiente ya no
    estaba, y toda operación de esa fecha se valuaba 16 % mal. Ese se detecta
    contra los vecinos inmediatos, no contra el mes — una devaluación real
    (el 2023-08-14 también saltó 15 %) se queda arriba y la mediana de tres la
    sigue, mientras que el pico queda solo. Los extremos de la serie no tienen
    vecino de los dos lados: se conservan.
    """
    if len(s) < 5:
        return s
    med = s.rolling(30, min_periods=5).median().ffill().bfill()
    s = s[(s > med * 0.60) & (s < med * 1.40)]
    vecinos = s.rolling(3, center=True).median()
    pico = ((s - vecinos).abs() > vecinos * 0.08).fillna(False)
    return s[~pico]


def _desde_argentinadatos() -> pd.Series:
    """Serie histórica completa. El array NO viene ordenado por fecha: hay que
    ordenarlo, no leer el último elemento."""
    r = requests.get(_URL_ARGDATOS, timeout=20, headers=_HEADERS)
    r.raise_for_status()
    datos = r.json()
    if not isinstance(datos, list):
        return pd.Series(dtype=float)
    filas = {}
    for d in datos:
        f, v = d.get("fecha"), d.get("venta") or d.get("compra")
        if f and v and float(v) > 50:
            filas[f] = float(v)
    if not filas:
        return pd.Series(dtype=float)
    s = pd.Series(filas)
    s.index = pd.to_datetime(s.index)
    return _filtrar_outliers(s.sort_index())


def _desde_dolarapi() -> pd.Series:
    """Solo el valor de hoy. Sirve para completar la rueda que la fuente
    histórica todavía no publicó, o si esa fuente está caída."""
    r = requests.get(_URL_DOLARAPI, timeout=15, headers=_HEADERS)
    r.raise_for_status()
    d = r.json()
    v = d.get("venta") or d.get("compra")
    f = (d.get("fechaActualizacion") or "")[:10]
    if not v or not f or float(v) <= 50:
        return pd.Series(dtype=float)
    return pd.Series({pd.Timestamp(f): float(v)})


def sincronizar(forzar: bool = False) -> dict:
    """Trae lo que falta y lo guarda. Devuelve un resumen de lo que hizo.

    No corta en la primera fuente que responde: la histórica y la del día se
    complementan, porque ArgentinaDatos a veces publica la rueda con uno o dos
    días de atraso y valuar la cartera de hoy con el MEP de anteayer es un error
    silencioso.
    """
    ultima = cache.ultima_fecha_mep()
    hoy = date.today().isoformat()
    if not forzar and ultima and ultima >= (date.today() - timedelta(days=1)).isoformat():
        return {"estado": "al dia", "ultima": ultima, "nuevas": 0}

    guardadas, fuentes = 0, []
    for nombre, fn in (("ArgentinaDatos", _desde_argentinadatos),
                       ("dolarapi", _desde_dolarapi)):
        try:
            s = fn()
        except Exception as e:
            print(f"  [mep] {nombre} no respondió: {e}")
            continue
        if s is not None and not s.empty:
            guardadas += cache.guardar_mep(s, nombre)
            fuentes.append(nombre)

    _memoria["serie"] = None                 # invalida el cacheado en memoria
    if not fuentes:
        return {"estado": "sin fuentes", "ultima": ultima, "nuevas": 0}

    _memoria["fuente"] = " + ".join(fuentes)
    return {"estado": "sincronizado", "fuente": _memoria["fuente"],
            "nuevas": guardadas, "ultima": cache.ultima_fecha_mep(), "hasta": hoy}


# ── Lectura ───────────────────────────────────────────────────────────────────

def serie() -> pd.Series:
    """La serie completa, cacheada en memoria (se lee muchas veces por request)."""
    if _memoria["serie"] is None:
        # También al leer: la caché guarda lo que las fuentes publicaron el día
        # que se sincronizó, y ya tiene adentro picos que el filtro viejo dejó pasar.
        _memoria["serie"] = _filtrar_outliers(cache.leer_mep())
    return _memoria["serie"]


def fuente() -> str:
    return _memoria["fuente"] or "caché local"


def valor(fecha, mep: pd.Series = None) -> float:
    """MEP de una fecha. Si ese día no cotizó, usa el último anterior.

    Devuelve None si la fecha es previa al inicio de la serie: es preferible un
    None explícito a convertir con un número inventado.
    """
    s = serie() if mep is None else mep
    if s is None or s.empty:
        return None
    ts = pd.Timestamp(fecha)
    previos = s.loc[:ts]
    return float(previos.iloc[-1]) if len(previos) else None


def a_usd(monto_ars: float, fecha, mep: pd.Series = None) -> float:
    """Convierte un monto en pesos usando el MEP de esa fecha exacta."""
    v = valor(fecha, mep)
    if not v or v <= 0:
        return None
    return float(monto_ars) / v


def serie_a_usd(precios_ars: pd.Series, mep: pd.Series = None) -> pd.Series:
    """Convierte una serie de precios en pesos a dólares, fecha por fecha.

    El MEP se alinea hacia adelante: un feriado toma el último valor conocido.
    """
    s = serie() if mep is None else mep
    if s is None or s.empty or precios_ars.empty:
        return pd.Series(dtype=float)
    idx = precios_ars.index
    if getattr(idx, "tz", None) is not None:
        precios_ars = precios_ars.copy()
        precios_ars.index = idx.tz_localize(None)
    alineado = s.reindex(precios_ars.index, method="ffill")
    return (precios_ars / alineado).dropna()


def eventos(desde: str = None, hasta: str = None) -> list[dict]:
    """Los hitos que movieron al MEP, para marcarlos sobre la serie.

    Es una lista curada a mano en `data/eventos_mep.json`: ningún proveedor
    publica "qué noticia movió al dólar", y adivinarlo con un detector de saltos
    pondría una etiqueta genérica sobre cada rueda volátil. Se edita el archivo.
    """
    try:
        ev = json.loads(EVENTOS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return sorted((e for e in ev
                   if (not desde or e["fecha"] >= desde)
                   and (not hasta or e["fecha"] <= hasta)),
                  key=lambda e: e["fecha"])
