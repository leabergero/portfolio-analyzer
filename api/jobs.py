"""
jobs.py — Los modelos corren en paralelo, no uno atrás del otro.

Todos los modelos parten de la misma matriz de retornos y son independientes
entre sí: no hay razón para que el usuario espere la suma de todos los tiempos.
Se lanzan juntos y el frontend va mostrando cada panel a medida que termina, en
vez de una pantalla en blanco hasta que esté todo.

Los resultados quedan en memoria por `run_id`, y una corrida se reusa mientras
nada de lo que se analiza haya cambiado: ver `_huella`. Volver a la pantalla no
es pedir otro análisis, y en la web cada recálculo era media pantalla de espera.

No se persisten a disco a propósito. Son de esta vuelta y de este proceso; la
caché de precios, que sí vive en disco, es la que evita el trabajo de verdad.
"""

import contextvars
import hashlib
import json
import os
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor

from core import mercado
from core.data import symbols
from core.data.sources import TTL_SPOT_H, spot_forzable
from core.io import store
from core.models import (blacklitterman, capm, composicion, hrp, markowitz,
                         momentum, montecarlo, portfolio, regimenes, risk,
                         targets)

# ── Lo que cada pestaña pide por su cuenta, recordado ────────────────────────
# La ventana de riesgo, el riesgo por activo, HRP, el backtest, los paneles de
# Monte Carlo: cada uno tiene su endpoint y la pestaña lo pide al abrirse. El
# lote los calcula antes, con los mismos argumentos que va a mandar la pantalla,
# y los deja acá; cuando la pestaña pregunta, la respuesta ya está.
#
# Un candado por clave: si la pestaña pregunta ANTES de que el lote llegue, lo
# calcula el request y el lote, al llegar, espera ese resultado en vez de
# hacerlo de nuevo. Así lo que el usuario abrió pasa adelante solo.
#
# Con otros parámetros —otro índice, otro horizonte, un activo del selector— la
# clave es otra y se calcula a pedido, como siempre.
_recuerdos = {}
_candados = {}
_generacion = {}
_MAX_RECUERDOS = 150


def _bl(posiciones, manuales, benchmark, max_weight, lab):
    return blacklitterman.analizar(
        posiciones, blacklitterman.views_combinadas(
            targets.analizar(posiciones), momentum.analizar(posiciones), manuales),
        benchmark, max_weight, lab)


SUELTOS = {
    "benchmarks": capm.comparar_benchmarks,
    # Necesita lo ya cerrado, que vive en el store bajo el nombre de la cartera.
    "riesgo_decisiones": lambda p, c: risk.decisiones(p, store.cargar_realizado(c)),
    "riesgo_rolling": risk.var_rolling,
    "riesgo_activos": risk.por_activo,
    "riesgo_cambiario": risk.riesgo_cambiario,
    "blacklitterman": _bl,
    "hrp": hrp.optimizar,
    "backtest": markowitz.backtest,
    "mc_analistas": montecarlo.escenario_analistas,
    "mc_activos": montecarlo.por_activo_fhs,
    "mc_correlaciones": montecarlo.correlaciones_moviles,
    "mc_motores": montecarlo.motores_fhs,
}


