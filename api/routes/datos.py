"""Datos transversales: MEP, validación de tickers, comparación y conectores."""

from flask import Blueprint, Response, jsonify, request

from api import sim
from core.broker import cocos, inviu, sesion, vault
from core.data import cache, connectors, fmp, mep, noticias, sources
from core.io import csv_native, store
from core.models import comparacion

bp = Blueprint("datos", __name__, url_prefix="/api")


@bp.get("/salud")
def salud():
    s = mep.serie()
    return jsonify({
        "ok": True,
        "mep": {"ruedas": len(s), "ultimo": round(float(s.iloc[-1]), 2) if len(s) else None,
                "fecha": str(s.index[-1].date()) if len(s) else None,
                "fuente": mep.fuente()},
        "cache": cache.estadisticas(),
        "carteras": store.nombres(),
        "conectores": {"cocos": cocos.estado(), "fmp": {"configurado": fmp.habilitado()}},
    })


# ── MEP ───────────────────────────────────────────────────────────────────────

@bp.get("/mep")
def mep_serie():
    s = mep.serie()
    if s.empty:
        return jsonify({"error": "Sin serie de MEP."}), 503
    desde = request.args.get("desde")
    if desde:
        s = s.loc[desde:]
    return jsonify({
        "fuente": mep.fuente(), "ruedas": len(s),
        "hoy": round(float(s.iloc[-1]), 2),
        "serie": [{"fecha": str(f.date()), "valor": round(float(v), 2)}
                  for f, v in s.items()],
        "eventos": mep.eventos(str(s.index[0].date()), str(s.index[-1].date())),
    })


@bp.post("/mep/sincronizar")
def mep_sync():
    return jsonify(mep.sincronizar(forzar=True))


# ── Validación de tickers ─────────────────────────────────────────────────────

@bp.get("/validar/<ticker>")
def validar(ticker):
    """¿Este ticker tiene datos suficientes para analizarlo?

    Se pide antes de agregar una posición: descubrir que no hay historia recién
    cuando falla el análisis completo es la peor forma de enterarse.
    """
    ticker = ticker.upper().strip()
    serie = sources.precios_base(ticker)
    if serie.empty:
        return jsonify({"ticker": ticker, "valido": False,
                        "detalle": "No se encontraron precios en ninguna fuente."})
    # Un ticker en una moneda que no se sabe convertir se valúa igual, pero con
    # el número crudo de su bolsa: SHEL.L cotiza en peniques y sumarlo a una
    # cartera como si fueran dólares la infla sin que nada avise. El aviso lo da
    # la pantalla al cargarlo, que es cuando todavía se puede no cargarlo.
    moneda = sources.ticker_currency(ticker)
    return jsonify({
        "ticker": ticker, "valido": True,
        "moneda": moneda,
        "convertible": moneda in ("ARS", "USD", "EUR"),
        "es_bono": sources.is_bond(ticker),
        "subyacente": sources.base_symbol(ticker),
        "ruedas": len(serie),
        "desde": str(serie.index[0].date()), "hasta": str(serie.index[-1].date()),
        "ultimo_usd": round(float(serie.iloc[-1]), 4),
        "alcanza_para_analisis": len(serie) >= 60,
        "detalle": ("Historia suficiente." if len(serie) >= 60 else
                    f"Solo {len(serie)} ruedas: hacen falta 60 para que la "
                    f"volatilidad y las correlaciones signifiquen algo."),
    })


@bp.get("/plantilla")
def plantilla():
    return Response(csv_native.plantilla(), mimetype="text/csv",
                    headers={"Content-Disposition":
                             'attachment; filename="plantilla_cartera.csv"'})


# ── Comparación (modo 2) ──────────────────────────────────────────────────────

@bp.post("/comparar")
def comparar():
    cuerpo = request.json or {}
    carteras = {n: store.cargar(n) for n in cuerpo.get("carteras", []) if store.cargar(n)}

    # La cartera simulada no existe en ningún lado: se arma acá, en memoria.
    # Es lo que evita tener que duplicar una cartera y editarla a mano sólo para
    # compararse contra uno mismo con dos activos más.
    base = cuerpo.get("sim_sobre")
    specs = sim.desde_request()
    if base and specs and store.cargar(base):
        carteras[f"{base} + simulación"] = sim.aplicar(store.cargar(base), specs)

    if len(carteras) < 2:
        return jsonify({"error": "Hacen falta al menos dos carteras con posiciones."}), 400
    return jsonify(comparacion.comparar(carteras, cuerpo.get("benchmark")))


# ── Noticias ──────────────────────────────────────────────────────────────────

@bp.get("/noticias")
def titulares():
    return jsonify(noticias.ultimas(request.args.get("limite", 40, type=int),
                                    request.args.get("seccion")))


@bp.get("/noticias/<cartera>")
def titulares_cartera(cartera):
    """Titulares que mencionan alguno de tus activos, por nombre de la empresa."""
    pos = store.cargar(cartera)
    if not pos:
        return jsonify({"error": f'La cartera "{cartera}" no existe.'}), 404
    return jsonify(noticias.por_cartera(pos))


# ── Reporte PDF ───────────────────────────────────────────────────────────────

