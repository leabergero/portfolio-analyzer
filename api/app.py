"""
app.py — El servidor. Delgado a propósito.

No hay lógica de negocio acá ni en `routes/`: los blueprints traducen HTTP a
llamadas al núcleo y devuelven JSON. Todo lo que calcula vive en `core/`, que no
sabe que existe la web — por eso los modelos se pueden probar sin levantar un
servidor, que es lo que hace `tests/test_verdades.py`.

Correr:

    ./.venv/bin/python -m api.app          →  http://127.0.0.1:5002
"""

import sys
from pathlib import Path

from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.routes import analisis, carteras, datos  # noqa: E402
from core.data import mep  # noqa: E402

WEB = Path(__file__).resolve().parent.parent / "web"
PUERTO = 5002

app = Flask(__name__, static_folder=None)
CORS(app)

app.register_blueprint(carteras.bp)
app.register_blueprint(analisis.bp)
app.register_blueprint(datos.bp)


@app.get("/")
def inicio():
    return send_from_directory(WEB, "index.html")


@app.get("/<path:recurso>")
def estatico(recurso):
    if (WEB / recurso).is_file():
        return send_from_directory(WEB, recurso)
    return jsonify({"error": "No encontrado."}), 404


@app.errorhandler(500)
def error_interno(e):
    # Un error de un modelo no puede tumbar la pantalla entera: se devuelve como
    # JSON para que el panel muestre el problema y el resto siga funcionando.
    return jsonify({"error": "Error interno", "detalle": str(e)}), 500


def main():
    print("\n" + "=" * 62)
    print("  Portfolio Analyzer")
    print("  Análisis de cartera · Comparación de carteras · todo en dólares")
    print(f"  http://127.0.0.1:{PUERTO}")
    print("=" * 62)

    r = mep.sincronizar()
    s = mep.serie()
    if len(s):
        print(f"  MEP: {len(s)} ruedas · hoy ${float(s.iloc[-1]):,.2f} · {r['estado']}")
    else:
        print("  MEP: sin serie — la valuación en dólares no va a funcionar.")

    from core.broker import cocos
    if not cocos.estado()["conectado"]:
        print("  Cocos: sin conectar (los bonos no van a tener precio; el resto sí).")
    print()

    app.run(host="127.0.0.1", port=PUERTO, debug=True, use_reloader=False)


if __name__ == "__main__":
    main()
