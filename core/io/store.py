"""
store.py — Dónde viven las carteras del usuario.

JSON plano en `data/`, gitignored. Es el único dato de la aplicación que **no**
es regenerable: la caché de precios y la serie MEP se vuelven a bajar, pero si
se pierden las carteras se pierde el trabajo del usuario.

Tres archivos, porque son tres cosas distintas:

    portfolios.json   posiciones abiertas — lo que tenés hoy
    realized.json     operaciones cerradas — lo que ya ganaste o perdiste
    plazas.json       desde qué mercado se mira cada cartera, cuando se eligió

`plazas.json` guarda **sólo las excepciones**: la plaza normalmente se deduce de
dónde cotizan los activos (`mercado.de_posiciones`) y no hace falta anotar nada.
Se escribe cuando el usuario dice otra cosa —un europeo con acciones de EE.UU.
que quiere medir en euros—, que es lo que ninguna posición puede decir. Va en un
archivo aparte para no tocar el formato de las carteras, que es el que entra y
sale por CSV.

Borrar una cartera NO borra su P&L realizado. Es historia: que hayas cerrado
todas las posiciones no significa que esas ganancias no hayan existido.
"""

import contextvars
import io
import json
import os
from datetime import datetime, timezone
from pathlib import Path

_DATA = Path(__file__).resolve().parents[2] / "data"
_EJEMPLOS = Path(__file__).resolve().parents[2] / "examples"

# Con qué estrena el que entra por primera vez: una cartera por plaza. No es
# decoración — la app tiene tres formas de mirar una cartera (Argentina, Europa,
# EE.UU.) y con una sola cartera argentina las otras dos no se pueden ni ver. La
# plaza de cada una la deduce `mercado.de_posiciones` de dónde cotizan sus
# activos, así que no hay nada que configurar.
MODELOS = {
    "Modelo Argentina": _EJEMPLOS / "modelo.csv",
    "Modelo Europa": _EJEMPLOS / "modelo-europa.csv",
    "Modelo EE.UU.": _EJEMPLOS / "modelo-eeuu.csv",
}
CARTERAS = _DATA / "portfolios.json"
REALIZADO = _DATA / "realized.json"

# ── De quién son las carteras que se están leyendo ────────────────────────────
# En la app local no hay pregunta: son las del dueño de la máquina, y viven en
# `data/`. Servida en la web hay muchos usuarios en el mismo proceso, y cada uno
# tiene que ver sólo lo suyo — es la única información personal que queda en
# nuestro disco, porque credenciales ya no guardamos ninguna.
#
# Es un ContextVar y no un global porque Flask atiende varias requests a la vez
# en hilos distintos: un global se pisaría entre usuarios, que es exactamente la
# forma de mostrarle a alguien la cartera de otro.

_usuario = contextvars.ContextVar("usuario", default=None)


def como(carpeta):
    """Fija de quién son los datos por el resto de este request. None = local."""
    _usuario.set(carpeta)


def quien():
    return _usuario.get()


def _dir() -> Path:
    carpeta = _usuario.get()
    return _DATA if carpeta is None else _DATA / "usuarios" / str(carpeta)


def _carteras() -> Path:
    return CARTERAS if _usuario.get() is None else _dir() / "portfolios.json"


def _realizado() -> Path:
    return REALIZADO if _usuario.get() is None else _dir() / "realized.json"


def _perfil() -> Path:
    return _dir() / "perfil.json"


def anotar(usuario: dict) -> None:
    """Deja constancia de quién es el dueño de esta carpeta.

    La app no necesita el email para funcionar —la carpeta la nombra el `sub` de
    Google— pero sin él la lista de altas son veinte dígitos sin cara. Se guarda
    dentro de la carpeta del usuario, con los mismos permisos 600 que sus
    carteras, y no en un registro central: así borrar a alguien sigue siendo
    borrar un directorio.

    `alta` se escribe una sola vez; `visto` en cada ingreso.
    """
    if quien() is None:
        return                     # en local no hay a quién anotar
    antes = _leer(_perfil())
    ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _escribir(_perfil(), {**antes,
                          "sub": quien(),
                          "email": usuario.get("email", ""),
                          "nombre": usuario.get("nombre", ""),
                          "alta": antes.get("alta") or ahora,
                          "visto": ahora})


def altas() -> list:
    """Todos los que entraron alguna vez, del más viejo al más nuevo."""
    perfiles = [_leer(d / "perfil.json") for d in (_DATA / "usuarios").glob("*") if d.is_dir()]
    return sorted([p for p in perfiles if p],
                  key=lambda p: (p.get("alta", ""), p.get("sub", "")))


