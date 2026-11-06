"""
cds.py — Qué chance le pone el mercado a un evento de crédito de cada emisor.

Sale del CDS a 5 años que ICE Clear Credit, la cámara que compensa los contratos,
publica gratis cada día: el cierre de la rueda anterior, sin historia. La
historia se arma sola guardando cada día que se pide en `data/cds_historia.json`.

ICE no da el spread sino el precio de un contrato con cupón fijo (100 o 500 pb)
sobre 100, y el precio va al revés que el riesgo: 102 es menos riesgo que el
cupón, 78 mucho más. Se pasa a spread con el modelo estándar de ISDA (riesgo de
default constante) y de ahí a probabilidad.

La probabilidad es la que cobra el seguro, no la real: incluye una prima por
riesgo y por liquidez, así que es un techo. Sirve para comparar emisores y ver
si el mercado se pone nervioso, no como pronóstico literal.
"""
import json
import logging
from collections import Counter
import math
import os
from datetime import date, datetime
from pathlib import Path

from core.data import cache, symbols

log = logging.getLogger(__name__)

URL = "https://www.ice.com/api/cds-settlement-prices/icc-single-names"
HORAS_CACHE = 6
RECUPERO = 0.40          # el estándar de ISDA para deuda senior
TASA = 0.04              # ponytail: tasa plana; ISDA usa la curva SOFR, mueve el spread < 1 pb
HISTORIA = Path(__file__).resolve().parents[2] / "data" / "cds_historia.json"
# Lo que publica ICE, tal cual y completo (todas las monedas y cupones): con esto
# la historia se puede recalcular si cambia el modelo. ~15 KB por día comprimido.
CRUDO = HISTORIA.parent / "cds_ice"

# La señal: cuánto se ensanchó en 20 ruedas, en desvíos de su propio año. Un
# salto de un día no anticipa nada; 20 ruedas sí (backtest 1987–2026 en
# ~/Vídeos/QUANTCENTRAL/cds-backtest-2026-11): con HYG/IEF por encima de 1,89
# —su percentil 95— la chance de que el S&P caiga 10 % en 60 ruedas pasa de
# 14,6 % a 29,4 % (p = 0,021). En 2026 se encendió el 16-oct, 12 días antes
# de Alphabet. Por emisor es la misma regla, todavía sin validar.
RUEDAS = 20
Z_ALERTA = 1.89
MIN_HISTORIA = 80        # 20 para el primer ensanche + 60 para medir su desvío
BACKTEST = {"base_pct": 14.6, "con_senal_pct": 29.4, "p": 0.021, "muestra_desde": 2007}