@bp.get("/reporte/<cartera>")
def reporte(cartera):
    """PDF con los gráficos dibujados en el servidor: no necesita navegador."""
    from core.models import reporte as rep
    pos = store.cargar(cartera)
    if not pos:
        return jsonify({"error": f'La cartera "{cartera}" no existe.'}), 404
    try:
        pdf = rep.generar(cartera, pos)
    except Exception as e:
        return jsonify({"error": f"No se pudo generar el reporte: {e}"}), 500
    from datetime import date as _d
    return Response(pdf, mimetype="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="{cartera}_{_d.today()}.pdf"'})


# ── Conectores ────────────────────────────────────────────────────────────────

@bp.get("/conectores")
def conectores():
    """Estado de las fuentes. Las dos que piden credencial son opcionales."""
    return jsonify({
        "publicas": [
            {"nombre": "ArgentinaDatos + dolarapi", "requiere": None,
             "aporta": "Serie del dólar MEP", "estado": "activo" if len(mep.serie()) else "sin datos"},
            {"nombre": "yfinance", "requiere": None,
             "aporta": "Acciones, CEDEARs, ETFs, benchmarks", "estado": "activo"},
        ],
        "con_credencial": [
            {"nombre": "Cocos Capital", "requiere": "cuenta de broker",
             "aporta": "Bonos soberanos, ONs y letras",
             "sin_ella": "El resto de la aplicación funciona igual; falta el precio de renta fija.",
             **cocos.estado()},
            {"nombre": "Financial Modeling Prep", "requiere": "API key (plan gratuito)",
             "aporta": "Precios objetivo de analistas de EE.UU.",
             "sin_ella": "Los objetivos salen de yfinance, con menos cobertura.",
             **fmp.estado()},
            {"nombre": "InvIU", "requiere": "cuenta de broker (login por navegador)",
             "aporta": "Cartera, operaciones, rentas y flujo proyectado de bonos",
             "sin_ella": "El resto de la aplicación funciona igual; falta esta cuenta.",
             **inviu.estado(), "vault_cargado": vault.existe(inviu.BROKER)},
        ],
        "descartadas": [
            {"nombre": "PyOBD / BYMA Open Data", "motivo": "Hoy devuelve vacío para todos los símbolos."},
            {"nombre": "yfinance para el MEP", "motivo": "Da AL30 y AL30D por delistados."},
        ],
    })


@bp.post("/conectores/fmp")
def guardar_fmp():
    key = (request.json or {}).get("api_key", "").strip()
    if not key:
        return jsonify({"error": "Falta la API key."}), 400
    connectors.guardar("fmp", {"api_key": key})
    return jsonify({"ok": True, **fmp.estado()})


# ── Broker ────────────────────────────────────────────────────────────────────

@bp.get("/broker/estado")
def broker_estado():
    return jsonify({**cocos.estado(),
                    "modo": "web" if sesion.modo_web() else "local",
                    "vault_cargado": False if sesion.modo_web() else vault.existe()})


def _parte_2fa(valor: str):
    """Separa lo que el usuario puso en el campo 2FA en (semilla, código puntual).

    Un código de la app son 6 dígitos y vale medio minuto: no se guarda, se usa
    sólo en esta conexión. Cualquier otra cosa se toma como semilla base32 y sí
    se guarda, porque genera los códigos sola de ahí en más.
    """
    v = (valor or "").strip()
    if v.replace(" ", "").isdigit() and len(v.replace(" ", "")) == 6:
        return "", v.replace(" ", "")
    return v, ""


@bp.post("/broker/vault")
def broker_vault():
    """Cifra email/contraseña, guarda la clave sola y conecta en un paso.

    El usuario nunca ve ni maneja la clave del vault. El 2FA puede ser la semilla
    (se guarda) o el código de 6 dígitos del momento (no se guarda: sirve sólo
    para este login, y después manda la sesión guardada).
    """
    c = request.json or {}
    semilla, codigo = _parte_2fa(c.get("totp_secret_key", ""))
    try:
        api_key = vault.crear({"email": c.get("email", ""),
                               "password": c.get("password", ""),
                               "totp_secret_key": semilla})
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"ok": True, **cocos.conectar(api_key, forzar_login=True, codigo_2fa=codigo)})


@bp.post("/broker/conectar")
def broker_conectar():
    """Conecta con la clave guardada. Reusa la sesión salvo forzar_login.

    Acepta un código 2FA puntual para cuando la sesión caducó y no hay semilla.
    """
    api_key = vault.clave_guardada()
    if not api_key:
        return jsonify({"error": "No hay credenciales cargadas."}), 400
    c = request.json or {}
    _, codigo = _parte_2fa(c.get("codigo_2fa", ""))
    return jsonify(cocos.conectar(api_key, c.get("forzar_login", False), codigo_2fa=codigo))


# ── Modo web: login sin vault ─────────────────────────────────────────────────

_INTENTOS = {}
_MAX_INTENTOS, _VENTANA = 5, 15 * 60


def _frenado(clave: str) -> int:
    """Segundos que faltan para poder reintentar, o 0.

    Este endpoint es un proxy al login de Cocos: sin freno sirve para probar
    contraseñas ajenas, o peor, para bloquearle la cuenta a un usuario a fuerza
    de intentos fallidos. El freno es por email, que es lo que Cocos bloquea.

        ponytail: contador en memoria, se borra al reiniciar y no se comparte
        entre procesos. Alcanza con un contenedor por usuario; en el despliegue
        el límite de verdad va en el proxy (nginx limit_req), que ve todas las
        IPs y sobrevive a los reinicios.
    """
    import time
    intentos = [t for t in _INTENTOS.get(clave, []) if time.time() - t < _VENTANA]
    _INTENTOS[clave] = intentos
    if len(intentos) < _MAX_INTENTOS:
        return 0
    return int(_VENTANA - (time.time() - intentos[0]))


def _anotar_fallo(clave: str):
    import time
    _INTENTOS.setdefault(clave, []).append(time.time())


@bp.post("/broker/web/login")
def broker_web_login():
    """Login con credenciales que no se guardan: ni en disco, ni cifradas.

    El usuario tipea email, contraseña y el código de 6 dígitos. Se hace el
    login contra Cocos, se le devuelve al navegador un sobre firmado con los
    JWT adentro, y las credenciales se van con el garbage collector.

    La semilla TOTP se rechaza a propósito: guardarla dejaría al servidor
    generando códigos solo para siempre, y la caducidad diaria del sobre —lo
    único que obliga al segundo factor a aparecer— no valdría nada.
    """
    if not sesion.modo_web():
        return jsonify({"error": "Este servidor corre en modo local: "
                                 "la conexión va por el vault."}), 400

    c = request.json or {}
    email = (c.get("email") or "").strip()
    semilla, codigo = _parte_2fa(c.get("codigo_2fa", ""))

    if semilla:
        return jsonify({"error": "Acá va el código de 6 dígitos de la app, "
                                 "no la semilla: la semilla no se guarda."}), 400
    if not codigo:
        return jsonify({"error": "Falta el código 2FA de 6 dígitos."}), 400

    if espera := _frenado(email):
        return jsonify({"error": f"Demasiados intentos. Probá en {espera // 60 + 1} min.",
                        "espera": espera}), 429

    estado, jwt = cocos.login(email, c.get("password") or "", codigo)
    if not estado["conectado"]:
        _anotar_fallo(email)
        return jsonify({"error": estado["detalle"]}), 401

    _INTENTOS.pop(email, None)
    return jsonify({"ok": True, "sobre": sesion.emitir(jwt),
                    "vence_en": sesion.DIA, **estado})


