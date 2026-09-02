"""
csv_native.py — El formato propio de carteras: entra y sale sin perder nada.

Lo que se exporta se vuelve a importar y da exactamente la misma cartera. Es una
verdad testeada, no una intención: `tests/test_verdades.py` compara campo por
campo después de la ida y vuelta.

Las tres columnas de control existen por errores de valuación concretos:

    source      "cocos" marca el instrumento como bono cotizado cada 100
                nominales. Sin esto, una ON que no figure en las tablas vale
                100 veces de más — pasó con TLCPO.BA.
    currency    anula la detección automática de moneda para el ticker que la
                convención no acierte, sin tocar código.
    asset_type  anula la clasificación por tipo para instrumentos nuevos.

Son la válvula de escape del sistema: cuando una regla automática falla con un
instrumento raro, se arregla editando una celda en vez de esperando una versión.
"""

import csv
import io
import re
from pathlib import Path

COLUMNAS = ["ticker", "buy_date", "buy_price", "qty",
            "commissions", "source", "currency", "asset_type", "notes"]

_NUMERICAS = ("buy_price", "qty", "commissions")
_TEXTO = ("ticker", "buy_date", "source", "currency", "asset_type", "notes")


def _abrir_lectura(origen):
    """Acepta ruta, texto o file object. Devuelve (file_obj, hay_que_cerrarlo)."""
    if hasattr(origen, "read"):
        return origen, False
    ruta = Path(origen)
    if ruta.exists():
        return open(ruta, newline="", encoding="utf-8-sig"), True
    return io.StringIO(str(origen)), False       # el CSV vino como string


def normalizar_fecha(valor: str) -> str:
    """A YYYY-MM-DD. Acepta los formatos que aparecen en datos reales.

    Las carteras exportadas de Yahoo traen "20250919" sin guiones, y esa fecha
    después se usa para buscar el MEP del día de la compra: si no parsea, la
    conversión a dólares falla en silencio o usa la fecha equivocada.
    """
    v = (valor or "").strip()
    if not v:
        return ""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
        return v
    if re.fullmatch(r"\d{8}", v):                       # 20250919
        return f"{v[:4]}-{v[4:6]}-{v[6:]}"
    m = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", v)   # 19/09/2025
    if m:
        d, mes, a = m.groups()
        return f"{a}-{int(mes):02d}-{int(d):02d}"
    return v          # se devuelve tal cual: mejor un dato raro visible que uno inventado


def _numero(valor, default=0.0) -> float:
    """Tolera coma decimal y separador de miles: "1.234,56" y "1234.56"."""
    if valor is None or valor == "":
        return default
    if isinstance(valor, (int, float)):
        return float(valor)
    v = str(valor).strip()
    if "," in v and "." in v:                # 1.234,56 → formato es-AR
        v = v.replace(".", "").replace(",", ".")
    elif "," in v:
        v = v.replace(",", ".")
    try:
        return float(v)
    except ValueError:
        return default


def read_positions(origen) -> list:
    """Lee posiciones. Un lote por fila; se admiten varios lotes del mismo ticker.

    Acepta también encabezados de otras exportaciones (`symbol`, `price`,
    `quantity`, `commission`), para que un CSV armado a mano no falle por el
    nombre de una columna.
    """
    f, cerrar = _abrir_lectura(origen)
    try:
        filas = list(csv.DictReader(f))
    finally:
        if cerrar:
            f.close()

    salida = []
    for fila in filas:
        d = {(k or "").strip().lower(): (v if v is not None else "")
             for k, v in fila.items()}
        ticker = (d.get("ticker") or d.get("symbol") or "").strip().upper()
        if not ticker:
            continue
        salida.append({
            "ticker": ticker,
            "buy_date": normalizar_fecha(d.get("buy_date") or d.get("trade date")
                                         or d.get("date") or ""),
            "buy_price": _numero(d.get("buy_price") or d.get("purchase price")
                                 or d.get("price")),
            "qty": _numero(d.get("qty") or d.get("quantity"), 0.0),
            "commissions": _numero(d.get("commissions") or d.get("commission")),
            "source": (d.get("source") or "").strip().lower(),
            "currency": (d.get("currency") or "").strip().upper(),
            "asset_type": (d.get("asset_type") or "").strip(),
            "notes": (d.get("notes") or "").strip(),
        })
    return salida


def write_positions(destino, posiciones) -> int:
    """Escribe en el formato propio. Devuelve cuántas filas escribió.

    Los números salen sin formato de miles ni coma decimal: el archivo es para
    volver a entrar, no para leerlo en una planilla. La versión legible es la
    exportación de reporte, que es otra función.
    """
    if hasattr(destino, "write"):
        f, cerrar = destino, False
    else:
        f, cerrar = open(destino, "w", newline="", encoding="utf-8"), True
    try:
        w = csv.DictWriter(f, fieldnames=COLUMNAS, extrasaction="ignore")
        w.writeheader()
        n = 0
        for p in posiciones:
            w.writerow({
                **{c: str(p.get(c, "") or "") for c in _TEXTO},
                **{c: _numero(p.get(c)) for c in _NUMERICAS},
            })
            n += 1
        return n
    finally:
        if cerrar:
            f.close()


def plantilla() -> str:
    """La plantilla de ejemplo, para descargar desde la interfaz."""
    ruta = Path(__file__).resolve().parents[2] / "examples" / "plantilla_cartera.csv"
    return ruta.read_text(encoding="utf-8") if ruta.exists() else ",".join(COLUMNAS) + "\n"