# Subyacente en EE.UU. → código de ICE. Sólo los que tienen CEDEAR o ADR; lo que
# no está acá no tiene CDS en la lista de ICE (ETFs, Micron, Adobe, Lilly, Vista…).
EMISOR = {
    "AAPL": "APLINC", "MSFT": "MSFT", "GOOGL": "ALPHINC", "GOOG": "ALPHINC", "AMZN": "AMZN",
    "META": "METAPL", "NVDA": "NVIDIA", "TSLA": "TESLINC", "AMD": "AMD", "INTC": "INTC",
    "AVGO": "BROINC", "ORCL": "ORCLE", "IBM": "IBM", "CSCO": "CISCOSY", "DELL": "DELLN",
    "HPQ": "HPINCAA", "NFLX": "NFLX", "UBER": "UBERTEC", "CRWV": "COREWEI", "XRX": "XRX",
    "TSM": "TAISEM", "BABA": "ALIBGRO", "BIDU": "BAIDINC", "KO": "KO", "PG": "PG",
    "MCD": "MCD", "WMT": "WALMINC", "HD": "HD", "LOW": "LOW", "TGT": "TGT", "BBY": "BBY",
    "MO": "MO", "MDLZ": "MONDINT", "KHC": "KRAFHEI", "GIS": "GIS", "YUM": "YUM", "TJX": "TJX",
    "DIS": "THWALT", "CMCSA": "CMCSA", "T": "ATTINC", "VZ": "VRZN", "TMUS": "DT-TMobileUS",
    "JPM": "JPM", "BAC": "BACORP", "C": "C", "GS": "GS", "MS": "MWD", "WFC": "WFC",
    "AXP": "AXP", "USB": "USB", "COF": "COF", "BRK-B": "BRK", "MET": "MET", "AIG": "AIG",
    "PFE": "PFE", "JNJ": "JNJ", "ABBV": "ABBVINC", "ABT": "ABT", "AMGN": "AMGN", "BMY": "BMY",
    "UNH": "UNH", "CVS": "CVSHEA", "TMO": "TMOFS", "DHR": "DHR", "TEVA": "TEVA",
    "XOM": "XOM", "CVX": "CVX", "COP": "COP", "OXY": "OXY", "HAL": "HAL", "PBR": "PETBRA",
    "VALE": "VALESA", "NEM": "NEWMOCO", "FCX": "FREEPIN", "GOLD": "BARRIMI", "BHP": "BHPGR",
    "RIO": "RIOLN-Ltd", "X": "X", "NUE": "NUE", "BA": "BA", "LMT": "LMT", "RTX": "RTXCOR",
    "NOC": "NORGRM", "GE": "GE", "HON": "HON", "CAT": "CAT", "DE": "DE", "F": "F", "GM": "GENMC",
    "UPS": "UPS", "FDX": "FDX", "UNP": "UNP", "CSX": "CSX", "DAL": "DAL", "AAL": "AMERAIAI",
    "UAL": "UNITAIBJ", "LUV": "LUV", "CCL": "CARNIVC", "RCL": "RCL", "MAR": "MAR",
    "AMX": "AMSAB", "DOW": "DOW", "WBA": "WALGBOO", "FISV": "FISV", "SHW": "SHW",
}
ARGENTINA = "ARGENT"
# Bonos del Tesoro en dólares (Bonares, Globales, Bonte, AO27/AO28). Las letras y
# los bonos en pesos son el mismo deudor, pero su default es otro.
_SOBERANO_USD = ("AL", "GD", "AE", "AO")


def emisor(ticker: str, source: str = None):
    """Código de ICE del que debe, o None si no hay CDS."""
    from core.data import finviz
    t = str(ticker).upper().strip()
    if source == symbols.SOURCE_FCI:
        return None
    if symbols.is_bond(t, source):
        base = symbols.base_symbol(t)
        return ARGENTINA if base[:2] in _SOBERANO_USD and base[2:4].isdigit() and len(base) == 4 else None
    return EMISOR.get(finviz.subyacente(t, source) or "")


# ── Modelo estándar: riesgo de default constante ──────────────────────────────

def _imm(d: date, siguiente: bool) -> date:
    """El 20 de mar/jun/sep/dic anterior (o siguiente) a `d`, incluido."""
    fechas = [date(a, m, 20) for a in (d.year - 1, d.year, d.year + 1) for m in (3, 6, 9, 12)]
    return min(f for f in fechas if f >= d) if siguiente else max(f for f in fechas if f <= d)


def _patas(lam: float, hoy: date, fin: date):
    """(protección, anualidad con riesgo, devengado) por unidad de nominal."""
    t = lambda d: max((d - hoy).days, 0) / 365.0
    T = t(fin)
    k = lam + TASA
    proteccion = (1 - RECUPERO) * lam / k * (1 - math.exp(-k * T)) if k else 0.0
    inicio = _imm(hoy, siguiente=False)
    anualidad, desde = 0.0, inicio
    while desde < fin:
        hasta = _imm(date.fromordinal(desde.toordinal() + 1), siguiente=True)
        delta = (hasta - desde).days / 360.0
        sobrevive_a, sobrevive_b = math.exp(-lam * t(desde)), math.exp(-lam * t(hasta))
        df = math.exp(-TASA * t(hasta))
        # El cupón entero si sobrevive; la mitad, en promedio, si cae en el período.
        anualidad += delta * df * (sobrevive_b + (sobrevive_a - sobrevive_b) / 2)
        desde = hasta
    devengado = ((hoy - inicio).days + 1) / 360.0
    return proteccion, anualidad, devengado


