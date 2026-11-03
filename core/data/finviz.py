"""
finviz.py — Earnings e insiders de lo que hay en cartera, desde Finviz.

Finviz sólo conoce lo que cotiza en EE.UU.: un CEDEAR se busca por su subyacente
y una acción argentina por su ADR. Lo que no tiene equivalente (bonos, FCI,
METR) no se pide: un símbolo argentino buscado tal cual puede ser otra empresa
allá, como KOD, que es Kodiak y no Coca-Cola.

Una sola página trae las dos cosas, así que es un pedido por subyacente, en fila
y cacheado 12 h. Finviz no tiene API: se lee su HTML, y si corta se muestra lo
que ya estaba. Una caída de red no se cachea como "no tiene datos".
"""
import html
import json
import logging
import time
import warnings
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from core.data import cache, symbols

log = logging.getLogger(__name__)

HORAS_CACHE = 12
PAUSA_S = 0.4
TOPE_S = 60            # lo que no entra sale en la próxima visita, ya con caché
VENTANA_DIAS = 90      # para reaccionar a tiempo: lo de hace medio año ya pasó
NY = ZoneInfo("America/New_York")      # un ex-dividendo es 04:00 UTC: en UTC cae bien, un balance no siempre
# "Reiterated" es casi todos los días y no cambia nada.
ACCIONES_ANALISTA = {"Upgrade", "Downgrade", "Initiated", "Resumed"}

CAMPOS = {"eps_12m": "EPS (ttm)", "eps_prox_q": "EPS next Q", "eps_qq": "EPS Q/Q",
          "ventas_qq": "Sales Q/Q", "pe": "P/E", "pe_futuro": "Forward P/E"}


def subyacente(ticker: str, source: str = None):
    """El símbolo en EE.UU., o None si no tiene uno confiable."""
    from core.models.targets import ADR_MAP
    t = str(ticker).upper().strip()
    if source == symbols.SOURCE_FCI or symbols.is_bond(t, source):
        return None
    if t.endswith(".BA"):
        if not symbols.es_cedear(t):
            return ADR_MAP.get(t)
        return symbols.eeuu(t)                    # GOGLD es Alphabet, no GOGL
    return None if "." in t else t


def _num(texto):
    """'29.13%' → 29.13; '-' o lo que no sea número → None."""
    try:
        return float(str(texto).replace("%", "").replace(",", ""))
    except ValueError:
        return None


def _anio_cercano(crudo: datetime, hoy: date, solo_pasado: bool = False) -> datetime:
    """Finviz no da el año: el que deja la fecha más cerca de hoy."""
    posibles = []
    for anio in (hoy.year - 1, hoy.year, hoy.year + 1):
        try:
            f = crudo.replace(year=anio)
        except ValueError:                           # 29 de febrero en año común
            continue
        if not solo_pasado or f.date() <= hoy:
            posibles.append(f)
    return min(posibles, key=lambda f: abs((f.date() - hoy).days))


def _balance(texto, hoy: date):
    """'Nov 02 AMC' → fecha y momento."""
    partes = str(texto or "").split()
    if len(partes) < 2:
        return None, None
    try:
        crudo = datetime.strptime(f"{partes[0]} {partes[1]} 2000", "%b %d %Y")
    except ValueError:
        return None, None
    return _anio_cercano(crudo, hoy).date().isoformat(), (partes[2] if len(partes) > 2 else None)


def _presentado(texto, hoy: date):
    """'Oct 29 06:30 PM' → '2026-10-29T18:30'. La operación llega días después de
    hecha: lo nuevo se reconoce por cuándo se presentó, no por su fecha. Nunca es
    futuro: un "Nov 05" visto el 3 de noviembre es del año pasado."""
    try:
        crudo = datetime.strptime(f"{texto} 2000", "%b %d %I:%M %p %Y")
    except ValueError:
        return None
    return _anio_cercano(crudo, hoy, solo_pasado=True).strftime("%Y-%m-%dT%H:%M")


def _fecha_insider(texto):
    """"Oct 27 '26" → '2026-10-27'."""
    try:
        return datetime.strptime(str(texto), "%b %d '%y").date().isoformat()
    except ValueError:
        return None


def _limpio(v):
    return None if v is None or v != v else v      # NaN no existe en JSON