@bp.post("/broker/desconectar")
def broker_desconectar():
    cocos.desconectar()
    return jsonify({"ok": True})


@bp.post("/broker/borrar")
def broker_borrar():
    """Desconecta y elimina credenciales, sesión y clave guardada."""
    cocos.desconectar()
    vault.borrar_todo()
    return jsonify({"ok": True})


# ── Cocos: datos personales de la cuenta (solo lectura) ────────────────────────
# Cada endpoint devuelve lo crudo del broker o {"error": ...}. La app no
# reescribe la forma: es un mirador de lo que Cocos expone, para ver qué hay
# antes de construir nada encima.

@bp.get("/cocos/resumen")
def cocos_resumen():
    """Todo en una llamada: posiciones, variación del día, saldos, banco, perfil."""
    if not cocos.estado()["conectado"]:
        return jsonify({"conectado": False})
    return jsonify({
        "conectado": True,
        "posiciones": cocos.posiciones(),
        "dia": cocos.posiciones_dia(),
        "fondos": cocos.fondos_disponibles(),
        "bancos": cocos.cuentas_bancarias(),
        "perfil": cocos.mis_datos(),
    })


@bp.get("/cocos/posiciones")
def cocos_posiciones():
    return jsonify({"posiciones": cocos.posiciones(), "dia": cocos.posiciones_dia()})


@bp.get("/cocos/movimientos")
def cocos_movimientos():
    limite = min(int(request.args.get("limite", 40)), 100)
    offset = int(request.args.get("offset", 0))
    return jsonify(cocos.movimientos(limite, offset))


@bp.get("/cocos/fci")
def cocos_fci():
    """El seguimiento por fondo y, con él, el resultado ya cerrado en dólares."""
    t = cocos.fci_tracking()
    if t.get("error"):
        return jsonify(t)
    return jsonify({**t, "cartera": store.cartera_de_cuenta(t.get("cuenta")),
                    "carteras": store.nombres()})


@bp.post("/cocos/fci/resultados/importar")
def cocos_fci_resultados_importar():
    """Lleva el resultado de los FCI a las operaciones cerradas de una cartera.

    Un registro por fondo, marcado con su lote: volver a importar pisa lo que
    dejó la vez anterior y no duplica nada.
    """
    cartera = (request.json or {}).get("cartera", "").strip()
    if cartera not in store.nombres():
        return jsonify({"error": "Esa cartera no existe."}), 400

    t = cocos.fci_tracking()
    if t.get("error"):
        return jsonify(t), 502

    previa = store.cartera_de_cuenta(t.get("cuenta"))
    if previa and previa != cartera:
        return jsonify({"error": f"Esta cuenta ya está asociada a «{previa}». "
                                 "Desasociala antes de importarla en otra."}), 409

    r = store.agregar_realizado(cartera, t["trades"], lote=cocos.LOTE_RESULTADOS_FCI)
    if t.get("cuenta"):
        store.asociar_cuenta(t["cuenta"], cartera)
    return jsonify({"ok": True, "cartera": cartera, "total_usd": t["total_usd"],
                    "tickers": [x["ticker"] for x in t["trades"]], **r})


@bp.get("/cocos/fci/tenencias")
def cocos_fci_tenencias():
    """Las participaciones en FCI como lotes, y a qué cartera va esta cuenta."""
    t = cocos.tenencias_fci()
    if t.get("error"):
        return jsonify(t)
    return jsonify({**t, "cartera": store.cartera_de_cuenta(t.get("cuenta")),
                    "carteras": store.nombres()})


@bp.post("/cocos/fci/importar")
def cocos_fci_importar():
    """Lleva las participaciones en FCI a una cartera, pisando la importación
    anterior. Recuerda la cuenta para no ofrecer después la cartera equivocada.
    """
    cartera = (request.json or {}).get("cartera", "").strip()
    if cartera not in store.nombres():
        return jsonify({"error": "Esa cartera no existe."}), 400

    t = cocos.tenencias_fci()
    if t.get("error"):
        return jsonify(t), 502
    # Sin fondos en la cuenta la importación igual corre, y limpia: si rescataste
    # todo, la cartera tiene que quedar sin el fondo. Rechazarlo acá dejaba una
    # tenencia fantasma que ya no existe en el broker.

    previa = store.cartera_de_cuenta(t.get("cuenta"))
    if previa and previa != cartera:
        return jsonify({"error": f"Esta cuenta ya está asociada a «{previa}». "
                                 "Desasociala antes de importarla en otra."}), 409

    r = store.reemplazar_source(cartera, sources.SOURCE_FCI, t["lotes"])
    if t.get("cuenta"):
        store.asociar_cuenta(t["cuenta"], cartera)
    return jsonify({"ok": True, "cartera": cartera, "cuenta_nueva": not previa,
                    "tickers": [l["ticker"] for l in t["lotes"]], **r})


# ── Compras y ventas: dos importaciones, cada una con su botón ───────────────
# Separadas a propósito. La foto de lo que tenés y la historia de lo que hiciste
# son decisiones distintas: alguien puede querer la cartera del broker sin pisar
# su P&L cargado a mano, o al revés.

def _especies_d_del_usuario() -> set:
    """Instrumentos que el usuario ya anota en su tramo en dólares.

    Se mira todo lo suyo, abierto y cerrado: si en alguna cartera figura
    `EWZD.BA`, entonces para él EWZ se anota así y no de otra forma.
    """
    from core.data.symbols import base_symbol, is_d_variant, strip_ba

    vistos = set()
    for nombre in store.nombres():
        vistos |= {p["ticker"] for p in store.cargar(nombre)}
        vistos |= {t["ticker"] for t in store.cargar_realizado(nombre)}
    return {base_symbol(strip_ba(t)) for t in vistos if is_d_variant(strip_ba(t))}


