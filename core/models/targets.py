"""
targets.py — Resolución del subyacente y precios objetivo de analistas.

Fase 1 expone solo la resolución de subyacentes, que es pura y la necesitan
varios módulos (clasificación por sector, precios objetivo, views de
Black-Litterman). El consenso de analistas y las views entran en la fase 3.

El orden en que se prueban los candidatos NO es cosmético: es el arreglo de un
bug real. Ver `underlying_candidates`.
"""

# ETFs populares sin cobertura de analistas: son fondos pasivos, no empresas con
# research. Para ellos la única referencia objetiva a ~12 meses es la curva de
# futuros. (raíz, sufijo yfinance, vencimientos trimestrales)
#
# OJO con el Dow: el ETF del índice es DIA. "DOW" es Dow Inc., una química real
# con su propio consenso de analistas — misma clase de trampa que KOD/Kodiak.
FUTURES_MAP = {
    "GLD": ("GC", ".CMX", False),
    "SLV": ("SI", ".CMX", False),
    "QQQ": ("NQ", ".CME", True),
    "SPY": ("ES", ".CME", True),
    "DIA": ("YM", ".CBT", True),
}

# Acciones argentinas y su ADR en EE.UU., donde publican los analistas grandes.
ADR_MAP = {
    "YPFD.BA": "YPF", "PAMP.BA": "PAM", "TECO2.BA": "TEO", "TGSU2.BA": "TGS",
    "CRES.BA": "CRESY", "GGAL.BA": "GGAL", "BMA.BA": "BMA", "BBAR.BA": "BBAR",
    "SUPV.BA": "SUPV", "CEPU.BA": "CEPU", "EDN.BA": "EDN", "LOMA.BA": "LOMA",
    "TXAR.BA": "TX", "IRSA.BA": "IRS",
}


def underlying_candidates(ticker: str) -> list:
    """Tickers a probar para resolver el activo real, del mejor al peor.

    La "D" antes de ".BA" es casi siempre el sufijo de cotización en dólares
    (mismo activo, otra moneda), así que el candidato SIN la D —el subyacente
    real: KOD→KO, GLDD→GLD, NKED→NKE— va PRIMERO.

    "Con la D" queda de último recurso, y es una posición deliberada: probarlo
    antes es peligroso porque colisiona con tickers reales de otras empresas.
    Pasó de verdad — "KOD" es Kodiak Sciences, una biotech que no tiene nada que
    ver con Coca-Cola, y su consenso de analistas se estaba usando para armar
    views de Black-Litterman sobre KO.

    Misma lógica que hace que el ETF del Dow sea DIA y no "DOW" (Dow Inc.).
    """
    from core.data.symbols import base_symbol, strip_ba

    t = ticker.upper().strip()
    candidatos = [t]

    if t in ADR_MAP:
        candidatos.append(ADR_MAP[t])

    if t.endswith(".BA"):
        base = base_symbol(t)          # ya sin la D de moneda, si la tenía
        sym = strip_ba(t)              # tal cual figura en BYMA
        candidatos.append(base)        # el subyacente real: prioridad
        if sym != base:
            candidatos.append(sym)     # último recurso: por si la D es del nombre

    vistos, salida = set(), []
    for c in candidatos:
        if c and c not in vistos:
            vistos.add(c)
            salida.append(c)
    return salida


# ══════════════════════════════════════════════════════════════════════════
#  Precio objetivo de analistas
# ══════════════════════════════════════════════════════════════════════════

_MESES_CODIGO = {1: "F", 2: "G", 3: "H", 4: "J", 5: "K", 6: "M",
                 7: "N", 8: "Q", 9: "U", 10: "V", 11: "X", 12: "Z"}
_TRIMESTRALES = {3, 6, 9, 12}


def _objetivo_yfinance(simbolo: str):
    """Consenso de analistas de yfinance, cacheado 24 h.

    Sin caché este era el modelo más lento de todos con diferencia: pide el
    `.info` completo por cada ticker y por cada candidato, y con seis posiciones
    tarda más que los otros diez modelos juntos. Un precio objetivo de analistas
    se mueve de semana en semana, así que cachearlo un día no pierde nada.
    """
    from core.data import cache

    clave = f"yf:target:{simbolo.upper()}"
    guardado = cache.leer_respuesta(clave, 24, default="__falta__")
    if guardado != "__falta__":
        return guardado

    r = _pedir_objetivo_yfinance(simbolo)
    cache.guardar_respuesta(clave, r)
    return r


def _precio_de_mercado(simbolo: str):
    """El último cierre: el MISMO precio con el que se valúa la cartera.

    El `.info` de yfinance trae un precio en vivo, y se cachea 24 h junto con el
    consenso —que sí conviene cachear, porque un precio objetivo se mueve de
    semana en semana—. El precio de hoy no: dos máquinas que pidieron el `.info`
    a horas distintas mostraban un "actual" distinto para el mismo papel —8,55 y
    8,38 el 2026-09-09— y ninguno de los dos coincidía con el 8,37 que la tabla
    de tenencias tenía dos paneles más arriba.
    """
    from core.data import sources

    s = sources.precios_base(simbolo)
    return round(float(s.iloc[-1]), 4) if not s.empty else None


