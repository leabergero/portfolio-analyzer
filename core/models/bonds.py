"""
bonds.py — Renta fija: flujos, TIR y riesgo de tasa.

    P_sucio = P_limpio + interés corrido
    P_sucio = Σ CFᵢ / (1 + y)^tᵢ                    → se despeja y por Brent

    D_Mac = Σ tᵢ · PV(CFᵢ) / P_sucio                duración de Macaulay
    D_mod = D_Mac / (1 + y/f)                       duración modificada
    DV01  = D_mod · P / 10.000                      qué se pierde con 1 pb
    C     = Σ tᵢ(tᵢ+1)·PV(CFᵢ) / [P(1+y)²]          convexidad

    ΔP/P ≈ −D_mod·Δy + ½·C·(Δy)²

**Las medidas de riesgo de tasa son la novedad respecto de las apps
anteriores**, que no calculaban ninguna: había una cartera 100 % de bonos y no
se podía responder cuánto se pierde si la curva sube 100 puntos básicos. Ver
`docs/PENDIENTES.md`.

Tres convenciones que hay que tener a la vista:

  · **Los flujos van por cada 100 de nominal RESIDUAL, no original.** Es la
    convención con la que cotiza el mercado y es la corrección más importante de
    este módulo. Un AL30 en 2026 ya amortizó el 33 % del capital: si se comparan
    los flujos por 100 nominales originales contra un precio que está expresado
    por 100 residuales, la TIR sale absurda.

    Terminal Financiera arrastra ese error: para el AL30 a 68 reporta **0,587 %**
    cuando el rendimiento real ronda el 11 %. Nunca se detectó porque las TIR se
    validaron con el AN29, que es *bullet* —devuelve todo el capital al
    vencimiento, así que su residual es siempre 100 y la distinción no aparece—.
    El error solo se manifiesta en bonos que **ya empezaron a amortizar**.

  · Acá se calcula **anual efectiva** con base ACT/365. Los soberanos argentinos
    en dólares se cotizan con **rendimiento equivalente de bono, capitalización
    semestral**. Se devuelven las dos, etiquetadas: esa diferencia sí es de
    convención, no un error.

  · El interés corrido va sobre el nominal remanente, descontando las
    amortizaciones ya pagadas.
"""

from datetime import date, datetime

import numpy as np
from scipy.optimize import brentq

from core.data.symbols import d_ticker, is_bond  # noqa: F401  — API pública
from core.models.instrumentos import ON_SPECS, SOBERANOS_SPECS, TODAS

DIAS_ANIO = 365.0


def _fecha(texto: str) -> date:
    return datetime.strptime(texto, "%Y-%m-%d").date()


def especie(ticker: str):
    """Condiciones de emisión, o None si el instrumento no está en el registro."""
    from core.data.symbols import base_symbol
    return TODAS.get(base_symbol(ticker))


# ── Flujos de fondos ──────────────────────────────────────────────────────────

def nominal_residual(ticker: str, liquidacion: date = None) -> float:
    """Cuánto queda vivo del capital, en porcentaje del nominal original.

    Un AL30 en septiembre de 2026 ya pagó cuatro amortizaciones de 8,33 %:
    su residual es 66,68 %. Este número es el que reconcilia los flujos con el
    precio de pantalla.
    """
    spec = especie(ticker)
    if not spec:
        return 100.0
    hoy = liquidacion or date.today()
    pagado = sum(pct for f, pct in zip(spec["amort_dates"], spec["amort_pct"])
                 if _fecha(f) <= hoy)
    return max(0.0, 100.0 - pagado)


def flujos(ticker: str, liquidacion: date = None, base: str = "residual") -> list:
    """[(fecha, monto)] pendientes de cobro.

    base="residual" (por defecto): montos por cada 100 de nominal **residual**,
    que es como cotiza el mercado y por lo tanto la base del precio que entra.
    base="original": por cada 100 de nominal original, útil para auditar.

    Cada fecha de cupón paga la tasa periódica sobre el capital que sigue vivo;
    cada amortización devuelve su porcentaje.
    """
    spec = especie(ticker)
    if not spec:
        return []
    hoy = liquidacion or date.today()
    vencimiento = _fecha(spec["maturity"])
    if hoy >= vencimiento:
        return []

    tasa_periodica = spec["coupon_rate"] / 100.0 / spec["coupon_freq"]
    amortizaciones = {_fecha(f): pct for f, pct in
                      zip(spec["amort_dates"], spec["amort_pct"])}

    # Fechas de cupón desde hoy hasta el vencimiento.
    fechas_cupon = []
    for anio in range(hoy.year, vencimiento.year + 1):
        for dia_mes in spec["coupon_dates"]:
            try:
                d, m = dia_mes.split("-")
                f = date(anio, int(m), int(d))
            except ValueError:
                continue
            if hoy < f <= vencimiento:
                fechas_cupon.append(f)

    eventos = sorted(set(fechas_cupon) | set(k for k in amortizaciones if hoy < k <= vencimiento))

    # Nominal vivo a hoy: lo que ya se amortizó no devenga más.
    vivo = 100.0 - sum(p for f, p in amortizaciones.items() if f <= hoy)

    salida = []
    for f in eventos:
        monto = vivo * tasa_periodica if f in fechas_cupon else 0.0
        if f in amortizaciones:
            monto += amortizaciones[f]
            vivo -= amortizaciones[f]
        if monto > 0:
            salida.append((f, monto))

    if base == "residual":
        residual = nominal_residual(ticker, hoy)
        if residual <= 0:
            return []
        factor = 100.0 / residual
        salida = [(f, m * factor) for f, m in salida]

    return [(f, round(m, 6)) for f, m in salida]


