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

from datetime import date

import numpy as np
import pandas as pd

from core import mercado
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

def precios_actuales(posiciones, hasta=None, previos=None, fechas=None,
                     vivo=False) -> dict:
    """{ticker: precio en la moneda de medición}. Un pedido por ticker.

    Con `vivo`, el precio es el último negociado y no el último cierre, y en
    `previos` queda el cierre anterior a hoy: es lo que hace falta para decir
    cuánto se movió la cartera en la rueda en curso. La serie de cierres no se
    toca —los modelos siguen midiendo sobre ella— y por eso el precio en vivo
    se pide aparte en vez de meterlo en la caché.
    """
    hoy = date.today()
    salida = {}
    for t in sorted({str(p["ticker"]).upper() for p in posiciones}):
        origen = next((p.get("source") for p in posiciones
                       if str(p["ticker"]).upper() == t and p.get("source")), None)
        s = sources.precios_base(t, hasta=hasta, source=origen)
        if s.empty:
            continue
        salida[t] = float(s.iloc[-1])
        if not vivo or previos is None:
            continue

        # El cierre de referencia es el último ANTERIOR a hoy. Tomar `iloc[-1]`
        # a secas compararía contra una vela de hoy si alguien ya la trajo, y
        # entonces el KPI mediría un rato de rueda en vez del día.
        cerrados = s[s.index.date < hoy] if len(s) else s
        ahora = sources.spot_base(t, origen)
        if ahora and len(cerrados):
            salida[t] = ahora
            previos[t] = float(cerrados.iloc[-1])
            if fechas is not None:
                fechas[t] = str(cerrados.index[-1].date())

    if vivo and fechas is not None and fechas:
        fechas["_previa"] = max(v for k, v in fechas.items() if not k.startswith("_"))
        fechas["_ultima"] = hoy.isoformat()
    return salida


def valuar(posiciones, precios=None, previos=None, fechas=None, vivo=False) -> dict:
    """Valúa la cartera lote por lote, en dólares.

    El costo de cada lote se convierte con el MEP de **su** fecha de compra;
    el valor actual, con el precio de hoy. Un lote sin precio disponible no se
    inventa: sale marcado y queda fuera de los totales.
    """
    if precios is None:
        previos = {} if previos is None else previos
        fechas = {} if fechas is None else fechas
        precios = precios_actuales(posiciones, previos=previos, fechas=fechas, vivo=vivo)
    previos = previos or {}
    serie_mep = mep_mod.serie()

    filas, total_valor, total_costo = [], 0.0, 0.0
    # La variación del día se mide sólo sobre los lotes que tienen los DOS
    # precios. Sumar al total de ayer los que no tienen cierre anterior daría
    # una diferencia que es la tenencia entera, no lo que se movió.
    hoy_comp, ayer_comp = 0.0, 0.0
    for p in posiciones:
        t = str(p["ticker"]).upper()
        qty = float(p.get("qty", 0))
        origen = p.get("source") or None
        es_bono = sources.is_bond(t, origen)
        moneda = (p.get("currency") or sources.ticker_currency(t)).upper()

        # El precio de compra sigue la misma convención que el de mercado: los
        # bonos cotizan cada 100 nominales. Salvo que el usuario lo haya cargado
        # ya por nominal, que es lo que decide `divisor_nominal`.
        div = sources.divisor_nominal(t, p.get("buy_price"), origen)
        compra = float(p.get("buy_price", 0)) / div
        comision = float(p.get("commissions", 0)) / div

        if moneda == "ARS":
            compra_usd = mep_mod.a_usd(compra, p.get("buy_date"), serie_mep)
            comision_usd = mep_mod.a_usd(comision, p.get("buy_date"), serie_mep) or 0.0
        else:
            compra_usd = mercado.escalar_a_usd(compra, moneda, p.get("buy_date"))
            comision_usd = mercado.escalar_a_usd(comision, moneda, p.get("buy_date"))

        # El precio de hoy ya viene en la moneda de la plaza; el costo todavía
        # no. Se pasa con el cambio de SU fecha, por la misma razón que el MEP:
        # convertir una compra de 2024 al euro de hoy mide el tipo de cambio.
        compra_usd = mercado.a_base(compra_usd, p.get("buy_date"))
        comision_usd = mercado.a_base(comision_usd, p.get("buy_date")) or 0.0

        precio_hoy = precios.get(t)

        # Un FCI sólo tiene precio si el fondo está HOY en la cuenta conectada:
        # Cocos no publica cuotapartes de fondos que no tenés. Un fondo que
        # rescataste, o el de otra cuenta de la familia, se quedaba sin precio y
        # la tenencia entera desaparecía del total de la cartera. Antes de
        # mostrar nada, se cae al PPC: es el último valor que Cocos dio por esa
        # cuotaparte, y una tenencia valuada a su costo se lee mucho mejor que
        # una tenencia valuada en cero. Queda marcada para que la pantalla lo
        # diga y nadie la confunda con un precio de mercado.
        estimado = False
        if precio_hoy is None and origen == sources.SOURCE_FCI and compra_usd:
            precio_hoy, estimado = compra_usd, True

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
            "precio_estimado": estimado,
            # El lote lo puso (o lo recortó) el simulador, no existe en la
            # cartera. La pantalla lo pinta aparte para que nadie lo lea como
            # tenencia real.
            "sim": bool(p.get("sim")),
        }
        previo = previos.get(t)
        if valor is not None and previo and not estimado:
            fila["precio_previo_usd"] = round(previo, 4)
            hoy_comp += valor
            ayer_comp += qty * previo

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
        "moneda": mercado.moneda(),
        "mep_hoy": round(float(serie_mep.iloc[-1]), 2) if not serie_mep.empty else None,
        "sin_precio": sorted(set(sin_precio)),
        # Cuánto se movió la cartera en la última rueda. En pesos esto lleva
        # adentro el MEP del día: la tenencia se mide en dólares, así que un
        # papel quieto con el dólar en alza baja igual.
        "pnl_dia": round(hoy_comp - ayer_comp, 2) if ayer_comp else None,
        "pnl_dia_pct": round((hoy_comp / ayer_comp - 1) * 100, 2) if ayer_comp else None,
        "dia_fecha": (fechas or {}).get("_ultima"),
        "dia_previa": (fechas or {}).get("_previa"),
    }


