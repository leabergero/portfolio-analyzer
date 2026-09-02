"""
portfolio.py — La cartera: pesos, valuación y P&L.

Fase 2 cubre lo que se puede responder sin modelos: qué tengo, cuánto vale hoy
en dólares y cuánto gané o perdí. Las métricas de riesgo y los modelos entran en
la fase 3.

Todo sale en dólares. La conversión usa el MEP de **la fecha de cada operación**
para el costo, y el MEP de hoy para el valor actual: comparar una compra de 2024
convertida al dólar de hoy contra su valor de hoy mide el movimiento del tipo de
cambio, no el rendimiento del activo.
"""

import numpy as np
import pandas as pd

from core.data import mep as mep_mod
from core.data import sources


def value_weights(posiciones, precios, tickers) -> np.ndarray:
    """Pesos por valor de mercado, alineados a `tickers` y agregando lotes.

    Dos lotes del mismo ticker son UNA posición. La versión anterior fallaba
    justo ahí: cuando el número de posiciones no coincidía con el de tickers con
    datos —por ejemplo con lotes repetidos— caía a equiponderado **sin avisar**.
    La cartera LEANDRO mostraba "20 % cada uno" cuando en realidad era METR
    95,7 % y COME 4,3 %, y con esos pesos falsos se calculaba todo lo demás.

    Solo cae a equiponderado si no hay ningún valor calculable, que es un caso
    genuinamente indeterminado.
    """
    valor = {}
    for p in posiciones:
        t = str(p["ticker"]).upper()
        if t in precios and precios[t]:
            valor[t] = valor.get(t, 0.0) + float(p.get("qty", 0)) * float(precios[t])

    w = np.array([valor.get(t, 0.0) for t in tickers], dtype=float)
    if w.sum() <= 0:
        return np.ones(len(tickers)) / max(1, len(tickers))
    return w / w.sum()


def concentracion(pesos) -> dict:
    """Cuán concentrada está de verdad la cartera.

    `N_efectivo = 1 / Σwᵢ²` responde algo que el número de posiciones esconde:
    una cartera con nueve activos donde uno pesa 95 % se comporta como si
    tuviera uno solo. Cuesta una línea y cambia la lectura de la cartera.
    """
    w = np.asarray(pesos, dtype=float)
    hhi = float((w ** 2).sum())
    return {
        "hhi": round(hhi, 4),
        "n_efectivo": round(1 / hhi, 2) if hhi > 0 else 0,
        "n_posiciones": int((w > 1e-9).sum()),
        "peso_maximo": round(float(w.max()) * 100, 2) if len(w) else 0,
    }


# ── Valuación ─────────────────────────────────────────────────────────────────

def precios_actuales(posiciones, hasta=None) -> dict:
    """{ticker: último precio en USD}. Un pedido por ticker, no por lote."""
    salida = {}
    for t in sorted({str(p["ticker"]).upper() for p in posiciones}):
        origen = next((p.get("source") for p in posiciones
                       if str(p["ticker"]).upper() == t and p.get("source")), None)
        s = sources.precios_usd(t, hasta=hasta, source=origen)
        if not s.empty:
            salida[t] = float(s.iloc[-1])
    return salida


