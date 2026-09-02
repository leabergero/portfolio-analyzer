# Decisiones fijadas

Lo que ya está decidido y no se vuelve a discutir salvo que aparezca evidencia
nueva. Si algo de acá cambia, se anota abajo con la fecha y el motivo.

## Producto

| Decisión | Elección |
|---|---|
| Alcance | **Un producto, dos modos**: Análisis de cartera · Comparación de carteras |
| Reemplaza a | Terminal Financiera v7.4.4 y QuantFolio v0.4 |
| Origen del código | **Escrito de nuevo.** Las dos apps viejas son referencia y árbitro, no fuente de copiado |
| Base funcional | Terminal Financiera manda; se le suma lo de QuantFolio que no tiene |

**Filosofía:** ver la posición de la cartera → entender el riesgo y los modelos
que lo sustentan → comparar contra benchmarks y entre carteras.

## Técnicas

| Decisión | Elección | Motivo |
|---|---|---|
| Datos numéricos | pandas + numpy + scipy | El cálculo pesado ya vive en numpy; pandas es la capa de alineación por fecha. Migrar a polars optimizaría el 0,02 % del tiempo — medido |
| Gráficos | **Plotly** | Revierte la decisión de Recharts de QuantFolio. Trae heatmap, scatter denso por WebGL y `toImage()` para el PDF |
| Estructura del frontend | React 18 UMD por CDN, **JSX precompilado** | Sin Babel en el navegador: son 2.914 KB que no dibujan nada. Un comando, no un toolchain |
| Tema | Claro / oscuro / seguir al sistema | Tokens CSS en un solo lugar; Plotly toma los colores de las mismas variables |
| Moneda | **Dólar siempre** | MEP por la fecha exacta de cada operación, nunca el de hoy |
| Precios de bonos | Cocos Capital + vault AES-256-GCM + 2FA | Único acceso a ONs y letras |
| Caché de mercado | Se reconstruye de cero | Las dos bases viejas se descartan |
| Control de versiones | git desde el primer commit | Ninguno de los dos proyectos anteriores lo tenía |

## Fuentes de datos y qué pasa sin cada una

Solo dos fuentes piden credencial, y las dos son **opcionales**. Ninguna
funcionalidad central puede depender de ellas.

| Fuente | Requiere | Aporta | Sin ella |
|---|---|---|---|
| ArgentinaDatos · dolarapi | nada | Serie del dólar MEP | No hay valuación en USD — por eso son públicas |
| yfinance | nada | Acciones, CEDEARs, ETFs, benchmarks, sector/industria | No hay renta variable |
| **Cocos Capital** | cuenta de broker | Bonos soberanos, ONs, letras | Todo lo demás anda; falta el precio de renta fija |
| **FMP** | API key gratuita | Precios objetivo de analistas (EE.UU.) | Los objetivos salen de yfinance, con menos cobertura |

Las credenciales del broker van cifradas en el vault (pueden mover dinero); la
API key de FMP va en `data/connectors.json` con permisos 600 y fuera de git (es
de solo lectura, y meterla en el vault obligaría a desbloquear el broker para
consultar un precio objetivo).

### FMP: la cuota manda el diseño

El plan gratuito son **250 consultas por día** y cada símbolo cuesta 3
(cotización + consenso + grados). Diez posiciones son 30 consultas por pantalla,
y el código anterior gastaba 3 más **cada vez que se dibujaba el panel de
conectores**. La cuota se agota sola: pasó, y al portar el conector la
encontramos agotada.

Por eso las respuestas se cachean 24 h en la tabla `respuestas`. Un consenso de
analistas se mueve de semana en semana; la caché no pierde nada y es lo único
que hace usable el plan gratuito. La misma tabla sirve para cachear el `.info`
de yfinance (sector, industria, tipo), que cambia una vez al año y se pedía en
cada request.

El estado del conector distingue **cuota agotada** (se repone mañana solo) de
**key rechazada** (hay que hacer algo). Decir "revisá el plan" cuando en
realidad hay que esperar al día siguiente manda a buscar un problema que no
existe.

## Cocos es la excepción, no la fuente por defecto

