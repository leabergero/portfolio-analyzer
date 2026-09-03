"""Datos transversales: MEP, validación de tickers, comparación y conectores."""

from flask import Blueprint, Response, jsonify, request

from core.broker import cocos, vault
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
    serie = sources.precios_usd(ticker)
    if serie.empty:
        return jsonify({"ticker": ticker, "valido": False,
                        "detalle": "No se encontraron precios en ninguna fuente."})
    return jsonify({
        "ticker": ticker, "valido": True,
        "moneda": sources.ticker_currency(ticker),
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
    nombres = (request.json or {}).get("carteras", [])
    if len(nombres) < 2:
        return jsonify({"error": "Hacen falta al menos dos carteras."}), 400
    carteras = {n: store.cargar(n) for n in nombres if store.cargar(n)}
    if len(carteras) < 2:
        return jsonify({"error": "Al menos dos de esas carteras no existen o están vacías."}), 400
    return jsonify(comparacion.comparar(
        carteras, (request.json or {}).get("benchmark", "SP500")))


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
    return jsonify({**cocos.estado(), "vault_cargado": vault.existe()})


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
    return jsonify(cocos.fci_tracking())


@bp.get("/cocos/fondos")
def cocos_fondos():
    return jsonify(cocos.fondos_disponibles())


@bp.get("/cocos/datos")
def cocos_datos():
    return jsonify(cocos.mis_datos())


@bp.get("/cocos/bancos")
def cocos_bancos():
    return jsonify({"cuentas": cocos.cuentas_bancarias()})


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
