"""
jobs.py — Los modelos corren en paralelo, no uno atrás del otro.

Todos los modelos parten de la misma matriz de retornos y son independientes
entre sí: no hay razón para que el usuario espere la suma de todos los tiempos.
Se lanzan juntos y el frontend va mostrando cada panel a medida que termina, en
vez de una pantalla en blanco hasta que esté todo.

Los resultados quedan en memoria por `run_id`. No se persisten a propósito: la
caché de precios y la de `.info` ya evitan el trabajo caro, así que rehacer un
análisis es barato, y guardar resultados obligaría a invalidarlos cuando cambian
los precios — más complejidad que beneficio.
"""

import contextvars
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor

from core.io import store
from core.models import (blacklitterman, capm, composicion, markowitz,
                         momentum, montecarlo, portfolio, regimenes, risk,
                         targets)

# Cada entrada: nombre visible + función que recibe las posiciones.
# Cada modelo recibe (posiciones, nombre de la cartera). El nombre casi nunca se
# usa —los modelos trabajan sobre las posiciones y nada más— pero la evolución
# necesita además lo que ya cerraste, que vive en el store bajo ese nombre.
MODELOS = {
    "posicion":     ("Posición",        lambda p, c: portfolio.valuar(p)),
    "composicion":  ("Composición",     lambda p, c: composicion.analizar(p)),
    "riesgo":       ("Riesgo",          lambda p, c: risk.analizar(p)),
    "stress":       ("Stress test",     lambda p, c: risk.stress_test(p)),
    "markowitz":    ("Markowitz",       lambda p, c: markowitz.optimizar(p)),
    "montecarlo":   ("Monte Carlo",     lambda p, c: montecarlo.simular(p)),
    "capm":         ("CAPM",            lambda p, c: capm.analizar(p)),
    "momentum":     ("Momentum",        lambda p, c: momentum.analizar(p)),
    "objetivos":    ("Objetivos",       lambda p, c: targets.analizar(p)),
    "regimenes":    ("Regímenes",       lambda p, c: regimenes.analizar(p)),
    # BL sin views devuelve el punto de partida y no sirve de nada: las views se
    # arman desde los precios objetivo, recortando confianza donde el momentum
    # va en contra. Es el uso para el que existe el modelo en esta aplicación.
    "blacklitterman": ("Black-Litterman", lambda p, c: blacklitterman.analizar(
        p, blacklitterman.views_combinadas(targets.analizar(p), momentum.analizar(p)))),

    # Estos tres los pedía cada panel por su cuenta, en paralelo a los once de
    # arriba y compitiendo con ellos por el mismo procesador: en la VM sumaban
    # unos 20 s a cada apertura de cartera —`benchmarks` 20,4 s, `evolucion`
    # 20,4 s, `correlaciones` 8,2 s— y `benchmarks` encima repetía el CAPM que
    # el lote ya había corrido, porque corre los tres índices y uno de ellos es
    # el mismo. Entran al lote: se calculan una vez, en paralelo con el resto, y
    # el frontend los recibe por el mismo canal que todo lo demás. Los endpoints
    # sueltos siguen existiendo para recalcular con otros parámetros.
    "evolucion":    ("Evolución",       lambda p, c: portfolio.evolucion(
        p, store.cargar_realizado(c))),
    "correlaciones": ("Correlaciones",  lambda p, c: portfolio.correlaciones(p)),
    "benchmarks":   ("Índices",         lambda p, c: capm.comparar_benchmarks(p)),
}

_corridas = {}
_lock = threading.Lock()
_pool = ThreadPoolExecutor(max_workers=6, thread_name_prefix="modelo")

# Las corridas viejas se descartan solas: sin esto la memoria crece sin techo en
# una sesión larga.
_MAX_CORRIDAS = 20


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
    try:
        r = fn(posiciones, cartera)
        _guardar(run_id, modelo, "error" if isinstance(r, dict) and "error" in r else "listo", r)
    except Exception as e:
        print(f"  [jobs] {modelo}: {type(e).__name__}: {e}")
        traceback.print_exc()
        _guardar(run_id, modelo, "error", {"error": f"{type(e).__name__}: {e}"})


def lanzar(nombre_cartera: str, posiciones: list, modelos: list = None) -> str:
    """Dispara todos los modelos y devuelve el identificador de la corrida."""
    elegidos = [m for m in (modelos or MODELOS) if m in MODELOS]
    run_id = uuid.uuid4().hex[:12]

    with _lock:
        _corridas[run_id] = {
            "cartera": nombre_cartera, "estado": "corriendo",
            "inicio": time.time(),
            "modelos": {m: {"estado": "en cola", "resultado": None} for m in elegidos},
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
    for m in elegidos:
        _guardar(run_id, m, "corriendo")
        fut = _pool.submit(contextvars.copy_context().run,
                           _ejecutar, run_id, m, MODELOS[m][1], posiciones,
                           nombre_cartera)
        # Red de seguridad: `_ejecutar` atrapa lo que falle DENTRO del modelo,
        # pero lo que falle antes de entrar —como el contexto de arriba— sólo
        # existe en el Future. Sin esto, un modelo que revienta ahí no da error:
        # se queda calculando para siempre, que es la peor forma de fallar.
        fut.add_done_callback(lambda f, m=m: _fallo_del_pool(run_id, m, f))

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
            "transcurrido": round(time.time() - c["inicio"], 2),
            "modelos": {m: {"estado": d["estado"], "nombre": MODELOS[m][0],
                            "segundos": d.get("t")}
                        for m, d in c["modelos"].items()},
            "resultados": {m: d["resultado"] for m, d in c["modelos"].items()
                           if d["estado"] in ("listo", "error")},
        }