def _a_escala(r: dict, destino, origen):
    """Los precios del consenso, llevados de la escala `origen` a `destino`.

    El upside es invariante al cambio de escala —el ratio del CEDEAR y el tipo de
    cambio se cancelan en el cociente— pero se recalcula igual contra el precio
    de hoy: el que venía del consenso se midió contra el precio del momento en
    que se pidió, que puede ser de ayer.
    """
    salida = dict(r)
    if not (destino and origen):
        return salida
    factor = destino / origen
    for k in ("objetivo_medio", "objetivo_alto", "objetivo_bajo"):
        if salida.get(k) is not None:
            salida[k] = round(float(salida[k]) * factor, 2)
    salida["actual"] = destino
    if salida.get("objetivo_medio"):
        salida["upside_pct"] = round((salida["objetivo_medio"] / destino - 1) * 100, 1)
    return salida


def _pedir_objetivo_yfinance(simbolo: str):
    try:
        import yfinance as yf
        info = yf.Ticker(simbolo).info or {}
    except Exception:
        return None
    actual = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")
    if not actual:
        return None
    objetivo = info.get("targetMeanPrice")
    if not objetivo:
        return {"actual": round(float(actual), 2), "objetivo_medio": None}
    return {
        "actual": round(float(actual), 2),
        "objetivo_medio": round(float(objetivo), 2),
        "objetivo_alto": info.get("targetHighPrice"),
        "objetivo_bajo": info.get("targetLowPrice"),
        "upside_pct": round((objetivo / actual - 1) * 100, 1),
        "recomendacion": info.get("recommendationKey"),
        "n_analistas": info.get("numberOfAnalystOpinions"),
        "fuente": "yfinance",
    }


def _curva_futuros(subyacente: str):
    """Retorno implícito a ~12 meses por la curva de futuros.

    Para ETFs como GLD, SLV o QQQ no hay analistas: son fondos pasivos, no
    empresas con research. El futuro a un año es el único precio de mercado
    objetivo que existe para ellos — pero refleja sobre todo **costo de acarreo**
    (tasa de interés y dividendos), no una predicción direccional. Por eso su
    view entra después con confianza moderada y fija.
    """
    import datetime as dt

    from core.data import cache

    spec = FUTURES_MAP.get(subyacente)
    if not spec:
        return None
    raiz, sufijo, trimestral = spec

    # La curva se arma probando vencimientos hasta que uno conteste, y los que no
    # existen contestan 404 después de esperar: siete pedidos a yfinance sin
    # caché, unos nueve segundos, en CADA corrida de los modelos. Es la mitad del
    # tiempo de un análisis completo. Un precio de futuro a doce meses no se
    # mueve en un día; se guarda por seis horas, negativos incluidos —el
    # vencimiento que no existe hoy tampoco existe en un rato—.
    clave = f"futuros:{subyacente}"
    guardado = cache.leer_respuesta(clave, 6.0, default="__falta__")
    if guardado != "__falta__":
        return guardado

    resultado = _pedir_curva_futuros(raiz, sufijo, trimestral)
    cache.guardar_respuesta(clave, resultado)
    return resultado


