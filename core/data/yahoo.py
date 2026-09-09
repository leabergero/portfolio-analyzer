"""
yahoo.py — Una sola sesión HTTP contra Yahoo, para toda la aplicación.

`yfinance` abre una sesión nueva por cada `Ticker` que se crea y no la cierra:
las conexiones quedan a medio cerrar —en `CLOSE-WAIT`— y se acumulan mientras el
proceso viva. En el servidor había nueve después de unas horas, y el proceso de
gunicorn vive semanas: cada una ocupa un descriptor de los 1.024 que tiene el
proceso y los buffers de un socket, en una máquina de 954 MB.

Con una sesión compartida, además, las conexiones se reusan: se ahorra el
handshake TLS de cada pedido, que en una serie de sesenta tickers no es poco.

Es un global a propósito y no un ContextVar: la sesión no es de un usuario ni de
un request, es del proceso, y `curl_cffi` la maneja bien desde varios hilos.
"""

_sesion = None


def sesion():
    global _sesion
    if _sesion is None:
        from curl_cffi import requests
        # `impersonate` es lo que hace que Yahoo conteste: sin eso responde 429
        # a cualquier cliente que no parezca un navegador. Es lo mismo que hace
        # yfinance por dentro cuando no se le pasa sesión.
        _sesion = requests.Session(impersonate="chrome")
    return _sesion


def ticker(simbolo: str):
    """Un `yfinance.Ticker` sobre la sesión compartida."""
    import yfinance as yf

    return yf.Ticker(simbolo, session=sesion())
