"""
cache.py — Caché de precios y serie MEP en SQLite.

La base es 100 % regenerable: si se borra, se vuelve a llenar sola desde las
fuentes. Por eso está en .gitignore y por eso no hay migraciones.
"""

import sqlite3
from pathlib import Path

import pandas as pd

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "market_cache.db"

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS precios (
    ticker TEXT NOT NULL,
    fecha  TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL, volume REAL,
    PRIMARY KEY (ticker, fecha)
);
CREATE TABLE IF NOT EXISTS mep (
    fecha TEXT PRIMARY KEY,
    valor REAL NOT NULL,
    fuente TEXT
);
CREATE TABLE IF NOT EXISTS respuestas (
    clave TEXT PRIMARY KEY,
    valor TEXT NOT NULL,
    guardado_en REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_precios_fecha ON precios(fecha);
"""

_COLUMNAS = ["Open", "High", "Low", "Close", "Volume"]


def conectar():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init():
    with conectar() as con:
        con.executescript(_ESQUEMA)


init()


# ── Precios ───────────────────────────────────────────────────────────────────

def rango_cacheado(ticker: str):
    """(primera_fecha, última_fecha) de lo que ya está guardado, o (None, None)."""
    with conectar() as con:
        r = con.execute("SELECT MIN(fecha) a, MAX(fecha) b FROM precios WHERE ticker=?",
                        (ticker.upper(),)).fetchone()
    return (r["a"], r["b"]) if r and r["a"] else (None, None)


def guardar_precios(ticker: str, df: pd.DataFrame) -> int:
    """Guarda un DataFrame indexado por fecha. Devuelve cuántas filas escribió.

    Vectorizado a propósito. La versión anterior recorría el DataFrame con
    `iterrows()` y leía celda por celda con `row.get(col)`: 75.000 accesos
    escalares por ticker. Medido sobre una serie de 5.334 ruedas:

        armar las filas   139,4 ms  →   9,9 ms   (14×)
        + INSERT en SQLite  ~35 ms  →   ~35 ms   (igual en ambos)
        ────────────────────────────────────────
        total por ticker  174,4 ms  →  44,9 ms   (3,9×)

    No es que pandas fuera lento: era el peor patrón posible de pandas. Este
    bucle se llevaba el 77 % del tiempo de un análisis completo.
    """
    if df is None or df.empty:
        return 0
    df = df[[c for c in _COLUMNAS if c in df.columns]].copy()
    for c in _COLUMNAS:
        if c not in df.columns:
            df[c] = None
    df = df[_COLUMNAS]

    idx = pd.to_datetime(df.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    fechas = idx.strftime("%Y-%m-%d")

    tk = ticker.upper()
    filas = [(tk, f, *[None if pd.isna(v) else float(v) for v in vals])
             for f, vals in zip(fechas, df.to_numpy())]
    with conectar() as con:
        con.executemany(
            "INSERT OR REPLACE INTO precios VALUES (?,?,?,?,?,?,?)", filas)
    return len(filas)


def leer_precios(ticker: str, desde: str, hasta: str) -> pd.DataFrame:
    """DataFrame [Open, High, Low, Close, Volume] indexado por fecha."""
    with conectar() as con:
        filas = con.execute(
            "SELECT fecha, open, high, low, close, volume FROM precios "
            "WHERE ticker=? AND fecha>=? AND fecha<=? ORDER BY fecha",
            (ticker.upper(), desde, hasta)).fetchall()
    if not filas:
        return pd.DataFrame()
    df = pd.DataFrame(filas, columns=["fecha"] + [c.lower() for c in _COLUMNAS])
    df.index = pd.to_datetime(df.pop("fecha"))
    df.columns = _COLUMNAS
    return df


def borrar_ticker(ticker: str) -> int:
    with conectar() as con:
        cur = con.execute("DELETE FROM precios WHERE ticker=?", (ticker.upper(),))
        return cur.rowcount


def estadisticas() -> dict:
    with conectar() as con:
        p = con.execute("SELECT COUNT(*) n, COUNT(DISTINCT ticker) t FROM precios").fetchone()
        m = con.execute("SELECT COUNT(*) n FROM mep").fetchone()
    return {"filas_precios": p["n"], "tickers": p["t"], "filas_mep": m["n"],
            "db": str(DB_PATH), "mb": round(DB_PATH.stat().st_size / 1e6, 2)
            if DB_PATH.exists() else 0}


# ── MEP ───────────────────────────────────────────────────────────────────────

def guardar_mep(serie: pd.Series, fuente: str = "") -> int:
    """Serie indexada por fecha con el valor del dólar MEP."""
    if serie is None or serie.empty:
        return 0
    idx = pd.to_datetime(serie.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    filas = [(f, float(v), fuente)
             for f, v in zip(idx.strftime("%Y-%m-%d"), serie.to_numpy())
             if pd.notna(v)]
    with conectar() as con:
        con.executemany("INSERT OR REPLACE INTO mep VALUES (?,?,?)", filas)
    return len(filas)


def leer_mep() -> pd.Series:
    """Serie completa del MEP, indexada por fecha y ordenada."""
    with conectar() as con:
        filas = con.execute("SELECT fecha, valor FROM mep ORDER BY fecha").fetchall()
    if not filas:
        return pd.Series(dtype=float)
    s = pd.Series([r["valor"] for r in filas],
                  index=pd.to_datetime([r["fecha"] for r in filas]), name="mep")
    return s


def ultima_fecha_mep():
    with conectar() as con:
        r = con.execute("SELECT MAX(fecha) f FROM mep").fetchone()
    return r["f"] if r and r["f"] else None


# ── Respuestas de APIs externas ───────────────────────────────────────────────
# Caché con vencimiento para datos que cambian lento pero se piden seguido.
# Dos consumidores concretos, los dos con motivo medido:
#
#   · FMP — el plan gratuito son 250 consultas por día y cada símbolo cuesta 3.
#     Sin caché, abrir la pestaña de objetivos con diez posiciones gasta 30, y
#     el panel de conectores gastaba 3 más cada vez que se dibujaba. Se agotaba
#     sola.
#   · yfinance `.info` — sector, industria y tipo de instrumento cambian una vez
#     al año; se pedían en cada request.

def guardar_respuesta(clave: str, valor, ttl_horas: float = 24) -> None:
    import json
    import time
    with conectar() as con:
        con.execute("INSERT OR REPLACE INTO respuestas VALUES (?,?,?)",
                    (clave, json.dumps(valor), time.time()))


def leer_respuesta(clave: str, ttl_horas: float = 24, default=None):
    """Devuelve lo guardado si no venció, si no `default`.

    El TTL se pasa al leer, no al escribir: el mismo dato puede tolerar
    distinta antigüedad según para qué se lo pida.
    """
    import json
    import time
    with conectar() as con:
        r = con.execute("SELECT valor, guardado_en FROM respuestas WHERE clave=?",
                        (clave,)).fetchone()
    if not r:
        return default
    if (time.time() - r["guardado_en"]) > ttl_horas * 3600:
        return default
    try:
        return json.loads(r["valor"])
    except Exception:
        return default


def limpiar_respuestas() -> int:
    with conectar() as con:
        return con.execute("DELETE FROM respuestas").rowcount