def _operaciones():
    return cocos.operaciones(_especies_d_del_usuario())


@bp.get("/cocos/operaciones")
def cocos_operaciones():
    """Lo que el historial dice que tenés abierto y lo que ya cerraste."""
    r = _operaciones()
    if r.get("error"):
        return jsonify(r)
    destino = store.cartera_de_cuenta(r.get("cuenta"))
    return jsonify({**r, "cartera": destino, "carteras": store.nombres(),
                    "cerrados": [{**c, "clave": cocos.clave_operacion(c)}
                                 for c in r["cerrados"]],
                    "ya_cargados": _ya_cargados(destino, r["abiertos"]),
                    "ya_cerradas": _ya_cerradas(destino, r["cerrados"])})


def _ya_cerradas(cartera: str, cerrados: list) -> list:
    """Operaciones que la cartera ya tiene cargadas y volverían a entrar.

    El deduplicado por clave no las ve: la misma venta cargada a mano desde
    Yahoo y traída del broker tiene otros precios —una convierte de una forma y
    la otra con el MEP— así que entran las dos y el resultado se cuenta doble.
    Se comparan por papel, fecha de venta y cantidad, que es lo que identifica
    la operación más allá de con qué número se la anotó.
    """
    if not cartera:
        return []
    from core.data.symbols import base_symbol, strip_ba

    def clave(t):
        return (base_symbol(strip_ba(t["ticker"])), t["sell_date"], round(float(t["qty"]), 4))

    previas = {clave(t): t["ticker"] for t in store.cargar_realizado(cartera)
               if (t.get("lote") or "") != cocos.LOTE_OPERACIONES}
    choques = []
    for c in cerrados:
        ya = previas.get(clave(c))
        if ya:
            choques.append({"ticker": c["ticker"], "como_lo_tenes": ya,
                            "clave": cocos.clave_operacion(c),
                            "sell_date": c["sell_date"], "qty": c["qty"]})
    return choques


def _ya_cargados(cartera: str, abiertos: list) -> list:
    """Tickers que la cartera ya tiene cargados a mano y volverían a entrar.

    Importar no pisa lo cargado a mano —eso es deliberado, nadie quiere perder
    lo que anotó— pero entonces el mismo papel queda dos veces y la cartera vale
    el doble. Se avisa antes, que es cuando sirve.
    """
    if not cartera:
        return []
    del_broker = {a["ticker"] for a in abiertos}
    return sorted({p["ticker"] for p in store.cargar(cartera)
                   if p["ticker"] in del_broker
                   and (p.get("lote") or "") != cocos.LOTE_OPERACIONES})


def _cartera_para(cuenta):
    """La cartera pedida, si existe y si esta cuenta no está atada a otra."""
    cartera = (request.json or {}).get("cartera", "").strip()
    if cartera not in store.nombres():
        return None, (jsonify({"error": "Esa cartera no existe."}), 400)
    previa = store.cartera_de_cuenta(cuenta)
    if previa and previa != cartera:
        return None, (jsonify({"error": f"Esta cuenta ya está asociada a «{previa}». "
                                        "Desasociala antes de importarla en otra."}), 409)
    return cartera, None


@bp.post("/cocos/operaciones/posiciones")
def cocos_importar_posiciones():
    """Lleva a la cartera lo que quedó abierto después de netear el historial."""
    r = _operaciones()
    if r.get("error"):
        return jsonify(r), 502
    cartera, error = _cartera_para(r.get("cuenta"))
    if error:
        return error

    van = r["abiertos"]
    res = store.reemplazar_lote(cartera, cocos.LOTE_OPERACIONES, van)
    if r.get("cuenta"):
        store.asociar_cuenta(r["cuenta"], cartera)
    return jsonify({"ok": True, "cartera": cartera, **res,
                    "tickers": sorted({x["ticker"] for x in van})})


@bp.post("/cocos/operaciones/cerradas")
def cocos_importar_cerradas():
    """Lleva al P&L realizado las compras que ya tienen su venta."""
    r = _operaciones()
    if r.get("error"):
        return jsonify(r), 502
    cartera, error = _cartera_para(r.get("cuenta"))
    if error:
        return error

    # Sin `solo` van todas; con `solo`, las que quedaron tildadas.
    solo = (request.json or {}).get("solo")
    van = (r["cerrados"] if solo is None
           else [c for c in r["cerrados"] if cocos.clave_operacion(c) in set(solo)])
    res = store.agregar_realizado(cartera, van, lote=cocos.LOTE_OPERACIONES)
    if r.get("cuenta"):
        store.asociar_cuenta(r["cuenta"], cartera)
    return jsonify({"ok": True, "cartera": cartera, **res,
                    "tickers": sorted({x["ticker"] for x in van})})


@bp.get("/cocos/fondos")
def cocos_fondos():
    return jsonify(cocos.fondos_disponibles())


@bp.get("/cocos/datos")
def cocos_datos():
    return jsonify(cocos.mis_datos())


@bp.get("/cocos/bancos")
def cocos_bancos():
    return jsonify({"cuentas": cocos.cuentas_bancarias()})


# ── InvIU ─────────────────────────────────────────────────────────────────────
# El login exige un navegador de verdad (reCAPTCHA), no hay vault de
# credenciales acá: no hace falta contraseña guardada, solo la sesión
# (idToken/refreshToken). Ver core/broker/inviu.py.
#
# Las posiciones y los cerrados salen de `movimientos()` (el historial
# completo del comitente), no de `operaciones()`: esta última solo mostró las
# últimas operaciones de la cuenta de prueba —parece ser otro canal, no el
# libro completo— y hubiera dejado afuera todo lo operado por el asesor antes
# de eso. `movimientos()` sí trae BUY_OPERATION/SELL_OPERATION desde el
# principio, igual que el `_historial_completo()` de Cocos.

@bp.get("/inviu/estado")
def inviu_estado():
    return jsonify({**inviu.estado(), "vault_cargado": vault.existe(inviu.BROKER)})