def valuar(posiciones, precios=None) -> dict:
    """Valúa la cartera lote por lote, en dólares.

    El costo de cada lote se convierte con el MEP de **su** fecha de compra;
    el valor actual, con el precio de hoy. Un lote sin precio disponible no se
    inventa: sale marcado y queda fuera de los totales.
    """
    precios = precios if precios is not None else precios_actuales(posiciones)
    serie_mep = mep_mod.serie()

    filas, total_valor, total_costo = [], 0.0, 0.0
    for p in posiciones:
        t = str(p["ticker"]).upper()
        qty = float(p.get("qty", 0))
        origen = p.get("source") or None
        es_bono = sources.is_bond(t, origen)
        moneda = (p.get("currency") or sources.ticker_currency(t)).upper()

        # El precio de compra sigue la misma convención que el de mercado:
        # los bonos cotizan cada 100 nominales, en su moneda de origen.
        compra = float(p.get("buy_price", 0)) / (100.0 if es_bono else 1.0)
        comision = float(p.get("commissions", 0)) / (100.0 if es_bono else 1.0)

        if moneda == "ARS":
            compra_usd = mep_mod.a_usd(compra, p.get("buy_date"), serie_mep)
            comision_usd = mep_mod.a_usd(comision, p.get("buy_date"), serie_mep) or 0.0
        else:
            compra_usd, comision_usd = compra, comision

        precio_hoy = precios.get(t)
        valor = qty * precio_hoy if precio_hoy else None
        costo = (qty * compra_usd + comision_usd) if compra_usd else None

        fila = {
            "ticker": t, "moneda": moneda, "es_bono": es_bono,
            "buy_date": p.get("buy_date", ""), "qty": qty,
            "buy_price": p.get("buy_price"),
            "buy_price_usd": round(compra_usd, 4) if compra_usd else None,
            "precio_usd": round(precio_hoy, 4) if precio_hoy else None,
            "valor_usd": round(valor, 2) if valor else None,
            "costo_usd": round(costo, 2) if costo else None,
            "source": origen or "",
            "sin_precio": precio_hoy is None,
        }
        if valor is not None and costo is not None:
            fila["pnl_usd"] = round(valor - costo, 2)
            fila["pnl_pct"] = round((valor / costo - 1) * 100, 2) if costo else None
            total_valor += valor
            total_costo += costo
        filas.append(fila)

    sin_precio = [f["ticker"] for f in filas if f["sin_precio"]]
    return {
        "posiciones": filas,
        "valor_total": round(total_valor, 2),
        "costo_total": round(total_costo, 2),
        "pnl": round(total_valor - total_costo, 2),
        "pnl_pct": round((total_valor / total_costo - 1) * 100, 2) if total_costo else 0,
        "moneda": "USD",
        "mep_hoy": round(float(serie_mep.iloc[-1]), 2) if not serie_mep.empty else None,
        "sin_precio": sorted(set(sin_precio)),
    }


def pnl_realizado(trades) -> dict:
    """Convierte a dólares los trades cerrados, con el MEP de cada pata.

    Se guardan en la moneda de origen y se convierten acá, no al importar:
    mezclar pesos y dólares sin esto suma peras con bananas — una venta de
    METR.BA en pesos junto a una de KOD.BA en dólares.
    """
    serie_mep = mep_mod.serie()
    salida, total = [], 0.0
    for t in trades:
        ticker = t["ticker"].upper()
        moneda = sources.ticker_currency(ticker)
        div = 100.0 if sources.is_bond(ticker) else 1.0
        compra, venta = t["buy_price"] / div, t["sell_price"] / div
        c_compra, c_venta = t.get("buy_comm", 0) / div, t.get("sell_comm", 0) / div

        if moneda == "ARS":
            compra = mep_mod.a_usd(compra, t["buy_date"], serie_mep)
            venta = mep_mod.a_usd(venta, t["sell_date"], serie_mep)
            c_compra = mep_mod.a_usd(c_compra, t["buy_date"], serie_mep) or 0.0
            c_venta = mep_mod.a_usd(c_venta, t["sell_date"], serie_mep) or 0.0
        if compra is None or venta is None:
            continue

        pnl = t["qty"] * (venta - compra) - c_compra - c_venta
        total += pnl
        salida.append({**t, "moneda": moneda, "pnl_usd": round(pnl, 2)})

    return {"trades": salida, "total_usd": round(total, 2), "n": len(salida)}


