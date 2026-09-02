# Modelos

Especificación matemática completa, fórmula por fórmula:
**https://claude.ai/code/artifact/2665458e-f0e8-4946-83e5-8d32cb4cdb60**

Este archivo es el resumen operativo: qué hay que corregir al escribir cada
módulo, y qué está bien y no hay que "arreglar".

---

## Errores del código viejo — NO copiarlos

Detectados el 2026-09-02 auditando Terminal Financiera v7.4.4 y QuantFolio v0.4.
Cada uno tiene su caso en `tests/test_verdades.py` cuando es testeable sin red.

| # | Dónde | Qué pasaba | Efecto |
|---|---|---|---|
| 1 | Tasa libre de riesgo | Usaba el Treasury 10Y para métricas diarias | Sharpe, Sortino, alpha y Treynor sesgados |
| 2 | `_sortino()` | Dividía la desviación a la baja por `N_neg`, no por `N` | Sortino subestimado ~√2; contamina el ganador de la comparación |
| 3 | `risk_decomposition()` | Ponderaba por nominales, ignoraba covarianzas, omitía el término cruzado | Los porcentajes no sumaban 100 % |
| 4 | `stress_test()` | Cálculo de pesos frágil, ya corregido en el resto | Caía a equiponderado sin avisar |
| 5 | `detect_regimes()` | Umbral `Q₇₅` calculado sobre toda la serie y aplicado hacia atrás | Sesgo de anticipación; invalida el replay histórico |
| 6 | Nombre "Markov" | Es un umbral sobre volatilidad móvil: sin estados latentes ni matriz de transición | La interfaz promete un modelo que no existe |

**Reemplazos:**

- (2) `downside_deviation(r, τ) = √( (1/N) Σ_{t=1..N} min(r_t − τ, 0)² )` — con
  N total. Ya tiene test con resultado calculable a mano.
- (3) Descomposición de Euler: `MCRᵢ = (Σw)ᵢ/σₚ`, `CRᵢ = wᵢ·MCRᵢ`, y se verifica
  con la identidad `Σ CRᵢ = σₚ`. Ya tiene test.
- (5) Umbral con **ventana expansiva**: `Q₇₅` calculado solo con datos hasta *t*.
- (6) O se renombra a lo que es (régimen por volatilidad), o se implementa un
  HMM de dos estados con `hmmlearn` — ver `PENDIENTES.md`.

---

## Verificado correcto — no tocar

- **Monte Carlo GBM**: `drift = μ − ½σ²` con μ y σ de retornos simples **está
  bien** — es la solución exacta del movimiento browniano geométrico. El
  problema del MC es otro: usa `Z` normal cuando los retornos son t de Student
  con ν≈3,7.
- **Markowitz**: SLSQP determinista; la frontera se barre desde el retorno de
  mínima varianza **hacia arriba** (barrer desde `mu.min()` trae la rama
  ineficiente y la curva zigzaguea).
- **Black-Litterman**: `μ_BL` y `Σ_BL` bien planteadas. Lo que hay que revisar
  son los parámetros, no las fórmulas — ver abajo.
- **CAPM**: beta, alpha de Jensen, Treynor, IR y R² correctos. Los tres
  benchmarks se llevan a USD antes de comparar.
- **Interés corrido**: se calcula sobre el nominal **remanente**, descontando
  amortizaciones ya pagadas. Correcto y no trivial para los amortizantes.
- **Máximo drawdown**, **VaR y CVaR históricos**: correctos.

---

## Parámetros a explicitar en Black-Litterman

Hoy están tomados por defecto y conviene que sean decisiones visibles:

- `w_mkt` son **los pesos propios de la cartera**, no capitalizaciones de
  mercado. Con eso "el equilibrio" es la ingeniería inversa de tu propia
  cartera. Es lo único posible sin market caps de BYMA, pero cambia la
  interpretación y hay que decirlo. Propuesta: usar capitalización de yfinance
  cuando exista, caer a los pesos propios cuando no, e informar cuál se usó.
- `δ = 2,5` fijo → calibrar con `δ = (E[r_m] − r_f)/σ²_m` usando el benchmark
  ya elegido.
- `τ = 0,05` fijo → He-Litterman sugiere `τ ≈ 1/T`.
- Los pesos finales se obtienen con `Σ_BL⁻¹(μ_BL − r_f)` recortando negativos y
  renormalizando. **No es lo mismo** que resolver con restricción `w ≥ 0`:
  debería usar SLSQP igual que Markowitz.
- El σ reportado usa `Σ` mientras el retorno usa `μ_BL`. Usar `Σ_BL` en ambos.

---

## Otras convenciones a fijar

- **Momentum**: la literatura usa **12−1** (saltea el último mes, por reversión
  de corto plazo). El código viejo usa los 12 completos.
- **Calmar**: `CAGR / |MDD|`, no `μ×252 / |MDD|`.
- **Sharpe**: dividir por σ del retorno **en exceso**, no del total.
- **TIR de bonos**: ver `PENDIENTES.md` — mostrar anual efectiva y semestral.