@bp.post("/inviu/web/sesion")
def inviu_web_sesion():
    """Recibe los tokens que ya sacaste conectando InvIU en tu máquina local
    (nunca la contraseña — esa no sale de ahí) y los devuelve envueltos en un
    sobre firmado, como el que ya usa Cocos. El servidor no los guarda en
    ningún lado, ni siquiera más allá de esta respuesta: se validan pidiendo
    los datos de la cuenta una vez y se sueltan enseguida.
    """
    if not sesion.modo_web():
        return jsonify({"error": "Esto es solo para el modo web; en local ya estás conectado."}), 400

    body = request.json or {}
    jwt = {"idToken": (body.get("idToken") or "").strip(),
           "refreshToken": (body.get("refreshToken") or "").strip()}
    if not jwt["idToken"] or not jwt["refreshToken"]:
        return jsonify({"error": "Faltan los tokens."}), 400

    estado, renovado = inviu.restaurar(jwt)
    inviu.olvidar()
    if not estado["conectado"]:
        return jsonify({"error": estado["detalle"]}), 401
    # Si InvIU rotó el refreshToken al validarlo, el sobre tiene que llevar
    # los tokens nuevos: los originales ya habrían quedado muertos.
    return jsonify({"ok": True, **estado, "sobre": sesion.emitir(renovado or jwt)})


@bp.get("/inviu/cartera")
def inviu_cartera():
    """Espejo de lo que InvIU expone hoy: tenencias con PPC y P&L en vivo,
    tal como los da el broker (ya en ARS y en USD, cada uno por separado)."""
    return jsonify(inviu.cartera())


@bp.get("/inviu/titular")
def inviu_titular():
    """Quién es el comitente, qué número de cuenta tiene y quién lo gestiona.

    Achicado a propósito: `user_info()` trae domicilio, fecha de nacimiento,
    documento y más, que no hace falta mostrar acá.
    """
    info = inviu.user_info()
    if isinstance(info, dict) and info.get("error"):
        return jsonify(info)
    cuenta = (info.get("accounts") or [{}])[0]
    asesor = info.get("advisor") or {}
    return jsonify({
        "titular": f"{info.get('firstName', '')} {info.get('lastName', '')}".strip(),
        "comitente": cuenta.get("externalId"),
        "custodio": (cuenta.get("custodian") or {}).get("friendlyName"),
        "perfil_riesgo": cuenta.get("riskProfile"),
        "gestor": f"{asesor.get('firstName', '')} {asesor.get('lastName', '')}".strip() or asesor.get("alias"),
        "gestor_alias": asesor.get("alias"),
        "gestor_email": asesor.get("email"),
        "mandato_discrecional": asesor.get("discretionaryMandate"),
    })


@bp.post("/inviu/conectar")
def inviu_conectar():
    """No bloquea: si hace falta navegador, lo abre en un hilo aparte y hay
    que sondear `/inviu/estado` hasta que `conectado` se resuelva."""
    api_key = vault.clave_guardada(inviu.BROKER)
    if not api_key:
        # No hay contraseña que cifrar —el login es por navegador—, así que
        # el vault solo envuelve la sesión y se crea con un relleno.
        api_key = vault.crear({"email": "-", "password": "-"}, inviu.BROKER)
    forzar = (request.json or {}).get("forzar_login", False)
    return jsonify(inviu.conectar_async(api_key, forzar))


@bp.post("/inviu/desconectar")
def inviu_desconectar():
    inviu.desconectar()
    return jsonify({"ok": True})


@bp.post("/inviu/borrar")
def inviu_borrar():
    inviu.desconectar()
    vault.borrar_todo(inviu.BROKER)
    return jsonify({"ok": True})


def _inviu_operaciones_procesadas():
    """Compras y ventas apareadas FIFO desde el historial de movimientos:
    abierto y cerrado, igual que `cocos.operaciones()` — mismo apareo, mismo
    motivo: esta cuenta rota bonos entre su clase en pesos y en dólares todo
    el tiempo (comprar AL30, vender AL30D más tarde), así que aparear por
    ticker crudo dejaba casi todo "abierto" para siempre — 52 posiciones
    abiertas contra las 9 reales que tiene la cuenta, verificado a mano.

    Por eso se apea por **bono subyacente** (`d_ticker`) y cada pata se
    convierte a USD con el MEP de SU fecha antes de aparear — igual que hace
    `cocos.operaciones()` con la misma estrategia. El resultado siempre está
    en dólares.

    "¿Es bono?" lo dice el propio movimiento (`asset.assetType == "bond"`),
    no la forma del ticker: `is_cocos_only()` es un patrón pensado para CSVs
    sin esa información y se queda corto acá —no reconoce YMCXO, TTCDO,
    IRCPO, VSCVO, BPOA8, ninguno matchea `_parece_on`— y esas posiciones
    quedaban sin aparear contra su clase en dólares. InvIU ya lo sabe con
    certeza; no hace falta adivinar.

    El mismo rulo pasa con los CEDEARs, no solo con los bonos: EWZ comprado
    como EWZD y vendido como EWZ, QQQ repartido entre QQQD y QQQ. Por eso
    `d_ticker` se aplica siempre, bono o no —es lo que ya hace `base_symbol`/
    `d_ticker` con KO/KOD, GLD/GLDD—; lo que cambia según el tipo es el
    sufijo de mercado: un CEDEAR sigue cotizando en BYMA (`.BA`) aunque
    liquide en dólares, un bono en su tramo dólar no está en BYMA para esta
    app y va a Cocos sin sufijo, igual que en `cocos.operaciones()`.

    Las cauciones no pasan por acá —`movimientos()` las trae con otros tipos
    (REPURCHASE_AGREEMENT_BORROWING/PLACEMENT/EXPIRATION), no BUY_OPERATION/
    SELL_OPERATION— así que quedan afuera solas, sin filtro extra.
    """
    from core.data import mep
    from core.data.symbols import d_ticker
    from core.io.csv_yahoo import _netear_fifo

    r = inviu.movimientos()
    if isinstance(r, dict) and r.get("error"):
        return r
    movs = (r or {}).get("results", [])

    ops, es_bono = {}, {}
    for orden, m in enumerate(reversed(movs)):    # más viejo primero
        if m.get("type") not in ("BUY_OPERATION", "SELL_OPERATION"):
            continue
        asset = m.get("asset") or {}
        instrumento = (asset.get("ticker") or "").upper().strip()
        cantidad = abs(m.get("quantity") or 0)
        importe = abs((m.get("amount") or {}).get("amount") or 0)
        fecha = m.get("concertationDate")
        moneda = ((m.get("amount") or {}).get("currency") or "ARS").upper()
        if not instrumento or not cantidad or not importe or not fecha:
            continue
        usd = importe if moneda != "ARS" else mep.a_usd(importe, fecha)
        if not usd:
            continue
        clave = d_ticker(instrumento)
        es_bono[clave] = asset.get("assetType") == "bond"
        compras, ventas = ops.setdefault(clave, ([], []))
        (compras if m["type"] == "BUY_OPERATION" else ventas).append(
            {"fecha": fecha, "orden": orden, "precio": usd / cantidad,
             "qty": cantidad, "comision": 0.0})

    abiertos, cerrados = [], []
    for clave, (compras, ventas) in ops.items():
        bono = es_bono.get(clave, False)
        ticker = clave if bono else f"{clave}.BA"
        fuente = "cocos" if bono else ""
        quedan, cierres = _netear_fifo(compras, ventas)
        for c in quedan:
            abiertos.append({
                "ticker": ticker, "buy_date": c["fecha"], "buy_price": round(c["precio"], 6),
                "qty": round(c["qty"], 6), "commissions": 0.0, "currency": "USD",
                "source": fuente, "notes": f"InvIU · {clave}",
            })
        for c in cierres:
            cerrados.append({
                "ticker": ticker, "buy_date": c["buy_date"], "sell_date": c["sell_date"],
                "buy_price": round(c["buy_price"], 6), "sell_price": round(c["sell_price"], 6),
                "qty": c["qty"], "buy_comm": 0.0, "sell_comm": 0.0, "moneda": "USD",
                "pnl": round(c["qty"] * (c["sell_price"] - c["buy_price"]), 4),
            })
    abiertos.sort(key=lambda x: (x["ticker"], x["buy_date"]))
    cerrados.sort(key=lambda x: x["sell_date"], reverse=True)
    c = inviu._c()
    return {"abiertos": abiertos, "cerrados": cerrados, "cuenta": c.account_id if c else None}