def matriz_retornos(posiciones, desde=None, hasta=None):
    """(DataFrame de retornos diarios en USD, {ticker: precio actual}).

    Base de todos los modelos de la fase 3. Descarta series con menos de 30
    ruedas: con menos, cualquier volatilidad o correlación es ruido.
    """
    retornos, precios = {}, {}
    for p in posiciones:
        t = str(p["ticker"]).upper()
        if t in retornos:
            continue
        s = sources.precios_usd(t, desde=desde, hasta=hasta, source=p.get("source") or None)
        if len(s) < 30:
            continue
        precios[t] = float(s.iloc[-1])
        retornos[t] = s.pct_change().dropna()

    if not retornos:
        return pd.DataFrame(), {}
    df = pd.DataFrame(retornos).ffill(limit=5)
    return df.dropna(thresh=max(1, len(df.columns) // 2)).fillna(0.0), precios


def correlaciones(posiciones, ventana: int = 252) -> dict:
    """Matriz de correlaciones y qué dice sobre el carácter de la cartera.

    La correlación media entre pares es el resumen que responde la pregunta
    práctica: **¿esta cartera es defensiva o agresiva?** Si todo se mueve junto,
    en una caída no hay dónde refugiarse — la diversificación es nominal.

    Se agrega la correlación **condicionada a las caídas del mercado**, porque
    es donde la diversificación se pone a prueba: los pares que se despegan en
    tiempos normales suelen juntarse justo cuando hace falta que no lo hagan.
    """
    ret_df, precios = matriz_retornos(posiciones)
    if ret_df.shape[1] < 2:
        return {"error": "Hacen falta al menos dos activos."}

    tickers = list(ret_df.columns)
    reciente = ret_df.tail(ventana) if len(ret_df) > ventana else ret_df
    matriz = reciente.corr()

    pares = [(a, b, float(matriz.loc[a, b]))
             for i, a in enumerate(tickers) for b in tickers[i + 1:]]
    media = float(np.mean([c for _, _, c in pares])) if pares else 0.0

    # Correlación en el 10 % de días peores de la cartera.
    w = value_weights(posiciones, precios, tickers)
    cartera = reciente[tickers].to_numpy() @ w
    umbral = float(np.percentile(cartera, 10))
    malos = reciente[cartera <= umbral]
    matriz_caidas = malos.corr() if len(malos) > 10 else None
    media_caidas = (float(np.mean([float(matriz_caidas.loc[a, b])
                                   for i, a in enumerate(tickers) for b in tickers[i + 1:]]))
                    if matriz_caidas is not None else None)

    if media < 0.3:
        caracter, lectura = "defensiva", (
            "Los activos se mueven de forma bastante independiente: cuando uno cae, "
            "los otros no necesariamente lo acompañan. La diversificación es real.")
    elif media < 0.6:
        caracter, lectura = "mixta", (
            "Hay diversificación, pero parcial: buena parte de la cartera se mueve junta.")
    else:
        caracter, lectura = "agresiva", (
            "Casi todo se mueve junto. La cartera se comporta como una apuesta única "
            "repartida en varios tickers: en una caída no hay dónde refugiarse.")

    aviso = None
    if media_caidas is not None and media_caidas - media > 0.15:
        aviso = (f"En los días peores la correlación media sube de {media:.2f} a "
                 f"{media_caidas:.2f}: parte de la diversificación desaparece justo "
                 f"cuando se la necesita.")

    return {
        "tickers": tickers,
        "matriz": [[round(float(matriz.loc[a, b]), 3) for b in tickers] for a in tickers],
        "matriz_caidas": ([[round(float(matriz_caidas.loc[a, b]), 3) for b in tickers]
                           for a in tickers] if matriz_caidas is not None else None),
        "correlacion_media": round(media, 3),
        "correlacion_media_en_caidas": round(media_caidas, 3) if media_caidas is not None else None,
        "caracter": caracter, "lectura": lectura, "aviso_caidas": aviso,
        "par_mas_correlacionado": (lambda p: {"a": p[0], "b": p[1], "corr": round(p[2], 3)})(
            max(pares, key=lambda x: x[2])) if pares else None,
        "par_menos_correlacionado": (lambda p: {"a": p[0], "b": p[1], "corr": round(p[2], 3)})(
            min(pares, key=lambda x: x[2])) if pares else None,
        "ventana_ruedas": len(reciente),
    }
