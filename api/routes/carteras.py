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
    buf = io.StringIO()
    csv_native.write_positions(buf, store.cargar(nombre))
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition":
                             f'attachment; filename="{nombre}.csv"'})


@bp.post("/<nombre>/importar")
def importar(nombre):
    if "file" not in request.files:
        return jsonify({"error": "No se adjuntó ningún archivo."}), 400
    try:
        posiciones = csv_native.read_positions(
            io.StringIO(request.files["file"].read().decode("utf-8-sig")))
    except Exception as e:
        return jsonify({"error": f"No se pudo leer el CSV: {e}"}), 400
    if not posiciones:
        return jsonify({"error": "El archivo no tiene posiciones legibles."}), 400
    return jsonify({"ok": True, **store.agregar(nombre, posiciones)})


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
    r_pnl = store.agregar_realizado(nombre, realizadas)
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