def _inviu_ya_cargados(cartera: str, abiertos: list) -> list:
    """Igual que `_ya_cargados`, para el lote de InvIU."""
    if not cartera:
        return []
    del_broker = {a["ticker"] for a in abiertos}
    return sorted({p["ticker"] for p in store.cargar(cartera)
                   if p["ticker"] in del_broker
                   and (p.get("lote") or "") != inviu.LOTE_OPERACIONES})


def _inviu_ya_cerradas(cartera: str, cerrados: list) -> list:
    """Igual que `_ya_cerradas`, para el lote de InvIU."""
    if not cartera:
        return []
    from core.data.symbols import base_symbol, strip_ba

    def clave(t):
        return (base_symbol(strip_ba(t["ticker"])), t["sell_date"], round(float(t["qty"]), 4))

    previas = {clave(t): t["ticker"] for t in store.cargar_realizado(cartera)
               if (t.get("lote") or "") != inviu.LOTE_OPERACIONES}
    choques = []
    for c in cerrados:
        ya = previas.get(clave(c))
        if ya:
            choques.append({"ticker": c["ticker"], "como_lo_tenes": ya,
                            "clave": inviu.clave_operacion(c),
                            "sell_date": c["sell_date"], "qty": c["qty"]})
    return choques


@bp.get("/inviu/operaciones")
def inviu_operaciones():
    """Lo que el historial dice que tenés abierto y lo que ya cerraste."""
    r = _inviu_operaciones_procesadas()
    if r.get("error"):
        return jsonify(r)
    destino = store.cartera_de_cuenta(r.get("cuenta"))
    return jsonify({**r, "cartera": destino, "carteras": store.nombres(),
                    "cerrados": [{**c, "clave": inviu.clave_operacion(c)}
                                 for c in r["cerrados"]],
                    "ya_cargados": _inviu_ya_cargados(destino, r["abiertos"]),
                    "ya_cerradas": _inviu_ya_cerradas(destino, r["cerrados"])})


@bp.post("/inviu/operaciones/posiciones")
def inviu_importar_posiciones():
    """Lleva a la cartera lo que quedó abierto después de netear el historial."""
    r = _inviu_operaciones_procesadas()
    if r.get("error"):
        return jsonify(r), 502
    cartera, error = _cartera_para(r.get("cuenta"))
    if error:
        return error

    van = r["abiertos"]
    res = store.reemplazar_lote(cartera, inviu.LOTE_OPERACIONES, van)
    if r.get("cuenta"):
        store.asociar_cuenta(r["cuenta"], cartera)
    return jsonify({"ok": True, "cartera": cartera, **res,
                    "tickers": sorted({x["ticker"] for x in van})})


@bp.post("/inviu/operaciones/cerradas")
def inviu_importar_cerradas():
    """Lleva al P&L realizado las compras que ya tienen su venta."""
    r = _inviu_operaciones_procesadas()
    if r.get("error"):
        return jsonify(r), 502
    cartera, error = _cartera_para(r.get("cuenta"))
    if error:
        return error

    solo = (request.json or {}).get("solo")
    van = (r["cerrados"] if solo is None
           else [c for c in r["cerrados"] if inviu.clave_operacion(c) in set(solo)])
    res = store.agregar_realizado(cartera, van, lote=inviu.LOTE_OPERACIONES)
    if r.get("cuenta"):
        store.asociar_cuenta(r["cuenta"], cartera)
    return jsonify({"ok": True, "cartera": cartera, **res,
                    "tickers": sorted({x["ticker"] for x in van})})


