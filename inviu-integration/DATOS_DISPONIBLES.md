# Qué se puede sacar de la API de InvIU

Capturado en vivo con tu cuenta real (`Cuenta 234424`, cuenta CVAL/BYMA con
gestión discrecional a cargo de un asesor). Todos los endpoints son
`https://inviuxy.inviu.com.ar/investor/...` salvo que se diga otra cosa, y
todos requieren el header `Authorization: Bearer {idToken}`.

## 1. Cartera actual (posiciones abiertas)

`GET /managed-portfolio/v4/account/{accountId}?term=24HS`

Por cada tenencia (bonos, CEDEARs, acciones, FCI — lo que tengas):
- ticker, nombre, cantidad total y disponible (`availableQuantity` vs
  `unavailableQuantity`, esto último son títulos en garantía/caución)
- precio de compra promedio (**en ARS y en USD por separado**, cada uno con
  su propio `invested`/PPC/% — no hay que reconvertir nada a mano)
- valuación actual (unitaria y total)
- **P&L no realizado**: `performance.pnl` (valor y %) y `performance.ppc`
  (contra el precio promedio de compra)
- `hasCollateral` (si está en garantía) y `availableToOperate`

Junto con eso, en la misma respuesta:
- patrimonio total y por categoría (`ARG_PESOS`, `US_DOLLARS`, `BOND`,
  `CEDEAR`, etc., con `sharePercent` de cada una)
- saldos disponibles por plazo de liquidación (`0HS`/`24HS`/`48HS`) y moneda
- tipo de cambio que usa InvIU internamente (`exchangeRate`,
  `exchangeRateByCurrency`)

## 2. Operaciones — abiertas y cerradas

`GET /investor/accounts/{accountId}/operations`

Historial de órdenes con `status` (`FILLED`, y presumiblemente `PENDING`/
`CANCELLED`/`REJECTED` — solo vi `FILLED` en tu cuenta), `operationType`
(`PLACEMENT`/`BORROWING` para cauciones, y el resto de compra/venta),
cantidad pedida vs ejecutada (`execution.pendingQuantity`), precio ejecutado,
canal (`DISCRETIONARY_MANAGEMENT` = lo operó tu asesor, `APPSMITH` = un panel
interno de InvIU). Esto es lo más parecido a "posiciones cerradas": cada
caución tomadora/colocadora sale como una operación con su resultado.

## 3. Movimientos de cartera (asientos, no cash)

`GET /clients/{clientId}/account/{accountId}/movements`

Cada asiento: activo (ticker, tipo, mercado), importe, precio, fecha de
concertación y de liquidación, y el **saldo acumulado** después de ese
movimiento (`accumulatedBalance`) — sirve para reconstruir la cartera en
cualquier fecha pasada sin tener que sumar todo a mano.

## 4. Movimientos de efectivo

`GET /investor/cash-movements?accountId={accountId}`

Depósitos, retiros, cobros de renta/amortización. Vacío en tu cuenta al
momento de la captura, pero el shape es `{paging, results[]}` igual que el
resto.

## 5. Rendimiento y evolución patrimonial

- `GET /account/{accountId}/performance?custodian=CVAL&clientId={clientId}` —
  performance simple (%, valuación).
- `GET /performance/aum-evolution/account/{accountId}?from=...&to=...&currency=USD` —
  el más rico: serie diaria de patrimonio (`aum` por día), **flujos de
  entrada/salida separados del rendimiento real** (`cashflowIn`/`cashflowOut`),
  foto de tenencias al inicio y al final del período (`initialHoldings`/
  `finalHoldings`, con `sharePercent` de cada activo), y un resumen con
  **TIR** (`tir`, `annualTir`) y ganancia estimada.

## 6. Flujo de fondos proyectado (solo para bonos)

`GET /account/{accountId}/projected-cashflows/v2?clientId={clientId}`

Para cada bono en cartera: próximos pagos de renta/amortización (fecha,
importe, moneda), y métricas de riesgo de tasa por moneda: **duration
modificada, convexidad, DV01 y TIR** agregada de la posición en bonos.

## 7. Poder de compra y límites

- `GET /account/{accountId}/buying-power` — límite autorizado, usado, % usado
  (relevante si operás con margen/caución).
- `GET /account/{accountId}/balances?clientId={clientId}` — disponible,
  poder de compra, y **capacidad de colocar/tomar caución**
  (`repurchase_agreement_placement`), todo desagregado por plazo (T+0/24/48h
  y a más de 48h) y moneda (ARS/USD/USD cable).

## 8. Universo de instrumentos operables

`GET /products/v3/BYMA?limit=5000`

El catálogo completo de lo que se puede operar en BYMA desde InvIU: ticker,
ISIN, tipo y subtipo de activo, moneda, si está habilitado para operar,
tamaño de lote mínimo. Sirve como maestro de instrumentos sin depender de
otra fuente.

## 9. Datos de la cuenta y del titular

- `GET /user/info` — datos personales completos (domicilio, fecha de
  nacimiento, estado civil, documento), perfil de riesgo (`riskProfile`),
  y **datos del asesor asignado** (nombre, mail, si tenés firmado mandato de
  gestión discrecional).
- `GET /account-details-v2/{accountId}` — CUIT, contacto, relación con la
  cuenta.
- `GET /settings` — parámetros de la plataforma (multiplicadores de precio
  por tipo de activo, monedas habilitadas) — más útil para saber cómo
  interpretar los otros endpoints que como dato en sí.
- `GET /notifications` — avisos de la plataforma.

## Lo que falta explorar

No pasé por "Depósitos y retiros" (puede ser el mismo `cash-movements`) ni
confirmé si `/operations` pagina o trae todo el historial de una — con más
volumen de operaciones habría que revisar si acepta `limit`/`offset` como
`managed-portfolio` y `products`.