def precio(spread_pb: float, cupon_pb: float, hoy: date, fin: date) -> float:
    """Precio limpio sobre 100 de un contrato con `cupon_pb`, si el spread es `spread_pb`."""
    lam = spread_pb / 1e4 / (1 - RECUPERO)
    lam = _lambda(lambda x: _spread(x, hoy, fin) - spread_pb, lam)
    prot, anual, dev = _patas(lam, hoy, fin)
    return 100 * (1 - (prot - cupon_pb / 1e4 * (anual - dev)))


def _spread(lam, hoy, fin):
    prot, anual, dev = _patas(lam, hoy, fin)
    return prot / (anual - dev) * 1e4


def _lambda(f, inicial):
    from scipy.optimize import brentq
    return brentq(f, 1e-7, 5.0, xtol=1e-10) if f(1e-7) * f(5.0) < 0 else inicial


def desde_precio(precio_ice: float, cupon_pb: float, hoy: date, fin: date) -> dict:
    """Spread y probabilidad de un evento de crédito, a partir del precio de ICE."""
    def error(lam):
        prot, anual, dev = _patas(lam, hoy, fin)
        return 100 * (1 - (prot - cupon_pb / 1e4 * (anual - dev))) - precio_ice
    lam = _lambda(error, None)
    if lam is None:
        return None
    anios = (fin - hoy).days / 365.0
    return {"spread_pb": round(_spread(lam, hoy, fin), 1),
            "prob_1a_pct": round((1 - math.exp(-lam)) * 100, 2),
            "prob_vto_pct": round((1 - math.exp(-lam * anios)) * 100, 2)}


# ── Datos de ICE y su historia ────────────────────────────────────────────────

