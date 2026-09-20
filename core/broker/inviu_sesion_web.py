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
resultan del login sí viajan: se imprimen en un código de una línea para
pegar en la pantalla de InvIU de la versión web. El servidor los valida una
vez contra InvIU y los devuelve envueltos en un sobre firmado que vive en tu
navegador — no los guarda.

Uso:
    python -m core.broker.inviu_sesion_web
    python -m core.broker.inviu_sesion_web --email vos@mail.com
"""

import argparse
import base64
import getpass
import json

from core.broker import inviu


def generar(email: str, password: str) -> str:
    tokens = inviu._login_navegador(email=email, password=password)
    return base64.b64encode(json.dumps(tokens).encode()).decode()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--email")
    args = ap.parse_args()
    email = args.email or input("Email de InvIU: ").strip()
    password = getpass.getpass("Clave de InvIU: ")
    print()
    print("Se abrió una ventana de Chrome. Si InvIU pide un código por mail "
          "o un captcha visible, resolvelo ahí — el script sigue solo.")
    print()
    print(generar(email, password))
