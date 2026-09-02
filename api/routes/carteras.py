"""Carteras: alta, edición, importación y exportación."""

import io

from flask import Blueprint, Response, jsonify, request

from core.io import csv_native, csv_yahoo, store
from core.models import portfolio

bp = Blueprint("carteras", __name__, url_prefix="/api/carteras")


@bp.get("")
def listar():
    todas = store.cargar_todas()
    return jsonify([{"nombre": n, "posiciones": len(p)} for n, p in todas.items()])


@bp.get("/<nombre>")
def leer(nombre):
    return jsonify(store.cargar(nombre))


@bp.post("/<nombre>")
def guardar(nombre):
    posiciones = (request.json or {}).get("posiciones", [])
    return jsonify({"ok": True, "guardadas": store.guardar(nombre, posiciones)})


@bp.delete("/<nombre>")
def borrar(nombre):
    return jsonify({"ok": store.borrar(nombre),
                    "nota": "El P&L realizado se conserva: es historia, no estado."})


@bp.post("/<nombre>/duplicar")
def duplicar(nombre):
    destino = (request.json or {}).get("destino", "").strip()
    if not destino:
        return jsonify({"error": "Falta el nombre de la copia."}), 400
    return jsonify({"ok": True, "copiadas": store.duplicar(nombre, destino),
                    "destino": destino})


@bp.get("/<nombre>/exportar")
def exportar(nombre):
    """El archivo es el respaldo completo: posiciones, cerradas y dividendos."""
    buf = io.StringIO()
    csv_native.write_todo(buf, store.cargar(nombre), store.cargar_realizado(nombre))
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition":
                             f'attachment; filename="{nombre}.csv"'})


@bp.post("/<nombre>/importar")
def importar(nombre):
    if "file" not in request.files:
        return jsonify({"error": "No se adjuntó ningún archivo."}), 400
    texto = request.files["file"].read().decode("utf-8-sig")
    try:
        posiciones = csv_native.read_positions(io.StringIO(texto))
        realizadas = csv_native.read_realizado(io.StringIO(texto))
    except Exception as e:
        return jsonify({"error": f"No se pudo leer el CSV: {e}"}), 400
    if not posiciones and not realizadas:
        return jsonify({"error": "El archivo no tiene posiciones legibles."}), 400

    lote = f"propio:{request.files['file'].filename or 'sin-nombre'}"
    resumen = store.agregar(nombre, posiciones) if posiciones else {"agregadas": 0, "omitidas": 0}
    r_real = (store.agregar_realizado(nombre, realizadas, lote) if realizadas
              else {"agregados": 0})
    return jsonify({"ok": True, **resumen,
                    "realizadas_agregadas": r_real["agregados"],
                    "dividendos": sum(1 for t in realizadas if t.get("tipo") == "dividendo")})


def _armar_dividendo(c: dict) -> dict:
    """Una fila de dividendo, o un error explicando qué le falta."""
    ticker = (c.get("ticker") or "").strip().upper()
    fecha = csv_native.normalizar_fecha(c.get("fecha") or "")
    try:
        importe = float(c.get("importe") or 0)
        qty = float(c.get("qty") or 0) or 1.0
        comision = float(c.get("comision") or 0)
    except (TypeError, ValueError):
        return {"error": "El importe y la cantidad tienen que ser números."}
    if not ticker or not fecha or importe <= 0:
        return {"error": "Hacen falta ticker, fecha e importe."}

    # `por_accion` distingue las dos formas de tenerlo anotado: el dividendo
    # unitario que publica la empresa, o el total que entró a la cuenta.
    unitario = importe if c.get("por_accion") else importe / qty

    # La moneda del cobro NO se deduce del ticker. Un CEDEAR D cotiza en
    # dólares, pero su dividendo suele acreditarse en pesos: dar por sentado que
    # un dividendo de TSMD.BA viene en dólares multiplica el importe por el MEP.
    # Se guarda dicha, y solo si no viene se usa la convención del ticker.
    moneda = (c.get("moneda") or "").strip().upper()
    if moneda not in ("ARS", "USD"):
        moneda = None

    trade = {"ticker": ticker, "tipo": "dividendo",
             "buy_date": fecha, "sell_date": fecha,
             "buy_price": 0.0, "sell_price": round(unitario, 6), "qty": qty,
             "buy_comm": 0.0, "sell_comm": comision,
             "pnl": round(qty * unitario - comision, 4),
             "notes": (c.get("notes") or "").strip()}
    if moneda:
        trade["moneda"] = moneda
    return trade


@bp.post("/<nombre>/dividendo")
def dividendo(nombre):
    """Registra dividendos cobrados. No tocan la posición: son resultado, no compra.

    Acepta una fila suelta o una lista: quien tiene seis cobros de un papel los
    carga de una vez en vez de repetir el formulario seis veces.
    """
    cuerpo = request.json or {}
    filas = cuerpo if isinstance(cuerpo, list) else cuerpo.get("dividendos") or [cuerpo]

    trades, errores = [], []
    for i, c in enumerate(filas):
        armado = _armar_dividendo(c)
        (errores if "error" in armado else trades).append(
            {"fila": i + 1, **armado} if "error" in armado else armado)
    if not trades:
        return jsonify({"error": errores[0]["error"] if errores
                        else "No se envió ningún dividendo.", "errores": errores}), 400

    r = store.agregar_realizado(nombre, trades)
    if not r["agregados"]:
        return jsonify({"error": "Esos dividendos ya estaban registrados."}), 409
    return jsonify({"ok": True, "trades": trades, "errores": errores,
                    "importe_total": round(sum(t["pnl"] for t in trades), 2), **r})


@bp.delete("/<nombre>/realizado")
def borrar_realizado(nombre):
    """Borra un registro del P&L realizado, por si se cargó mal."""
    c = request.json or {}
    quitados = store.quitar_realizado(nombre, c)
    return jsonify({"ok": True, "quitados": quitados})


@bp.post("/<nombre>/importar-yahoo")
def importar_yahoo(nombre):
    if "file" not in request.files:
        return jsonify({"error": "No se adjuntó ningún archivo."}), 400
    contenido = io.StringIO(request.files["file"].read().decode("utf-8-sig"))
    try:
        abiertas, realizadas = csv_yahoo.parse_yahoo(contenido)
    except csv_yahoo.NoEsYahoo as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"No se pudo leer el CSV: {e}"}), 400

    resumen = store.agregar(nombre, abiertas)
    # El archivo identifica el lote: volver a subirlo pisa lo que dejó la vez
    # anterior en vez de sumarse a ello.
    r_pnl = store.agregar_realizado(
        nombre, realizadas, f"yahoo:{request.files['file'].filename or 'sin-nombre'}")
    pnl = portfolio.pnl_realizado(store.cargar_realizado(nombre))
    return jsonify({
        "ok": True, **resumen,
        "cerradas_por_venta": len(realizadas),
        "nuevas_al_realizado": r_pnl["agregados"],
        "pnl_realizado_usd": pnl["total_usd"],
        "nota": "Solo se importó lo que sigue abierto. Las ventas netearon FIFO "
                "contra las compras más viejas; lo cerrado fue al P&L realizado.",
    })


@bp.get("/<nombre>/realizado")
def realizado(nombre):
    return jsonify(portfolio.pnl_realizado(store.cargar_realizado(nombre)))