def interes_corrido(ticker: str, liquidacion: date = None, base: str = "residual") -> float:
    """Cupón devengado desde el último pago, en la misma base que los flujos."""
    spec = especie(ticker)
    if not spec:
        return 0.0
    hoy = liquidacion or date.today()

    ultimo = None
    for anio in range(hoy.year - 1, hoy.year + 1):
        for dia_mes in spec["coupon_dates"]:
            try:
                d, m = dia_mes.split("-")
                f = date(anio, int(m), int(d))
            except ValueError:
                continue
            if f <= hoy and (ultimo is None or f > ultimo):
                ultimo = f
    if ultimo is None:
        return 0.0

    amortizaciones = {_fecha(f): pct for f, pct in
                      zip(spec["amort_dates"], spec["amort_pct"])}
    vivo = 100.0 - sum(p for f, p in amortizaciones.items() if f <= ultimo)

    dias_periodo = DIAS_ANIO / spec["coupon_freq"]
    devengado = (vivo * spec["coupon_rate"] / 100.0 / spec["coupon_freq"]
                 * (hoy - ultimo).days / dias_periodo)

    if base == "residual":
        residual = nominal_residual(ticker, hoy)
        devengado = devengado * 100.0 / residual if residual > 0 else 0.0

    return round(max(0.0, devengado), 4)


# ── TIR ───────────────────────────────────────────────────────────────────────

def tir(precio_sucio: float, cashflows: list, liquidacion: date = None):
    """Tasa anual efectiva que iguala el valor presente de los flujos al precio.

    Brent sobre un intervalo amplio: los bonos argentinos han cotizado con TIR
    de tres dígitos y con TIR negativa, así que acotar de menos deja casos sin
    resolver.
    """
    if not cashflows or precio_sucio <= 0:
        return None
    hoy = liquidacion or date.today()
    futuros = [(f, cf) for f, cf in cashflows if (f - hoy).days > 0]
    if not futuros:
        return None

    tiempos = np.array([(f - hoy).days / DIAS_ANIO for f, _ in futuros])
    montos = np.array([cf for _, cf in futuros])

    def diferencia(y):
        return float((montos / (1 + y) ** tiempos).sum()) - precio_sucio

    for lo, hi in ((-0.95, 10.0), (-0.99, 2.0), (-0.50, 30.0)):
        try:
            if diferencia(lo) * diferencia(hi) < 0:
                return round(brentq(diferencia, lo, hi, maxiter=500, xtol=1e-10), 6)
        except Exception:
            continue
    return None


def tir_semestral(tir_efectiva: float):
    """Pasa de tasa anual efectiva a nominal con capitalización semestral.

        y_sem = 2 · [ (1 + y_efectiva)^(1/2) − 1 ]
    """
    if tir_efectiva is None or tir_efectiva <= -1:
        return None
    return round(2 * ((1 + tir_efectiva) ** 0.5 - 1), 6)


def _fechas_cupon_alrededor(ticker: str, liquidacion: date):
    """(cupón anterior, cupón siguiente) respecto de la fecha de liquidación."""
    spec = especie(ticker)
    if not spec:
        return None, None
    fechas = []
    for anio in range(liquidacion.year - 1, _fecha(spec["maturity"]).year + 1):
        for dia_mes in spec["coupon_dates"]:
            try:
                d, m = dia_mes.split("-")
                fechas.append(date(anio, int(m), int(d)))
            except ValueError:
                continue
    fechas.sort()
    previa = max((f for f in fechas if f <= liquidacion), default=None)
    proxima = min((f for f in fechas if f > liquidacion), default=None)
    return previa, proxima


