"""
noticias.py — Contexto de mercado desde RSS públicos.

Sirve para leer un movimiento de la cartera junto a lo que estaba pasando. No
pretende explicar nada: que una noticia coincida con una caída no significa que
la haya causado — el mismo criterio que el calendario de `regimenes.py`.

Se parsea con `xml.etree` de la biblioteca estándar en vez de agregar
`feedparser`: son treinta líneas y un RSS es XML plano. Una dependencia menos
que mantener.

Todas las fuentes son públicas y sin credencial, como el resto de lo que no es
Cocos ni FMP.
"""

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from xml.etree import ElementTree

import requests

from core.data import cache

FUENTES = [
    ("Ámbito · Economía",   "https://www.ambito.com/rss/economia.xml",            "economia"),
    ("Ámbito · Finanzas",   "https://www.ambito.com/rss/finanzas.xml",            "mercados"),
    ("Cronista · Mercados", "https://www.cronista.com/files/rss/mercados-online.xml", "mercados"),
    ("Infobae · Economía",  "https://www.infobae.com/feeds/rss/economia/",        "economia"),
    ("iProfesional",        "https://www.iprofesional.com/rss/finanzas",          "mercados"),
    ("Bloomberg Línea",     "https://www.bloomberglinea.com/arc/outboundfeeds/rss/?outputType=xml", "mundo"),
]

_TTL_MINUTOS = 20
_HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/rss+xml, application/xml"}


def _texto(elemento, etiqueta):
    hijo = elemento.find(etiqueta)
    return (hijo.text or "").strip() if hijo is not None and hijo.text else ""


def _limpiar(html: str) -> str:
    """Los feeds meten HTML en la descripción. Se saca sin traer un parser."""
    sin_tags = re.sub(r"<[^>]+>", " ", html or "")
    return re.sub(r"\s+", " ", sin_tags).strip()


def _fecha_iso(texto: str):
    """Los RSS usan RFC-822; algunos, ISO. Se prueban los dos y se normaliza."""
    if not texto:
        return None
    for formato in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z",
                    "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            d = datetime.strptime(texto.strip(), formato)
            if d.tzinfo is None:
                d = d.replace(tzinfo=timezone.utc)
            return d.astimezone(timezone.utc).isoformat()
        except ValueError:
            continue
    return None


def _leer_fuente(fuente):
    nombre, url, seccion = fuente
    try:
        r = requests.get(url, timeout=8, headers=_HEADERS)
        r.raise_for_status()
        raiz = ElementTree.fromstring(r.content)
    except Exception as e:
        print(f"  [noticias] {nombre}: {type(e).__name__}")
        return []

    salida = []
    for item in raiz.iter("item"):
        titulo = _texto(item, "title")
        if not titulo:
            continue
        salida.append({
            "titulo": titulo,
            "resumen": _limpiar(_texto(item, "description"))[:260],
            "enlace": _texto(item, "link"),
            "fecha": _fecha_iso(_texto(item, "pubDate")),
            "fuente": nombre, "seccion": seccion,
        })
    return salida


def ultimas(limite: int = 40, seccion: str = None) -> dict:
    """Titulares de todas las fuentes, ordenados por fecha.

    Las seis se piden en paralelo: en serie, una fuente lenta retrasa a todas.
    Cacheado 20 minutos — es contexto, no un ticker en vivo.
    """
    guardado = cache.leer_respuesta("noticias:todas", _TTL_MINUTOS / 60, default=None)
    if guardado is None:
        with ThreadPoolExecutor(max_workers=6) as pool:
            listas = list(pool.map(_leer_fuente, FUENTES))
        guardado = [n for lista in listas for n in lista]
        guardado.sort(key=lambda n: n["fecha"] or "", reverse=True)
        if guardado:
            cache.guardar_respuesta("noticias:todas", guardado)

    items = [n for n in guardado if not seccion or n["seccion"] == seccion]
    activas = sorted({n["fuente"] for n in guardado})
    return {
        "noticias": items[:limite],
        "total": len(items),
        "fuentes_activas": activas,
        "fuentes_caidas": [f[0] for f in FUENTES if f[0] not in activas],
        "nota": "Contexto de mercado. Que una noticia coincida con un movimiento "
                "de la cartera no significa que lo haya causado.",
    }


def por_cartera(posiciones, limite: int = 25) -> dict:
    """Titulares que mencionan alguno de tus activos.

    Se busca por el nombre de la empresa, no por el ticker: ningún medio escribe
    "GGAL.BA" en un titular. El nombre sale del `.info` que ya está cacheado, así
    que no cuesta consultas nuevas.
    """
    from core.data import sources

    nombres = {}
    for p in posiciones:
        ticker = str(p["ticker"]).upper()
        info = sources.info(sources.base_symbol(ticker))
        largo = (info.get("longName") or info.get("shortName") or "").strip()
        if largo:
            # "Grupo Financiero Galicia S.A." → "Grupo Financiero Galicia"
            clave = re.sub(r"\b(s\.?a\.?|inc\.?|corp\.?|ltd\.?|plc|group|company)\b",
                           "", largo, flags=re.I).strip(" .,")
            if len(clave) > 3:
                nombres[clave.lower()] = ticker

    todas = ultimas(limite=300)["noticias"]
    encontradas = []
    for n in todas:
        texto = (n["titulo"] + " " + n["resumen"]).lower()
        tocados = sorted({t for clave, t in nombres.items() if clave in texto})
        if tocados:
            encontradas.append({**n, "activos": tocados})

    return {"noticias": encontradas[:limite], "total": len(encontradas),
            "activos_buscados": sorted(set(nombres.values()))}
