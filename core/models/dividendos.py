"""
dividendos.py — Los dividendos que cobraron tus lotes, estimados con yfinance.

Sirve para cualquier cartera, tenga broker conectado o no: Yahoo publica el
dividendo **bruto** por papel y por fecha ex-dividendo, y con las fechas de cada
lote se sabe cuáles lo cobraron. Del bruto al neto se pasa con la retención que
el usuario configuró en la cartera para ese tipo de papel.

Tres cosas que no son obvias:

  1. Yahoo ajusta los dividendos viejos por splits (NVDA 2024: 0,04 → 0,004).
     Está bien así: los lotes importados ya tienen la cantidad post-split, y un
     lote cargado a mano con la cantidad vieja tampoco se valuaría bien.

  2. A la historia de un CEDEAR le faltan pagos (QQQD.BA trae 1 de 6, IEURD.BA
     ninguno). El hueco se tapa con el pago del subyacente llevado a la escala
     del CEDEAR por el cociente de precios del mismo día: el rendimiento del
     dividendo es el mismo en los dos, y el cociente ya lleva adentro el ratio
     y, si el CEDEAR cotiza en pesos, el tipo de cambio.

  3. Cobra quien tenía el papel al ex-dividendo: comprado ANTES de esa fecha y
     vendido ese día o después.
"""

from datetime import date, timedelta

from core.data import cache, mep, sources
from core.data.symbols import SOURCE_FCI, base_symbol

LOTE = "yfinance:dividendos"
# Un dividendo ya cargado —a mano, desde Yahoo o desde el broker— se reconoce
# por papel y fecha: la de cobro cae después del ex-dividendo, en general dentro
# del mes (KO 16 días, MSFT 21). Con un pago mensual (GGAL) el siguiente
# ex-dividendo ya queda fuera de la ventana.
VENTANA_DIAS = 30


def tipo(ticker: str, source: str = None) -> str:
    """Contra qué retención va: "acciones", "cedears" o "bonos"."""
    if sources.is_bond(ticker, source):
        return "bonos"
    if not ticker.upper().endswith(".BA"):
        return "acciones"
    # Yahoo corta el nombre —"ADVANCED MICRO DEVICES INC CEDE", el de GLD es un
    # GDR— y a veces ni lo dice: "TAIWAN SEMICONDUCTOR MANUFACTUR". Ahí decide
    # el país: en BYMA, una empresa de afuera es un CEDEAR.
    ficha = sources.info(ticker)
    nombre = (ficha.get("shortName") or "").upper()
    pais = ficha.get("country")
    if "CEDE" in nombre or "GDR" in nombre.split() or (pais and pais != "Argentina"):
        return "cedears"
    return "acciones"


def _serie(ticker: str) -> dict:
    """{fecha ex-dividendo: bruto por papel}, cacheada un día."""
    clave = f"yf:div:{ticker.upper()}"
    guardado = cache.leer_respuesta(clave, 24)
    if guardado is not None:
        return guardado
    try:
        from core.data import yahoo
        s = yahoo.ticker(ticker).dividends
        datos = {i.date().isoformat(): float(v) for i, v in s.items() if v > 0}
    except Exception:
        return {}                     # una caída de red no se cachea como "no paga"
    cache.guardar_respuesta(clave, datos)
    return datos


def cobros(ticker: str, clase: str, desde: str = "") -> dict:
    """Pagos brutos del papel desde `desde`, con los huecos del CEDEAR tapados
    por el subyacente. Sólo se mira desde la primera compra: cada hueco cuesta
    un pedido de precios, y ADBE paga desde antes de que existiera el CEDEAR."""
    propios = {f: v for f, v in _serie(ticker).items() if f > desde}
    if clase != "cedears":
        return propios
    # ponytail: el subyacente es el símbolo de BYMA sin la D; un CEDEAR cuyo
    # símbolo difiere del de EE.UU. (BRKB → BRK-B) queda sin tapar sus huecos.
    base = base_symbol(ticker)
    todos = dict(propios)
    fechas = [date.fromisoformat(f) for f in propios]
    for f, monto in _serie(base).items():
        if f <= desde:
            continue
        d = date.fromisoformat(f)
        if any(abs((d - x).days) <= 7 for x in fechas):
            continue
        desde = (d - timedelta(days=10)).isoformat()
        cierres = [_cierre(x, desde, f) for x in (ticker, base)]
        if all(cierres):
            todos[f] = monto * cierres[0] / cierres[1]
    return todos


def _cierre(ticker: str, desde: str, hasta: str):
    """Último cierre dentro de la ventana, o None. Sin historia, `precios` cae
    al precio de hoy: usarlo daría el cociente de hoy para un pago de otro año."""
    df = sources.precios(ticker, desde, hasta)
    if df.empty or not (desde <= df.index[-1].date().isoformat() <= hasta):
        return None
    return float(df["Close"].iloc[-1]) or None