def pnl_realizado(trades) -> dict:
    """Convierte a dólares los trades cerrados, con el MEP de cada pata.

    Se guardan en la moneda de origen y se convierten acá, no al importar:
    mezclar pesos y dólares sin esto suma peras con bananas — una venta de
    METR.BA en pesos junto a una de KOD.BA en dólares.
    """
    serie_mep = mep_mod.serie()
    salida, total = [], 0.0
    total_activo = total_fx = 0.0
    por_moneda = {}
    for t in trades:
        ticker = t["ticker"].upper()
        # Una moneda guardada en el registro manda sobre la convención del
        # ticker: el dividendo de un CEDEAR D se cobra en pesos aunque el papel
        # cotice en dólares, y quien lo cargó es el único que sabe cuál fue.
        moneda = (t.get("moneda") or sources.ticker_currency(ticker)).upper()
        # La escala la fija el precio más grande de la operación: si uno de los
        # dos vino en cero (un dividendo) no puede decidir por los dos.
        div = sources.divisor_nominal(
            ticker, max(abs(t["buy_price"] or 0), abs(t["sell_price"] or 0)))
        compra, venta = t["buy_price"] / div, t["sell_price"] / div
        c_compra, c_venta = t.get("buy_comm", 0) / div, t.get("sell_comm", 0) / div
        mep_c = mep_v = None

        if moneda == "ARS":
            mep_c = mep_mod.valor(t["buy_date"], serie_mep)
            mep_v = mep_mod.valor(t["sell_date"], serie_mep)
            compra = mep_mod.a_usd(compra, t["buy_date"], serie_mep)
            venta = mep_mod.a_usd(venta, t["sell_date"], serie_mep)
            c_compra = mep_mod.a_usd(c_compra, t["buy_date"], serie_mep) or 0.0
            c_venta = mep_mod.a_usd(c_venta, t["sell_date"], serie_mep) or 0.0
        elif moneda != "USD":
            # Un cerrado en euros: cada pata al cambio de SU fecha, igual que con
            # el MEP. La apertura activo/tipo de cambio queda para el peso, que
            # es donde el salto del dólar explica la mitad del resultado.
            compra = mercado.escalar_a_usd(compra, moneda, t["buy_date"])
            venta = mercado.escalar_a_usd(venta, moneda, t["sell_date"])
            c_compra = mercado.escalar_a_usd(c_compra, moneda, t["buy_date"]) or 0.0
            c_venta = mercado.escalar_a_usd(c_venta, moneda, t["sell_date"]) or 0.0
        if compra is None or venta is None:
            continue

        pnl = t["qty"] * (venta - compra) - c_compra - c_venta

        # De dónde salió ese número: el papel y el dólar, por separado.
        #
        #     P&L = ingreso/MEP_v − costo/MEP_c
        #         = (ingreso − costo)/MEP_v  +  costo × (1/MEP_v − 1/MEP_c)
        #           └── el papel ───────────┘  └── el tipo de cambio ──────┘
        #
        # La ganancia se convierte al MEP de la VENTA, que es el dólar con el
        # que se cobró: valuarla a la de compra deja un tercer término suelto.
        # Los dos suman el neto exacto, sin residuo.
        if moneda == "ARS" and mep_c and mep_v:
            costo_ars = t["qty"] * t["buy_price"] / div + t.get("buy_comm", 0) / div
            ingreso_ars = t["qty"] * t["sell_price"] / div - t.get("sell_comm", 0) / div
            pnl_activo = (ingreso_ars - costo_ars) / mep_v
            pnl_fx = costo_ars * (1 / mep_v - 1 / mep_c)
        else:
            pnl_activo, pnl_fx = pnl, 0.0      # sin exposición: ya estaba en dólares

        # A la moneda de medición con el cambio de la fecha de venta, que es el
        # día en que se cobró. Los tres términos se convierten con el mismo
        # número, así que la identidad P&L = papel + tipo de cambio sobrevive.
        pnl = mercado.a_base(pnl, t["sell_date"])
        pnl_activo = mercado.a_base(pnl_activo, t["sell_date"])
        pnl_fx = mercado.a_base(pnl_fx, t["sell_date"])

        total += pnl
        total_activo += pnl_activo
        total_fx += pnl_fx
        # El resultado en la moneda de la operación viaja al lado del de dólares:
        # es el único número que se puede cotejar contra el resumen del broker,
        # que no sabe nada de MEP.
        origen = t.get("pnl")
        if origen is not None:
            por_moneda[moneda] = round(por_moneda.get(moneda, 0.0) + origen, 2)
        salida.append({**t, "moneda": moneda, "pnl_usd": round(pnl, 2),
                       "pnl_activo_usd": round(pnl_activo, 2),
                       "pnl_fx_usd": round(pnl_fx, 2),
                       "pnl_origen": origen,
                       "mep_compra": round(mep_c, 2) if mep_c else None,
                       "mep_venta": round(mep_v, 2) if mep_v else None})

    return {"trades": salida, "total_usd": round(total, 2), "n": len(salida),
            "total_origen": por_moneda,
            "total_activo_usd": round(total_activo, 2),
            "total_fx_usd": round(total_fx, 2)}


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
        s = sources.precios_base(t, desde=desde, hasta=hasta, source=p.get("source") or None)
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


