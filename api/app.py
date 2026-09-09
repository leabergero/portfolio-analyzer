"""
app.py — El servidor. Delgado a propósito.

No hay lógica de negocio acá ni en `routes/`: los blueprints traducen HTTP a
llamadas al núcleo y devuelven JSON. Todo lo que calcula vive en `core/`, que no
sabe que existe la web — por eso los modelos se pueden probar sin levantar un
servidor, que es lo que hace `tests/test_verdades.py`.

Correr:

    ./.venv/bin/python -m api.app          →  http://127.0.0.1:5002
"""

import logging
import os
import sys
from pathlib import Path

from flask import Flask, g, jsonify, request, send_from_directory
from flask_cors import CORS

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.routes import acceso, analisis, carteras, datos  # noqa: E402
from core import mercado, usuarios  # noqa: E402
from core.broker import cocos, sesion  # noqa: E402
from core.io import store  # noqa: E402
from core.data import mep  # noqa: E402

WEB = Path(__file__).resolve().parent.parent / "web"
PUERTO = int(os.environ.get("PA_PUERTO", 5002))

app = Flask(__name__, static_folder=None)
CORS(app)
# Las líneas de diagnóstico de sesión son INFO y Flask corta en WARNING: sin
# esto, cuando algo rechaza un sobre el log dice 401 y no dice por qué.
app.logger.setLevel(logging.INFO)

app.register_blueprint(carteras.bp)
app.register_blueprint(analisis.bp)
app.register_blueprint(datos.bp)
app.register_blueprint(acceso.bp)


# ── Cabeceras de seguridad ────────────────────────────────────────────────────
# La CSP describe exactamente lo que esta página carga hoy, ni más ni menos. Lo
# que importa acá: `img-src` habilita googleusercontent, que es de donde viene
# la foto de perfil de Google. Sin eso el avatar sale como un círculo vacío y
# nadie entiende por qué.
#
# `script-src 'self'` a secas: el único que puede poner código en esta página es
# este servidor. React y Plotly se sirven desde `web/vendor/` justamente para
# poder decir esto — un script de terceros lee el localStorage, donde vive el
# sobre de sesión de Cocos.

CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self'",
    # 'unsafe-inline': el <style> de index.html y los style={{}} de React son
    # atributos inline. Sacarlo exige mover todo a hojas aparte.
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "img-src 'self' data: blob: https://*.googleusercontent.com",
    "connect-src 'self'",
    "worker-src 'self' blob:",          # Plotly arma workers desde blob:
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])


@app.after_request
def cabeceras(resp):
    resp.headers.setdefault("Content-Security-Policy", CSP)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    if request.is_secure:
        # Sólo sobre HTTPS: en local haría inaccesible el 127.0.0.1 por http.
        resp.headers.setdefault("Strict-Transport-Security",
                                "max-age=31536000; includeSubDomains")
    return resp


# ── Sesión web: el sobre entra y sale en cada request ─────────────────────────
# Sin cabecera `X-Sesion` no pasa nada y el modo local sigue igual: la app lee
# el vault del disco como siempre. Con cabecera, el cliente de Cocos se arma al
# empezar el request y se suelta al terminar, así entre request y request el
# proceso no tiene ningún token vivo en memoria.

CABECERA = "X-Sesion"
FIN = "X-Sesion-Fin"      # "este sobre ya no vale, tiralo"

# Lo único que se sirve sin sobre: la página, sus assets, y las dos rutas que el
# navegador necesita ANTES de tener sesión — saber en qué modo corre el servidor
# y poder hacer el login.
LIBRES = ("/api/modo", "/api/yo", "/api/entrar", "/api/entrar/google", "/api/salir")

# Endpoints de la app de escritorio que en la web no puede tocar nadie. El front
# no los muestra, pero un POST a mano sí llega: son el vault del dueño de la
# máquina y la API key de FMP, que es nuestra y la comparten todos los usuarios.
# Sin este corte, cualquiera con sesión podía borrar el vault o cambiarle la
# clave de FMP a todo el mundo.
SOLO_LOCAL = ("/api/broker/vault", "/api/broker/conectar", "/api/broker/borrar",
              "/api/broker/desconectar", "/api/conectores/fmp")


@app.get("/api/modo")
def modo():
    """En qué modo corre este servidor. Sin sesión: el front lo pregunta al abrir."""
    return jsonify({"modo": "web" if sesion.modo_web() else "local"})


# ── Plaza ─────────────────────────────────────────────────────────────────────
# Desde dónde se mira la cartera: define la moneda de medición, la tasa libre de
# riesgo y el índice con el que abre. Viaja en cada request porque es del
# navegador que pregunta, no del servidor. Sin cabecera, Argentina.

