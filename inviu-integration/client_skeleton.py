"""
client_skeleton.py — cliente de InvIU, con endpoints confirmados capturando
tráfico real (ver DATOS_DISPONIBLES.md) desde `lab_server.py` con una cuenta
propia. Nada de esto se adivinó del bundle JS: cada URL y cada shape de acá
abajo salió de una respuesta real.

Login en dos pasos (por detrás es AWS Cognito con un "custom challenge", pero
la API de InvIU lo envuelve con su propio contrato):

    1. login(email, password, recaptcha_token) → si hace falta 2FA, devuelve
       el challenge; si no, ya trae los tokens.
    2. responder_challenge(codigo) → con el código que llega por mail, cierra
       el login y guarda idToken/refreshToken.

El único hueco real es `recaptcha_token`: InvIU exige un `g-recaptcha-response`
de Google reCAPTCHA v3 en el primer paso, y eso solo se genera ejecutando el
JS real de Google en un navegador de verdad — no hay forma honesta de armarlo
con `requests` solo. Por eso el login sigue necesitando pasar por
`lab_server.py` (Playwright) para conseguir ese token; una vez logueado, el
resto de este cliente no lo necesita más (usa `idToken`/`refreshToken`, que
duran hasta que caducan).

    ponytail: sin manejo de reintentos ni de refresh automático al vencer el
    idToken — es un cliente de lab para probar contra la cuenta real, no el
    de producción. Si esto se integra a portfolio-analyzer, ahí se le suma el
    patrón de sesión por request que ya tiene cocos.py.
"""

import requests

BASE_API_URL = "https://inviuxy.inviu.com.ar/investor"


