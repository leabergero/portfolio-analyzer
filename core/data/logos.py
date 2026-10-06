"""
logos.py — El logo de cada papel, bajado una vez y servido desde el server.

La página no carga imágenes de afuera (CSP), así que el logo se baja acá la
primera vez que alguien lo pide, se achica a 32×32 y queda en `data/logos/`.
Si no aparece en ninguna fuente se anota el intento y se reintenta a la semana.

De dónde sale, en orden:

  · un bono, letra u ON: la bandera del país emisor —hoy todos argentinos—;
  · un FCI de Cocos: la bandera de su moneda (pesos → AR, dólares → EE.UU.);
  · el CDN público de Cocos (`AAPL.jpg`, `GGAL.jpg`), que cubre acciones y CEDEARs;
  · FMP, que cubre lo que Cocos no lista (AIR.PA, ASML.AS).
"""

import io
import re
import time
from pathlib import Path

import requests

from core.data.symbols import base_symbol, is_bond, strip_ba

DIR = Path(__file__).resolve().parents[2] / "data" / "logos"
REINTENTO = 7 * 86400
LADO = 32

COCOS = "https://assets.cocos.capital/cocos/logos/{}.jpg"
FMP = "https://financialmodelingprep.com/image-stock/{}.png"
BANDERA = "https://flagcdn.com/w80/{}.png"

# El CEDEAR de Alphabet es GOGLD en BYMA; Cocos lo publica como GOOGL.
ALIAS = {"GOGL": "GOOGL"}


def _es_bono_ar(ticker: str) -> bool:
    """Un bono, letra u ON argentina, seguro: por tabla o por llevar un número
    sin sufijo de mercado (AL30D, S15G5D, MCC3D). Las tablas de `symbols` no
    tienen todas las ONs y el logo no sabe de qué posición viene."""
    # ponytail: una acción de EE.UU. cargada sin sufijo y con un número en el
    # símbolo saldría con bandera; sumar el caso acá si aparece.
    if is_bond(ticker) or ("." not in ticker and re.search(r"\d", ticker)):
        return True
    # Con `.BA` un número no alcanza (TGSU2, TECO2 son acciones), y terminar
    # en O tampoco (VALO, AGRO). Una letra (S15G5) o el tramo en dólares de una
    # ON (MGCGOD), sí.
    return bool(re.fullmatch(r"[ST]\d{2}[A-Z]\d{1,2}D?|[A-Z0-9]{3,5}OD", strip_ba(ticker)))


def fuentes(ticker: str) -> list:
    """Las URLs a probar para ese ticker, de la más fiel a la más genérica."""
    t = ticker.upper()
    if t.startswith("CAUCION"):
        return []
    if t.startswith("COCO"):                        # FCI de Cocos
        return [BANDERA.format("us" if "USD" in t else "ar")]
    if _es_bono_ar(t):
        return [BANDERA.format("ar")]
    base = ALIAS.get(base_symbol(strip_ba(t)), base_symbol(strip_ba(t)))
    if "." not in t and t.endswith("D"):
        # Tramo en dólares sin sufijo: un CEDEAR que llegó así de Inviu (QQQD,
        # EWZD) tiene logo en Cocos; una ON sin número (TLCMD, VSCVD), no.
        return [COCOS.format(base), BANDERA.format("ar")]
    # Fuera de BYMA el sufijo es parte del símbolo (AIR.PA); en BYMA, no.
    fmp = t if "." in t and not t.endswith(".BA") else base
    return [COCOS.format(base), FMP.format(fmp)]


def _bajar(url: str):
    """32×32 en PNG, centrado y con transparencia, o None si no es una imagen."""
    from PIL import Image

    try:
        r = requests.get(url, timeout=10)
        if r.status_code != 200 or not r.headers.get("content-type", "").startswith("image"):
            return None
        img = Image.open(io.BytesIO(r.content)).convert("RGBA")
    except Exception:
        return None
    img.thumbnail((LADO, LADO))
    lienzo = Image.new("RGBA", (LADO, LADO), (0, 0, 0, 0))
    lienzo.paste(img, ((LADO - img.width) // 2, (LADO - img.height) // 2))
    salida = io.BytesIO()
    lienzo.save(salida, "PNG", optimize=True)
    return salida.getvalue()


def ruta(ticker: str):
    """El archivo del logo, bajándolo si hace falta. None si no hay logo."""
    t = ticker.upper()
    png, nada = DIR / f"{t}.png", DIR / f"{t}.none"
    if png.exists():
        return png
    if nada.exists() and time.time() - nada.stat().st_mtime < REINTENTO:
        return None
    DIR.mkdir(parents=True, exist_ok=True)
    for url in fuentes(t):
        datos = _bajar(url)
        if datos:
            # Escritura atómica: dos pedidos del mismo logo a la vez no dejan
            # un archivo a medias.
            tmp = png.with_suffix(f".{time.time_ns()}.tmp")
            tmp.write_bytes(datos)
            tmp.replace(png)
            nada.unlink(missing_ok=True)
            return png
    nada.touch()
    return None


if __name__ == "__main__":
    casos = {"AL30D": "ar", "MGCTD": "ar", "S15G5D": "ar", "COCORMA": "ar",
             "COCOSPPA": "ar", "COCOUSDPA": "us", "COCOAUSD": "us"}
    for tk, pais in casos.items():
        assert fuentes(tk) == [BANDERA.format(pais)], (tk, fuentes(tk))
    assert fuentes("AAPLD.BA")[0] == COCOS.format("AAPL")
    assert fuentes("GOGLD.BA")[0] == COCOS.format("GOOGL")
    assert fuentes("AIR.PA")[1] == FMP.format("AIR.PA")
    assert fuentes("CAUCIONT") == []
    assert fuentes("S15G5.BA") == fuentes("MGCGOD.BA") == [BANDERA.format("ar")]
    for accion in ("TGSU2.BA", "VALO.BA", "AGRO.BA", "CTIO.BA"):
        assert "flagcdn" not in fuentes(accion)[0], accion
    assert fuentes("TLCMD") == [COCOS.format("TLCM"), BANDERA.format("ar")]
    assert fuentes("QQQD")[0] == COCOS.format("QQQ")
    assert fuentes("JPM") == [COCOS.format("JPM"), FMP.format("JPM")]
    print("ok")
