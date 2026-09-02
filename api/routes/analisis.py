"""
analisis.py — Modo 1: una cartera en profundidad.

Dos formas de pedir lo mismo, según haga falta:

  · `POST /api/analisis/<cartera>` dispara **todos** los modelos en paralelo y
    devuelve un `run_id`; el frontend consulta el estado y va pintando cada
    panel cuando llega. Es lo que usa la pantalla completa.
  · Los endpoints sueltos (`/riesgo`, `/markowitz`, …) calculan uno solo, en el
    momento. Sirven para recalcular una pestaña cuando el usuario cambia un
    parámetro —el benchmark, el horizonte del Monte Carlo— sin rehacer todo.
"""

from flask import Blueprint, jsonify, request

from api import jobs
from core.io import store
from core.models import (blacklitterman, bonds, capm, composicion, markowitz,
                         momentum, montecarlo, portfolio, regimenes, risk,
                         targets)

bp = Blueprint("analisis", __name__, url_prefix="/api")


def _posiciones(nombre):
    p = store.cargar(nombre)
    return p if p else None


def _falta(nombre):
    return jsonify({"error": f'La cartera "{nombre}" no existe o está vacía.'}), 404


# ── Análisis completo, en paralelo ────────────────────────────────────────────

@bp.post("/analisis/<nombre>")
def lanzar(nombre):
    pos = _posiciones(nombre)
    if not pos:
        return _falta(nombre)
    modelos = (request.json or {}).get("modelos")
    return jsonify({"run_id": jobs.lanzar(nombre, pos, modelos),
                    "modelos": list(jobs.MODELOS)})


@bp.get("/analisis/<nombre>/<run_id>")
def consultar(nombre, run_id):
    e = jobs.estado(run_id)
    return (jsonify(e) if e else
            (jsonify({"error": "Esa corrida no existe o ya se descartó."}), 404))


# ── Modelos sueltos ───────────────────────────────────────────────────────────

def _simple(nombre, fn, *args, **kwargs):
    pos = _posiciones(nombre)
    if not pos:
        return _falta(nombre)
    return jsonify(fn(pos, *args, **kwargs))


@bp.get("/posicion/<nombre>")
def posicion(nombre):
    return _simple(nombre, portfolio.valuar)


@bp.get("/composicion/<nombre>")
def comp(nombre):
    return _simple(nombre, composicion.analizar)


@bp.get("/riesgo/<nombre>")
def riesgo(nombre):
    return _simple(nombre, risk.analizar, request.args.get("benchmark", "SP500"))


@bp.get("/stress/<nombre>")
def stress(nombre):
    return _simple(nombre, risk.stress_test)


@bp.get("/markowitz/<nombre>")
def mk(nombre):
    cap = request.args.get("cap", type=float)
    return _simple(nombre, markowitz.optimizar,
                   request.args.get("benchmark", "SP500"), cap)


@bp.get("/montecarlo/<nombre>")
def mc(nombre):
    return _simple(nombre, montecarlo.simular,
                   request.args.get("horizonte", 252, type=int),
                   request.args.get("simulaciones", 10000, type=int),
                   request.args.get("motor", "t"))


@bp.get("/montecarlo/<nombre>/motores")
def mc_motores(nombre):
    """Los tres motores lado a lado: cuánto cambia el supuesto de distribución."""
    return _simple(nombre, montecarlo.comparar_motores,
                   request.args.get("horizonte", 252, type=int))


@bp.get("/capm/<nombre>")
def capm_(nombre):
    return _simple(nombre, capm.analizar, request.args.get("benchmark", "SP500"))


@bp.get("/capm/<nombre>/benchmarks")
def capm_todos(nombre):
    """Los tres índices con su R²: cuál es el comparable legítimo."""
    return _simple(nombre, capm.comparar_benchmarks)


@bp.get("/momentum/<nombre>")
def mom(nombre):
    return _simple(nombre, momentum.analizar)


@bp.get("/objetivos/<nombre>")
def objetivos(nombre):
    return _simple(nombre, targets.analizar)


@bp.get("/regimenes/<nombre>")
def regs(nombre):
    return _simple(nombre, regimenes.analizar)


@bp.get("/bonos/<nombre>")
def bonos(nombre):
    """Duración, DV01 y convexidad de la parte de renta fija."""
    return _simple(nombre, bonds.riesgo_tasa_cartera)


@bp.get("/bonos/curva")
def curva():
    """Curva de rendimientos. precios: {"AL30": 68.0, ...} por 100 residuales."""
    precios = request.args.to_dict()
    try:
        precios = {k: float(v) for k, v in precios.items()}
    except ValueError:
        return jsonify({"error": "Los precios tienen que ser números."}), 400
    return jsonify(bonds.curva(precios))


@bp.post("/blacklitterman/<nombre>")
def bl(nombre):
    pos = _posiciones(nombre)
    if not pos:
        return _falta(nombre)
    cuerpo = request.json or {}
    views = cuerpo.get("views")

    # Sin views explícitas se arman desde los precios objetivo, recortando la
    # confianza donde el momentum va en contra.
    if views is None and cuerpo.get("desde_objetivos"):
        views = blacklitterman.views_desde_objetivos(
            targets.analizar(pos), momentum.analizar(pos))

    return jsonify(blacklitterman.analizar(
        pos, views, cuerpo.get("benchmark", "SP500"), cuerpo.get("max_weight")))