class InviuClient:
    def __init__(self):
        self.id_token = None
        self.refresh_token = None
        self.account_id = None
        self.client_id = None
        self.session = requests.Session()

    def _headers(self):
        # Cloudflare delante de la API devuelve 403 ("Just a moment...") al
        # user-agent por defecto de `requests`, sin mirar siquiera el token.
        # Con un user-agent de navegador y el origin/referer reales, pasa.
        return {
            "Authorization": f"Bearer {self.id_token}",
            "Content-Type": "application/json", "Accept": "application/json",
            "X-Platform": "web", "X-Client-Version": "1.0.0",
            "Origin": "https://inversor.inviu.com.ar",
            "Referer": "https://inversor.inviu.com.ar/",
            "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
        }

    def _get(self, ruta, **params):
        r = self.session.get(f"{BASE_API_URL}{ruta}", headers=self._headers(),
                              params=params or None, timeout=15)
        r.raise_for_status()
        return r.json() if r.content else None

    def _post(self, ruta, body):
        r = self.session.post(f"{BASE_API_URL}{ruta}", headers=self._headers(),
                               json=body, timeout=15)
        r.raise_for_status()
        return r.json() if r.content else None

    # ── Login ──────────────────────────────────────────────────────────────

    def login(self, email: str, password: str, recaptcha_token: str) -> dict:
        """Paso 1. Devuelve el challenge (2FA por mail) si hace falta, o ya
        los tokens si la cuenta no lo tiene activado (`isEnrolled`)."""
        datos = self._post("/auth/login/v4", {
            "email": email, "password": password,
            "g-recaptcha-response": recaptcha_token,
        })
        if not datos.get("hasChallenge"):
            self._guardar_tokens(datos["tokens"])
        return datos

    def responder_challenge(self, challenge: dict, codigo: str) -> dict:
        """Paso 2. `challenge` es el dict `{challengeName, challengeSession,
        userId}` que devolvió `login()`. El código del mail va, tal como lo
        manda la app, en un campo que se llama `password` — no es un error de
        este cliente, es así como InvIU arma ese body."""
        datos = self._post("/auth/login-challenge", {
            "challengeName": challenge["challengeName"],
            "challengeSession": challenge["challengeSession"],
            "userId": challenge["userId"],
            "password": codigo,
        })
        self._guardar_tokens(datos)
        return datos

    def _guardar_tokens(self, tokens: dict):
        self.id_token = tokens["idToken"]
        self.refresh_token = tokens.get("refreshToken", self.refresh_token)

    def cargar_cuenta(self):
        """Completa `account_id`/`client_id` desde `/user/info`. Hace falta
        antes de llamar a cualquier endpoint de cuenta de acá abajo."""
        info = self.user_info()
        self.account_id = info["accounts"][0]["id"]
        self.client_id = info["accounts"][0]["userId"]
        return info

    # ── Cartera y operaciones ─────────────────────────────────────────────

    def cartera(self, plazo: str = "24HS") -> dict:
        """Posiciones abiertas: tenencias, PPC en ARS y en USD, P&L, patrimonio
        total por categoría. `plazo` es 24HS/48HS/0HS (liquidación)."""
        return self._get(f"/managed-portfolio/v4/account/{self.account_id}",
                          term=plazo)

    def operaciones(self) -> list:
        """Historial de órdenes con `status` (FILLED/...), cantidad pedida vs
        ejecutada, canal. Lo más parecido a "posiciones cerradas"."""
        return self._get(f"/investor/accounts/{self.account_id}/operations")

    def movimientos(self) -> dict:
        """Asientos de cartera con saldo acumulado después de cada uno."""
        return self._get(f"/clients/{self.client_id}/account/{self.account_id}/movements")

    def movimientos_efectivo(self) -> dict:
        return self._get("/investor/cash-movements", accountId=self.account_id)

    # ── Rendimiento ───────────────────────────────────────────────────────

    def performance(self) -> list:
        return self._get(f"/account/{self.account_id}/performance",
                          custodian="CVAL", clientId=self.client_id)

    def evolucion_patrimonio(self, desde: str, hasta: str, moneda: str = "USD") -> dict:
        """Serie diaria de AUM, flujos in/out separados del rendimiento, foto
        de tenencias al inicio/final del período, y TIR. Fechas ISO
        (`AAAA-MM-DD`)."""
        return self._get(f"/performance/aum-evolution/account/{self.account_id}",
                          **{"from": desde, "to": hasta, "custodian": "cval",
                             "clientId": self.client_id, "currency": moneda})

    def flujo_proyectado(self) -> dict:
        """Próximos pagos de renta/amortización de los bonos en cartera, más
        duration modificada, convexidad, DV01 y TIR por moneda."""
        return self._get(f"/account/{self.account_id}/projected-cashflows/v2",
                          clientId=self.client_id)

    # ── Poder de compra ───────────────────────────────────────────────────

    def poder_compra(self) -> dict:
        return self._get(f"/account/{self.account_id}/buying-power")

    def balances(self) -> dict:
        """Disponible, poder de compra y capacidad de caución, por plazo y
        moneda (ARS/USD/USD cable)."""
        return self._get(f"/account/{self.account_id}/balances",
                          clientId=self.client_id)

    # ── Cuenta y catálogo ─────────────────────────────────────────────────

    def user_info(self) -> dict:
        return self._get("/user/info")

    def account_details(self) -> list:
        return self._get(f"/{self.client_id}/account-details-v2/{self.account_id}")

    def productos(self, mercado: str = "BYMA", limite: int = 5000) -> dict:
        """Catálogo de instrumentos operables: ticker, ISIN, tipo, moneda."""
        return self._get(f"/products/v3/{mercado}", limit=limite)

    def settings(self) -> dict:
        return self._get("/settings")

    def notifications(self) -> dict:
        return self._get("/notifications")


def demo():
    """Self-check sin red: solo valida que las rutas y los headers se arman
    bien. No hay credenciales reales acá."""
    c = InviuClient()
    c.id_token = "fake"
    c.account_id = "acc-1"
    c.client_id = "cli-1"
    assert c._headers()["Authorization"] == "Bearer fake"

    capturado = {}
    def _get_fake(self, ruta, **params):
        capturado["ruta"], capturado["params"] = ruta, params
        return {}
    InviuClient._get = _get_fake

    c.cartera("48HS")
    assert capturado["ruta"] == "/managed-portfolio/v4/account/acc-1"
    assert capturado["params"] == {"term": "48HS"}

    c.evolucion_patrimonio("2026-01-01", "2026-09-01")
    assert capturado["params"]["from"] == "2026-01-01"
    assert capturado["params"]["currency"] == "USD"

    print("ok")


if __name__ == "__main__":
    demo()
