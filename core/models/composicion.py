"""
composicion.py — En qué está invertida la cartera: tipo, sector e industria.

Tres cortes de la misma cartera, cada uno más fino que el anterior:

    tipo        renta variable · ETF · commodities · RF pública · RF privada (ON)
    sector      Utilities · Technology · Consumer Defensive · Energía…
    industria   Utilities - Regulated Gas · Semiconductors · Beverages…

Los pesos se calculan sobre el **valor actual en dólares**, no sobre el precio
de compra. Con precio de compra, una posición vieja comprada en pesos a un tipo
de cambio anterior aparenta dominar la cartera aunque hoy valga poco.

Tres trampas que este módulo resuelve y que costaron tiempo descubrir:

  1. Un CEDEAR cotiza en BYMA como "equity" genérico aunque el subyacente sea un
     ETF. QQQD.BA devuelve quoteType=EQUITY sin sector; el que sabe la verdad es
     QQQ. Por eso se prueban todos los candidatos y se prefiere el tipo más
     específico — pero solo para tickers con sufijo "D", porque para los demás
     el segundo candidato es una colisión de nombres esperando pasar.

  2. Un ETF **no tiene sector GICS**, y está bien que no lo tenga: es una canasta
     diversificada, no una empresa. Meterlos todos en "Sin clasificar" parece un
     error de la aplicación. El equivalente para un fondo es `category`
     ("Large Growth", "Commodities Focused"), y eso es lo que se muestra.

  3. Los bonos y ONs tampoco tienen sector. Se agrupan por tipo de emisor, que
     es la pregunta que de verdad se hace sobre renta fija.
"""

from core.data import sources
from core.models.targets import underlying_candidates

# Acciones argentinas: yfinance las cubre mal o en inglés. Tabla corta y curada.
SECTORES_AR = {
    "GGAL": "Financiero", "BBAR": "Financiero", "SUPV": "Financiero", "BMA": "Financiero",
    "YPFD": "Energía", "PAMP": "Energía", "TGSU2": "Energía", "TGNO4": "Energía",
    "METR": "Utilities", "TRAN": "Utilities", "CEPU": "Utilities", "EDN": "Utilities",
    "COME": "Consumo", "MIRG": "Consumo",
    "CRES": "Agro", "AGRO": "Agro",
    "ALUA": "Materiales", "TXAR": "Materiales", "LOMA": "Materiales",
    "IRSA": "Inmobiliario", "TECO2": "Comunicaciones",
}

# Tipos de renta fija por emisor.
TIPOS_RF = {
    **{s: "RF Pública Nacional" for s in
       ("AL29", "AL30", "AL35", "AL41", "GD29", "GD30", "GD35",
        "GD38", "GD41", "GD46", "AE38", "AN29", "PARP")},
    **{s: "RF Pública Nacional (CER)" for s in ("TX26", "TX28", "DICP", "CUAP", "TZXD5")},
    **{s: "RF Pública Provincial" for s in ("BPOA7", "BPOB7", "BPOC7", "BPOD7")},
    **{s: "RF Privada (ON)" for s in
       ("PLC4O", "RUCDO", "TLCTO", "VSCXO", "YCA6O", "CSDOO",
        "MFCCO", "GNNNO", "TGS4O", "YPF4O", "PAMB8", "CARC1", "IRCP2")},
}

# Subyacentes de commodities: ETFs de metales, futuros y mineras.
COMMODITIES = {"GLD", "SLV", "IAU", "SGOL", "PPLT", "PALL", "GDX", "GDXJ", "SIL",
               "GC=F", "SI=F", "PL=F", "PA=F"}

_PALABRAS_COMMODITY = ("gold", "silver", "metal", "commodity", "precious")


