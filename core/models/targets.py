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
