"""
lab_server.py — lab local para investigar la API de InvIU con tu cuenta real.

Cómo funciona, en una frase: abre un Chrome de verdad apuntado a la página
oficial de InvIU, VOS te logueás ahí con tu usuario y tu 2FA reales (tu
contraseña nunca pasa por este servidor), y este proceso mira en silencio
el tráfico de red y el localStorage de esa pestaña para sacar los tokens y
mostrarte tu cartera acá en el lab.

Todo corre en tu máquina, en un solo proceso, para un solo usuario: no hay
multiusuario ni nada que valga la pena generalizar todavía (ver README).

    ponytail: estado global de módulo (_estado) en vez de una clase — es un
    lab de una sola sesión en un solo proceso, no un servidor real. Si esto
    se integra a portfolio-analyzer, ese es el momento de mirar cómo cocos.py
    resuelve lo mismo por request con ContextVar.
"""

import threading
from concurrent.futures import ThreadPoolExecutor

from flask import Flask, jsonify, send_from_directory
from playwright.sync_api import sync_playwright

LOGIN_URL = "https://inversor.inviu.com.ar/login"
DOMINIOS_API = ("inviuxy.inviu.com.ar", "api-web.inviu.com.ar")

app = Flask(__name__)

_estado = {
    "playwright": None, "browser": None, "page": None,
    "conectado": False, "detalle": "sin conectar",
    "capturas": [],       # cada request/response real visto en esos dominios
    "cartera": None,
}
_lock = threading.Lock()

# La API sync de Playwright solo se puede usar desde el hilo que la arrancó;
# Flask no garantiza que dos requests caigan en el mismo hilo. Un pool de un
# solo worker fija ese hilo, y todo lo que toque `page`/`browser` pasa por acá
# en vez de tocarlos directo desde el handler de Flask. Sin esto, `page.url`
# tiraba `greenlet.error` capturado por un `except Exception` demasiado ancho,
# y el lab nunca se enteraba de que ya habías iniciado sesión.
_hilo_pw = ThreadPoolExecutor(max_workers=1)


def _en_pw(fn):
    return _hilo_pw.submit(fn).result()


def _en_dominio_api(url: str) -> bool:
    return any(d in url for d in DOMINIOS_API)


def _cuerpo_pedido(request):
    """El body que se mandó, con la contraseña tapada antes de guardarlo."""
    try:
        datos = request.post_data_json
    except Exception:
        return None
    if isinstance(datos, dict) and "password" in datos:
        datos = {**datos, "password": "***"}
    return datos


def _registrar_respuesta(response):
    """Guarda cada llamada real a la API de InvIU que haga la SPA sola, pedido
    y respuesta juntos.

    Esto es lo que reemplaza la ingeniería inversa manual: en vez de adivinar
    el endpoint de login y su body a mano, se ve acá tal cual la app los usa.
    """
    if not _en_dominio_api(response.url):
        return
    try:
        cuerpo = response.json()
    except Exception:
        cuerpo = None
    entrada = {"metodo": response.request.method, "url": response.url,
               "status": response.status,
               "pedido": _cuerpo_pedido(response.request), "cuerpo": cuerpo}
    _estado["capturas"].append(entrada)
    if "consolidated-portfolio" in response.url and cuerpo:
        _estado["cartera"] = cuerpo


@app.get("/")
def index():
    return send_from_directory(".", "lab.html")


def _conectar():
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=False)
    page = browser.new_page()
    page.on("response", _registrar_respuesta)
    page.goto(LOGIN_URL)
    _estado.update(playwright=pw, browser=browser, page=page,
                   detalle="ventana abierta, logueate ahí")


@app.post("/api/conectar")
def conectar():
    with _lock:
        if _estado["page"] is not None:
            return jsonify(_publico())
        _en_pw(_conectar)
    return jsonify(_publico())


def _chequear_login():
    page = _estado["page"]
    if page is None or _estado["conectado"]:
        return
    # "Logueado" = ya no estamos en /login. No hace falta adivinar el
    # endpoint: el cambio de URL lo dice solo.
    url_actual = page.url
    if url_actual and "/login" not in url_actual:
        tokens = page.evaluate(
            "() => Object.entries(localStorage)"
            ".filter(([k]) => /token|auth|session/i.test(k))"
        )
        _estado.update(conectado=True, detalle="conectado",
                       tokens_localstorage=dict(tokens))


