"""
inviu_sesion_web.py — Imprime el código para activar InvIU en la versión web.

Se corre en la máquina local, DESPUÉS de conectar InvIU como siempre (botón
"Conectar" del modo desktop, que ya resolvió el reCAPTCHA y guardó la sesión
en el vault local). Lee esos tokens ya obtenidos —nunca la contraseña— y los
imprime en una línea para pegar en la pantalla web de InvIU. El servidor los
valida una vez y los guarda en un sobre firmado en el navegador; no quedan
en ningún lado del lado del servidor.

Uso:
    python -m core.broker.inviu_sesion_web
"""

import base64
import json

from core.broker import inviu, vault


def generar() -> str:
    api_key = vault.clave_guardada(inviu.BROKER)
    if not api_key:
        raise SystemExit("No hay InvIU conectado localmente. Conectalo primero "
                          "desde la pantalla desktop y volvé a correr esto.")
    sesion = vault.cargar_sesion(api_key, inviu.BROKER)
    if not sesion:
        raise SystemExit("No hay sesión guardada de InvIU. Conectalo primero "
                          "desde la pantalla desktop y volvé a correr esto.")
    return base64.b64encode(json.dumps(sesion).encode()).decode()


if __name__ == "__main__":
    print(generar())
