# Mapeo InvIU → esquema de `portfolio-analyzer`

**Estado: implementado y probado contra la cuenta real.** `core/broker/inviu.py`
y las rutas `/api/inviu/*` en `api/routes/datos.py` ya existen. Lo que sigue
documenta las decisiones tomadas, para quien toque esto después.

## Lo que salió distinto de lo planeado acá abajo

1. **Las posiciones NO salen de `cartera()`, salen de `movimientos()`.**
   `operaciones()` (la ruta que parecía el equivalente de Cocos) solo trae las
   últimas operaciones de la cuenta — 8 registros en una cuenta con más de un
   año de historia — probablemente otro canal, no el libro completo.
   `movimientos()` sí tiene `BUY_OPERATION`/`SELL_OPERATION` desde el
   principio, así que las posiciones abiertas y cerradas se reconstruyen con
   el mismo apareo FIFO de `_netear_fifo`, no con una foto directa.

2. **Esta cuenta rota bonos y CEDEARs entre su clase en pesos y en dólares
   todo el tiempo** (compra AL30, vende AL30D; compra EWZD, vende EWZ). Sin
   agrupar por instrumento subyacente, el primer intento dio **52 posiciones
   "abiertas" contra las 9 reales** que tiene la cuenta — verificado a mano
   contra `cartera()`. La solución: `d_ticker()` de `core/data/symbols.py`
   **siempre**, bono o CEDEAR, y convertir cada pata a USD con el MEP de su
   fecha antes de aparear (igual estrategia que ya usa `cocos.operaciones()`
   para el mismo problema).

3. **`is_cocos_only()` no alcanza para saber si algo es bono.** Es un patrón
   pensado para CSVs sin metadata (`_parece_on` exige un dígito antes de la
   "O" final) y no reconoció YMCXO, TTCDO, IRCPO, VSCVO ni BPOA8 de esta
   cuenta real. InvIU manda `asset.assetType` (`"bond"` / `"cedear"`) en cada
   movimiento — con eso no hace falta adivinar nada.

4. **`d_ticker()` tenía un bug de verdad**, no solo una laguna de esta
   integración: su propia documentación decía "las ONs reemplazan la O
   final" pero el código solo lo hacía para los 13 tickers de la tabla
   `ON_D_TICKER` a mano; cualquier ON nueva caía en "agregar D sin más"
   (`DNC7O` → `"DNC7OD"`, que no cierra contra `DNC7D`). Se corrigió el
   fallback para que cumpla lo que decía su docstring, y se sumaron dos pares
   irregulares confirmados con datos reales (`BPOB8`→`BPB8D`,
   `BPOA8`→`BPA8D`). Con el fix, los 99 tests existentes siguen pasando.

Plan original (sigue vigente para lo que no cambió):

Regla general: **todo lo que venga en ARS se guarda en ARS con su fecha**, y
la conversión a USD la hace `mep.a_usd(monto, fecha)` al importar — igual que
hace `cocos.py` hoy. No hay que convertir nada a mano acá.

## 1. Posiciones abiertas → lotes (`tenencias()`)

Fuente: `cartera()` → `holdingsByCategory[].holdings[]`.

| Campo del lote | De dónde sale |
|---|---|
| `ticker` | `holding["ticker"]`. Los bonos duales (AL30/AL30D) necesitan la misma decisión que ya toma `symbols.d_ticker`/`is_cocos_only` en Cocos: **a confirmar con qué ticker InvIU realmente factura cada holding** (vi `AO28`, `MGCTO` sin sufijo — parece que la API ya devuelve la especie que corresponde, no ambas). |
| `buy_date` | **No viene en `cartera()`** (es una foto, no un historial). Sale de `movimientos()`: la fecha de la primera compra de ese ticker que no esté ya vendida — mismo problema que resuelve `_netear_fifo` con Cocos. |
| `buy_price` | `holding.averagePurchasePrice.amount`, en la moneda que InvIU ya identifica (`averagePurchasePrice.currency`) — no hace falta reconvertir, ya viene separado en `assetPerformanceByCurrency.ARS`/`.USD`. |
| `qty` | `holding.quantity` (ojo: `availableQuantity` + `unavailableQuantity` — lo segundo son títulos en garantía por caución, no hay que perderlos silenciosamente). |
| `currency` | La cuenta es ARS con equivalente USD ya calculado; se guarda en la moneda nativa del instrumento (`averagePurchasePrice.currency`). |
| `source` | `"inviu"` (constante nueva, mismo patrón que `SOURCE_FCI = "cocos-fci"`). |
| `notes` | `holding.name` (la descripción larga, ej. "USD BONO TESORO NACIONAL VTO. 31/10/2028"). |

Las dos categorías de efectivo (`ARG_PESOS`, `US_DOLLARS`) **no son lotes**:
son el saldo de caja, van a la caja de la cartera, no a las tenencias. El
saldo negativo en `US_DOLLARS` (visto en la cuenta real: −US$7.170,70) es la
deuda de la caución tomadora — tiene que restar del patrimonio, no ignorarse.