def _bajar() -> list:
    import requests
    r = requests.get(URL, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    return r.json()


def _resumir(filas) -> dict:
    """{código: {fecha, spread_pb, prob…}} con un contrato por emisor: senior, en
    dólares, y del cupón más cercano a su spread (el más negociado)."""
    por = {}
    for x in filas:
        p = x["instrumentName"].split(".")
        if len(p) < 6 or p[1] != "SNRFOR" or p[2] != "USD":
            continue
        try:
            hoy = date.fromisoformat(x["clearingDate"])
            r = desde_precio(float(x["eodPrice"]), float(p[4]), hoy, date.fromisoformat(p[5]))
        except (ValueError, KeyError):
            continue
        if not r:
            continue
        r.update(fecha=x["clearingDate"], nombre=x["name"], cupon_pb=int(float(p[4])), vto=p[5])
        viejo = por.get(p[0])
        if not viejo or abs(r["spread_pb"] - r["cupon_pb"]) < abs(viejo["spread_pb"] - viejo["cupon_pb"]):
            por[p[0]] = r
    return por


def _escribir(destino: Path, datos: bytes) -> None:
    tmp = destino.with_suffix(".tmp")
    tmp.write_bytes(datos)
    os.replace(tmp, destino)


def _guardar_crudo(filas: list) -> None:
    """Un archivo por fecha de cierre. ICE mezcla fechas —unos pocos emisores ya
    vienen con la de hoy mientras el resto sigue en la de ayer—, así que cada
    fila va a su día y se suma a lo que ese día ya tenía."""
    import gzip
    CRUDO.mkdir(exist_ok=True)
    por_fecha = {}
    for x in filas:
        if x.get("clearingDate") and x.get("instrumentName"):
            por_fecha.setdefault(x["clearingDate"], {})[x["instrumentName"]] = x
    for fecha, nuevas in por_fecha.items():
        destino = CRUDO / f"{fecha}.json.gz"
        try:
            viejas = {x["instrumentName"]: x for x in json.loads(gzip.decompress(destino.read_bytes()))}
        except (OSError, ValueError):
            viejas = {}
        if any(viejas.get(k) != v for k, v in nuevas.items()):
            viejas.update(nuevas)
            _escribir(destino, gzip.compress(json.dumps(sorted(viejas.values(), key=lambda x: x["instrumentName"]),
                                                       separators=(",", ":")).encode()))


def _guardar_historia(hoy: dict) -> dict:
    """Suma a la historia el spread de cada emisor en SU fecha de cierre, y la devuelve."""
    try:
        h = json.loads(HISTORIA.read_text())
    except (OSError, ValueError):
        h = {}
    cambio = False
    for cod, v in hoy.items():
        if h.setdefault(v["fecha"], {}).get(cod) != v["spread_pb"]:
            h[v["fecha"]][cod] = v["spread_pb"]
            cambio = True
    if cambio:
        _escribir(HISTORIA, json.dumps(h, separators=(",", ":"), sort_keys=True).encode())
    return h


def ultimo(forzar: bool = False) -> tuple:
    """(resumen por emisor, historia, aviso). Si ICE no responde, lo último guardado.

    `forzar` es para el timer: cada precio queda unas 24 h en ICE (Asia cierra
    antes que EE.UU.), así que una bajada diaria que no lea la caché no pierde días."""
    clave = "cds:ice:v1"
    datos = None if forzar else cache.leer_respuesta(clave, HORAS_CACHE)
    aviso = None
    if datos is None:
        try:
            filas = _bajar()
            _guardar_crudo(filas)
            datos = _resumir(filas)
            cache.guardar_respuesta(clave, datos)
        except Exception as e:
            log.warning("ICE CDS: %s", e)
            datos = cache.leer_respuesta(clave, 24 * 30, {})
            aviso = "ICE no respondió: se muestra el último cierre guardado." if datos else \
                    "ICE no respondió y no hay un cierre guardado."
    return datos, (_guardar_historia(datos) if datos else {}), aviso


def _cambio(historia: dict, cod: str, fecha: str, dias: int):
    """Cuánto se movió el spread desde hace `dias` (o lo más cerca que haya)."""
    objetivo = date.fromordinal(date.fromisoformat(fecha).toordinal() - dias).isoformat()
    previas = [f for f in historia if f <= objetivo and cod in historia[f]]
    if not previas:
        return None
    return round(historia[fecha][cod] - historia[max(previas)][cod], 1) if cod in historia.get(fecha, {}) else None


def _z(serie: list):
    """z del ensanche de las últimas RUEDAS contra los anteriores, o None si falta historia."""
    if len(serie) < MIN_HISTORIA:
        return None
    import numpy as np
    s = np.array(serie, dtype=float)
    d = s[RUEDAS:] - s[:-RUEDAS]
    sd = d[-253:-1].std(ddof=1)
    return round(float(d[-1] / sd), 2) if sd > 0 else None


def alerta_mercado() -> dict:
    """Ensanche de 20 ruedas del high yield contra el Treasury (HYG/IEF), en z."""
    clave = f"cds:alerta:{date.today().isoformat()}"
    guardado = cache.leer_respuesta(clave, HORAS_CACHE)
    if guardado is not None:
        return guardado
    import numpy as np
    from core.data import yahoo
    try:
        # Ajustados: HYG reparte todos los meses y sin ajustar cada pago parece estrés.
        px = {t: yahoo.ticker(t).history(start="2006-01-01", auto_adjust=True)["Close"] for t in ("HYG", "IEF")}
    except Exception as e:
        log.warning("alerta HYG/IEF: %s", e)
        return {"error": "Yahoo no respondió: sin alerta de mercado por ahora."}
    import pandas as pd
    df = pd.DataFrame(px).dropna()
    df.index = df.index.tz_localize(None) if getattr(df.index, "tz", None) else df.index
    estres = -(np.log(df.HYG) - np.log(df.IEF)) * 1e4
    d = estres.diff(RUEDAS)
    z = (d / d.rolling(252).std().shift(1)).dropna()
    # Un episodio sigue vivo mientras no pasen RUEDAS seguidas debajo del umbral:
    # en 2026 cruzó el 16-oct, aflojó unos días y volvió el 30-oct; es la misma alerta.
    arriba = np.flatnonzero(z.values >= Z_ALERTA)
    desde = None
    if len(arriba) and len(z) - 1 - arriba[-1] < RUEDAS:
        i = len(arriba) - 1
        while i > 0 and arriba[i] - arriba[i - 1] <= RUEDAS:
            i -= 1
        desde = str(z.index[arriba[i]].date())
    encendida = bool(z.iloc[-1] >= Z_ALERTA)
    ult = z.iloc[-130:]
    r = {"z": round(float(z.iloc[-1]), 2), "umbral": Z_ALERTA, "encendida": encendida, "desde": desde,
         "fecha": str(z.index[-1].date()), **BACKTEST,
         "serie": [[str(i.date()), round(float(v), 2)] for i, v in ult.items()]}
    cache.guardar_respuesta(clave, r)
    return r


def analizar(posiciones) -> dict:
    """Por ticker y por cartera, pesado por lo que vale hoy cada posición."""
    from core.models import portfolio
    datos, historia, aviso = ultimo()
    val = portfolio.valuar(posiciones)
    valor, tipo = {}, {}
    for f in val["posiciones"]:
        if f.get("source") == symbols.SOURCE_FCI or not f.get("valor_usd"):
            continue                           # los FCI son la caja, ver fci-fuera-de-la-tir
        valor[f["ticker"]] = valor.get(f["ticker"], 0) + f["valor_usd"]
        tipo[f["ticker"]] = f.get("source")
    total = sum(valor.values())

    activos, sin_cds = [], []
    for t in sorted(valor, key=valor.get, reverse=True):
        cod = emisor(t, tipo[t])
        d = datos.get(cod) if cod else None
        if not d:
            sin_cds.append(t)
            continue
        bono = symbols.is_bond(t, tipo[t])
        activos.append({
            "ticker": t, "emisor": d["nombre"], "codigo": cod, "es_bono": bono,
            "valor_usd": round(valor[t], 2), "peso_pct": round(valor[t] / total * 100, 2),
            **{k: d[k] for k in ("spread_pb", "prob_1a_pct", "prob_vto_pct", "fecha", "vto", "cupon_pb")},
            "cambio_1d_pb": _cambio(historia, cod, d["fecha"], 1),
            "cambio_30d_pb": _cambio(historia, cod, d["fecha"], 30),
            # Una acción en un evento de crédito va casi a cero; un bono recupera algo.
            "perdida_si_cae": 1 - RECUPERO if bono else 1.0,
            "serie": [[f, historia[f][cod]] for f in sorted(historia) if cod in historia[f]],
        })
        a = activos[-1]
        a["z20"] = _z([v for _, v in a["serie"]])
        a["faltan_dias"] = max(MIN_HISTORIA - len(a["serie"]), 0)

    cubierto = sum(a["valor_usd"] for a in activos)
    cartera = None
    if cubierto:
        w = [(a["valor_usd"] / cubierto, a) for a in activos]
        perdida = sum(a["valor_usd"] * a["prob_1a_pct"] / 100 * a["perdida_si_cae"] for a in activos)
        ninguno = math.prod(1 - a["prob_1a_pct"] / 100 for a in {a["codigo"]: a for a in activos}.values())
        cartera = {
            "spread_pb": round(sum(x * a["spread_pb"] for x, a in w), 1),
            "prob_1a_pct": round(sum(x * a["prob_1a_pct"] for x, a in w), 2),
            "alguno_1a_pct": round((1 - ninguno) * 100, 2),
            "perdida_1a_usd": round(perdida, 2),
            "perdida_1a_pct": round(perdida / total * 100, 3),
            "cobertura_pct": round(cubierto / total * 100, 1),
            "dias_historia": len(historia),
        }
    return {"activos": activos, "cartera": cartera, "sin_cds": sin_cds, "aviso": aviso,
            "mercado": alerta_mercado(), "z_alerta": Z_ALERTA,
            # La de la mayoría: Asia ya puede venir con la de hoy.
            "fecha": Counter(v["fecha"] for v in datos.values()).most_common(1)[0][0] if datos else None,
            "recupero_pct": RECUPERO * 100}


if __name__ == "__main__":                       # chequeo de ida y vuelta, sin red
    hoy, fin = date(2026, 11, 5), date(2031, 12, 20)
    for s, c in ((47, 100), (222, 100), (975, 500), (100, 100)):
        r = desde_precio(precio(s, c, hoy, fin), c, hoy, fin)
        assert abs(r["spread_pb"] - s) < 0.5, (s, c, r)
    assert abs(precio(100, 100, hoy, fin) - 100) < 1e-6
    quieto = [100 + (i % 3) for i in range(100)]
    assert _z(quieto[:79]) is None and abs(_z(quieto)) < 2
    assert _z(quieto[:-1] + [140]) > Z_ALERTA                       # un ensanche brusco enciende
    print("ok", desde_precio(102.4436, 100, hoy, fin), datetime.now().isoformat(timespec="seconds"))
