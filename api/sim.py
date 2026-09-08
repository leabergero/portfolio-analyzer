"""
sim.py — Activos en simulación: "¿y si compro esto?", sin inventar una cartera.

No se guarda nada. La simulación viaja en el header `X-Sim` de cada request
—`AAPL:10,GGAL.BA:-100`— y se aplica a las posiciones en memoria, justo antes
de que los modelos las vean. Como todos los modelos reciben la lista de
posiciones por parámetro, alcanza con engancharla en el único embudo que las
carga (`analisis._posiciones`) para que composición, riesgo, Markowitz, Monte
Carlo y Black-Litterman contesten sobre la cartera simulada.

El camino de escritura —`/api/carteras`, `store`— NO mira este header: una
simulación no se puede guardar sin querer, ni con el simulador prendido.

Comprar es un lote nuevo a precio de hoy: costo = valor, así que no inventa P&L,
pero corre los pesos, las correlaciones, el VaR y la frontera, que es la
pregunta que uno está haciendo.

Vender NO es un lote negativo —eso daría pesos negativos y rompería el
optimizador, que asume posiciones largas—: se descuenta de los lotes que ya
tenés, del más viejo al más nuevo, igual que netea una venta real. Y tampoco
realiza ganancia: una venta hipotética cambia la exposición de acá en adelante,
no lo que ya ganaste.
"""

from flask import request

from core.data import sources


def desde_request() -> list:
    """[(ticker, cantidad)] leídos del header. Cantidad negativa = venta."""
    salida = []
    for parte in (request.headers.get("X-Sim") or "").split(","):
        ticker, _, cantidad = parte.partition(":")
        ticker = ticker.strip().upper()
        try:
            cantidad = float(cantidad)
        except ValueError:
            continue
        if ticker and cantidad:
            salida.append((ticker, cantidad))
    return salida


def _compra(ticker: str, qty: float):
    """Un lote comprado hoy a precio de mercado, o None si el ticker no cotiza.

    El precio sale de la misma serie que después usa la valuación, así que el
    costo y el valor del lote coinciden al centavo: la simulación no aporta P&L
    ni para bien ni para mal. Va en USD y con la fecha de la última rueda, no
    con la de hoy: si el mercado está cerrado, ese es el precio que existe.
    """
    s = sources.precios_usd(ticker)
    if s.empty:
        return None
    return {"ticker": ticker, "qty": float(qty),
            "buy_date": str(s.index[-1].date()),
            "buy_price": float(s.iloc[-1]), "commissions": 0.0,
            "currency": "USD", "source": "", "sim": True}


def aplicar(posiciones: list, specs: list = None) -> list:
    """Las posiciones como quedarían con la simulación puesta."""
    specs = desde_request() if specs is None else specs
    if not specs:
        return posiciones

    salida = [dict(p) for p in posiciones]

    # Ventas primero: se descuentan de lo que ya hay antes de sumar las compras,
    # para que vender y volver a comprar el mismo papel no se cancele mal.
    pendiente = {t: -q for t, q in specs if q < 0}
    if pendiente:
        for p in sorted(salida, key=lambda x: str(x.get("buy_date") or "")):
            t = str(p.get("ticker") or "").upper()
            resta = pendiente.get(t, 0.0)
            if resta <= 0:
                continue
            tenia = float(p.get("qty") or 0)
            baja = min(resta, tenia)
            p["qty"] = tenia - baja
            p["sim"] = True
            pendiente[t] = resta - baja
        # Un lote vendido entero se va: dejarlo en cero lo mostraría como una
        # tenencia que no tenés y le daría peso cero a un ticker que ya no está.
        salida = [p for p in salida if float(p.get("qty") or 0) > 0]

    for t, q in specs:
        if q > 0:
            lote = _compra(t, q)
            if lote:
                salida.append(lote)

    return salida
