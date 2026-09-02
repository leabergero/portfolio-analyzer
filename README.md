# Portfolio Analyzer

Herramienta de análisis de carteras con foco en el mercado argentino: acciones,
CEDEARs, bonos soberanos y obligaciones negociables. **Todo medido en dólares**,
con el MEP de la fecha exacta de cada operación.

Reemplaza a Terminal Financiera v7.4.4 y a QuantFolio v0.4, fusionándolas en un
solo producto con dos modos de uso.

> **Ver la posición de la cartera → entender el riesgo y los modelos que lo
> sustentan → comparar contra benchmarks y entre carteras.**

## Los dos modos

**Análisis de cartera** — *¿qué tengo, cuánto vale y cuánto puedo perder?*
Posición y P&L, composición por tipo/sector/industria, riesgo (VaR, CVaR,
stress, distribución), Markowitz, Black-Litterman, Monte Carlo, CAPM, momentum,
precios objetivo, regímenes, curva de bonos, MEP y noticias.

**Comparación** — *¿cuál de estas estrategias es mejor, y por qué?*
Cartera contra benchmark (S&P 500 · STOXX 600 · Merval, todos en USD) y carteras
entre sí, con el ganador justificado por criterios explícitos.

## Estado

**Fase 2 terminada** — 18 de 23 verdades en verde, 0 en rojo.

```bash
python3 tests/test_verdades.py          # la suite corre sin instalar nada
```

`tests/test_verdades.py` es la red de seguridad de la reescritura: cada caso es
un bug real que ya se pagó una vez en las apps anteriores. Se escribió **antes**
que los modelos, así que lo que sigue en *pendiente* es el plan de trabajo — y
cuando un caso pasa a verde, esa pieza está terminada.

| Fase | Qué entrega | Estado |
|---|---|---|
| 0 | Esqueleto, git, suite de verdades | ✅ |
| 1 | Núcleo de datos: precios, caché, MEP, Cocos + vault, FMP | ✅ |
| 2 | Carteras y CSV (propio + Yahoo), verificado contra la app vieja | ✅ |
| 3 | Modo Análisis | — |
| 4 | Modo Comparación | — |
| 5 | PDF, noticias, MEP, conectores; se archivan las apps viejas | — |

### Verificación de la fase 2

Las mismas carteras, valuadas por las dos aplicaciones el mismo día:

| Cartera | Portfolio Analyzer | Terminal Financiera |
|---|---|---|
| KARIN | $21.680,60 | $21.680,60 |
| LEANDRO | $8.225,54 | $8.225,54 |
| MAMI | $14.122,85 | $14.122,85 |

La cartera de bonos no valúa sin Cocos conectado, y se reporta como
`sin_precio` en vez de darla en cero: un total silenciosamente incompleto es
peor que un total ausente.

## Estructura

```
core/           el motor — no sabe que existe la web
  data/         fuentes, caché, MEP, conectores
  broker/       Cocos Capital + vault cifrado
  models/       cartera, riesgo, optimización, simulación, bonos
  io/           importadores y exportadores CSV
api/            Flask delgado, sin lógica de negocio
web/            interfaz (React + Plotly, JSX precompilado)
tests/          las verdades
docs/           decisiones, modelos, pendientes
examples/       plantilla CSV descargable
```

## Documentación

- [`docs/DECISIONES.md`](docs/DECISIONES.md) — lo que ya está decidido y por qué
- [`docs/MODELOS.md`](docs/MODELOS.md) — qué corregir del código viejo y qué no tocar
- [`docs/PENDIENTES.md`](docs/PENDIENTES.md) — riesgo de tasa y herramientas propuestas

---

© Leandro R. Bergero · Msc Finance and Banking BSM-UPF
· [github.com/leabergero](https://github.com/leabergero)
