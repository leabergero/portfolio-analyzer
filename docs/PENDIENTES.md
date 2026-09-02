# Pendientes

Cosas decididas o propuestas que NO entran todavía, para que no se pierdan ni se
re-discutan. Cada una dice en qué fase corresponde y por qué.

---

## Riesgo de tasa en renta fija — pedido explícito, para más adelante

**Estado:** aprobado en concepto, se implementa después del núcleo.
**Fase sugerida:** 3 (modo Análisis), junto al módulo de bonos.

Hoy ninguna de las dos apps anteriores calcula **ninguna** medida de riesgo de
tasa, y hay una cartera que es 100 % renta fija (soberanos + ONs). Sin esto no
se puede responder la pregunta básica de un tenedor de bonos: *si la curva se
mueve 100 puntos básicos, ¿cuánto pierdo?*

Fórmulas a implementar:

```
D_Mac  = Σ tᵢ · PV(CFᵢ) / P_sucio
D_mod  = D_Mac / (1 + y/f)
DV01   = D_mod · P / 10.000
C      = Σ tᵢ(tᵢ+1) · PV(CFᵢ) / [P (1+y)²]

ΔP/P  ≈  −D_mod · Δy  +  ½ · C · (Δy)²
```

Notas de implementación:

- Se apoya en `get_bond_cashflows()` y `calc_ytm()`, que ya hay que escribir
  igual para la curva de TIR — el costo incremental es bajo.
- Agregable a nivel cartera ponderando por valor de mercado de cada bono.
- KPI de salida: **"si la curva sube 100 pb, perdés US$ X"**, que es la forma
  en que el dato se usa de verdad.
- Al implementarlo, agregar su caso a `tests/test_verdades.py`: un bono bullet
  a un año con cupón 0 tiene duración 1 exacta — es verificable a mano.

---

## Convención de TIR: mostrar las dos

**Fase sugerida:** 3, junto a lo anterior.

El cálculo actual usa capitalización **anual efectiva** con base ACT/365,25.
Los soberanos argentinos en dólares se cotizan con **rendimiento equivalente de
bono, capitalización semestral**, y el interés corrido en **30/360**. La TIR de
la app no va a coincidir con la pantalla del broker, y la diferencia no es un
error de datos sino de convención. Calcular ambas y etiquetar cuál es cuál.

---

## Herramientas nuevas propuestas

Detalle y fórmulas: https://claude.ai/code/artifact/2665458e-f0e8-4946-83e5-8d32cb4cdb60

### Prioridad alta — modo Análisis

| Herramienta | Por qué | Fase |
|---|---|---|
| Contribución al riesgo (Euler) | Reemplaza la descomposición vieja, que estaba mal planteada. `Σ CRᵢ = σₚ` exacto. Ya tiene su verdad escrita en el test. | 3 |
| Concentración: HHI y `N_ef = 1/Σw²` | Una línea de código. KARIN tiene 9 posiciones y un N efectivo de ~1,1: diversificación aparente, no real. | 3 |
| VaR de Cornish-Fisher | Con curtosis en exceso de 13, el VaR normal miente y el histórico no extrapola. Tres líneas. | 3 |
| Monte Carlo con colas gordas | La app detecta t de Student con ν≈3,7 y después simula con normal. t escalada + bootstrap por bloques. | 3 |
| Duración / DV01 / convexidad | Ver arriba. | 3 |

### Prioridad alta — modo Comparación

| Herramienta | Por qué | Fase |
|---|---|---|
| Test de diferencia de Sharpe (Jobson-Korkie-Memmel) | Sin esto el modo Comparación corona ganadores que los datos no sostienen. Convierte "cuál se ve mejor" en "cuál es mejor". | 4 |
| Sharpe deflactado (Bailey–López de Prado) | Comparar muchas variantes garantiza encontrar una buena por azar. Corrige por nº de pruebas y por no-normalidad. | 4 |
| Intervalos de confianza por bootstrap de bloques | Una barra de error en cada número de la tabla comparativa. Si los intervalos se superponen, no hay ganador. | 4 |

### Complementarias

| Herramienta | Modo | Fase |
|---|---|---|
| Volatilidad EWMA (λ=0,94) y GARCH(1,1) | Análisis | 3+ |
| Correlación condicionada a caídas | Análisis | 3+ |
| Liquidez: días para salir (el volumen ya está en la caché) | Análisis | 3+ |
| Regímenes con HMM real (`hmmlearn`) | Análisis | 3+ |
| Dominancia estocástica de 2º orden | Comparación | 4+ |
| Omega e índice de úlcera (Martin) | Comparación | 4+ |
| Atribución de Brinson | Comparación | 4+ |
| Rotación y costo de implementación | Comparación | 4+ |
| Frontera remuestreada (Michaud) | Comparación | 4+ |

---

## Decisiones aplazadas

- **Build con Vite / PWA:** no se hace. El JSX se precompila con un solo comando
  a `web/app.js`; no se adopta un toolchain.
- **OpenBB:** no entra. Para `.BA` rutea a yfinance igual y es lento de importar.
- **FMP plan pago / Benzinga:** solo si hace falta cobertura de price targets
  para ADRs argentinos, que el free tier bloquea.
- **WebSocket:** el push por SSE ya funciona; no se agrega `flask-sock`.
- **Bundle parcial de Plotly:** validar durante la fase 3 si alguno cubre
  scatter + barras + donut + heatmap. Si no, queda el completo — no se arma un
  bundle a medida por eso.
