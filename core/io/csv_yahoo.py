"""
csv_yahoo.py — Importa el CSV de Yahoo Finance tal cual se descarga.

Yahoo exporta el historial completo de operaciones, compras y ventas mezcladas.
Importarlo entero como posiciones daría una cartera falsa: aparecerían activos
que ya vendiste. Por eso las ventas **netean FIFO** contra los lotes de compra
más viejos de ese ticker, y solo entra a la cartera **lo que sigue abierto**.

Lo que cerró no se descarta: sale por separado como P&L realizado, con las dos
patas y sus comisiones, para poder mostrar cuánto se ganó de verdad.

Tres cosas que el archivo real trae y hay que manejar:

  · Filas `$$CASH_TX` — depósitos, retiros e intereses. No son posiciones.
  · Filas de *watchlist* — sin fecha ni precio de compra: nunca se operaron.
  · Comas sin comillas dentro de `Comment`. Corren la última columna y, si no se
    reparan, el neteo lee "Transaction Type" de otro campo y trabaja sobre
    basura sin fallar. Es el peor tipo de error: silencioso y plausible.
"""

import csv
import io
from pathlib import Path

from core.io.csv_native import normalizar_fecha


def _abrir(origen):
    if hasattr(origen, "read"):
        return origen, False
    ruta = Path(origen)
    if ruta.exists():
        return open(ruta, newline="", encoding="utf-8-sig"), True
    return io.StringIO(str(origen)), False


class NoEsYahoo(ValueError):
    """El archivo no tiene la forma de una exportación de Yahoo Finance."""


# Columnas mínimas que trae cualquier exportación de Yahoo con operaciones.
_REQUERIDAS = {"symbol", "trade date", "purchase price", "quantity"}


def leer_filas(origen) -> list:
    """Parsea por POSICIÓN, no por nombre de columna, y repara filas rotas.

    `csv.DictReader` descartaría el sobrante de una fila con una coma de más y
    perdería el último campo. Acá se reabsorbe todo lo que sobra dentro de
    `Comment` y se preserva la última columna, que es la que dice si la
    operación fue compra o venta.
    """
    f, cerrar = _abrir(origen)
    try:
        crudas = list(csv.reader(f))
    finally:
        if cerrar:
            f.close()
    if not crudas:
        return []

    encabezado = [h.strip().lower() for h in crudas[0]]

    # Sin esto, subir el CSV equivocado devuelve "0 importadas" y el usuario no
    # tiene forma de saber si el archivo estaba vacío, si el formato era otro o
    # si la aplicación falló. Un error claro vale más que un cero silencioso.
    faltan = _REQUERIDAS - set(encabezado)
    if faltan:
        raise NoEsYahoo(
            "No parece una exportación de Yahoo Finance: faltan las columnas "
            + ", ".join(sorted(faltan))
            + ". Si es una cartera en el formato propio, usá el importador de CSV.")

    n = len(encabezado)
    i_comment = encabezado.index("comment") if "comment" in encabezado else n - 2

    filas = []
    for cruda in crudas[1:]:
        if not cruda or not any(c.strip() for c in cruda):
            continue
        if len(cruda) > n:
            sobran = len(cruda) - n
            cruda = (cruda[:i_comment]
                     + [",".join(cruda[i_comment:i_comment + sobran + 1])]
                     + cruda[i_comment + sobran + 1:])
        elif len(cruda) < n:
            cruda = cruda + [""] * (n - len(cruda))
        filas.append({encabezado[i]: (cruda[i] or "").strip() for i in range(n)})
    return filas


def _aplicar_entrega(compras: list, entrega: dict) -> bool:
    """Reparte acciones recibidas sin pagar (split, dividendo en acciones).

    Un split NO es una compra a precio cero. Tratarlo así deja lotes con costo 0
    que el FIFO consume al final: mientras se liquide todo da el mismo resultado,
    pero con posición abierta el costo queda mal repartido —los lotes "gratis"
    figuran con 100 % de ganancia y los viejos con todo el costo encima—.

    Lo correcto es lo que hace el mercado: la misma plata pasa a estar repartida
    en más acciones. Se prorratea sobre los lotes abiertos a la fecha, en
    proporción a lo que cada uno tiene vivo, y baja el precio unitario de cada
    uno. El costo total no cambia; la cantidad, sí.
    """
    vivos = [c for c in compras if c["resta"] > 1e-9 and c["fecha"] <= entrega["fecha"]]
    base = sum(c["resta"] for c in vivos)
    if base <= 1e-9:
        return False                      # nada abierto: no hay dónde repartirlo
    factor = 1 + entrega["qty"] / base
    for c in vivos:
        c["resta"] *= factor
        c["qty"] *= factor
        c["precio"] /= factor
    return True


