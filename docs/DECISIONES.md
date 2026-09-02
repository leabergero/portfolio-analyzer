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