def tir_mercado(precio_sucio: float, cashflows: list, ticker: str,
                liquidacion: date = None):
    """TIR en la convención con la que cotiza el mercado (ISMA / *street*).

    El tiempo se mide en **períodos de cupón**, no en años calendario:

        t = w + k        w = fracción que resta del período en curso
                         k = cuántos cupones enteros faltan después
        P = Σ CFᵢ / (1 + y/f)^tᵢ

    Por qué importa: descontando con años ACT/365, la identidad "un bono a la
    par rinde su cupón" solo se cumple **el día del cupón**. A mitad de período
    el resultado se desvía, y el desvío crece con los días transcurridos —
    medido sobre el AN29 al 6,5 %: −0,006 pp el día del cupón, +0,31 a los 46
    días, +0,65 a los 91, +1,29 a los 166. Un rendimiento que se mueve más de un
    punto según el día del mes en que se mire no es utilizable, y es el número
    que el usuario va a comparar contra la pantalla del broker.

    Con períodos de cupón la identidad se cumple cualquier día.
    """
    spec = especie(ticker)
    if not spec or not cashflows or precio_sucio <= 0:
        return None
    hoy = liquidacion or date.today()
    f = spec["coupon_freq"]

    previa, proxima = _fechas_cupon_alrededor(ticker, hoy)
    if not proxima:
        return None
    largo_periodo = (proxima - previa).days if previa else DIAS_ANIO / f
    if largo_periodo <= 0:
        return None
    w = (proxima - hoy).days / largo_periodo          # fracción que resta

    futuros = [(d, cf) for d, cf in cashflows if d > hoy]
    if not futuros:
        return None
    # Períodos entre el próximo cupón y cada flujo.
    t = np.array([w + (d - proxima).days / largo_periodo for d, _ in futuros])
    montos = np.array([cf for _, cf in futuros])

    def diferencia(y_nominal):
        return float((montos / (1 + y_nominal / f) ** t).sum()) - precio_sucio

    for lo, hi in ((-0.9, 5.0), (-0.99, 1.5), (-0.5, 20.0)):
        try:
            if diferencia(lo) * diferencia(hi) < 0:
                return round(brentq(diferencia, lo, hi, maxiter=500, xtol=1e-10), 6)
        except Exception:
            continue
    return None


# ── Riesgo de tasa ────────────────────────────────────────────────────────────

def riesgo_tasa(precio_sucio: float, cashflows: list, y: float,
                frecuencia: int = 2, liquidacion: date = None) -> dict:
    """Duración, DV01 y convexidad.

    Responde la pregunta que un tenedor de bonos hace de verdad: **si la curva
    se mueve 100 puntos básicos, cuánto pierdo**. Ninguna de las dos apps
    anteriores la calculaba.
    """
    if not cashflows or y is None or precio_sucio <= 0:
        return {}
    hoy = liquidacion or date.today()
    futuros = [(f, cf) for f, cf in cashflows if (f - hoy).days > 0]
    if not futuros:
        return {}

    t = np.array([(f - hoy).days / DIAS_ANIO for f, _ in futuros])
    cf = np.array([c for _, c in futuros])
    vp = cf / (1 + y) ** t
    precio_teorico = float(vp.sum())
    if precio_teorico <= 0:
        return {}

    d_mac = float((t * vp).sum() / precio_teorico)
    d_mod = d_mac / (1 + y / frecuencia)
    convexidad = float((t * (t + 1) * vp).sum() / (precio_teorico * (1 + y) ** 2))

    def variacion(pb):
        dy = pb / 10_000.0
        return round((-d_mod * dy + 0.5 * convexidad * dy ** 2) * 100, 3)

    return {
        "duracion_macaulay": round(d_mac, 3),
        "duracion_modificada": round(d_mod, 3),
        "dv01": round(d_mod * precio_sucio / 10_000, 5),
        "convexidad": round(convexidad, 3),
        "sensibilidad_pct": {"+100pb": variacion(100), "-100pb": variacion(-100),
                             "+200pb": variacion(200), "-200pb": variacion(-200)},
    }


