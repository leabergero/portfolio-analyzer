"""
symbols.py — Qué es cada ticker y en qué moneda cotiza.

Este es el módulo más peligroso del núcleo: casi todos los errores de valuación
que se pagaron en las apps anteriores nacieron acá. Por eso es puro (solo
stdlib), no hace red ni base de datos, y cada regla tiene su caso en
`tests/test_verdades.py`.

Las dos convenciones que hay que tener claras, porque se parecen y no son lo
mismo:

  1. BYMA, listado bursátil (sufijo .BA). Casi todo cotiza en dos monedas y la
     variante dólar es el ticker base + "D":
         KO   → KOD.BA    (CEDEAR de Coca-Cola, en dólares)
         GLD  → GLDD.BA   (CEDEAR del ETF de oro, en dólares)
         AL30 → AL30D.BA  (soberano, tramo en dólares)

  2. API interna de Cocos (sin .BA). Los bonos soberanos siguen la misma regla
     (base + "D"), pero las obligaciones negociables NO: reemplazan la "O"
     final por "D".
         AL30  → AL30D    ✅ agregar
         PLC4O → PLC4D    ✅ reemplazar   (PLC4OD no existe)

Y la excepción que rompe la simetría: un bono en su variante "D" igual llega
DESDE COCOS EN PESOS. La "D" del CEDEAR dice "cotiza en dólares"; la "D" del
bono es solo el nombre de la especie.
"""

# ── Registro de instrumentos que solo existen en Cocos ────────────────────────
# Bonos, ONs y letras. No están en yfinance ni en BYMA Open Data: pedirlos ahí
# devuelve vacío o, peor, otra especie. Cotizan cada 100 nominales.

SOBERANOS = {
    # Ley extranjera / local, en dólares
    "AL29", "AL30", "AL35", "AL41",
    "GD29", "GD30", "GD35", "GD38", "GD41", "GD46",
    "AE38", "AN29",
    # CER y ajustables
    "TX26", "TX28", "TZXD5", "DICP", "CUAP", "PARP",
    # BOPREAL
    "BPOA7", "BPOB7", "BPOC7", "BPOD7",
}

# Obligaciones negociables. El valor es el ticker del tramo en dólares que usa
# la API de Cocos — irregular, por eso es una tabla y no una regla.
ON_D_TICKER = {
    "PLC4O": "PLC4D",
    "RUCDO": "RUCDD",
    "TLCTO": "TLCTD",
    "VSCXO": "VSCXD",
    "YCA6O": "YCA6D",
    "CSDOO": "CSDOD",
    "MFCCO": "MFCCD",
    "GNNNO": "GNNND",
    "TGS4O": "TGS4D",
    "YPF4O": "YPF4D",
    "PAMB8": "PAMB8D",
    "CARC1": "CARC1D",
    "IRCP2": "IRCP2D",
}

LETRAS = {
    "S31E5", "S28F5", "S31M5", "S30J5", "S31J5",
    "T17O5", "T31O5", "T14N5", "T28N5", "T15D5", "T30E6",
}

COCOS_ONLY = SOBERANOS | set(ON_D_TICKER) | LETRAS

# Símbolos reales de BYMA que terminan en "D" de casualidad y cotizan en pesos:
# NO son la variante dólar de nada. Si aparece otro, va acá — no se toca la
# regla general.
D_FALSOS_POSITIVOS = {"YPFD"}


# ── Descomposición del ticker ─────────────────────────────────────────────────

def strip_ba(ticker: str) -> str:
    """Saca el sufijo de BYMA. METR.BA → METR · AL30D.BA → AL30D"""
    t = ticker.upper().strip()
    return t[:-3] if t.endswith(".BA") else t


def is_d_variant(symbol: str) -> bool:
    """¿Es el tramo en dólares de otro instrumento?

    Exige al menos 2 caracteres antes de la "D" (KOD → base "KO"). El umbral
    importa: cuando pedía 3, los CEDEARs de tickers cortos como KO no se
    detectaban, se los trataba como pesos y se les aplicaba el MEP sobre un
    precio que ya estaba en dólares.
    """
    sym = symbol.upper()
    if sym in D_FALSOS_POSITIVOS:
        return False
    return len(sym) >= 3 and sym.endswith("D") and sym[-2].isalnum()


def base_symbol(ticker: str) -> str:
    """El instrumento subyacente, sin sufijo de mercado ni de moneda.

    GLDD.BA → GLD    (no "GL": rstrip("D") se comía las dos)
    KOD.BA  → KO
    AL30D.BA→ AL30
    METR.BA → METR
    """
    sym = strip_ba(ticker)
    return sym[:-1] if is_d_variant(sym) else sym


def d_ticker(symbol: str) -> str:
    """Ticker del tramo en dólares, en el espacio de nombres de Cocos.

    Soberanos y letras agregan "D"; las ONs reemplazan la "O" final.
    """
    sym = base_symbol(symbol)
    if sym in ON_D_TICKER:
        return ON_D_TICKER[sym]
    return sym + "D"


# ── Clasificación ─────────────────────────────────────────────────────────────

def _parece_soberano(sym: str) -> bool:
    """Dos letras y dos dígitos: AL30, GD35, TX26. Descarta acciones (COME,
    TECO2) porque exige que TODO lo que sigue a las dos letras sean dígitos."""
    return len(sym) == 4 and sym[:2].isalpha() and sym[2:].isdigit()


def _parece_on(sym: str) -> bool:
    """Termina en dígito + "O": PLC4O, YCA6O, TGS4O, YPF4O.

    A propósito conservador. Las ONs con nombre irregular (RUCDO, VSCXO...)
    están en la tabla, y para cualquier especie nueva está la columna `source`
    del CSV — no hace falta adivinar.
    """
    return len(sym) >= 4 and sym.endswith("O") and sym[-2].isdigit()


def is_cocos_only(ticker: str) -> bool:
    """¿Solo existe en Cocos? (bonos, ONs, letras)"""
    sym = strip_ba(ticker)
    base = base_symbol(ticker)
    return (sym in COCOS_ONLY or base in COCOS_ONLY
            or _parece_soberano(base) or _parece_on(base))


def is_bond(ticker: str, source: str = None) -> bool:
    """¿Cotiza cada 100 nominales y hay que dividir el precio por 100?

    `source="cocos"` explícito en la posición MANDA sobre las tablas. Sin esto,
    una ON que no figure en el registro no se normaliza y la posición vale 100
    veces de más: pasó con TLCPO.BA, que llegó a dominar el 96 % de una cartera
    de bonos y a clasificarse como renta variable.

    La ruta de precios ya respetaba el source explícito; la de normalización no.
    Las dos tienen que mirar el mismo dato.
    """
    return source == "cocos" or is_cocos_only(ticker)


def ticker_currency(ticker: str) -> str:
    """"ARS" o "USD" — en qué moneda llega el precio de este ticker.

    Determina si se aplica o no la conversión por MEP. Equivocarse acá mueve la
    valuación por un factor de ~1.500.
    """
    t = ticker.upper().strip()

    # Sin sufijo de BYMA es un ticker extranjero: nativamente en dólares.
    if not t.endswith(".BA"):
        return "USD"

    # Bonos, ONs y letras: Cocos los devuelve en pesos incluso en su variante
    # "D". Va ANTES del chequeo de variante dólar, justamente por eso.
    if is_cocos_only(t):
        return "ARS"

    # Acciones y CEDEARs: la "D" sí significa que ya viene en dólares.
    return "USD" if is_d_variant(strip_ba(t)) else "ARS"