def _plazas() -> Path:
    return _dir() / "plazas.json"


def plaza(nombre: str):
    """La plaza que el usuario fijó para esa cartera, o None si no fijó ninguna."""
    return _leer(_plazas()).get(nombre) or None


def plazas() -> dict:
    return _leer(_plazas())


def fijar_plaza(nombre: str, clave) -> None:
    """Fija la plaza de una cartera. Sin clave, vuelve a deducirse sola."""
    datos = _leer(_plazas())
    if clave:
        datos[nombre] = clave
    elif nombre not in datos:
        return                      # nada que borrar: no se escribe por las dudas
    else:
        del datos[nombre]
    _escribir(_plazas(), datos)

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
    if quien() is not None:
        # Servida en la web, la cartera de alguien es lo único personal que queda
        # en disco: no tiene por qué leerla ningún otro proceso de la máquina.
        # El vault usa los mismos permisos por la misma razón.
        try:
            os.chmod(ruta, 0o600)
            os.chmod(ruta.parent, 0o700)
        except OSError:
            pass


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
        # De qué importación vino, para poder pisarla sin tocar lo demás. El
        # `source` no sirve para eso: además de marcar el origen, decide de
        # dónde sale el precio, así que un valor inventado ahí deja a un bono
        # sin cotización. Vacío = cargada a mano.
        "lote": str(posicion.get("lote", "") or "").strip(),
    }


# ── Carteras ──────────────────────────────────────────────────────────────────

def nombres() -> list:
    return sorted(_leer(_carteras()).keys())


def cargar(nombre: str) -> list:
    return [_normalizar(p) for p in _leer(_carteras()).get(nombre, [])]


def cargar_todas() -> dict:
    return {n: [_normalizar(p) for p in ps] for n, ps in _leer(_carteras()).items()}


def guardar(nombre: str, posiciones: list) -> int:
    datos = _leer(_carteras())
    limpias = [_normalizar(p) for p in posiciones if str(p.get("ticker", "")).strip()]
    datos[nombre] = limpias
    _escribir(_carteras(), datos)
    return len(limpias)


def borrar(nombre: str) -> bool:
    """Borra la cartera. El P&L realizado queda: es historia, no estado."""
    datos = _leer(_carteras())
    if nombre not in datos:
        return False
    del datos[nombre]
    _escribir(_carteras(), datos)
    fijar_plaza(nombre, None)
    return True


def duplicar(origen: str, destino: str) -> int:
    n = guardar(destino, cargar(origen))
    fijar_plaza(destino, plaza(origen))
    return n


def sembrar() -> bool:
    """Le deja al usuario nuevo una cartera modelo por plaza. Devuelve si sembró.

    Una app de carteras vacía no se puede recorrer: sin posiciones no hay
    riesgo, ni frontera, ni Monte Carlo que mirar, y el que entra por primera
    vez no ve qué hace la herramienta hasta después de cargar diez lotes a mano.
    Son tres y no una porque la app mira una cartera desde tres plazas, y con
    una sola cartera argentina las otras dos no se pueden ni ver.

    Se siembra **una sola vez**, y la condición es que el archivo de carteras no
    exista todavía. Borrarlas lo escribe —aunque quede vacío—, así que las
    carteras modelo no reaparecen en el próximo ingreso: si las borraste, las
    borraste.
    """
    if _carteras().exists():
        return False

    from core.io import csv_native

    sembradas = 0
    for nombre, ruta in MODELOS.items():
        if not ruta.exists():
            continue
        texto = ruta.read_text(encoding="utf-8-sig")
        posiciones = csv_native.read_positions(io.StringIO(texto))
        if not posiciones:
            continue
        guardar(nombre, posiciones)
        realizadas = csv_native.read_realizado(io.StringIO(texto))
        if realizadas:
            agregar_realizado(nombre, realizadas, "modelo")
        sembradas += 1
    return sembradas > 0


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


