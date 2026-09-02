"""
store.py — Dónde viven las carteras del usuario.

JSON plano en `data/`, gitignored. Es el único dato de la aplicación que **no**
es regenerable: la caché de precios y la serie MEP se vuelven a bajar, pero si
se pierden las carteras se pierde el trabajo del usuario.

Dos archivos, porque son dos cosas distintas:

    portfolios.json   posiciones abiertas — lo que tenés hoy
    realized.json     operaciones cerradas — lo que ya ganaste o perdiste

Borrar una cartera NO borra su P&L realizado. Es historia: que hayas cerrado
todas las posiciones no significa que esas ganancias no hayan existido.
"""

import json
from pathlib import Path

_DATA = Path(__file__).resolve().parents[2] / "data"
CARTERAS = _DATA / "portfolios.json"
REALIZADO = _DATA / "realized.json"

_CAMPOS = ("ticker", "buy_date", "buy_price", "qty",
           "commissions", "source", "currency", "asset_type", "notes")


def _leer(ruta: Path) -> dict:
    if not ruta.exists():
        return {}
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  [store] {ruta.name} ilegible: {e}")
        return {}


def _escribir(ruta: Path, datos: dict) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(ruta.suffix + ".tmp")
    tmp.write_text(json.dumps(datos, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(ruta)      # atómico: un corte a mitad de escritura no deja el archivo a medias


def _normalizar(posicion: dict) -> dict:
    """Deja la posición con todos los campos del contrato y los tipos correctos."""
    from core.io.csv_native import normalizar_fecha

    return {
        "ticker": str(posicion.get("ticker", "")).strip().upper(),
        "buy_date": normalizar_fecha(posicion.get("buy_date", "")),
        "buy_price": float(posicion.get("buy_price") or 0),
        "qty": float(posicion.get("qty") or 0),
        "commissions": float(posicion.get("commissions") or 0),
        "source": str(posicion.get("source", "") or "").strip().lower(),
        "currency": str(posicion.get("currency", "") or "").strip().upper(),
        "asset_type": str(posicion.get("asset_type", "") or "").strip(),
        "notes": str(posicion.get("notes", "") or "").strip(),
    }


# ── Carteras ──────────────────────────────────────────────────────────────────

def nombres() -> list:
    return sorted(_leer(CARTERAS).keys())


def cargar(nombre: str) -> list:
    return [_normalizar(p) for p in _leer(CARTERAS).get(nombre, [])]


def cargar_todas() -> dict:
    return {n: [_normalizar(p) for p in ps] for n, ps in _leer(CARTERAS).items()}


def guardar(nombre: str, posiciones: list) -> int:
    datos = _leer(CARTERAS)
    limpias = [_normalizar(p) for p in posiciones if str(p.get("ticker", "")).strip()]
    datos[nombre] = limpias
    _escribir(CARTERAS, datos)
    return len(limpias)


def borrar(nombre: str) -> bool:
    """Borra la cartera. El P&L realizado queda: es historia, no estado."""
    datos = _leer(CARTERAS)
    if nombre not in datos:
        return False
    del datos[nombre]
    _escribir(CARTERAS, datos)
    return True


def duplicar(origen: str, destino: str) -> int:
    return guardar(destino, cargar(origen))


def agregar(nombre: str, nuevas: list) -> dict:
    """Suma posiciones evitando duplicar lotes ya cargados.

    La clave de duplicado es el **lote completo** (ticker, fecha, precio,
    cantidad, comisión), no (ticker, fecha): un mismo día podés haber comprado
    dos veces el mismo papel a precios distintos, y colapsarlas perdería una.
    Así se puede volver a subir el mismo archivo sin ensuciar la cartera.
    """
    existentes = cargar(nombre)
    clave = lambda p: (p["ticker"], p["buy_date"], p["buy_price"],
                       p["qty"], p["commissions"])          # noqa: E731
    vistas = {clave(p) for p in existentes}

    agregadas = omitidas = 0
    for p in (_normalizar(x) for x in nuevas):
        if not p["ticker"]:
            continue
        if clave(p) in vistas:
            omitidas += 1
            continue
        existentes.append(p)
        vistas.add(clave(p))
        agregadas += 1

    guardar(nombre, existentes)
    return {"agregadas": agregadas, "omitidas": omitidas, "total": len(existentes)}


# ── P&L realizado ─────────────────────────────────────────────────────────────

def cargar_realizado(nombre: str) -> list:
    return _leer(REALIZADO).get(nombre, [])


def agregar_realizado(nombre: str, trades: list, lote: str = None) -> dict:
    """Suma trades cerrados. Con `lote`, REEMPLAZA lo que ese lote había dejado.

    El deduplicado por clave no alcanza cuando cambia la forma de calcular: al
    corregir el tratamiento de los splits, reimportar el mismo CSV generó trades
    con otras cantidades y otros precios —ninguna clave coincidía— y el P&L de
    COME quedó contado dos veces, −2.079.644 en vez de −1.040.884.

    Por eso cada importación se marca con su archivo de origen: volver a subir
    el mismo archivo pisa lo suyo y solo lo suyo. Los dividendos cargados a mano
    no llevan lote y no los borra ninguna reimportación.
    """
    datos = _leer(REALIZADO)
    existentes = datos.get(nombre, [])
    reemplazados = 0
    if lote:
        previos = len(existentes)
        existentes = [t for t in existentes if t.get("lote") != lote]
        reemplazados = previos - len(existentes)
        trades = [dict(t, lote=lote) for t in trades]

    clave = lambda t: (t["ticker"], t["buy_date"], t["buy_price"],               # noqa: E731
                       t["sell_date"], t["sell_price"], t["qty"])
    vistas = {clave(t) for t in existentes}

    agregados = 0
    for t in trades:
        if clave(t) in vistas:
            continue
        existentes.append(t)
        vistas.add(clave(t))
        agregados += 1

    datos[nombre] = existentes
    _escribir(REALIZADO, datos)
    return {"agregados": agregados, "reemplazados": reemplazados,
            "total": len(existentes)}


def quitar_realizado(nombre: str, filtro: dict) -> int:
    """Saca los registros que coinciden con todos los campos de `filtro`."""
    datos = _leer(REALIZADO)
    existentes = datos.get(nombre, [])
    if not filtro:
        return 0
    quedan = [t for t in existentes
              if not all(str(t.get(k, "")) == str(v) for k, v in filtro.items())]
    datos[nombre] = quedan
    _escribir(REALIZADO, datos)
    return len(existentes) - len(quedan)