def _inviu_rentas() -> dict:
    """Depósitos, retiros, amortizaciones y rentas (solo la pata en USD) del
    historial. La pata en ARS de una renta no es plata real —viene negativa,
    es un ajuste técnico de Caja de Valores sobre la clase peso del mismo
    bono dual, no un movimiento de caja— y no entra acá. Ver
    inviu-integration/MAPEO_A_PORTFOLIO.md."""
    r = inviu.movimientos()
    if isinstance(r, dict) and r.get("error"):
        return r
    salida = []
    for m in (r or {}).get("results", []):
        tipo = m.get("type")
        moneda = (m.get("amount") or {}).get("currency")
        monto = (m.get("amount") or {}).get("amount") or 0
        if tipo == "AMORTIZATION":
            categoria = "Amortización"
        elif tipo in ("INCOME", "DIVIDEND") and moneda == "USD":
            categoria = "Renta"
        elif tipo == "CASH_IN":
            categoria = "Depósito"
        elif tipo == "CASH_OUT":
            categoria = "Retiro"
        else:
            continue
        salida.append({
            "fecha": m.get("concertationDate"), "tipo": categoria,
            "ticker": (m.get("asset") or {}).get("ticker") or "CASH",
            "moneda": moneda, "monto": monto,
            "descripcion": m.get("description"), "movementId": m.get("movementId"),
        })
    salida.sort(key=lambda x: x["fecha"], reverse=True)
    return {"movimientos": salida}


@bp.get("/inviu/rentas")
def inviu_rentas():
    """Depósitos/retiros (informativo) + rentas/amortizaciones (importables)."""
    return jsonify(_inviu_rentas())


@bp.get("/inviu/evolucion")
def inviu_evolucion():
    """TIR real de la cuenta según InvIU (`summary.tir`/`annualTir`) — un
    control cruzado contra la TIR que calcula la propia app con MEP por
    fecha. Si difieren mucho, hay algo para investigar de un lado o del otro.
    `desde` por defecto cubre toda la vida de la cuenta: no hay endpoint para
    preguntar "cuándo se abrió", así que se manda una fecha bien vieja y
    InvIU devuelve lo que realmente tiene."""
    from datetime import date
    desde = request.args.get("desde", "2015-01-01")
    hasta = request.args.get("hasta", date.today().isoformat())
    moneda = request.args.get("moneda", "USD")
    return jsonify(inviu.evolucion_patrimonio(desde, hasta, moneda))


@bp.get("/inviu/flujo-proyectado")
def inviu_flujo_proyectado():
    """Próximos cobros de renta/amortización de los bonos en cartera, más
    duration/DV01/convexidad agregados que ya calcula InvIU."""
    return jsonify(inviu.flujo_proyectado())


def _tasas_caucion() -> dict:
    """La TNA de la caución más reciente de cada lado, si `operaciones()` la
    trae. Confirmado contra el boleto real (descargado desde Movimientos):
    la fila "Apertura tomadora futuro" del 18/09 dice "Tasa 2,49 %", y acá
    `price.amount` daba 2.5 para esa misma operación — es la TNA, no un
    precio."""
    ops = inviu.operaciones()
    if not isinstance(ops, list):
        return {}
    tasas = {}
    for op in reversed(ops):    # operaciones() viene del más viejo al más nuevo
        if op.get("assetType") != "REPURCHASE_AGREEMENT":
            continue
        lado = "tomadora" if op.get("operationType") == "BORROWING" else "colocadora"
        if lado not in tasas:
            tasas[lado] = (op.get("price") or {}).get("amount")
    return tasas


def _resultado_neto_caucion(movs: list) -> dict:
    """Interés pagado (tomadora) contra interés cobrado (colocadora), en todo
    el historial — para saber si el carry trade de verdad rindió o no.

    La lógica: lo que entra al tomar (BORROWING, positivo) menos lo que se
    devuelve al vencer (EXPIRATION del ticker "CT") es el costo real en
    dólares; lo que sale al colocar (PLACEMENT, negativo) más lo que se cobra
    al vencer (EXPIRATION del ticker "CC") es la ganancia real en pesos. Cada
    pata en pesos se pasa a dólares con el MEP de **su** fecha — sumar pesos
    de fechas distintas sin convertir sería sumar cosas que valen distinto.

    Junta también la primera y la última fecha de cada lado, para poder
    armar un registro de cerradas con `buy_date`/`sell_date` reales — ver
    `_caucion_trades`.
    """
    from core.data import mep as mep_mod

    neto = {"tomadora_usd": 0.0, "tomadora_cargos_usd": 0.0, "colocadora_usd": 0.0}
    fechas = {"tomadora": [], "colocadora": []}
    for m in movs:
        tipo = m.get("type")
        ticker = (m.get("asset") or {}).get("ticker")
        amt = m.get("amount") or {}
        monto, moneda, fecha = amt.get("amount") or 0, amt.get("currency"), m.get("concertationDate")
        if tipo == "REPURCHASE_AGREEMENT_BORROWING":
            neto["tomadora_usd"] += monto
            fechas["tomadora"].append(fecha)
        elif tipo == "REVERSE_REPURCHASE_AGREEMENT_PLACEMENT":
            neto["colocadora_usd"] += mep_mod.a_usd(monto, fecha) or 0
            fechas["colocadora"].append(fecha)
        elif tipo == "EXPIRATION" and ticker == "CT":
            if moneda == "USD":
                neto["tomadora_usd"] += monto
            else:
                neto["tomadora_cargos_usd"] += mep_mod.a_usd(monto, fecha) or 0
            fechas["tomadora"].append(fecha)
        elif tipo == "EXPIRATION" and ticker == "CC":
            neto["colocadora_usd"] += mep_mod.a_usd(monto, fecha) or 0
            fechas["colocadora"].append(fecha)

    neto = {k: round(v, 2) for k, v in neto.items()}
    neto["total_usd"] = round(sum(neto.values()), 2)
    neto["_fechas"] = {lado: (min(fs), max(fs)) for lado, fs in fechas.items() if fs}
    return neto