def _clasificar_tipo(ticker: str, base: str, source: str):
    """(tipo, ficha_del_subyacente). La ficha se reutiliza para sector."""
    if sources.is_bond(ticker, source):
        return TIPOS_RF.get(base, "Renta Fija"), {}
    if base in COMMODITIES:
        return "Commodities", sources.info(base)

    # Solo vale seguir buscando después de un "equity" genérico si el ticker es
    # un CEDEAR con sufijo "D". Para los demás, el segundo candidato es el
    # símbolo pelado, que colisiona con tickers reales de otras empresas —
    # "METR" sin .BA es un fondo mutuo de EE.UU. que no tiene nada que ver con
    # Metrogas, y aceptarlo convertiría una acción en "Fondo".
    es_cedear_d = base != sources.strip_ba(ticker)

    generico, ficha_generica = None, {}
    for candidato in underlying_candidates(ticker):
        ficha = sources.info(candidato)
        tipo_yf = (ficha.get("quoteType") or "").lower()
        categoria = (ficha.get("category") or "").lower()
        if not tipo_yf:
            continue

        if "etf" in tipo_yf:
            especifico = ("Commodities"
                          if any(p in categoria for p in _PALABRAS_COMMODITY)
                          else "ETF")
            return especifico, ficha
        if "bond" in tipo_yf or "fixed" in tipo_yf:
            return "Renta Fija", ficha
        if "fund" in tipo_yf:
            return "Fondo", ficha
        if "equity" in tipo_yf:
            if generico is None:
                generico, ficha_generica = "Renta Variable", ficha
            if not es_cedear_d:
                break

    return (generico or "Otro"), ficha_generica


def _clasificar_sector(ticker: str, base: str, tipo: str, ficha: dict):
    """(sector, industria). Nunca devuelve un genérico si hay algo mejor."""
    if base in SECTORES_AR:
        return SECTORES_AR[base], SECTORES_AR[base]

    sector = ficha.get("sector")
    industria = ficha.get("industry")

    if not sector or not industria:
        for candidato in underlying_candidates(ticker):
            otra = sources.info(candidato)
            sector = sector or otra.get("sector")
            industria = industria or otra.get("industry")
            if sector and industria:
                break

    # Fondos y canastas: no tienen sector GICS porque no son una empresa. La
    # categoría del fondo es el equivalente y es información real, no relleno.
    if not sector and tipo in ("ETF", "Commodities", "Fondo"):
        categoria = ficha.get("category") or next(
            (sources.info(c).get("category") for c in underlying_candidates(ticker)
             if sources.info(c).get("category")), None)
        if categoria:
            return categoria, categoria

    if not sector:
        sector = tipo if tipo.startswith("RF") or tipo == "Renta Fija" else "Sin clasificar"
    return sector, (industria or sector)


def analizar(posiciones, precios=None) -> dict:
    """Composición de la cartera por tipo, sector e industria.

    Devuelve porcentajes sobre el valor total en dólares, ordenados de mayor a
    menor, más el detalle por activo para poder auditar cualquier clasificación
    que sorprenda.
    """
    from core.models.portfolio import precios_actuales

    precios = precios if precios is not None else precios_actuales(posiciones)

    por_tipo, por_sector, por_industria, detalle = {}, {}, {}, []
    total = 0.0

    for p in posiciones:
        ticker = str(p["ticker"]).upper()
        precio = precios.get(ticker)
        if not precio:
            continue
        valor = float(p.get("qty", 0)) * precio
        if valor <= 0:
            continue

        origen = p.get("source") or None
        base = sources.base_symbol(ticker)

        tipo = p.get("asset_type") or None
        if tipo:
            ficha = sources.info(base)
        else:
            tipo, ficha = _clasificar_tipo(ticker, base, origen)
        sector, industria = _clasificar_sector(ticker, base, tipo, ficha)

        por_tipo[tipo] = por_tipo.get(tipo, 0.0) + valor
        por_sector[sector] = por_sector.get(sector, 0.0) + valor
        por_industria[industria] = por_industria.get(industria, 0.0) + valor
        total += valor

        detalle.append({"ticker": ticker, "subyacente": base, "valor_usd": round(valor, 2),
                        "tipo": tipo, "sector": sector, "industria": industria,
                        "nombre": ficha.get("longName") or ficha.get("shortName") or ""})

    if total <= 0:
        return {"error": "Sin precios para calcular la composición."}

    def reparto(d):
        return [{"etiqueta": k, "valor_usd": round(v, 2), "pct": round(v / total * 100, 2)}
                for k, v in sorted(d.items(), key=lambda x: -x[1])]

    # Un activo que aparece dos veces en el detalle son dos lotes: se agregan.
    agregado = {}
    for d in detalle:
        a = agregado.setdefault(d["ticker"], {**d, "valor_usd": 0.0})
        a["valor_usd"] = round(a["valor_usd"] + d["valor_usd"], 2)

    return {
        "por_tipo": reparto(por_tipo),
        "por_sector": reparto(por_sector),
        "por_industria": reparto(por_industria),
        "detalle": sorted(agregado.values(), key=lambda x: -x["valor_usd"]),
        "valor_total": round(total, 2),
        "moneda": "USD",
    }
