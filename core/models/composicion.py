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

# ETFs de un país o una región: yfinance no trae `country` para un ETF —es
# un dato de empresa, no de fondo—, así que sin esta tabla un ETF de China o
# de Europa quedaba con el país por default (EE.UU., o Argentina si la
# especie D no tenía subyacente con `country`).
#
# La clave es el ticker tal como llega a `base_symbol`: para un CEDEAR
# (FXID.BA) eso ya es el subyacente pelado ("FXI"); para un ETF europeo
# comprado directo (IWDA.AS) `base_symbol` no le toca el sufijo de plaza —no
# es ".BA"— así que la clave lleva el ticker completo.
#
# ponytail: tabla curada a mano con los iShares/MSCI de un solo país y los
# regionales más comunes en BYMA (CEDEAR), Europa (UCITS) y EE.UU. — no es
# exhaustiva. Un ETF de país que no esté acá cae en el fallback de
# `_clasificar_pais` (país del sufijo). Agregar la línea que falte cuando
# aparezca en una cartera real, como ya pasó con FXI/EWZ/IEUR.
PAISES_ETF = {
    # Un solo país (iShares MSCI, listados en EE.UU. — CEDEAR en BYMA con "D")
    "EWA": "Australia", "EWC": "Canada", "EWG": "Germany", "EWH": "Hong Kong",
    "EWI": "Italy", "EWJ": "Japan", "EWK": "Belgium", "EWL": "Switzerland",
    "EWN": "Netherlands", "EWO": "Austria", "EWP": "Spain", "EWQ": "France",
    "EWS": "Singapore", "EWT": "Taiwan", "EWU": "United Kingdom", "EWW": "Mexico",
    "EWY": "South Korea", "EWZ": "Brazil", "EZA": "South Africa",
    "EIDO": "Indonesia", "EPHE": "Philippines", "EPU": "Peru", "ECH": "Chile",
    "EIRL": "Ireland", "EIS": "Israel", "EPOL": "Poland", "ENZL": "New Zealand",
    "ENOR": "Norway", "EDEN": "Denmark", "EFNL": "Finland", "EWD": "Sweden",
    "THD": "Thailand", "TUR": "Turkey", "INDA": "India", "MCHI": "China",
    "FXI": "China", "KSA": "Saudi Arabia", "QAT": "Qatar", "ARGT": "Argentina",

    # Regiones y "el mundo": no son un país, así que no salen coloreados en el
    # mapa —Plotly pinta países, no continentes—, pero sí entran en el reparto.
    "IEUR": "Europe", "VGK": "Europe", "EZU": "Eurozone",
    "EFA": "Developed Markets ex-US", "EEM": "Emerging Markets", "VWO": "Emerging Markets",
    "IPAC": "Asia-Pacific", "AAXJ": "Asia ex-Japan", "ILF": "Latin America",
    "ACWI": "World", "URTH": "World", "VT": "World",

    # UCITS europeos (Amsterdam, Londres, Frankfurt…): la clave lleva el
    # sufijo de plaza porque `base_symbol` solo le saca el ".BA" a un CEDEAR.
    "IWDA.AS": "World", "VWCE.DE": "World", "VWRL.L": "World", "VWRL.AS": "World",
    "XDWD.L": "World", "SWDA.L": "World",
    "CSPX.L": "United States", "VUSA.L": "United States", "SXR8.DE": "United States",
    "IUSA.L": "United States", "CSPX.AS": "United States",
    "EIMI.L": "Emerging Markets", "IS3N.DE": "Emerging Markets",
    "IMEU.L": "Europe", "MEUD.PA": "Europe", "VEUR.AS": "Europe",
    "IJPN.L": "Japan", "SJPA.L": "Japan",
    "FLXC.DE": "China", "MCHA.L": "China",
}

# Empresas cuyo `country` en yfinance es la sede legal, no donde está el
# negocio real —lo que importa para el riesgo geográfico de la cartera—.
# Vista Energy (VIST) mudó su holding a México en 2023 por temas fiscales,
# pero opera y factura en Vaca Muerta: es una apuesta a Argentina, no a
# México, y así hay que verla en el mapamundi.
PAISES_MANUAL = {
    "VIST": "Argentina",
}


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
            # Si el subyacente ya dijo "equity", es una acción: el siguiente
            # candidato (el ticker con la D) colisiona con otro papel —MUD es
            # un ETF bajista sobre Micron, no el CEDEAR de Micron—.
            if not es_cedear_d or candidato == base:
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


def _clasificar_pais(ticker: str, base: str, tipo: str, ficha: dict) -> str:
    """País de la inversión, no de la plaza donde cotiza.

    Un CEDEAR cotiza en BYMA pero el país que importa es el del subyacente
    —la `ficha` ya es la del subyacente cuando `_clasificar_tipo` lo resolvió—.
    Los bonos y ONs de esta app son todos emisores argentinos, y yfinance no
    trae `country` para ellos.

    Sin `country` en la ficha, no alcanza con mirar el sufijo del ticker: un
    ETF (GLDD.BA, QQQD.BA, SLVD.BA) no tiene `country` en yfinance —eso es un
    dato de empresa, no de fondo— y quedaba mal clasificado como Argentina
    solo por el ".BA" de la especie D. La pregunta correcta es si hay un
    CEDEAR de por medio (`base` distinto del ticker sin sufijo): si lo hay, el
    subyacente casi siempre cotiza en EE.UU.; si no, el ".BA" sí es Argentina.
    """
    if tipo.startswith("RF") or tipo == "Renta Fija":
        return "Argentina"
    if base in PAISES_MANUAL:
        return PAISES_MANUAL[base]
    if base in PAISES_ETF:
        return PAISES_ETF[base]
    pais = ficha.get("country")
    if pais:
        return pais
    # En inglés, no "Estados Unidos": yfinance ya devuelve `country` en inglés
    # ("United States") y el mapamundi lo busca por nombre (`locationmode:
    # "country names"` en Plotly) — dos idiomas para el mismo país abrían dos
    # porciones separadas en vez de sumarse en una.
    if base != sources.strip_ba(ticker):
        return "United States"
    return "Argentina" if ticker.upper().endswith(".BA") else "United States"


def analizar(posiciones, precios=None) -> dict:
    """Composición de la cartera por tipo, sector e industria.

    Devuelve porcentajes sobre el valor total en dólares, ordenados de mayor a
    menor, más el detalle por activo para poder auditar cualquier clasificación
    que sorprenda.
    """
    from core.models.portfolio import precios_actuales

    precios = precios if precios is not None else precios_actuales(posiciones)

    por_tipo, por_sector, por_industria, por_pais, detalle = {}, {}, {}, {}, []
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
        # Los FCI de esta app son fondos argentinos (Cocos), aunque estén en dólares.
        pais = ("Argentina" if origen == sources.SOURCE_FCI
                else _clasificar_pais(ticker, base, tipo, ficha))

        por_tipo[tipo] = por_tipo.get(tipo, 0.0) + valor
        por_sector[sector] = por_sector.get(sector, 0.0) + valor
        por_industria[industria] = por_industria.get(industria, 0.0) + valor
        por_pais[pais] = por_pais.get(pais, 0.0) + valor
        total += valor

        detalle.append({"ticker": ticker, "subyacente": base, "valor_usd": round(valor, 2),
                        "tipo": tipo, "sector": sector, "industria": industria, "pais": pais,
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
        "por_pais": reparto(por_pais),
        "detalle": sorted(agregado.values(), key=lambda x: -x["valor_usd"]),
        "valor_total": round(total, 2),
        "moneda": "USD",
    }