**La aplicación tiene que funcionar completa sin cuenta de broker.** Cocos
Capital se usa **exclusivamente** para los instrumentos que no existen en
ninguna fuente pública:

- bonos soberanos argentinos,
- obligaciones negociables,
- letras.

Todo lo demás —acciones, CEDEARs, ETFs, benchmarks y **el dólar MEP**— sale de
fuentes públicas sin credenciales. El MEP en particular lo necesita cualquiera
que abra la aplicación: hacerlo depender del broker dejaría sin valuación en
dólares a todo usuario que no tenga cuenta.

Consecuencia de diseño: **sin Cocos conectado, la aplicación funciona entera
salvo los precios de bonos y ONs.** Eso no es un modo degradado accidental, es
el comportamiento esperado y hay que mantenerlo así.

### Fuentes del MEP (todas públicas)

| Orden | Fuente | Qué aporta |
|---|---|---|
| 1 | `api.argentinadatos.com/v1/cotizaciones/dolares/bolsa` | Serie diaria completa desde 2018 **y** el día de hoy. Primaria |
| 2 | `dolarapi.com/v1/dolares/bolsa` | Solo el valor de hoy: completa la rueda que la primaria a veces publica con un día de atraso |
| 3 | Caché local | Siempre es la base; con ella la app valúa aunque las dos APIs estén caídas |

Descartadas, para no volver a intentarlas:

- **PyOBD / BYMA Open Data** — hoy devuelve vacío para todos los símbolos,
  incluidos GGAL y METR. El respaldo que Terminal Financiera declara por esta
  vía es código muerto.
- **yfinance con AL30/AL30D** — los da por delistados.
- **Cocos** — funciona, pero exige cuenta. Ver arriba.

Dos detalles que cuestan caro si se olvidan: la API de ArgentinaDatos **no
devuelve el array ordenado por fecha** (hay que ordenarlo, no leer el último
elemento), y **requiere header `User-Agent`** o responde 404.

## Contrato del CSV propio

```
ticker, buy_date, buy_price, qty, commissions, source, currency, asset_type, notes
```

Las tres últimas columnas de control son la novedad y existen por una razón
concreta:

- **`source`** — `cocos` marca el instrumento como bono cotizado cada 100
  nominales. Sin esto, un ON que no figure en las tablas valúa **100× de más**
  (bug real: `TLCPO.BA`).
- **`currency`** — anula la detección automática de moneda para el ticker que la
  convención no acierte, sin tocar código.
- **`asset_type`** — anula la clasificación por tipo para instrumentos nuevos.

Lo que se exporta se puede volver a importar y da la misma cartera. Es una
verdad testeada, no una intención.

## Convenciones de cálculo

Ver `docs/MODELOS.md`. Las que más se prestan a confusión:

- **Anualización**: aritmética (`μ×252`) como insumo de media-varianza;
  geométrica (`CAGR`) para reportar al usuario. Cada KPI declara cuál usa.
- **Tasa libre de riesgo**: letra del Tesoro a **13 semanas** (`^IRX`) para todo
  lo que se mide sobre retornos diarios. El 10 años **no** es libre de riesgo a
  horizonte diario.
- **Serie de la cartera**: pesos de hoy aplicados a toda la historia. Mide el
  riesgo de la cartera que tenés ahora; no es tu P&L histórico, que se calcula
  aparte desde los lotes.
- **Curtosis**: es curtosis **en exceso** (normal = 0). Etiquetarlo en la interfaz.
- **VaR**: se guarda negativo (es un cuantil), se muestra como pérdida positiva.

## Registro de cambios de decisión

| Fecha | Qué cambió | Motivo |
|---|---|---|
| 2026-09-02 | Recharts → **Plotly** | Medido: la ventaja de peso de Recharts se anula con el compilador JSX en el navegador (3.634 KB vs 3.733 KB). Plotly trae heatmap, WebGL y export a PNG de fábrica |
| 2026-09-02 | pandas se queda (no polars) | Medido: el cálculo de pandas es 0,43 ms de 1.832 ms. El cuello real era un `iterrows()`, 13× más rápido sin migrar |