def _pedir_curva_futuros(raiz: str, sufijo: str, trimestral: bool):
    """La parte que sale a la red. Separada para que la caché de arriba se lea
    de un vistazo."""
    import datetime as dt

    try:
        import yfinance as yf
        frente = yf.Ticker(f"{raiz}=F").info or {}
        spot = frente.get("regularMarketPrice") or frente.get("previousClose")
        if not spot:
            return None
        for meses in (12, 11, 13, 9, 15, 6, 18):
            base = dt.date.today().replace(day=1)
            m = base.month - 1 + meses
            objetivo = base.replace(year=base.year + m // 12, month=m % 12 + 1)
            while trimestral and objetivo.month not in _TRIMESTRALES:
                m += 1
                objetivo = base.replace(year=base.year + m // 12, month=m % 12 + 1)
            simbolo = f"{raiz}{_MESES_CODIGO[objetivo.month]}{str(objetivo.year)[-2:]}{sufijo}"
            info = yf.Ticker(simbolo).info or {}
            fwd = info.get("regularMarketPrice") or info.get("previousClose")
            if fwd:
                meses_reales = max((objetivo - dt.date.today()).days / 30.44, 1)
                ret = ((fwd / spot) ** (12 / meses_reales) - 1) * 100
                return {"actual": round(float(spot), 2),
                        "objetivo_medio": round(float(spot) * (1 + ret / 100), 2),
                        "upside_pct": round(ret, 1), "n_analistas": None,
                        "recomendacion": None, "fuente": f"futuros ({simbolo})",
                        "es_futuro": True}
    except Exception:
        return None
    return None


def objetivo(ticker: str) -> dict:
    """Precio objetivo del consenso, resolviendo el subyacente si hace falta.

    Prueba FMP primero (mejor cobertura en EE.UU.), después yfinance, y si el
    activo es un ETF sin analistas, la curva de futuros.

    **Reexpresión de escala.** Cuando el consenso viene de otro candidato —el
    ADR de una acción argentina, o el subyacente de un CEDEAR— los precios están
    en la escala de ESE instrumento, no en la del ticker que tenés. El upside en
    cambio es invariante: el ratio del CEDEAR y el tipo de cambio se cancelan en
    el cociente objetivo/actual. Así que se conserva el upside y se reexpresa el
    objetivo sobre el precio propio. No hace falta ninguna tabla de ratios de
    BYMA, y se autocorrige si el ratio cambia.
    """
    from core.data import fmp

    ticker = ticker.upper().strip()
    propio = _objetivo_yfinance(ticker)
    # El precio manda desde la serie de cierres, no desde el `.info` cacheado.
    precio_propio = _precio_de_mercado(ticker) or (propio or {}).get("actual")

    if propio and propio.get("objetivo_medio"):
        r = _a_escala(propio, precio_propio, propio.get("actual"))
        return {"ticker": ticker, "disponible": True, **r, "reexpresado": False}

    for candidato in underlying_candidates(ticker):
        if candidato == ticker:
            continue
        r = (fmp.objetivo(candidato) if fmp.habilitado() else None) or _objetivo_yfinance(candidato)
        if r and r.get("objetivo_medio"):
            return _reexpresar(ticker, r, precio_propio, candidato,
                               _precio_de_mercado(candidato))

    for candidato in underlying_candidates(ticker):
        if candidato in FUTURES_MAP:
            r = _curva_futuros(candidato)
            if r:
                return _reexpresar(ticker, r, precio_propio, candidato)

    salida = {"ticker": ticker, "disponible": False}
    if precio_propio:
        salida["actual"] = precio_propio
    return salida


def _reexpresar(ticker, r, precio_propio, origen, precio_origen=None):
    """Lleva objetivo y precio a la escala del ticker propio.

    La escala de salida sale de dos precios de cierre —el del ticker y el del
    instrumento del consenso—, no del `.info` de cada uno: así dos máquinas con
    la misma cartera muestran el mismo número. Para la curva de futuros no hay
    serie comparable y se usa el spot que ella misma trajo.
    """
    salida = {"ticker": ticker, "disponible": True, **r,
              "origen_consenso": origen, "reexpresado": False}
    referencia = precio_origen or r.get("actual")
    if precio_propio and referencia:
        salida.update(_a_escala(r, precio_propio, referencia))
        salida["reexpresado"] = True
    return salida


def analizar(posiciones) -> dict:
    """Precios objetivo de toda la cartera, con la señal combinada."""
    from core.models import momentum as mom

    momentos = {m["ticker"]: m for m in mom.analizar(posiciones).get("por_activo", [])}
    salida = []
    for ticker in sorted({str(p["ticker"]).upper() for p in posiciones}):
        r = objetivo(ticker)
        señal_mom = momentos.get(ticker, {}).get("señal")
        r["momentum"] = señal_mom
        r["combinada"], r["combinada_texto"] = _combinar(r.get("upside_pct"), señal_mom)
        salida.append(r)

    con_dato = [s for s in salida if s.get("disponible") and s.get("upside_pct") is not None]
    return {
        "por_activo": salida,
        "upside_promedio_pct": (round(sum(s["upside_pct"] for s in con_dato) / len(con_dato), 1)
                                if con_dato else None),
        "con_cobertura": len(con_dato), "total": len(salida),
    }


def _combinar(upside, señal_momentum):
    """Cruza fundamento (precio objetivo) con timing (momentum).

    El usuario notó el problema real: Objetivos podía decir "comprar" por un
    upside alto mientras el activo venía cayendo, y entrabas a pérdida. Un
    objetivo alto dice **cuánto** puede valer, no **cuándo**.
    """
    if upside is None:
        return "SIN DATO", "No hay cobertura de analistas para este activo."
    if señal_momentum in ("EVITAR", "ESPERAR"):
        if upside > 15:
            return ("ESPERAR GIRO", "Buen precio objetivo pero viene cayendo. "
                                    "Esperá señal de giro antes de entrar.")
        return "REDUCIR", "Sin recorrido al alza y con el momentum en contra."
    if upside > 15:
        return "COMPRAR", "Recorrido al alza y momentum acompañando."
    if upside > 0:
        return "MANTENER", "Cerca del precio objetivo: poco recorrido."
    return "CARO", "Cotiza por encima del objetivo del consenso."
