# Integración InvIU — laboratorio de investigación

**La integración real ya está armada y en uso**: `core/broker/inviu.py` +
las rutas `/api/inviu/*` en `api/routes/datos.py`, con su pestaña en
`web/app.jsx` (`Inviu`/`MiInviu`). Esta carpeta queda como referencia de cómo
se descubrió cada endpoint y por qué se tomó cada decisión — ver
`MAPEO_A_PORTFOLIO.md` para el mapeo final y `lab_server.py`/`lab.html` si
hace falta volver a inspeccionar tráfico real de la cuenta.

## Cómo se llegó hasta acá

InvIU **no tiene API pública** (verificado: no hay portal de desarrolladores,
ninguna librería de terceros en GitHub la envuelve). El único camino es el
mismo que ya se usó con Cocos Capital: ingeniería inversa de la API privada
que usa la webapp, y un cliente propio en `core/broker/` que la consuma.

A diferencia de Cocos (que tiene `pycocos`, una librería ya escrita que solo
hubo que parchear), acá no existe nada previo: hay que construirlo desde cero.

## Lo que ya se sacó del bundle JS público

La webapp (`https://inversor.inviu.com.ar`) es Angular y sirve su config y su
JS sin login. De ahí, sin autenticarse, salió esto:

**Dominios:**
- API principal: `https://inviuxy.inviu.com.ar/investor`
- Market data: `https://api-web.inviu.com.ar`

**Autenticación:**
- Tokens `{idToken, refreshToken}`, guardados en `localStorage` del navegador.
- Cabecera: `Authorization: Bearer {idToken}`.
- `POST /auth/refresh` con `{idToken, refreshToken}` → devuelve `{idToken, refreshToken}` nuevos.
- `POST /users/logout` con `{refreshToken}`.
- El formulario de login (`/login`) pide email + contraseña + reCAPTCHA v3
  (site key pública: `6LcYFJAoAAAAADu7zrXYsG6vp7jOzMj3DuLu-nD1`), pero el
  endpoint exacto de login vive en un chunk que Angular carga recién al
  navegar a esa ruta — no está en el HTML inicial, así que no se pudo bajar
  sin ejecutar la app en un navegador real.

**Endpoints de datos (mapeados por nombre, sin probar):**
- `GET /global/all/consolidated-portfolio` — cartera consolidada
- `GET /cval/BYMA/client` — cartera Argentina (BYMA)
- `GET /user/info`, `GET /settings`, `GET /bank-accounts`
- `GET /market-data/snapshot`, `GET /market-data/realtime`
- `GET /orders`, `GET /orders/limits`, `POST /orders/v2`
- `GET /performance/aum-evolution/consolidated`
- `GET /assets/mutual-funds`

## Lo que falta y por qué no lo puedo hacer yo

Necesito capturar el request real de login (URL exacta, body, respuesta) y
confirmar el shape de `consolidated-portfolio`. Eso requiere loguearse de
verdad con una cuenta de InvIU — algo que solo podés hacer vos, con tu propia
cuenta, y que yo no puedo ni debo ejecutar por vos (no tengo ni debo pedirte
tu contraseña).

### Cómo capturarlo (5 minutos)

1. Abrí `https://inversor.inviu.com.ar/login` en Chrome/Firefox.
2. Abrí las DevTools (F12) → pestaña **Network** → filtrá por `Fetch/XHR`.
3. Iniciá sesión con tu cuenta.
4. Buscá el request que dispara al tipear el login (va a `inviuxy.inviu.com.ar`,
   método POST). Con el botón derecho → **Copy → Copy as cURL**.
5. Pegame ese cURL acá (**tachá o reemplazá tu contraseña real antes de
   pegarlo** — solo necesito ver la forma del request, no tus credenciales).
6. De paso, andá a la pantalla de tu cartera y hacé lo mismo con el request
   a `consolidated-portfolio` (ese no tiene contraseña, se puede pegar entero).

Con esos dos cURL completo `core/broker/inviu.py` en `portfolio-analyzer`,
calcado del patrón de `core/broker/cocos.py` (mismo manejo de sesión por
`ContextVar`, mismo sobre firmado en modo web).

## Archivos

- `api_map.txt` — todas las rutas de API encontradas en el bundle, crudo.
- `client_skeleton.py` — arranque del cliente, con lo confirmado ya andando
  (refresh, logout, market data) y el login marcado como `NotImplementedError`
  hasta tener el cURL real.