def _filas_insiders(df) -> list:
    if df is None:
        return []
    filas = []
    for _, f in df.iterrows():
        link = str(f.get("SEC Form 4 Link") or "")
        filas.append({
            "nombre": f.get("Insider Trading"), "cargo": f.get("Relationship"),
            "fecha": _fecha_insider(f.get("Date")), "tipo": f.get("Transaction"),
            "precio": _limpio(f.get("Cost")), "acciones": _limpio(f.get("#Shares")),
            "valor_usd": _limpio(f.get("Value ($)")), "tenencia": _limpio(f.get("#Shares Total")),
            "presentado": f.get("SEC Form 4"),
            "link": link.replace("http://", "https://", 1) if link.startswith(("http://www.sec.gov/", "https://www.sec.gov/")) else None,
        })
    return filas


def _resumen_insiders(filas, hoy: date) -> dict:
    """Plata de compras y ventas ejecutadas. Afuera las "Proposed Sale" (el aviso
    Form 144 de una venta que después aparece como Sale: contarían dos veces) y
    el ejercicio de opciones, que no es una decisión de mercado."""
    desde = (hoy - timedelta(days=VENTANA_DIAS)).isoformat()
    recientes = [f for f in filas if (f["fecha"] or "") >= desde]
    suma = lambda tipo: sum(f["valor_usd"] or 0 for f in recientes if f["tipo"] == tipo)
    compras, ventas = suma("Buy"), suma("Sale")
    return {"compras_usd": compras, "ventas_usd": ventas, "neto_usd": compras - ventas,
            "ultimo": max((f["fecha"] for f in filas if f["fecha"]), default=None),
            "ult_presentado": max(filter(None, (_presentado(f.get("presentado"), hoy) for f in filas)), default=None)}


def _eventos_de(chart_events, ratings, ex_fecha) -> list:
    """Calendario del papel: balances, ex-dividendos y cambios de analistas."""
    salida = []
    for e in chart_events or []:
        fecha = datetime.fromtimestamp(e["dateTimestamp"], NY).date().isoformat()
        if e.get("eventType") == "chartEvent/earnings":
            salida.append({"fecha": fecha, "tipo": "balance", "periodo": e.get("fiscalPeriod"),
                           "eps": e.get("epsActual"), "eps_esperado": e.get("epsEstimate"),
                           "ventas_m": e.get("salesActual"), "ventas_esperado_m": e.get("salesEstimate")})
        elif e.get("eventType") == "chartEvent/dividends":
            salida.append({"fecha": fecha, "tipo": "dividendo",
                           "monto": (e.get("ordinary") or 0) + (e.get("special") or 0)})
    for r in ratings or []:
        if r.get("action") in ACCIONES_ANALISTA:
            salida.append({"fecha": r.get("date"), "tipo": "analista", "accion": r["action"], "firma": r.get("firm"),
                           "rating": html.unescape(r.get("rating") or ""), "objetivo": html.unescape(r.get("priceTarget") or "")})
    # Un ex-dividendo anunciado puede no estar todavía entre los eventos del gráfico.
    try:
        ex = datetime.strptime(str(ex_fecha), "%b %d, %Y").date().isoformat()
    except ValueError:
        ex = None
    if ex and not any(x["tipo"] == "dividendo" and x["fecha"] == ex for x in salida):
        salida.append({"fecha": ex, "tipo": "dividendo", "monto": None})
    return salida


def _datos_incrustados(soup) -> tuple:
    """(eventos, ratings) del JSON que la página trae para sus gráficos. La librería
    no los expone. Si Finviz lo cambia, queda sin calendario y lo demás sigue."""
    eventos, ratings = [], []
    try:
        for s in soup.find_all("script"):
            texto = s.string or ""
            i = texto.find('"chartEvents":')
            if i >= 0:
                eventos, _ = json.JSONDecoder().raw_decode(texto[i + len('"chartEvents":'):])
                break
        isla = soup.find("script", attrs={"data-ssr-props": "ssr-island-analyst-ratings-0"})
        if isla and isla.string:
            ratings = json.loads(isla.string).get("ratings") or []
    except (ValueError, TypeError, AttributeError) as e:
        log.warning("finviz: calendario ilegible: %s", e)
    return eventos, ratings


def _bajar(sym: str) -> dict:
    """La ficha cruda. Un 404 es un dato (no existe); lo demás se propaga."""
    from finvizfinance.quote import finvizfinance
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")           # un ETF no trae insiders: es normal
            q = finvizfinance(sym)
            fund, insiders = q.ticker_fundament(), q.ticker_inside_trader()
    except Exception as e:
        if "404" in str(e):
            return {"existe": False}
        raise
    return {"existe": True, "eventos": _eventos_de(*_datos_incrustados(q.soup), fund.get("Dividend Ex-Date")),
            "fund": {k: fund.get(k) for k in (
                "Company", "Earnings", "EPS/Sales Surpr.", "Insider Own", "Insider Trans", *CAMPOS.values())},
            "insiders": _filas_insiders(insiders)}