def _hacer_login(email, password):
    page = _estado["page"]
    if "/login" not in page.url:
        page.goto(LOGIN_URL)
    page.wait_for_selector('input[type="email"]', timeout=15000)
    page.fill('input[type="email"]', email)
    page.fill('input[type="password"]', password)
    page.get_by_text("Ingresar", exact=True).click()
    page.wait_for_timeout(2500)


@app.post("/api/login")
def login():
    from flask import request
    body = request.get_json()
    with _lock:
        if _estado["page"] is None:
            return jsonify({"error": "primero abrí el navegador"}), 400
        try:
            _en_pw(lambda: _hacer_login(body["email"], body["password"]))
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return jsonify(_publico())


def _hacer_2fa(codigo):
    page = _estado["page"]
    # No sabemos el selector exacto del campo del código: se toma el primer
    # input de texto visible en pantalla en este paso, que es como InvIU
    # arma el paso de challenge (un solo campo).
    campo = page.locator(
        'input[type="text"]:visible, input[type="tel"]:visible, '
        'input[type="number"]:visible'
    ).first
    campo.fill(codigo)
    for texto in ("Confirmar", "Ingresar", "Continuar", "Verificar"):
        boton = page.get_by_text(texto, exact=True)
        if boton.count():
            boton.first.click()
            break
    page.wait_for_timeout(2500)


@app.post("/api/2fa")
def dos_fa():
    from flask import request
    body = request.get_json()
    with _lock:
        if _estado["page"] is None:
            return jsonify({"error": "primero abrí el navegador"}), 400
        try:
            _en_pw(lambda: _hacer_2fa(body["codigo"]))
        except Exception as e:
            return jsonify({"error": str(e)}), 500
        _en_pw(_chequear_login)
    return jsonify(_publico())


@app.get("/api/estado")
def estado():
    with _lock:
        if _estado["page"] is not None:
            _en_pw(_chequear_login)
    return jsonify(_publico())


def _debug_info():
    page = _estado["page"]
    if page is None:
        return {"page": None}
    return {"url": page.url, "n_paginas_contexto": len(page.context.pages)}


@app.get("/api/debug")
def debug():
    with _lock:
        return jsonify(_en_pw(_debug_info))


@app.get("/api/screenshot")
def screenshot():
    with _lock:
        if _estado["page"] is None:
            return jsonify({"error": "sin página"})
        _en_pw(lambda: _estado["page"].screenshot(path="screenshot.png"))
    return send_from_directory(".", "screenshot.png")


def _recorrer_tabs():
    """Hace click en cada pestaña de la app para que la SPA dispare sola sus
    llamadas — la forma más rápida de mapear toda la API sin adivinar rutas."""
    page = _estado["page"]
    tabs = ["Operaciones", "Movimientos", "Depósitos y retiros",
            "Datos personales", "Rendimientos", "Flujo de fondos proyectados"]
    vistas = []
    for nombre in tabs:
        try:
            page.get_by_text(nombre, exact=True).first.click(timeout=5000)
            page.wait_for_timeout(1500)
            vistas.append(nombre)
        except Exception as e:
            vistas.append(f"{nombre} (fallo: {e})")
    return vistas


@app.post("/api/recorrer")
def recorrer():
    with _lock:
        if _estado["page"] is None:
            return jsonify({"error": "sin página"})
        vistas = _en_pw(_recorrer_tabs)
    return jsonify({"vistas": vistas, "n_capturas": len(_estado["capturas"])})


def _leer_tokens():
    page = _estado["page"]
    if page is None:
        return None
    pares = page.evaluate(
        "() => Object.entries(localStorage)"
        ".filter(([k]) => /token|auth|session/i.test(k))"
    )
    return dict(pares)


@app.get("/api/token")
def token():
    with _lock:
        return jsonify(_en_pw(_leer_tokens) or {})


@app.get("/api/cartera")
def cartera():
    with _lock:
        return jsonify({"cartera": _estado["cartera"],
                        "capturas": _estado["capturas"]})


def _cerrar():
    if _estado["browser"]:
        _estado["browser"].close()
    if _estado["playwright"]:
        _estado["playwright"].stop()


@app.post("/api/cerrar")
def cerrar():
    with _lock:
        if _estado["page"] is not None:
            _en_pw(_cerrar)
        _estado.update(playwright=None, browser=None, page=None,
                       conectado=False, detalle="sin conectar")
    return jsonify(_publico())


def _publico() -> dict:
    return {"conectado": _estado["conectado"], "detalle": _estado["detalle"],
            "n_capturas": len(_estado["capturas"])}


if __name__ == "__main__":
    app.run(port=5057, debug=False)