def tir(movimientos) -> float:
    """Tasa anual que hace cero el valor presente de una lista (fecha, monto).

    Convención del inversor: lo que sale del bolsillo va negativo, lo que vuelve
    —o lo que hoy vale la tenencia— positivo.

    Bisección sobre una grilla y no Newton: con flujos irregulares una derivada
    mal condicionada manda la tasa al infinito. Y no alcanza con mirar los
    extremos del intervalo: una cartera que compra y vende seguido alterna
    signos, y ahí el VPN puede cruzar el cero más de una vez. Se barre, se toma
    el primer cruce —la tasa más baja, la lectura conservadora— y se afina ahí.
    """
    movimientos = [(pd.Timestamp(f), float(m)) for f, m in movimientos if abs(m) > 1e-9]
    if not any(m < 0 for _, m in movimientos) or not any(m > 0 for _, m in movimientos):
        return None

    t0 = min(f for f, _ in movimientos)
    montos = np.array([m for _, m in movimientos])
    anos = np.array([(f - t0).days / 365.25 for f, _ in movimientos])

    def vpn(r):
        return float((montos / (1.0 + r) ** anos).sum())

    # Vectorizado: la serie móvil pide una TIR por semana y a mano son minutos.
    grilla = np.linspace(-0.95, 10.0, 400)
    valores = (montos / (1.0 + grilla[:, None]) ** anos).sum(axis=1)
    cruces = np.flatnonzero(np.diff(np.signbit(valores)))
    if not len(cruces):
        return None

    i = int(cruces[0])
    bajo, alto = grilla[i], grilla[i + 1]
    creciente = valores[i] < valores[i + 1]
    for _ in range(60):
        medio = (bajo + alto) / 2
        if (vpn(medio) > 0) == creciente:
            alto = medio
        else:
            bajo = medio
    return round((bajo + alto) / 2 * 100, 2)