def _caucion_trades(movs: list) -> list:
    """El resultado neto de cada lado, como un registro de cerrado más —
    listo para `store.agregar_realizado`. No hay un "trade" real por
    posición para anotar (son cientos de rollovers), así que cada lado entra
    como un único cerrado agregado, igual que hace `cocos._resultados_realizados`
    con el barrido diario de FCI."""
    neto = _resultado_neto_caucion(movs)
    fechas = neto.pop("_fechas", {})
    trades = []
    if "tomadora" in fechas:
        pnl = round(neto["tomadora_usd"] + neto["tomadora_cargos_usd"], 4)
        desde, hasta = fechas["tomadora"]
        trades.append({
            "ticker": "CAUCIONT", "buy_date": desde, "sell_date": hasta,
            "buy_price": 0.0, "sell_price": pnl, "qty": 1,
            "buy_comm": 0.0, "sell_comm": 0.0, "moneda": "USD",
            "pnl": pnl, "tipo": "caucion",
        })
    if "colocadora" in fechas:
        pnl = round(neto["colocadora_usd"], 4)
        desde, hasta = fechas["colocadora"]
        trades.append({
            "ticker": "CAUCIONC", "buy_date": desde, "sell_date": hasta,
            "buy_price": 0.0, "sell_price": pnl, "qty": 1,
            "buy_comm": 0.0, "sell_comm": 0.0, "moneda": "USD",
            "pnl": pnl, "tipo": "caucion",
        })
    return trades


def _inviu_caucion() -> dict:
    """La caución tomadora/colocadora, **solo si sigue vigente hoy**, más el
    resultado neto acumulado de todo el historial.

    Cada apertura ya trae reservada su propia devolución futura (el boleto
    real lo muestra como dos patas de una misma operación: "contado" hoy,
    "futuro" al vencimiento) — así que "¿sigue abierta?" no es "¿es la más
    reciente?", es "¿su vencimiento todavía no llegó?". La tomadora rueda
    todos los días hábiles y por eso casi siempre está vigente; la colocadora
    de esta cuenta liquida en el día y su última (14/09) ya venció, así que
    hoy no hay ninguna colocadora abierta — y no hay que mostrar una vieja
    como si lo estuviera.
    """
    from datetime import date

    r = inviu.movimientos()
    if isinstance(r, dict) and r.get("error"):
        return r
    movs = (r or {}).get("results", [])
    tasas = _tasas_caucion()
    hoy = date.today().isoformat()

    def _vigente(tipo_apertura, ticker_vencimiento):
        lado = "tomadora" if tipo_apertura == "REPURCHASE_AGREEMENT_BORROWING" else "colocadora"
        vencimiento = next((x for x in movs if x["type"] == "EXPIRATION"
                            and (x.get("asset") or {}).get("ticker") == ticker_vencimiento), None)
        if not vencimiento or (vencimiento.get("liquidationDate") or "") < hoy:
            return None
        apertura = next((x for x in movs if x["type"] == tipo_apertura
                         and x.get("concertationDate") == vencimiento.get("concertationDate")), None)
        if not apertura:
            return None
        return {
            "monto": abs((apertura.get("amount") or {}).get("amount") or 0),
            "moneda": (apertura.get("amount") or {}).get("currency"),
            "desde": apertura.get("concertationDate"),
            "vence": vencimiento.get("liquidationDate"),
            "tasa_tna": tasas.get(lado),
        }

    neto = _resultado_neto_caucion(movs)
    neto.pop("_fechas", None)
    return {"tomadora": _vigente("REPURCHASE_AGREEMENT_BORROWING", "CT"),
            "colocadora": _vigente("REVERSE_REPURCHASE_AGREEMENT_PLACEMENT", "CC"),
            "resultado_neto": neto}


@bp.get("/inviu/caucion")
def inviu_caucion():
    return jsonify(_inviu_caucion())


@bp.post("/inviu/caucion/importar")
def inviu_importar_caucion():
    """Los resultados netos de cauciones tomadora/colocadora al P&L
    realizado, uno por lado (ver `_caucion_trades`)."""
    r = inviu.movimientos()
    if isinstance(r, dict) and r.get("error"):
        return jsonify(r), 502
    trades = _caucion_trades((r or {}).get("results", []))
    if not trades:
        return jsonify({"error": "No hay cauciones en el historial."}), 400

    c = inviu._c()
    cartera, error = _cartera_para(c.account_id if c else None)
    if error:
        return error

    res = store.agregar_realizado(cartera, trades, lote=inviu.LOTE_CAUCION)
    if c and c.account_id:
        store.asociar_cuenta(c.account_id, cartera)
    return jsonify({"ok": True, "cartera": cartera, **res,
                    "tickers": [t["ticker"] for t in trades]})


@bp.post("/inviu/rentas/importar")
def inviu_importar_rentas():
    """Rentas y amortizaciones al P&L realizado. Depósitos y retiros no entran
    acá — son aportes de capital, no resultado (ver MAPEO_A_PORTFOLIO.md)."""
    r = _inviu_rentas()
    if r.get("error"):
        return jsonify(r), 502

    c = inviu._c()
    cuenta = c.account_id if c else None
    cartera, error = _cartera_para(cuenta)
    if error:
        return error

    trades = [{
        "ticker": m["ticker"], "buy_date": m["fecha"], "sell_date": m["fecha"],
        "buy_price": 0.0, "sell_price": round(m["monto"], 6), "qty": 1,
        "buy_comm": 0.0, "sell_comm": 0.0, "moneda": m["moneda"],
        "pnl": round(m["monto"], 4), "tipo": "renta",
    } for m in r["movimientos"] if m["tipo"] in ("Renta", "Amortización")]

    res = store.agregar_realizado(cartera, trades, lote=inviu.LOTE_RENTAS)
    if cuenta:
        store.asociar_cuenta(cuenta, cartera)
    return jsonify({"ok": True, "cartera": cartera, **res,
                    "tickers": sorted({t["ticker"] for t in trades})})


# ── Caché ─────────────────────────────────────────────────────────────────────

@bp.get("/cache")
def cache_estado():
    return jsonify(cache.estadisticas())


@bp.delete("/cache/<ticker>")
def cache_borrar(ticker):
    return jsonify({"ok": True, "filas_borradas": cache.borrar_ticker(ticker)})


@bp.delete("/cache/respuestas")
def cache_respuestas():
    return jsonify({"ok": True, "borradas": cache.limpiar_respuestas()})