def suelto(cartera: str, clave: str, posiciones: list, *args, **kwargs):
    """El resultado de `SUELTOS[clave]`, calculado una sola vez mientras no
    cambie nada de lo que se analiza (lo mismo que mira `_huella`) ni se pida
    recalcular. Los errores no se recuerdan: son el entorno, no un resultado."""
    from core.models.portfolio import HISTORIA_LARGA
    quien = store.quien()
    crudo = json.dumps([quien, mercado.actual(), HISTORIA_LARGA.get(), symbols.LAB.get(), cartera,
                        _generacion.get((quien, cartera), 0), clave, args, kwargs, posiciones],
                       sort_keys=True, default=str)
    huella = hashlib.sha1(crudo.encode()).hexdigest()
    with _lock:
        candado = _candados.setdefault(huella, threading.Lock())
    with candado:
        with _lock:
            hallado = _recuerdos.get(huella)
        if hallado and time.time() - hallado[0] < _TTL_CORRIDA_S:
            return hallado[1]
        r = SUELTOS[clave](posiciones, *args, **kwargs)
        if not (isinstance(r, dict) and "error" in r):
            with _lock:
                if len(_recuerdos) >= _MAX_RECUERDOS:
                    for vieja in sorted(_recuerdos, key=lambda k: _recuerdos[k][0])[:_MAX_RECUERDOS // 3]:
                        _recuerdos.pop(vieja, None)
                        _candados.pop(vieja, None)
                _recuerdos[huella] = (time.time(), r)
        return r


def _indice(p, c):
    """El índice que la pantalla elige sola: el que mejor explica la cartera."""
    return (suelto(c, "benchmarks", p) or {}).get("recomendado")


def _tibio(clave, args=lambda p, c: ()):
    """Deja calculado lo que una pestaña va a pedir. No devuelve el resultado:
    viaja por su endpoint, no en cada consulta del estado de la corrida."""
    def correr(p, c):
        suelto(c, clave, p, *args(p, c))
    return correr


# Cada entrada: nombre visible + función que recibe (posiciones, nombre de la
# cartera). El nombre casi nunca se usa —los modelos trabajan sobre las
# posiciones y nada más— pero la evolución necesita además lo que ya cerraste,
# que vive en el store bajo ese nombre.
#
# **El orden es la prioridad.** Se encolan así y, donde el pool tiene un solo
# hilo (la VM), se calculan así: primero lo que muestra Posición, después
# Riesgo, Optimización, Monte Carlo y al final Regímenes, que es lo que menos
# se consulta. Antes arrancaban todos juntos y cada uno
# terminaba cuando le tocaba: en la VM, con MAMI, Posición quedaba completa a
# los 80 s y Monte Carlo salía a los 55 (2026-10-13). En fila son 3 s y 12 s.
#
# Los argumentos de los `_tibio` son los que manda la pantalla por defecto: si
# no coinciden, el cálculo adelantado no le sirve a nadie.
MODELOS = {
    # ── Posición ──
    # El único que pide precio en vivo: es la foto de la tenencia y la variación
    # del día. Todo lo demás mide sobre cierres, y así sigue.
    "posicion":     ("Posición",        lambda p, c: portfolio.valuar(p, vivo=True)),
    "composicion":  ("Composición",     lambda p, c: composicion.analizar(p)),
    # Estos tres (evolución, correlaciones, índices) los pedía cada panel por su
    # cuenta, en paralelo al lote y compitiendo con él por el mismo procesador.
    # Entran al lote: se calculan una vez y el frontend los recibe por el mismo
    # canal que todo lo demás. Los endpoints sueltos siguen existiendo para
    # recalcular con otros parámetros.
    "evolucion":    ("Evolución",       lambda p, c: portfolio.evolucion(
        p, store.cargar_realizado(c), flujos_fci=store.flujos_fci(c))),
    "riesgo":       ("Riesgo",          lambda p, c: risk.analizar(p)),
    "momentum":     ("Momentum",        lambda p, c: momentum.analizar(p)),
    "correlaciones": ("Correlaciones",  lambda p, c: portfolio.correlaciones(p)),
    "capm":         ("CAPM",            lambda p, c: capm.analizar(p)),
    "benchmarks":   ("Índices",         lambda p, c: suelto(c, "benchmarks", p)),

    # ── Riesgo ──
    "stress":       ("Stress test",     lambda p, c: risk.stress_test(p)),
    # En el orden de la pestaña: va debajo de los márgenes, antes de la ventana.
    "riesgo_decisiones": ("Riesgo de cada decisión", _tibio("riesgo_decisiones", lambda p, c: (c,))),
    "riesgo_rolling": ("Riesgo en el tiempo", _tibio("riesgo_rolling", lambda p, c: (21, None))),
    "riesgo_activos": ("Riesgo por activo", _tibio("riesgo_activos", lambda p, c: (None,))),
    "riesgo_cambiario": ("Riesgo cambiario", _tibio("riesgo_cambiario")),

    # ── Optimización ──
    "objetivos":    ("Objetivos",       lambda p, c: targets.analizar(p)),
    "markowitz":    ("Markowitz",       lambda p, c: markowitz.optimizar(p, lab=True)),
    # BL sin views devuelve el punto de partida y no sirve de nada: las views se
    # arman desde los precios objetivo, recortando confianza donde el momentum
    # va en contra, y las opiniones guardadas pisan activo por activo. Es el
    # mismo pedido que hace la pestaña, contra el índice que ella elige sola.
    "blacklitterman": ("Black-Litterman", lambda p, c: suelto(
        c, "blacklitterman", p, store.opiniones(c), _indice(p, c), None, True)),
    "hrp":          ("HRP",             _tibio("hrp", lambda p, c: (_indice(p, c), True))),
    "backtest":     ("Backtest",        _tibio("backtest", lambda p, c: (6, _indice(p, c), True))),

    # ── Monte Carlo ──
    "montecarlo":   ("Monte Carlo",     lambda p, c: montecarlo.simular_fhs(p)),
    "mc_analistas": ("Monte Carlo según analistas",
                     _tibio("mc_analistas", lambda p, c: (store.opiniones(c), 252))),
    "mc_activos":   ("Monte Carlo por activo", _tibio("mc_activos", lambda p, c: (252, 4000))),
    "mc_correlaciones": ("Correlaciones móviles", _tibio("mc_correlaciones", lambda p, c: (63, 40))),
    "mc_motores":   ("Motores de Monte Carlo", _tibio("mc_motores", lambda p, c: (252,))),

    # ── Regímenes, al final: se mira poco, para tener una idea general ──
    "regimenes":    ("Regímenes",       lambda p, c: regimenes.analizar(p)),
}

_corridas = {}
_lock = threading.Lock()
# Cuántos modelos a la vez. Seis rinde en una máquina con núcleos de sobra; en
# la VM, que recibe menos de un núcleo, seis hilos se pelean por él y la corrida
# tarda más que con dos (MAMI, 2026-10-13: 65 s con seis, 48 s con dos). Por eso
# es una perilla del entorno y no un número fijo.
_pool = ThreadPoolExecutor(max_workers=int(os.environ.get("PA_HILOS_MODELOS", 6)),
                           thread_name_prefix="modelo")

# Las corridas viejas se descartan solas: sin esto la memoria crece sin techo en
# una sesión larga.
_MAX_CORRIDAS = 20

# ── Volver a Análisis no es pedir otro análisis ───────────────────────────────
# Cada vez que la pantalla se monta lanza el lote, así que ir a Comparación y
# volver rehacía los catorce modelos. En la máquina de su dueño se nota poco; en
# la web es media pantalla de espera por cada ida y vuelta.
#
# Mientras no cambie NADA de lo que se está analizando, el resultado tampoco
# cambia: se devuelve la corrida que ya existe. El techo es el mismo que el de
# los precios —yfinance se vuelve a preguntar cada dos horas—, así que recalcular
# antes daría exactamente los mismos números con otra espera.
#
# Lo que "no cambie nada" quiere decir, y por qué cada cosa está en la huella:
#
#   · el usuario, porque en la web hay muchos a la vez y todos tienen una
#     cartera llamada «Modelo» — sin esto uno vería el análisis de otro;
#   · la plaza, porque la misma cartera mirada desde Europa da otros números;
#   · las posiciones ya simuladas, que es lo que los modelos reciben de verdad.
_TTL_CORRIDA_S = TTL_SPOT_H * 3600


def _huella(nombre_cartera, posiciones, elegidos) -> str:
    from core.models.portfolio import HISTORIA_LARGA
    crudo = json.dumps([store.quien(), mercado.actual(), HISTORIA_LARGA.get(), symbols.LAB.get(), nombre_cartera,
                        sorted(elegidos), posiciones],
                       sort_keys=True, default=str)
    return hashlib.sha1(crudo.encode()).hexdigest()[:16]


def _reusable(huella: str):
    """El `run_id` de una corrida que sirve tal cual, o None.

    Una que todavía corre también sirve: son los mismos modelos sobre los mismos
    datos, y mandar el segundo lote sólo los haría pelear por el procesador.

    La que fracasó entera no se reusa. Eso no es un resultado, es el entorno
    caído —sin red, sin fuente de precios— y dejarlo pegado dos horas convierte
    un tropiezo de un minuto en una tarde sin análisis.
    """
    ahora = time.time()
    with _lock:
        candidatas = [(c["inicio"], rid, c) for rid, c in _corridas.items()
                      if c.get("huella") == huella
                      and ahora - c["inicio"] < _TTL_CORRIDA_S]
        for _, rid, c in sorted(candidatas, reverse=True):
            if c.get("cancelada"):
                continue
            modelos = c["modelos"].values()
            if all(m["estado"] == "error" for m in modelos):
                continue
            return rid
    return None


def _guardar(run_id, modelo, estado, dato=None):
    with _lock:
        c = _corridas.get(run_id)
        if not c:
            return
        c["modelos"][modelo] = {"estado": estado, "resultado": dato,
                                "t": round(time.time() - c["inicio"], 2)}
        if all(m["estado"] in ("listo", "error") for m in c["modelos"].values()):
            c["estado"] = "terminado"
            c["duracion"] = round(time.time() - c["inicio"], 2)


def _ejecutar(run_id, modelo, fn, posiciones, cartera):
    _guardar(run_id, modelo, "corriendo")
    try:
        r = fn(posiciones, cartera)
        _guardar(run_id, modelo, "error" if isinstance(r, dict) and "error" in r else "listo", r)
    except Exception as e:
        print(f"  [jobs] {modelo}: {type(e).__name__}: {e}")
        traceback.print_exc()
        _guardar(run_id, modelo, "error", {"error": f"{type(e).__name__}: {e}"})


def lanzar(nombre_cartera: str, posiciones: list, modelos: list = None,
           forzar: bool = False) -> str:
    """Dispara todos los modelos y devuelve el identificador de la corrida.

    Si ya hay una corrida viva sobre exactamente lo mismo, devuelve esa: volver
    a la pantalla no es pedir otro análisis. `forzar` es el botón de recalcular.
    """
    elegidos = [m for m in (modelos or MODELOS) if m in MODELOS]
    huella = _huella(nombre_cartera, posiciones, elegidos)
    if not forzar and (previa := _reusable(huella)) is not None:
        return previa

    run_id = uuid.uuid4().hex[:12]

    with _lock:
        # Corrida nueva, números nuevos: lo recordado de la anterior no vale.
        quien = (store.quien(), nombre_cartera)
        _generacion[quien] = _generacion.get(quien, 0) + 1
        # Lo que todavía espera en la fila de las corridas anteriores de este
        # usuario ya no lo mira nadie: pasó a otra cartera o pidió recalcular.
        # Con un solo hilo (la VM), dejarlo ahí hacía esperar a la cartera de
        # la pantalla detrás del lote entero de la anterior: abrir LEANDRO,
        # MAMI y KARIN seguidas encolaba 72 modelos (2026-10-16). Lo que ya
        # arrancó termina; la corrida no se reusa porque le faltan modelos.
        # ponytail: dos pestañas del mismo usuario en carteras distintas se
        # cancelan entre sí y la de atrás queda quieta hasta que se la vuelva a
        # abrir; prioridad por corrida si eso llega a pasar de verdad.
        previas = [c for c in _corridas.values()
                   if c.get("quien") == store.quien() and c["estado"] == "corriendo"]
        _corridas[run_id] = {
            "cartera": nombre_cartera, "estado": "corriendo",
            "inicio": time.time(), "huella": huella, "quien": store.quien(),
            "modelos": {m: {"estado": "en cola", "resultado": None} for m in elegidos},
            "futuros": [],
        }
        # Descarta las más viejas.
        if len(_corridas) > _MAX_CORRIDAS:
            for viejo in sorted(_corridas, key=lambda k: _corridas[k]["inicio"])[:-_MAX_CORRIDAS]:
                _corridas.pop(viejo, None)

    # La plaza elegida vive en un ContextVar del request, y un ContextVar no
    # cruza a un hilo nuevo: sin copiar el contexto acá, los modelos correrían
    # todos con la plaza por defecto y una cartera mirada desde Europa volvería
    # medida en dólares.
    #
    # **Una copia por modelo, no una para todos.** Un mismo `Context` no se puede
    # entrar dos veces a la vez: compartirlo entre los once dejaba correr al
    # primero y mataba a los otros diez con `RuntimeError: cannot enter context`,
    # y como la excepción se la queda el Future y nadie la miraba, esos modelos
    # se quedaban en "corriendo" para siempre. La pantalla mostraba "1 de 11
    # modelos listos" y ahí se quedaba.
    # "posicion" es el único que pide precio en vivo (ver `MODELOS`), así que es
    # el único al que le sirve un `forzar`: los demás miden sobre cierres, que
    # ya tienen su propio TTL. Saltar el TTL de 2 h del spot en cada recalculo
    # sería un burst a yfinance en un día movido; `spot_forzable` es el freno
    # de 15 minutos entre dos pedidos de precio fresco.
    fn_posicion = None
    if forzar and "posicion" in elegidos and spot_forzable(nombre_cartera):
        fn_posicion = lambda p, c: portfolio.valuar(p, vivo=True, forzar=True)

    for m in elegidos:
        fn = fn_posicion if m == "posicion" and fn_posicion else MODELOS[m][1]
        fut = _pool.submit(contextvars.copy_context().run,
                           _ejecutar, run_id, m, fn, posiciones,
                           nombre_cartera)
        # Red de seguridad: `_ejecutar` atrapa lo que falle DENTRO del modelo,
        # pero lo que falle antes de entrar —como el contexto de arriba— sólo
        # existe en el Future. Sin esto, un modelo que revienta ahí no da error:
        # se queda calculando para siempre, que es la peor forma de fallar.
        fut.add_done_callback(lambda f, m=m: _fallo_del_pool(run_id, m, f))
        _corridas[run_id]["futuros"].append(fut)

    for c in previas:
        if sum(f.cancel() for f in c["futuros"]):
            c["cancelada"] = True

    return run_id


def _fallo_del_pool(run_id, modelo, fut):
    try:
        e = fut.exception()
    except Exception:                      # cancelado: no hay nada que reportar
        return
    if e is not None:
        print(f"  [jobs] {modelo} no llegó a correr: {type(e).__name__}: {e}")
        _guardar(run_id, modelo, "error", {"error": f"{type(e).__name__}: {e}"})


def estado(run_id: str):
    """Estado y resultados parciales. El frontend consulta esto mientras dibuja."""
    with _lock:
        c = _corridas.get(run_id)
        if not c:
            return None
        return {
            "run_id": run_id, "cartera": c["cartera"], "estado": c["estado"],
            "duracion": c.get("duracion"),
            # Desde cuándo son estos números, para poder decirlo en pantalla.
            "edad_s": round(time.time() - c["inicio"]),
            "transcurrido": round(time.time() - c["inicio"], 2),
            "modelos": {m: {"estado": d["estado"], "nombre": MODELOS[m][0],
                            "segundos": d.get("t")}
                        for m, d in c["modelos"].items()},
            "resultados": {m: d["resultado"] for m, d in c["modelos"].items()
                           if d["estado"] in ("listo", "error")},
        }