def reemplazar_source(nombre: str, source: str, nuevas: list) -> dict:
    """Deja en la cartera exactamente los lotes que vienen de ese `source`.

    Lo que llega del broker es una foto consolidada, no un historial: al
    re-sincronizar cambian la cantidad y el PPC del mismo fondo, y `agregar` los
    vería como lotes nuevos y los duplicaría. Acá se pisan los anteriores.

    Lo cargado a mano no se toca nunca: sólo se reemplaza lo que tiene ese
    mismo `source`.
    """
    previas = cargar(nombre)
    resto = [p for p in previas if (p.get("source") or "") != source]
    limpias = [_normalizar(x) for x in nuevas if str(x.get("ticker") or "").strip()]
    guardar(nombre, resto + limpias)
    return {"importadas": len(limpias), "reemplazadas": len(previas) - len(resto),
            "total": len(resto) + len(limpias)}


def reemplazar_lote(nombre: str, lote: str, nuevas: list) -> dict:
    """Deja en la cartera exactamente las posiciones de esa importación.

    Gemela de `reemplazar_source`, pero marcando por importación y no por
    proveedor de precios: lo que viene del broker son CEDEARs y bonos, que ya
    necesitan su propio `source` para que la cotización salga de donde debe.

    Lo cargado a mano no lleva lote y no lo toca ninguna reimportación.
    """
    if not lote:
        raise ValueError("Sin lote no se puede reemplazar nada sin riesgo.")
    previas = cargar(nombre)
    resto = [p for p in previas if (p.get("lote") or "") != lote]
    limpias = [_normalizar(dict(x, lote=lote)) for x in nuevas
               if str(x.get("ticker") or "").strip()]
    guardar(nombre, resto + limpias)
    return {"importadas": len(limpias), "reemplazadas": len(previas) - len(resto),
            "total": len(resto) + len(limpias)}


# ── P&L realizado ─────────────────────────────────────────────────────────────

def _normalizar_trade(t: dict) -> dict:
    """Fechas a ISO. Es lo único que hay que tocar: el resto ya viene tipado.

    Sin esto la deduplicación no ve como iguales a dos importaciones del mismo
    archivo: Yahoo exporta "20250919" y el CSV propio "2025-09-19", así que la
    clave difiere y el mismo trade entra dos veces. Pasó en MAMI —11 operaciones
    duplicadas, el realizado dio 4.588 en vez de 2.300— y no se ve a simple
    vista, porque las dos copias son legítimas cada una por su lado.
    """
    from core.io.csv_native import normalizar_fecha

    return {**t, "buy_date": normalizar_fecha(t.get("buy_date", "")),
            "sell_date": normalizar_fecha(t.get("sell_date", ""))}


def cargar_realizado(nombre: str) -> list:
    return [_normalizar_trade(t) for t in _leer(_realizado()).get(nombre, [])]


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
    datos = _leer(_realizado())
    existentes = [_normalizar_trade(t) for t in datos.get(nombre, [])]
    trades = [_normalizar_trade(t) for t in trades]
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
    _escribir(_realizado(), datos)
    return {"agregados": agregados, "reemplazados": reemplazados,
            "total": len(existentes)}


def quitar_realizado(nombre: str, filtro: dict) -> int:
    """Saca los registros que coinciden con todos los campos de `filtro`."""
    datos = _leer(_realizado())
    existentes = datos.get(nombre, [])
    if not filtro:
        return 0
    quedan = [t for t in existentes
              if not all(str(t.get(k, "")) == str(v) for k, v in filtro.items())]
    datos[nombre] = quedan
    _escribir(_realizado(), datos)
    return len(existentes) - len(quedan)


# ── Qué cartera es cada comitente ─────────────────────────────────────────────
# Vivía en `data/connectors.json`, y ahí no puede seguir por dos razones. Es el
# nombre de la cartera de alguien, así que es suyo y no de todos. Y ese archivo
# guarda además el client secret de Google: escribirlo desde una acción del
# usuario, con leer-modificar-escribir y sin lock, es una forma de perderlo si
# dos importan a la vez.

def _mapa_cocos() -> Path:
    return _dir() / "cocos.json"


def cartera_de_cuenta(cuenta: str):
    """Nombre de la cartera asociada a ese comitente, o None."""
    if not cuenta:
        return None
    propio = _leer(_mapa_cocos()).get(str(cuenta))
    if propio or quien() is not None:
        return propio
    # App local: la asociación vieja sigue en connectors.json. Se lee de ahí una
    # última vez para no perderla; la próxima importación ya la escribe acá.
    from core.data import connectors
    return connectors.cartera_de_cuenta(cuenta)


def asociar_cuenta(cuenta: str, cartera: str) -> None:
    mapa = _leer(_mapa_cocos())
    mapa[str(cuenta)] = cartera
    _escribir(_mapa_cocos(), mapa)