def evolucion(posiciones, trades=None, n_ruedas: int = 30) -> dict:
    """Cómo se movió la cartera en el tiempo: rendimiento acumulado y últimas ruedas.

    Reconstruye la cartera **como fue**, no como quedó: cada posición cerrada
    pesa desde que se compró hasta que se vendió. Valuar solo lo que sigue
    abierto contaría la historia al revés —una cartera que rotó entera parecería
    haber tenido siempre lo de hoy— y en carteras con mucha rotación el número
    que sale no se parece a nada.

    El rendimiento es el resultado sobre la plata puesta: cuánto valen las
    tenencias más los dividendos cobrados, menos lo que salió del bolsillo hasta
    ahí. La curva va en dólares porque es la única que no se mueve sola —un
    porcentaje sobre capital variable cae de golpe el día de un aporte, sin que
    haya pasado nada en el mercado—. Los dividendos no son un retiro: quedan como
    caja adentro, que es donde suman al resultado.
    """
    from core.data import sources as _src

    # ── Un solo formato para lo abierto y lo cerrado ──────────────────────────
    # (ticker, qty, desde, hasta|None, costo_usd, ingreso_usd|None)
    tramos, dividendos, sin_serie = [], [], set()

    precios_ref = precios_actuales(posiciones)
    lotes = valuar(posiciones, precios_ref)["posiciones"]
    for l in lotes:
        if l["costo_usd"] is None or not l["buy_date"]:
            continue
        tramos.append((l["ticker"], l["qty"], l["buy_date"], None, l["costo_usd"], None))

    for t in (pnl_realizado(trades or [])["trades"]):
        ticker = str(t["ticker"]).upper()
        div = _src.divisor_nominal(
            ticker, max(abs(t.get("buy_price") or 0), abs(t.get("sell_price") or 0)))
        mc = t.get("mep_compra") or 1.0
        mv = t.get("mep_venta") or 1.0
        costo = (t["qty"] * (t.get("buy_price") or 0) / div + t.get("buy_comm", 0) / div) / mc
        ingreso = (t["qty"] * (t.get("sell_price") or 0) / div - t.get("sell_comm", 0) / div) / mv
        if t.get("tipo") == "dividendo":
            # No se vendió nada: entró plata y se queda en la cartera.
            dividendos.append((t["sell_date"], ingreso))
            continue
        tramos.append((ticker, t["qty"], t["buy_date"], t["sell_date"], costo, ingreso))

    if not tramos:
        return {"error": "Sin operaciones para reconstruir la historia."}

    # ── Series de todo lo que la cartera tuvo alguna vez ──────────────────────
    origen = {str(p["ticker"]).upper(): (p.get("source") or None) for p in posiciones}
    series = {}
    for ticker, *_ in tramos:
        if ticker in series or ticker in sin_serie:
            continue
        s = _src.precios_base(ticker, source=origen.get(ticker))
        if s.empty:
            sin_serie.add(ticker)
        else:
            series[ticker] = s
    if not series:
        return {"error": "Sin series de precios para esta cartera."}

    # Lo que no se puede valuar sale entero —cantidad y plata—: dejar el flujo
    # sin el activo inventa un retorno el día que se compra o se vende.
    tramos = [x for x in tramos if x[0] not in sin_serie]

    px = pd.DataFrame(series).sort_index().ffill().dropna(how="all")
    inicio = pd.Timestamp(min(x[2] for x in tramos))
    previas = px.index[px.index < inicio]
    px = px.loc[previas[-1]:] if len(previas) else px.loc[inicio:]
    if len(px) < 2:
        return {"error": "Hacen falta al menos dos ruedas desde la primera compra."}

    def rueda(fecha):
        """La primera rueda desde una fecha; None si cae fuera de la ventana."""
        futuras = px.index[px.index >= pd.Timestamp(fecha)]
        return futuras[0] if len(futuras) else None

    cant = pd.DataFrame(0.0, index=px.index, columns=px.columns)
    flujo = pd.Series(0.0, index=px.index)
    caja = pd.Series(0.0, index=px.index)
    for ticker, qty, desde, hasta, costo, ingreso in tramos:
        d = pd.Timestamp(desde)
        h = pd.Timestamp(hasta) if hasta else None
        vivo = (cant.index >= d) & (cant.index < h if h is not None else True)
        cant.loc[vivo, ticker] += qty
        # Solo cuenta como movimiento lo que pasó dentro de la ventana: un lote
        # anterior ya está en el capital inicial, no es plata que entró.
        if d >= px.index[0] and (f := rueda(d)) is not None:
            flujo.loc[f] += costo
        if h is not None and (f := rueda(h)) is not None:
            flujo.loc[f] -= ingreso

    for fecha, monto in dividendos:
        f = rueda(fecha)
        if f is not None:
            caja.loc[f:] += monto

    # El valor de las tenencias va sin la caja de dividendos, para que coincida
    # con el KPI "Valor total" de arriba; el resultado sí la cuenta.
    tenencias = (cant * px).sum(axis=1)
    puesto = flujo.cumsum()
    resultado = tenencias + caja - puesto

    # Referencia para el "vs. mes anterior": el resultado al último cierre del
    # mes pasado. En dólares y no en porcentaje: el porcentaje se mueve solo
    # cuando entra plata, y ese salto no es rendimiento de nada.
    mes = px.index[-1].to_period("M")
    previos = resultado.index[resultado.index.to_period("M") < mes]
    ref = float(resultado.loc[previos[-1]]) if len(previos) else 0.0

    ult = px.tail(n_ruedas + 1)
    var = ult.pct_change().iloc[1:] * 100.0
    hoy = cant.iloc[-1]
    abiertos = [t for t in px.columns if hoy[t] > 0]
    orden = sorted(abiertos, key=lambda t: -(hoy[t] * float(px[t].iloc[-1])))

    neto = float(puesto.iloc[-1])
    final = float(resultado.iloc[-1])

    # ── Dos tasas anuales, que contestan preguntas distintas ─────────────────
    # La histórica arrastra todo lo que pasó por la cartera, aciertos y errores
    # ya liquidados. La de composición mira solo lo que sigue abierto: a qué
    # tasa viene rindiendo lo que uno tiene HOY, que es lo que se compara contra
    # un plazo fijo antes de decidir si conviene seguir.
    hoy = px.index[-1]
    movimientos = [(f, -float(v)) for f, v in flujo.items()]
    inicial = float(tenencias.iloc[0]) - float(flujo.iloc[0])
    if inicial > 1e-9:                       # tenencia previa a la ventana
        movimientos.insert(0, (px.index[0], -inicial))
    movimientos.append((hoy, float(tenencias.iloc[-1] + caja.iloc[-1])))
    anos = (hoy - px.index[0]).days / 365.25

    def movimientos_de(desde, hasta):
        """La cartera vista como una sola inversión entre dos fechas.

        Arranca con lo que ya valía ese día —el punto de partida, no un aporte—,
        suma lo que entró y resta lo que salió, y cierra con lo que vale al
        final: las posiciones abiertas a precio de mercado más los dividendos
        cobrados dentro del tramo. Por eso se mueve todos los días: si mañana
        sube un papel pesado, el no realizado cambia y la tasa con él.
        """
        medio = px.index[(px.index > desde) & (px.index <= hasta)]
        mov = [(desde, -float(tenencias.loc[desde]))]
        mov += [(f, -float(flujo.loc[f])) for f in medio]
        cobrado = float(caja.loc[hasta] - caja.loc[desde])
        mov.append((hasta, float(tenencias.loc[hasta]) + cobrado))
        return mov, cobrado

    def serie_movil(meses, paso):
        """La misma tasa, calculada parada en cada semana del último año.

        Un punto por semana: una ventana de doce meses no se mueve lo suficiente
        entre dos ruedas como para justificar 250 optimizaciones, y la curva sale
        igual.
        """
        fechas = [f for f in px.index if f >= hoy - pd.DateOffset(months=meses)]
        puntos = []
        for f in fechas[::paso] + fechas[-1:]:
            tramo = px.index[(px.index >= f - pd.DateOffset(months=meses)) & (px.index <= f)]
            if len(tramo) < 2 or (f - tramo[0]).days / 365.25 < 0.25:
                continue
            t = tir(movimientos_de(tramo[0], f)[0])
            if t is not None and (not puntos or puntos[-1]["fecha"] != str(f.date())):
                puntos.append({"fecha": str(f.date()), "tir_pct": t})
        return puntos

    def ventana(meses):
        dentro = px.index[px.index >= hoy - pd.DateOffset(months=meses)]
        if len(dentro) < 2:
            return None
        arranque = dentro[0]
        mov, cobrado = movimientos_de(arranque, hoy)
        anual = (hoy - arranque).days / 365.25
        movidos = flujo.loc[dentro[1]:]
        return {"tir_pct": tir(mov) if anual >= 0.25 else None,
                "anos": round(anual, 2),
                "desde": str(arranque.date()),
                "valor_inicial_usd": round(float(tenencias.loc[arranque]), 2),
                "aportado_usd": round(float(movidos.clip(lower=0).sum()), 2),
                "retirado_usd": round(float(-movidos.clip(upper=0).sum()), 2),
                "dividendos_usd": round(cobrado, 2),
                "completa": arranque <= px.index[0],
                "serie": serie_movil(meses, paso=5)}

    return {
        # Anualizar menos de un trimestre da un número que no significa nada.
        "tir_anual_pct": tir(movimientos) if anos >= 0.25 else None,
        "anos": round(anos, 2),
        "ultimos_12m": ventana(12),
        # Lo que ganó o perdió sobre la plata que salió del bolsillo: el mismo
        # número que suman los KPIs de arriba (abierto + realizado).
        "resultado_usd": round(final, 2),
        "puesto_neto_usd": round(neto, 2),
        "rendimiento_pct": round(final / neto * 100, 2) if neto > 0 else None,
        "resultado_mes_anterior_usd": round(ref, 2),
        "desde": str(px.index[0].date()),
        "aportado_usd": round(float(flujo[flujo > 0].sum()), 2),
        "retirado_usd": round(float(-flujo[flujo < 0].sum()), 2),
        "dividendos_usd": round(float(caja.iloc[-1]), 2),
        "valor_hoy_usd": round(float(tenencias.iloc[-1]), 2),
        "cerradas": sum(1 for x in tramos if x[3]),
        "sin_serie": sorted(sin_serie),
        "resultado_serie": [round(float(v), 2) for v in resultado],
        "valor_usd": [round(float(v), 2) for v in tenencias],
        # Cuánto capital había puesto en cada rueda: es la línea contra la que
        # se mira el valor. Por debajo, la cartera vale menos de lo que costó.
        "puesto_serie": [round(float(v), 2) for v in puesto],
        "fechas": [str(f.date()) for f in resultado.index],
        "ruedas": {
            "fechas": [str(f.date()) for f in var.index],
            "tickers": [{
                "ticker": t,
                "var_pct": [round(float(v), 2) for v in var[t]],
                "acum_pct": round((float(ult[t].iloc[-1]) / float(ult[t].iloc[0]) - 1) * 100, 2),
            } for t in orden if t in var.columns],
        },
    }
