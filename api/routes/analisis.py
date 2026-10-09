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

from api import jobs, sim
from core.data import bonistas
from core.data.symbols import is_bond
from core.io import store
from core.models import (blacklitterman, bonds, capm, composicion, hrp, markowitz,
                         momentum, montecarlo, portfolio, regimenes, risk,
                         targets)

bp = Blueprint("analisis", __name__, url_prefix="/api")


def _posiciones(nombre):
    """Las posiciones de la cartera, con la simulación puesta si la hay.

    Único embudo: todos los modelos parten de acá, así que la simulación entra
    a todos por igual sin tocar ninguno. Ver `api/sim.py`.
    """
    p = sim.aplicar(store.cargar(nombre))
    return p if p else None


def _falta(nombre):
    return jsonify({"error": f'La cartera "{nombre}" no existe o está vacía.'}), 404


# ── Análisis completo, en paralelo ────────────────────────────────────────────

@bp.post("/analisis/<nombre>")
def lanzar(nombre):
    pos = _posiciones(nombre)
    if not pos:
        return _falta(nombre)
    c = request.json or {}
    # `forzar` es el botón de recalcular: sin él se reusa la corrida que ya hay.
    return jsonify({"run_id": jobs.lanzar(nombre, pos, c.get("modelos"),
                                          forzar=bool(c.get("forzar"))),
                    "modelos": list(jobs.MODELOS)})


@bp.get("/analisis/<nombre>/<run_id>")
def consultar(nombre, run_id):
    e = jobs.estado(run_id)
    return (jsonify(e) if e else
            (jsonify({"error": "Esa corrida no existe o ya se descartó."}), 404))


# ── Modelos sueltos ───────────────────────────────────────────────────────────

def _lab() -> bool:
    """`?lab=11`: el modelo propuesto (Monte Carlo FHS y Markowitz con sus
    insumos) en vez del de producción, hasta que se apruebe."""
    from core.models.portfolio import HISTORIA_LARGA
    return HISTORIA_LARGA.get()


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


@bp.get("/evolucion/<nombre>")
def evolucion(nombre):
    """Rendimiento acumulado (TWR) y variación diaria de las últimas ruedas.

    Va con los trades cerrados además de las posiciones: la historia de la
    cartera incluye lo que ya no está.
    """
    pos = _posiciones(nombre)
    if not pos:
        return _falta(nombre)
    return jsonify(portfolio.evolucion(pos, store.cargar_realizado(nombre),
                                       request.args.get("ruedas", 30, type=int)))


@bp.get("/riesgo/<nombre>")
def riesgo(nombre):
    return _simple(nombre, risk.analizar, request.args.get("benchmark"))


@bp.get("/riesgo/<nombre>/por-activo")
def riesgo_activos(nombre):
    """VaR, CVaR, VaR 99 y peor caída de cada activo, no solo del agregado."""
    return _simple(nombre, risk.por_activo, request.args.get("benchmark"))


@bp.get("/riesgo/<nombre>/rolling")
def riesgo_rolling(nombre):
    """VaR en ventana móvil con los eventos macro superpuestos."""
    return _simple(nombre, risk.var_rolling, request.args.get("ventana", 21, type=int),
                   request.args.get("activo"))


@bp.get("/riesgo/<nombre>/cambiario")
def riesgo_fx(nombre):
    """Cuánto del riesgo viene del activo y cuánto del tipo de cambio."""
    return _simple(nombre, risk.riesgo_cambiario)


@bp.get("/riesgo/<nombre>/ajustar")
def riesgo_ajustar(nombre):
    """Qué comprar y vender para que la pérdida de un día malo no supere un límite."""
    objetivo = request.args.get("var", type=float)
    if objetivo is None:
        return jsonify({"error": "Falta el VaR objetivo (parámetro `var`, en %)."}), 400
    return _simple(nombre, risk.rebalancear_a_var, objetivo,
                   request.args.get("benchmark"))


@bp.get("/correlaciones/<nombre>")
def correlaciones(nombre):
    """Matriz de correlaciones y si la cartera es defensiva o agresiva."""
    return _simple(nombre, portfolio.correlaciones,
                   request.args.get("ventana", 252, type=int))


@bp.get("/markowitz/<nombre>/backtest")
def mk_backtest(nombre):
    """¿La cartera optimizada habría funcionado fuera de muestra?"""
    return _simple(nombre, markowitz.backtest,
                   request.args.get("meses", 6, type=int),
                   request.args.get("benchmark"), _lab())


@bp.get("/stress/<nombre>")
def stress(nombre):
    return _simple(nombre, risk.stress_test)


@bp.get("/markowitz/<nombre>")
def mk(nombre):
    cap = request.args.get("cap", type=float)
    return _simple(nombre, markowitz.optimizar,
                   request.args.get("benchmark"), cap, _lab())


@bp.get("/hrp/<nombre>")
def hrp_ep(nombre):
    """Hierarchical Risk Parity: pesos por clustering, sin invertir la covarianza."""
    return _simple(nombre, hrp.optimizar, request.args.get("benchmark"), _lab())