## 2. Operaciones cerradas → `cerrados[]`

Fuente: `operaciones()`, filtrando `status == "FILLED"` (los `CANCELLED`/
`REJECTED` no movieron nada, se descartan igual que un pedido no ejecutado).

Complicación real, ya vista en la cuenta de prueba: **las cauciones
(`REPURCHASE_AGREEMENT`, `operationType` `PLACEMENT`/`BORROWING`) no son
compra/venta de un instrumento** — son préstamos de corto plazo. No entran en
el apareo FIFO de `_netear_fifo` como si fueran un ticker más: se
contabilizan aparte, como un movimiento financiero (intereses pagados/
cobrados), igual que Cocos ya separa `LOTE_RESULTADOS_FCI` de
`LOTE_OPERACIONES`. Falta decidir el label (`LOTE_CAUCIONES_INVIU`, o similar).

El resto (`BUY`/`SELL` sobre bonos, CEDEARs, acciones) sí entra directo a
`_netear_fifo`, con:

| Campo de compra/venta | De dónde sale |
|---|---|
| `fecha` | `execution.dateExecuted` |
| `orden` | índice del array (ya viene ordenado) |
| `precio` | `execution.averagePrice` |
| `qty` | `execution.quantity` |
| `comision` | no vi comisión separada en las 8 operaciones capturadas — puede venir implícita en `averagePrice` como con Cocos (`amount`/`quantity`), a confirmar con una operación real que sí tenga comisión. |

## 3. Movimientos de cartera → reconstrucción histórica

Fuente: `movimientos()`. Sirve para dos cosas que `cartera()` sola no puede
dar:

- **`buy_date` de lo que ya está en cartera** (punto 1): la primera compra sin
  vender de cada ticker.
- **Depósitos y retiros** (`CASH_IN`/`CASH_OUT`) → van a un registro de
  aportes/retiros de la cartera, **no** a resultado. Ya confirmado con la
  cuenta real: 3× `CASH_IN` = US$20.000,45, 1× `CASH_OUT` = −US$5.000.
- **Amortizaciones** (`AMORTIZATION`) → ingreso de caja real, entra como
  resultado realizado igual que un dividendo.
- **Rentas/cupones** (`INCOME`/`DIVIDEND`) → **usar solo la pata en USD**
  (ticker con sufijo "D"). La pata en ARS del mismo `asset.id` **no es plata
  real, y no es un error dejarla afuera**: confirmado contra la pantalla real
  de InvIU (no solo el ratio de la API) que esa pata viene **negativa** — una
  renta/cobro de verdad entraría en positivo al saldo en pesos, nunca en
  negativo. Es un ajuste técnico de Caja de Valores sobre el valor residual en
  pesos de la clase peso del mismo bono dual (AL30/AL30D, GD35/GD35D, etc.),
  no un movimiento de caja. Importarla sumaría una resta que nunca salió de la
  cuenta. Única excepción vista: `NOW` (CEDEAR sin especie dual) trae un solo
  movimiento en ARS que si es real — ese sí se convierte con MEP de su fecha.

## 4. Rendimiento — no hay que recalcularlo

`evolucion_patrimonio()` ya trae **TIR** (`summary.tir`, `summary.annualTir`)
y **ganancia estimada** (`summary.estimatedEarnings`) calculados por InvIU
sobre flujos reales (separa `cashflowIn`/`cashflowOut` de la ganancia). Antes
de reimplementar el cálculo de rendimiento de `portfolio-analyzer` para
InvIU, comparar contra esto — puede ser más simple traer el número hecho que
recalcularlo lote por lote como se hace para Cocos.

## 5. Lo que no es cartera, pero conviene guardar igual

- `flujo_proyectado()` → duration, convexidad, DV01, TIR de la pata en bonos.
  No hay nada parecido hoy en `portfolio-analyzer` — sería una sección nueva,
  no un campo que ya exista para mapear.
- `poder_compra()` / `balances()` → información de cuenta, no de cartera. Solo
  tiene sentido si en algún momento se muestra "cuánto podés operar", no para
  el cálculo de P&L.

## Lo que falta confirmar con más operaciones reales (no se pudo probar con 1 sola cuenta)

- Si `operaciones()` pagina (como `products` y `managed-portfolio`, que tienen
  `paging.total`) — con 8 operaciones no se pudo saber si hay un límite.
- Cómo se ve una comisión real (no hubo ninguna operación con comisión != 0
  en la cuenta de prueba).
- Si los bonos duales (AL30/AL30D) alguna vez aparecen los dos a la vez en
  `cartera()` (posición mixta pesos+dólares del mismo bono) — con la cuenta
  de prueba todos los holdings vinieron con un solo ticker por bono.
