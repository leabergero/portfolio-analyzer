"""
inviu_sesion_web.py — Genera el código para activar InvIU en la versión web.

No hace falta correr el servidor de esta app ni tener un vault local: solo
Playwright (ya viene en requirements.txt) y tu usuario y clave de InvIU. Abre
un Chrome real, completa el formulario, y lo que sigue es lo de siempre:
el reCAPTCHA de InvIU (invisible) corre solo por tratarse de un navegador de
verdad, y si aparece el código que llega por mail o algún challenge visible,
se resuelven a mano en esa misma ventana antes de que el script siga.

Ni el usuario ni la clave quedan guardados en ningún lado — viajan una sola
vez, en memoria, para tipearlos en el formulario de InvIU. Los tokens que
resultan del login sí viajan: al terminar, este script abre tu navegador
directo en la pantalla de InvIU de la versión web con el código ya cargado —
va como fragmento de la URL (lo que sigue al `#`), que el navegador nunca le
manda a ningún servidor, solo lo lee el JavaScript de esa misma página. Ahí
alcanza con apretar "Usar esta sesión": el servidor lo valida una vez contra
InvIU y lo devuelve envuelto en un sobre firmado que vive en tu navegador —
no lo guarda.

Uso:
    python -m core.broker.inviu_sesion_web
    python -m core.broker.inviu_sesion_web --email vos@mail.com
    python -m core.broker.inviu_sesion_web --url http://localhost:5002
"""

import argparse
import base64
import getpass
import json
import webbrowser
from urllib.parse import quote

from core.broker import inviu

URL_WEB_POR_DEFECTO = "https://portfolio.quantcentral.eu"


def generar(email: str, password: str) -> str:
    tokens = inviu._login_navegador(email=email, password=password)
    return base64.b64encode(json.dumps(tokens).encode()).decode()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--email")
    ap.add_argument("--url", default=URL_WEB_POR_DEFECTO,
                     help="Base de la versión web (default: producción)")
    args = ap.parse_args()
    email = args.email or input("Email de InvIU: ").strip()
    password = getpass.getpass("Clave de InvIU: ")
    print()
    print("Se abrió una ventana de Chrome. Si InvIU pide un código por mail "
          "o un captcha visible, resolvelo ahí — el script sigue solo.")
    print()
    codigo = generar(email, password)
    destino = f"{args.url}/#inviu-web={quote(codigo)}"
    print("Abriendo tu navegador en la pantalla de InvIU. Si no se abre solo, "
          "pegá esto ahí:")
    print(codigo)
    webbrowser.open(destino)