def analizar_bono(ticker: str, precio_limpio: float, liquidacion: date = None) -> dict:
    """Ficha completa de un bono a un precio dado, por cada 100 nominales."""
    spec = especie(ticker)
    if not spec:
        return {"error": f"{ticker} no está en el registro de especies."}

    hoy = liquidacion or date.today()
    corrido = interes_corrido(ticker, hoy)
    sucio = precio_limpio + corrido
    cfs = flujos(ticker, hoy)

    y_mercado = tir_mercado(sucio, cfs, ticker, hoy)      # la que cotiza el broker
    y_efectiva = tir(sucio, cfs, hoy)                     # anual efectiva ACT/365

    salida = {
        "ticker": ticker.upper(), "nombre": spec.get("name", ""),
        "moneda": spec.get("currency", "USD"),
        "vencimiento": spec["maturity"],
        "anios_al_vencimiento": round((_fecha(spec["maturity"]) - hoy).days / DIAS_ANIO, 2),
        "cupon_anual_pct": spec["coupon_rate"],
        "nominal_residual_pct": round(nominal_residual(ticker, hoy), 2),
        "precio_limpio": round(precio_limpio, 4),
        "interes_corrido": corrido,
        "precio_sucio": round(sucio, 4),
        # La de mercado va primero porque es la comparable con la pantalla del
        # broker; la efectiva queda al lado para que la diferencia se lea como
        # convención y no como discrepancia de datos.
        "tir_pct": round(y_mercado * 100, 3) if y_mercado is not None else None,
        "tir_convencion": f"nominal, capitalización {spec['coupon_freq']} veces al año",
        "tir_efectiva_anual_pct": round(y_efectiva * 100, 3) if y_efectiva is not None else None,
        "flujos_pendientes": [{"fecha": str(f), "monto": m} for f, m in cfs],
        "proximo_flujo": ({"fecha": str(cfs[0][0]), "monto": cfs[0][1]} if cfs else None),
    }
    # El riesgo de tasa se mide con la tasa de mercado, que es la que se mueve
    # cuando "la curva sube 100 puntos básicos".
    salida.update(riesgo_tasa(sucio, cfs, y_mercado, spec["coupon_freq"], hoy))
    return salida


def curva(precios: dict, liquidacion: date = None) -> list:
    """Curva de rendimientos: (años al vencimiento, TIR) por especie.

    precios: {ticker: precio limpio por cada 100 nominales}.
    """
    salida = []
    for ticker, precio in precios.items():
        if not precio or precio <= 0:
            continue
        ficha = analizar_bono(ticker, float(precio), liquidacion)
        if ficha.get("tir_pct") is not None:
            salida.append({k: ficha[k] for k in
                           ("ticker", "nombre", "anios_al_vencimiento",
                            "tir_pct", "tir_efectiva_anual_pct", "precio_limpio",
                            "duracion_modificada", "dv01", "convexidad")
                           if k in ficha})
    return sorted(salida, key=lambda x: x["anios_al_vencimiento"])


def riesgo_tasa_cartera(posiciones, precios: dict = None) -> dict:
    """Duración y DV01 de la parte de renta fija de la cartera.

    Se agregan ponderando por valor de mercado. El DV01 total es lo que se
    pierde, en dólares, si toda la curva sube un punto básico.
    """
    from core.models.portfolio import precios_actuales

    precios = precios if precios is not None else precios_actuales(posiciones)
    bonos, valor_rf = [], 0.0

    for p in posiciones:
        ticker = str(p["ticker"]).upper()
        if not especie(ticker):
            continue
        precio_usd = precios.get(ticker)
        if not precio_usd:
            continue
        # precios_actuales devuelve el precio por unidad ya dividido por 100.
        ficha = analizar_bono(ticker, precio_usd * 100)
        if ficha.get("duracion_modificada") is None:
            continue
        valor = float(p.get("qty", 0)) * precio_usd
        valor_rf += valor
        bonos.append({**{k: ficha[k] for k in
                         ("ticker", "nombre", "tir_pct", "tir_efectiva_anual_pct",
                          "duracion_modificada", "convexidad", "anios_al_vencimiento")},
                      "valor_usd": round(valor, 2)})

    if not bonos:
        return {"error": "La cartera no tiene renta fija con precio disponible."}

    pesos = np.array([b["valor_usd"] for b in bonos]) / valor_rf
    d_mod = float((pesos * np.array([b["duracion_modificada"] for b in bonos])).sum())
    convex = float((pesos * np.array([b["convexidad"] for b in bonos])).sum())

    def variacion(pb):
        dy = pb / 10_000.0
        return round((-d_mod * dy + 0.5 * convex * dy ** 2) * valor_rf, 2)

    return {
        "valor_renta_fija": round(valor_rf, 2),
        "duracion_modificada": round(d_mod, 3),
        "convexidad": round(convex, 3),
        "dv01_usd": round(d_mod * valor_rf / 10_000, 2),
        "si_la_curva_sube": {"+100pb": variacion(100), "+200pb": variacion(200)},
        "si_la_curva_baja": {"-100pb": variacion(-100), "-200pb": variacion(-200)},
        "bonos": sorted(bonos, key=lambda b: -b["valor_usd"]),
    }