def estimar(lotes: list, pagos: dict, retenciones: dict, existentes: list = (),
            hoy: str = None) -> list:
    """Los dividendos que cobraron los lotes, como registros del P&L realizado.

    lotes        [{ticker, buy_date, sell_date (None si sigue abierto), qty, clase}]
    pagos        {ticker: {fecha ex: bruto por papel}}
    retenciones  {clase: % retenido}
    existentes   dividendos ya registrados: no se vuelven a proponer.
    """
    hoy = hoy or date.today().isoformat()
    ya = {}
    for t in existentes:
        ya.setdefault(base_symbol(t["ticker"]), []).append(date.fromisoformat(t["sell_date"]))

    por_pago = {}
    for lote in lotes:
        for ex, bruto in (pagos.get(lote["ticker"]) or {}).items():
            if not (lote["buy_date"] < ex <= hoy) or (lote["sell_date"] and lote["sell_date"] < ex):
                continue
            d = date.fromisoformat(ex)
            if any(0 <= (x - d).days <= VENTANA_DIAS for x in ya.get(base_symbol(lote["ticker"]), [])):
                continue
            clave = (lote["ticker"], ex)
            x = por_pago.setdefault(clave, {"qty": 0.0, "bruto": bruto, "clase": lote["clase"]})
            x["qty"] += float(lote["qty"])

    salida = []
    for (ticker, ex), x in sorted(por_pago.items()):
        ret = float(retenciones.get(x["clase"]) or 0)
        neto = x["bruto"] * (1 - ret / 100)
        salida.append({
            "ticker": ticker, "tipo": "dividendo", "buy_date": ex, "sell_date": ex,
            "buy_price": 0.0, "sell_price": round(neto, 6), "qty": round(x["qty"], 6),
            "buy_comm": 0.0, "sell_comm": 0.0, "pnl": round(x["qty"] * neto, 4),
            "moneda": sources.ticker_currency(ticker), "lote": LOTE, "estimado": True,
            "bruto": round(x["bruto"], 6), "retencion": ret,
            "notes": f"Yahoo · bruto {x['bruto']:.4f} por papel · retención {ret:g} %",
        })
    return salida


def proponer(posiciones: list, realizadas: list, retenciones: dict) -> list:
    """Arma los lotes de la cartera —abiertos y cerrados— y estima sus dividendos."""
    lotes = []
    for p in posiciones:
        lotes.append({"ticker": str(p["ticker"]).upper(), "buy_date": p.get("buy_date") or "",
                      "sell_date": None, "qty": p.get("qty") or 0, "source": p.get("source")})
    for t in realizadas:
        if t.get("tipo") in ("dividendo", "fci"):
            continue
        lotes.append({"ticker": t["ticker"].upper(), "buy_date": t["buy_date"],
                      "sell_date": t["sell_date"], "qty": t["qty"], "source": None})

    # Los bonos pagan renta, no dividendos, y yfinance no la tiene; un FCI no paga.
    clases, pagos = {}, {}
    for lote in lotes:
        t = lote["ticker"]
        if t not in clases:
            clases[t] = tipo(t, lote["source"])
        lote["clase"] = clases[t]
    for t, clase in clases.items():
        propios = [l for l in lotes if l["ticker"] == t and l["buy_date"]]
        if propios and clase != "bonos" and SOURCE_FCI not in {l["source"] for l in propios}:
            pagos[t] = cobros(t, clase, min(l["buy_date"] for l in propios))

    existentes = [t for t in realizadas if t.get("tipo") == "dividendo"]
    return estimar([l for l in lotes if l["buy_date"]], pagos, retenciones, existentes)


def registro(realizadas: list) -> list:
    """Cada dividendo cobrado con su bruto y lo que se le retuvo, para controlar.

    El bruto de lo traído de Yahoo viaja en el registro. El de lo cargado a mano
    o corregido no: se busca en Yahoo el ex-dividendo de los 45 días previos al
    cobro y se multiplica por la cantidad. Sin ese dato, el bruto queda vacío
    —mejor un hueco que una retención inventada—.
    """
    filas = []
    for t in sorted((t for t in realizadas if t.get("tipo") == "dividendo"),
                    key=lambda t: t["sell_date"], reverse=True):
        ticker, qty, neto = t["ticker"].upper(), float(t.get("qty") or 0), float(t.get("pnl") or 0)
        unitario = t.get("bruto")
        if unitario is None:
            clase = tipo(ticker)
            cobro = date.fromisoformat(t["sell_date"])
            pagos = cobros(ticker, clase, (cobro - timedelta(days=46)).isoformat())
            previos = [f for f in pagos if (cobro - date.fromisoformat(f)).days >= 0]
            unitario = pagos[max(previos)] if previos else None
        bruto = unitario * qty if unitario is not None else None
        # Yahoo da el bruto en la moneda del papel; el cobro pudo anotarse en otra
        # (BYMA pagó en dólares). Se compara en la del cobro, al MEP de ese día.
        moneda = (t.get("moneda") or sources.ticker_currency(ticker)).upper()
        if bruto is not None and t.get("bruto") is None and moneda != sources.ticker_currency(ticker):
            bruto = mep.a_usd(bruto, t["sell_date"]) if moneda == "USD" \
                else bruto * (mep.valor(t["sell_date"]) or 0) or None
        filas.append({
            "fecha": t["sell_date"], "ticker": ticker, "clase": tipo(ticker),
            "moneda": moneda,
            "bruto": round(bruto, 2) if bruto is not None else None,
            "retencion": round(bruto - neto, 2) if bruto is not None else None,
            "retencion_pct": round((1 - neto / bruto) * 100, 3) if bruto else None,
        })
    return filas
