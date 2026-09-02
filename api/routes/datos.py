"""Datos transversales: MEP, validación de tickers, comparación y conectores."""

from flask import Blueprint, Response, jsonify, request

from core.broker import cocos, vault
from core.data import cache, connectors, fmp, mep, sources
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


@bp.post("/broker/vault")
def broker_vault():
    """Cifra las credenciales y devuelve la API key. Se muestra UNA sola vez."""
    c = request.json or {}
    try:
        api_key = vault.crear({"email": c.get("email", ""),
                               "password": c.get("password", ""),
                               "totp_secret_key": c.get("totp_secret_key", "")})
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"ok": True, "api_key": api_key,
                    "aviso": "Guardá esta clave: es lo único que abre el vault y "
                             "no se puede recuperar."})


@bp.post("/broker/conectar")
def broker_conectar():
    c = request.json or {}
    if not c.get("api_key"):
        return jsonify({"error": "Falta la API key del vault."}), 400
    return jsonify(cocos.conectar(c["api_key"], c.get("forzar_login", False)))


@bp.post("/broker/desconectar")
def broker_desconectar():
    cocos.desconectar()
    return jsonify({"ok": True})


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