def _netear_fifo(compras: list, ventas: list, entregas: list = None):
    """Aparea ventas contra las compras más viejas. Devuelve (abiertos, cerrados).

    Las comisiones se prorratean por la fracción del lote que se vende: vender
    la mitad de un lote arrastra la mitad de la comisión de compra.
    """
    compras = [dict(c, resta=c["qty"]) for c in sorted(compras, key=lambda x: (x["fecha"], x["orden"]))]
    ventas = sorted(ventas, key=lambda x: (x["fecha"], x["orden"]))
    entregas = sorted(entregas or [], key=lambda x: (x["fecha"], x["orden"]))

    cerrados, i = [], 0
    for venta in ventas:
        # Las entregas anteriores a esta venta ya tienen que estar repartidas:
        # se vende la cantidad post-split contra el costo post-split.
        while entregas and entregas[0]["fecha"] <= venta["fecha"]:
            _aplicar_entrega(compras, entregas.pop(0))
        pendiente = venta["qty"]
        while pendiente > 1e-9 and i < len(compras):
            lote = compras[i]
            if lote["resta"] <= 1e-9:
                i += 1
                continue
            apareado = min(pendiente, lote["resta"])
            cerrados.append({
                "buy_date": lote["fecha"], "buy_price": lote["precio"],
                "sell_date": venta["fecha"], "sell_price": venta["precio"],
                "qty": round(apareado, 6),
                "buy_comm": round(lote["comision"] * apareado / lote["qty"], 4),
                "sell_comm": round(venta["comision"] * apareado / venta["qty"], 4),
            })
            lote["resta"] -= apareado
            pendiente -= apareado
        # Si sobra cantidad vendida, el CSV no muestra la compra correspondiente
        # (posición abierta antes del historial exportado). Se ignora el resto:
        # inventar un lote de compra sería inventar un precio.

    for entrega in entregas:                       # las que quedaron sin ventas
        _aplicar_entrega(compras, entrega)

    abiertos = [{"fecha": c["fecha"], "precio": c["precio"],
                 "qty": round(c["resta"], 6),
                 "comision": round(c["comision"] * c["resta"] / c["qty"], 4)}
                for c in compras if c["resta"] > 1e-9]
    return abiertos, cerrados


def parse_yahoo(origen):
    """Devuelve (posiciones_abiertas, trades_realizados).

    Las posiciones salen en el formato propio, listas para guardar. Los trades
    quedan en la moneda de cotización del ticker: la conversión a dólares se
    hace al mostrarlos, con el MEP de la fecha de cada pata, no acá.
    """
    filas = leer_filas(origen)

    compras, ventas, entregas, dividendos = {}, {}, {}, []
    for orden, fila in enumerate(filas):
        ticker = (fila.get("symbol") or "").strip().upper()
        if not ticker or ticker.startswith("$$"):
            continue                                  # depósitos, retiros, intereses
        fecha = fila.get("trade date") or ""
        if not fecha or fila.get("purchase price") in (None, ""):
            continue                                  # watchlist: nunca se operó
        try:
            precio = float(fila["purchase price"])
            qty = float(fila.get("quantity") or 0)
            comision = float(fila.get("commission") or 0)
        except ValueError:
            continue
        if qty <= 0:
            continue

        registro = {"fecha": normalizar_fecha(fecha), "precio": precio,
                    "qty": qty, "comision": comision, "orden": orden}
        # Las exportaciones viejas de Yahoo no traen la columna: se asume compra.
        tipo = (fila.get("transaction type") or "BUY").strip().upper()
        nota = (fila.get("comment") or "").strip().lower()

        if tipo in ("DIVIDEND", "DIV", "DIVIDENDO") or "dividendo" in nota:
            # Cobrado, no invertido: es resultado realizado del día que se cobró.
            dividendos.append({"ticker": ticker, "fecha": normalizar_fecha(fecha),
                               "qty": qty, "importe_unitario": precio,
                               "importe": round(qty * precio - comision, 4)})
        elif tipo in ("SPLIT", "STOCK DIVIDEND") or precio == 0:
            # Acciones que entraron sin pagar nada. Un precio de compra de cero
            # no existe: es un split o un dividendo en acciones, y se reparte
            # sobre lo que ya se tenía en vez de crear un lote regalado.
            entregas.setdefault(ticker, []).append(registro)
        elif tipo == "SELL":
            ventas.setdefault(ticker, []).append(registro)
        else:
            compras.setdefault(ticker, []).append(registro)

    abiertas, realizadas = [], []
    for ticker in sorted(set(compras) | set(ventas) | set(entregas)):
        quedan, cerrados = _netear_fifo(compras.get(ticker, []), ventas.get(ticker, []),
                                        entregas.get(ticker, []))
        for lote in quedan:
            abiertas.append({
                "ticker": ticker, "buy_date": lote["fecha"],
                "buy_price": lote["precio"], "qty": lote["qty"],
                "commissions": lote["comision"],
                "source": "", "currency": "", "asset_type": "", "notes": "",
            })
        for t in cerrados:
            pnl = t["qty"] * (t["sell_price"] - t["buy_price"]) - t["buy_comm"] - t["sell_comm"]
            realizadas.append({"ticker": ticker, **t, "pnl": round(pnl, 4)})

    # Los dividendos viajan con los trades cerrados: son resultado realizado
    # igual, solo que sin contrapartida de compra.
    for d in dividendos:
        realizadas.append({"ticker": d["ticker"], "tipo": "dividendo",
                           "buy_date": d["fecha"], "sell_date": d["fecha"],
                           "buy_price": 0.0, "sell_price": d["importe_unitario"],
                           "qty": d["qty"], "buy_comm": 0.0, "sell_comm": 0.0,
                           "pnl": d["importe"]})

    return abiertas, realizadas
