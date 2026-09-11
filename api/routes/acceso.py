"""Ingreso a la aplicación. Google pone la identidad; acá no hay contraseñas."""

from flask import Blueprint, current_app, jsonify, redirect, request

from core import usuarios
from core.io import store

bp = Blueprint("acceso", __name__, url_prefix="/api")

_VUELTA = "/api/entrar/google"


def _redirect_uri() -> str:
    """La URL exacta a la que Google devuelve el navegador.

    Tiene que coincidir carácter por carácter con la que esté cargada en la
    consola de Google, o el ingreso corta con redirect_uri_mismatch.
    """
    return request.url_root.rstrip("/") + _VUELTA


@bp.get("/entrar")
def entrar():
    if not usuarios.configurado():
        return jsonify({"error": "El ingreso con Google todavía no está configurado."}), 503
    destino = request.args.get("destino", "/")
    if not destino.startswith("/"):
        destino = "/"          # sólo rutas de esta app, nunca un sitio externo
    return redirect(usuarios.url_de_ingreso(_redirect_uri(), destino))


@bp.get("/entrar/google")
def entrar_google():
    """La vuelta de Google. Canjea el código y deja la sesión en una cookie."""
    if request.args.get("error"):
        return redirect("/?ingreso=cancelado")
    try:
        destino = usuarios.leer_estado(request.args.get("state"))
        usuario = usuarios.canjear(request.args.get("code", ""), _redirect_uri())
    except usuarios.NoAutenticado as e:
        current_app.logger.warning("ingreso rechazado: %s", e)
        return redirect("/?ingreso=fallo")

    # Estrena con una cartera de ejemplo: sin posiciones no hay riesgo ni
    # frontera ni Monte Carlo que mirar, y el que entra por primera vez no ve
    # qué hace la app hasta después de cargar diez lotes a mano. Se siembra una
    # sola vez y se puede borrar; borrada, no vuelve.
    store.como(usuarios.carpeta(usuario))
    store.sembrar()
    store.anotar(usuario)

    r = redirect(destino)
    r.set_cookie(usuarios.COOKIE, usuarios.emitir(usuario),
                 max_age=usuarios.MES, httponly=True, samesite="Lax",
                 secure=request.is_secure, path="/")
    return r


@bp.get("/yo")
def yo():
    """Quién está usando la app. El front lo pregunta al abrir."""
    try:
        u = usuarios.leer(request.cookies.get(usuarios.COOKIE))
    except usuarios.NoAutenticado:
        return jsonify({"dentro": False, "configurado": usuarios.configurado()})
    return jsonify({"dentro": True, "email": u.get("email"),
                    "nombre": u.get("nombre"), "foto": u.get("foto")})


@bp.post("/salir")
def salir():
    r = jsonify({"ok": True})
    r.delete_cookie(usuarios.COOKIE, path="/")
    return r
