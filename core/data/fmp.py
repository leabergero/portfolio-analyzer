"""
fmp.py — Financial Modeling Prep: precios objetivo de analistas.

Fuente **opcional**. Aporta consenso de analistas (precio objetivo y
recomendación) con mejor cobertura que yfinance para acciones de EE.UU. Si no
hay key configurada, o si la consulta falla, quien la usa cae a yfinance sin
enterarse: `core.models.targets` prueba FMP primero y sigue.

Límites reales del plan gratuito, medidos:
  · Acciones de EE.UU. grandes  → sí (AAPL devuelve consenso)
  · ADRs argentinos (GGAL, YPF) → bloqueados por plan pago
  · **250 consultas por día**, y cada símbolo cuesta 3 (cotización + consenso +
    grados). Diez posiciones son 30 consultas por pantalla.
Por eso FMP nunca reemplaza a yfinance: lo complementa donde tiene cobertura.

Las respuestas se cachean 24 h. Un consenso de analistas se mueve de semana en
semana, no de minuto en minuto, así que la caché no pierde nada y es lo único
que hace usable el plan gratuito. Sin ella la cuota se agota sola — pasó.

API "stable", vigente desde agosto de 2025. La ruta vieja `/api/v3/` ya no
responde.
"""

import requests

from core.data import cache
from core.data.connectors import clave

BASE = "https://financialmodelingprep.com/stable"
_TIMEOUT = 8
_TTL_HORAS = 24

# Motivo por el que la última consulta no devolvió nada. Distinguir la cuota
# agotada de una key inválida importa: lo primero se arregla solo mañana, lo
# segundo pide que el usuario haga algo.
_ultimo_error = None

# Cortacircuitos. Cuando la API contesta 429, dejar de preguntarle por un rato:
# seguir insistiendo no devuelve la cuota y sí cuesta tiempo real. Con la cuota
# agotada, un análisis de seis posiciones llegaba a hacer ~36 pedidos fallidos
# en cadena — 16 s de espera para nada, y era el modelo más lento de todos.
_CORTE_MINUTOS = 30
_sin_cuota_desde = None


def _en_corte() -> bool:
    import time
    if _sin_cuota_desde is None:
        return False
    if time.time() - _sin_cuota_desde > _CORTE_MINUTOS * 60:
        return False
    return True


def habilitado() -> bool:
    """Hay key configurada y la cuota no está agotada."""
    return bool(clave("fmp")) and not _en_corte()


def _pedir(recurso: str, simbolo: str, key: str):
    """Lista de resultados, o None. Cachea 24 h, incluidos los vacíos.

    FMP responde 200 con un mensaje de error en el cuerpo, así que no alcanza
    con mirar el código de estado.
    """
    global _ultimo_error

    ck = f"fmp:{recurso}:{simbolo.upper()}"
    guardado = cache.leer_respuesta(ck, _TTL_HORAS, default="__falta__")
    if guardado != "__falta__":
        return guardado

    try:
        r = requests.get(f"{BASE}/{recurso}",
                         params={"symbol": simbolo, "apikey": key}, timeout=_TIMEOUT)
    except Exception as e:
        _ultimo_error = f"red: {type(e).__name__}"
        return None

    if r.status_code == 429:
        global _sin_cuota_desde
        import time
        _ultimo_error = "cuota"
        _sin_cuota_desde = time.time()    # corta el resto de los pedidos
        return None                       # NO se cachea: mañana vuelve a andar
    if r.status_code in (401, 403):
        _ultimo_error = "key"
        return None

    try:
        datos = r.json()
    except Exception:
        _ultimo_error = "respuesta ilegible"
        return None

    if isinstance(datos, dict):           # {"Error Message": ...} o plan premium
        _ultimo_error = "premium" if "premium" in str(datos).lower() else "sin dato"
        cache.guardar_respuesta(ck, None)  # el bloqueo por plan no cambia en el día
        return None

    salida = datos if isinstance(datos, list) and datos else None
    cache.guardar_respuesta(ck, salida)
    _ultimo_error = None if salida else "sin dato"
    return salida


def objetivo(simbolo: str):
    """Consenso de analistas para un símbolo. None si no hay cobertura.

    Devuelve la misma forma que el equivalente de yfinance, para que quien
    consume no tenga que saber de dónde vino más allá del campo `fuente`.
    """
    if not habilitado():
        return None
    key = clave("fmp")

    cotizacion = _pedir("quote", simbolo, key)
    consenso = _pedir("price-target-consensus", simbolo, key)
    if not cotizacion or not consenso:
        return None

    actual = cotizacion[0].get("price")
    objetivo_medio = consenso[0].get("targetConsensus")
    if not actual or not objetivo_medio:
        return None

    grados = (_pedir("grades-consensus", simbolo, key) or [{}])[0]
    n = sum(grados.get(k, 0) or 0
            for k in ("strongBuy", "buy", "hold", "sell", "strongSell")) or None

    return {
        "actual": round(float(actual), 2),
        "objetivo_medio": round(float(objetivo_medio), 2),
        "objetivo_alto": consenso[0].get("targetHigh"),
        "objetivo_bajo": consenso[0].get("targetLow"),
        "upside_pct": round((objetivo_medio / actual - 1) * 100, 1),
        "recomendacion": (grados.get("consensus") or "").lower() or None,
        "n_analistas": n,
        "fuente": "FMP",
    }


_DIAGNOSTICO = {
    "cuota": "cuota diaria agotada (250 consultas). Se repone mañana; "
             "mientras tanto los precios objetivo salen de yfinance",
    "key": "la API key fue rechazada — revisá que siga vigente",
    "premium": "ese símbolo requiere plan pago",
    "sin dato": "sin cobertura de analistas para ese símbolo",
}


def estado() -> dict:
    """Diagnóstico para la sección de conectores.

    Prueba con AAPL, que el plan gratuito cubre. Usa la caché, así que abrir el
    panel de conectores no consume cuota — el código anterior gastaba 3
    consultas cada vez que se dibujaba la pantalla.
    """
    if not clave("fmp"):
        return {"conectado": False, "detalle": "sin API key"}
    if _en_corte():
        return {"conectado": False, "motivo": "cuota",
                "detalle": _DIAGNOSTICO["cuota"]}
    if objetivo("AAPL"):
        return {"conectado": True,
                "detalle": "precios objetivo de EE.UU. disponibles "
                           "(los ADRs argentinos requieren plan pago)"}
    motivo = _DIAGNOSTICO.get(_ultimo_error, _ultimo_error or "falló la prueba")
    return {"conectado": False, "detalle": motivo, "motivo": _ultimo_error}
