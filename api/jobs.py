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

import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor

from core.models import (blacklitterman, capm, composicion, markowitz,
                         momentum, montecarlo, portfolio, regimenes, risk,
                         targets)

# Cada entrada: nombre visible + función que recibe las posiciones.
MODELOS = {
    "posicion":     ("Posición",        lambda p: portfolio.valuar(p)),
    "composicion":  ("Composición",     composicion.analizar),
    "riesgo":       ("Riesgo",          risk.analizar),
    "stress":       ("Stress test",     risk.stress_test),
    "markowitz":    ("Markowitz",       markowitz.optimizar),
    "montecarlo":   ("Monte Carlo",     montecarlo.simular),
    "capm":         ("CAPM",            capm.analizar),
    "momentum":     ("Momentum",        momentum.analizar),
    "objetivos":    ("Objetivos",       targets.analizar),
    "regimenes":    ("Regímenes",       regimenes.analizar),
    "blacklitterman": ("Black-Litterman", lambda p: blacklitterman.analizar(p)),
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


def _ejecutar(run_id, modelo, fn, posiciones):
    try:
        r = fn(posiciones)
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

    for m in elegidos:
        _guardar(run_id, m, "corriendo")
        _pool.submit(_ejecutar, run_id, m, MODELOS[m][1], posiciones)

    return run_id


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