def _ficha(sym: str, hasta: float):
    """(ficha, ya venía de la caché). Sin red ni tiempo, (None, _)."""
    clave = f"finviz:v2:{sym}"
    guardado = cache.leer_respuesta(clave, HORAS_CACHE)
    if guardado is not None:
        return guardado, True
    if time.monotonic() > hasta:
        return None, False
    ficha = _bajar(sym)
    cache.guardar_respuesta(clave, ficha)
    return ficha, False


def _ultimo_balance(eventos) -> dict:
    """El último balance con resultados: su fecha y los brutos de la sorpresa."""
    publicados = [e for e in eventos if e["tipo"] == "balance" and e.get("eps") is not None]
    if not publicados:
        return {}
    e = max(publicados, key=lambda x: x["fecha"])
    return {k: e.get(k) for k in ("fecha", "eps", "eps_esperado", "ventas_m", "ventas_esperado_m")}


def _armar(sym, tickers, ficha, hoy: date) -> dict:
    f = ficha["fund"]
    # Finviz pasa a dar el próximo apenas se anuncia: sólo sirve si ya ocurrió.
    anunciado, _ = _balance(f.get("Earnings"), hoy)
    ultimo = _ultimo_balance(ficha.get("eventos", []))
    fecha = ultimo.get("fecha") or (anunciado if anunciado and anunciado <= hoy.isoformat() else None)
    surpr = str(f.get("EPS/Sales Surpr.") or "").split()
    earnings = {k: _num(f.get(v)) for k, v in CAMPOS.items()}
    earnings.update(ultimo, fecha=fecha,
                    sorpresa_eps=_num(surpr[0]) if surpr else None,
                    sorpresa_ventas=_num(surpr[1]) if len(surpr) > 1 else None)
    filas = sorted(ficha["insiders"], key=lambda x: x["fecha"] or "", reverse=True)
    desde = (hoy - timedelta(days=VENTANA_DIAS)).isoformat()
    return {"subyacente": sym, "tickers": tickers, "empresa": f.get("Company"),
            "eventos": [e for e in ficha.get("eventos", []) if (e["fecha"] or "") >= desde],
            "earnings": earnings if fecha or earnings["eps_12m"] is not None else None,
            "insiders": ({"propio_pct": _num(f.get("Insider Own")), "cambio_pct": _num(f.get("Insider Trans")),
                          **_resumen_insiders(filas, hoy),
                          # Las mismas de la suma, para que el total se pueda cotejar. Un
                          # ejercicio a $0 es acciones que entregan como sueldo: taparía lo que importa.
                          "filas": [{**x, "presentado": _presentado(x["presentado"], hoy)}
                                    for x in filas if x["valor_usd"] and (x["fecha"] or "") >= desde]}
                         if filas or _num(f.get("Insider Own")) is not None else None)}


def analizar(posiciones) -> dict:
    """Sólo lo que Finviz tiene; lo demás se nombra en `sin_datos`."""
    por_sym, sin_datos = {}, []
    for p in posiciones:
        t = str(p["ticker"]).upper()
        sym = subyacente(t, p.get("source"))
        if sym:
            por_sym.setdefault(sym, set()).add(t)
        elif p.get("source") != symbols.SOURCE_FCI:
            sin_datos.append(t)

    hoy, hasta, activos, aviso = date.today(), time.monotonic() + TOPE_S, [], None
    for sym in sorted(por_sym):
        tickers = sorted(por_sym[sym])
        if aviso:
            sin_datos += tickers
            continue
        try:
            ficha, de_cache = _ficha(sym, hasta)
        except Exception as e:                       # bloqueo o red: no insistir con el resto
            log.warning("finviz %s: %s", sym, e)
            ficha, de_cache = None, False
        if ficha is None:
            aviso = "Finviz no respondió: faltan algunos papeles. Se reintenta en la próxima visita."
            sin_datos += tickers
            continue
        armado = _armar(sym, tickers, ficha, hoy) if ficha.get("existe") else None
        if armado and (armado["earnings"] or armado["insiders"] or armado["eventos"]):
            activos.append(armado)
        else:
            sin_datos += tickers
        if not de_cache:
            time.sleep(PAUSA_S)
    return {"activos": activos, "sin_datos": sorted(set(sin_datos)), "aviso": aviso}