@app.before_request
def elegir_mercado():
    mercado.poner(request.headers.get("X-Mercado"))


@app.before_request
def abrir_sesion():
    if not sesion.modo_web():
        return None                       # modo local: manda el vault, se ignora
    if not request.path.startswith("/api/") or request.path in LIBRES:
        return None
    if request.path in SOLO_LOCAL:
        return jsonify({"error": "Esa operación no existe en la web."}), 403

    # 1 · Quién sos. Esta es la puerta: sin sesión de la app no se pasa.
    try:
        g.usuario = usuarios.leer(request.cookies.get(usuarios.COOKIE))
    except usuarios.NoAutenticado as e:
        app.logger.warning("401 ingreso · %s · %s", request.path, e)
        return jsonify({"error": str(e), "ingresar": True}), 401
    store.como(usuarios.carpeta(g.usuario))

    # 2 · Cocos, opcional. Quien no conectó el broker usa la app igual: carga su
    #     cartera a mano o por CSV y los precios salen de yfinance. Por eso la
    #     falta de sobre no corta el request, sólo deja el broker sin conectar.
    sobre = request.headers.get(CABECERA)
    if not sobre:
        return None
    # Si el sobre no sirve, el broker se cae pero la app NO. Cocos es opcional:
    # bloquear todo acá dejaba a alguien sin poder mirar sus propias carteras
    # porque se le venció una sesión que ni siquiera necesita. Se marca el sobre
    # como muerto, el front lo tira, y se sigue como quien nunca lo conectó.
    try:
        jwt = sesion.leer(sobre)
    except sesion.SesionInvalida as e:
        app.logger.info("sobre de Cocos descartado · %s · %s", request.path, e)
        g.sobre_muerto = str(e)
        return None

    g.login_ts = jwt.pop("login_ts", None)
    estado, renovado = cocos.restaurar(jwt)
    if not estado["conectado"]:
        app.logger.info("Cocos no restauró · %s · %s", request.path, estado["detalle"])
        g.sobre_muerto = estado["detalle"]
        return None
    if renovado:
        # Cocos renovó el access token: hay que devolverle un sobre nuevo al
        # navegador, con el login_ts VIEJO. Si acá se emitiera uno fresco, el
        # reloj de 24 h se reiniciaría solo y el 2FA diario no llegaría nunca.
        g.sobre_nuevo = sesion.emitir(renovado, login_ts=g.login_ts)
    return None


@app.after_request
def cerrar_sesion(resp):
    if not sesion.modo_web():
        return resp
    if cocos.sesion_muerta():
        app.logger.info("Cocos devolvió 401 · %s", request.path)
        g.sobre_muerto = "Cocos rechazó la sesión."

    if motivo := g.pop("sobre_muerto", None):
        # El sobre no vale más: el front lo tira y muestra el broker como
        # desconectado, sin sacar al usuario de la app.
        resp.headers[FIN] = "1"
        # En los endpoints del broker sí corta: pedir posiciones sin sesión no
        # tiene respuesta útil, y un 200 con un ApiException adentro deja al
        # front mostrando un error genérico en vez de ofrecer reconectar.
        if request.path.startswith(("/api/cocos/", "/api/broker/")):
            muerta = jsonify({"error": motivo, "reautenticar": True})
            muerta.status_code = 401   # after_request devuelve respuesta, no tupla
            muerta.headers[FIN] = "1"
            return muerta
    if sobre := g.pop("sobre_nuevo", None):
        resp.headers[CABECERA] = sobre
    return resp


@app.teardown_request
def soltar_cliente(exc):
    if not sesion.modo_web():
        return
    # Con hilos reusados (gunicorn), lo que quede seteado en el contexto lo
    # heredaría el próximo usuario que caiga en ese hilo. Se limpia siempre.
    store.como(None)
    if g.pop("login_ts", None) is not None:
        cocos.olvidar()


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

    if not cocos.estado()["conectado"]:
        print("  Cocos: sin conectar (los bonos no van a tener precio; el resto sí).")
    # Recién clonado no hay ninguna cartera y la app no se puede recorrer. La
    # cartera modelo se siembra sólo si el archivo de carteras no existe: quien
    # ya tiene las suyas no se entera de que esto existe.
    if store.sembrar():
        print("  Se cargó la cartera «Modelo» de ejemplo (examples/modelo.csv).")
        print("  Borrala cuando cargues las tuyas: no vuelve a aparecer.")
    print()

    app.run(host="127.0.0.1", port=PUERTO, debug=True, use_reloader=False)


if __name__ == "__main__":
    main()