@bp.get("/montecarlo/<nombre>")
def mc(nombre):
    return _simple(nombre, montecarlo.simular,
                   request.args.get("horizonte", 252, type=int),
                   request.args.get("simulaciones", 10000, type=int),
                   request.args.get("motor", "t"))


@bp.get("/montecarlo/<nombre>/fhs")
def mc_fhs(nombre):
    """Lab 11: el modelo propuesto (simulación histórica filtrada)."""
    return _simple(nombre, montecarlo.simular_fhs,
                   request.args.get("horizonte", 252, type=int))


@bp.get("/montecarlo/<nombre>/analistas")
def mc_analistas(nombre):
    """El Monte Carlo con el rendimiento de Black-Litterman: precios objetivo
    y los precios fijados a mano (una OPA) incluidos."""
    return _simple(nombre, montecarlo.escenario_analistas, store.opiniones(nombre),
                   request.args.get("horizonte", 252, type=int))


@bp.get("/opiniones/<nombre>")
def opiniones_get(nombre):
    return jsonify(store.opiniones(nombre))


@bp.put("/opiniones/<nombre>")
def opiniones_put(nombre):
    if not store.cargar(nombre):
        return _falta(nombre)
    store.fijar_opiniones(nombre, (request.json or {}).get("manuales") or {})
    return jsonify(store.opiniones(nombre))


@bp.get("/montecarlo/<nombre>/motores")
def mc_motores(nombre):
    """Los tres motores lado a lado: cuánto cambia el supuesto de distribución."""
    if _lab():
        return _simple(nombre, montecarlo.motores_fhs, request.args.get("horizonte", 252, type=int))
    return _simple(nombre, montecarlo.comparar_motores,
                   request.args.get("horizonte", 252, type=int))


@bp.get("/montecarlo/<nombre>/por-activo")
def mc_activos(nombre):
    """Simula cada activo por separado: qué papel puede hundir el resultado."""
    if _lab():
        # `?escenario=analistas`: los mismos ajustes de Black-Litterman que el
        # abanico de ese escenario, para que cada activo cuente lo mismo.
        ajustes = {}
        if request.args.get("escenario") == "analistas":
            pos = _posiciones(nombre)
            if not pos:
                return _falta(nombre)
            aj = montecarlo.ajustes_analistas(pos, store.opiniones(nombre))
            if "error" in aj:
                return jsonify(aj)
            ajustes = {"deriva_anual": aj["deriva"], "vol_anual": aj["vol"]}
        return _simple(nombre, montecarlo.por_activo_fhs,
                       request.args.get("horizonte", 252, type=int),
                       request.args.get("simulaciones", 4000, type=int), **ajustes)
    return _simple(nombre, montecarlo.por_activo,
                   request.args.get("horizonte", 252, type=int),
                   request.args.get("simulaciones", 4000, type=int),
                   request.args.get("motor", "t"))


@bp.get("/montecarlo/<nombre>/correlaciones")
def mc_correlaciones(nombre):
    """Correlación móvil para animar: las correlaciones no son estables."""
    return _simple(nombre, montecarlo.correlaciones_moviles,
                   request.args.get("ventana", 63, type=int),
                   request.args.get("pasos", 40, type=int))


@bp.get("/capm/<nombre>")
def capm_(nombre):
    return _simple(nombre, capm.analizar, request.args.get("benchmark"))


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


@bp.get("/tir/<nombre>")
def tir_por_activo(nombre):
    """TIR por ticker de renta fija de la cartera: primero el catálogo propio
    de `bonds.py` (exacto, calcado del flujo de fondos real), y para lo que
    ese catálogo no tiene, bonistas.com como respaldo (ver `core.data.bonistas`).
    `{"AO28D": 9.36, ...}`, en %."""
    posiciones = store.cargar(nombre)
    tickers = sorted({p["ticker"].upper() for p in posiciones
                      if is_bond(p["ticker"], p.get("source"))})
    if not tickers:
        return jsonify({})

    propio = bonds.riesgo_tasa_cartera(posiciones)
    tirs = ({b["ticker"]: b["tir_pct"] for b in propio.get("bonos", [])}
            if not propio.get("error") else {})
    for t in tickers:
        if t not in tirs:
            v = bonistas.tir_pct(t)
            if v is not None:
                tirs[t] = v
    return jsonify(tirs)


@bp.post("/blacklitterman/<nombre>")
def bl(nombre):
    pos = _posiciones(nombre)
    if not pos:
        return _falta(nombre)
    cuerpo = request.json or {}
    views = cuerpo.get("views")
    # Sin `manuales` en el pedido, las guardadas (`store.opiniones`).
    manuales = cuerpo["manuales"] if "manuales" in cuerpo else store.opiniones(nombre)

    # Sin views explícitas se arman desde los precios objetivo, dejando que las
    # manuales pisen activo por activo. Es el uso normal: BL automático, con la
    # posibilidad de imponer una opinión propia donde el usuario la tenga.
    if views is None:
        views = blacklitterman.views_combinadas(
            targets.analizar(pos), momentum.analizar(pos), manuales)

    return jsonify(blacklitterman.analizar(
        pos, views, cuerpo.get("benchmark"), cuerpo.get("max_weight"), _lab()))
