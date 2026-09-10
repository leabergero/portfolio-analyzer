#!/usr/bin/env python3
"""
test_verdades.py — Los casos que ya nos costaron caro.

Cada test de este archivo es un bug REAL que se pagó una vez en Terminal
Financiera o en QuantFolio. Se escriben ANTES que los modelos: al principio
fallan todos, y eso es la definición de "terminado" para cada pieza del núcleo.

Reglas del archivo:

  1. Nada de red, nada de base de datos. Entradas sintéticas, funciones puras.
     Un test que depende del precio de hoy no es una verdad, es una foto: mañana
     falla solo y termina desactivado.

  2. Cada test dice qué bug previene. Si alguien lo borra dentro de dos años,
     que sepa qué está reactivando.

  3. Lo que todavía no existe sale como PENDIENTE, no como error. Así el archivo
     funciona como checklist de la reescritura.

Correr:

    python3 tests/test_verdades.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class Pendiente(Exception):
    """El módulo o la función todavía no existe. No es una falla."""


def require(modulo, *nombres):
    """Importa nombres del núcleo, o marca el test como pendiente."""
    try:
        mod = __import__(modulo, fromlist=list(nombres) or ["_"])
    except ImportError as e:
        raise Pendiente(f"{modulo} — {e}") from None
    faltan = [n for n in nombres if not hasattr(mod, n)]
    if faltan:
        raise Pendiente(f"{modulo} sin {', '.join(faltan)}")
    return [getattr(mod, n) for n in nombres] if len(nombres) != 1 else getattr(mod, nombres[0])


def casi(a, b, tol=1e-9):
    return abs(float(a) - float(b)) <= tol


class datos_aparte:
    """Manda las escrituras de `store` a un directorio temporal.

    Sin esto, un test que guarda carteras escribe —y limpia— en `data/`, que es
    donde están las carteras reales. Pasó el 2026-09-08: la limpieza de un test
    borró `data/usuarios/` con la cartera que un usuario acababa de importar.
    Ningún test puede tocar el directorio de datos de verdad.
    """

    def __enter__(self):
        import tempfile
        from pathlib import Path as _P
        store = require("core.io", "store")
        self.store = store
        self.previo = store._DATA
        self.tmp = tempfile.mkdtemp(prefix="pa-test-")
        store._DATA = _P(self.tmp)
        return _P(self.tmp)

    def __exit__(self, *_):
        import shutil
        self.store._DATA = self.previo
        self.store.como(None)
        shutil.rmtree(self.tmp, ignore_errors=True)


class cache_aparte:
    """Manda la caché de precios a una base temporal. Misma razón que
    `datos_aparte`: un test no puede escribir en la caché de verdad."""

    def __enter__(self):
        import tempfile
        from pathlib import Path as _P
        cache = require("core.data", "cache")
        self.cache = cache
        self.previo = cache.DB_PATH
        self.tmp = tempfile.mkdtemp(prefix="pa-cache-")
        cache.DB_PATH = _P(self.tmp) / "test.db"
        cache.init()
        return cache

    def __exit__(self, *_):
        import shutil
        self.cache.DB_PATH = self.previo
        shutil.rmtree(self.tmp, ignore_errors=True)


def cliente_web(flask_app):
    """Test client con la sesión de la app ya puesta.

    Desde que el ingreso es con Google, la sesión de la app es la puerta: sin
    ella ningún endpoint responde, tenga o no sobre de Cocos.
    """
    usuarios = require("core", "usuarios")
    c = flask_app.test_client()
    c.set_cookie(usuarios.COOKIE,
                 usuarios.emitir({"sub": "1234567890", "email": "x@y.z",
                                  "nombre": "Prueba", "foto": ""}))
    return c


class modo_web:
    """Pone el proceso en modo multiusuario mientras dure el bloque.

    Sin esto los tests del sobre corren en modo local, donde la cabecera se
    ignora a propósito — y pasarían en verde sin probar nada.
    """

    def __enter__(self):
        import os
        self.previo = os.environ.get("PA_MODO")
        os.environ["PA_MODO"] = "web"

    def __exit__(self, *_):
        import os
        if self.previo is None:
            os.environ.pop("PA_MODO", None)
        else:
            os.environ["PA_MODO"] = self.previo


# ══════════════════════════════════════════════════════════════════════════
#  MONEDA — el bug más caro de todos
# ══════════════════════════════════════════════════════════════════════════

def test_cedears_dolar_son_usd():
    """Un CEDEAR con sufijo "D" ya cotiza en dólares: NO se divide por el MEP.

    Bug original (QuantFolio, vivo al 2026-09-02): trataba KOD.BA como pesos y
    lo dividía por el MEP (~1.544). La cartera KARIN valía $3.733 en QuantFolio
    y $21.682 en Terminal Financiera — la misma cartera, el mismo día. Ese
    número concreto no sirve de test porque cambia con el precio; la verdad
    durable es la moneda.
    """
    ticker_currency = require("core.data.symbols","ticker_currency")
    for t in ("KOD.BA", "GLDD.BA", "SLVD.BA", "QQQD.BA", "NVDAD.BA", "MSFTD.BA"):
        assert ticker_currency(t) == "USD", f"{t} debería ser USD"


def test_acciones_ars_son_ars():
    """Contrapartida: sin la "D", cotiza en pesos y sí lleva conversión MEP."""
    ticker_currency = require("core.data.symbols","ticker_currency")
    for t in ("METR.BA", "COME.BA", "GGAL.BA", "PAMP.BA"):
        assert ticker_currency(t) == "ARS", f"{t} debería ser ARS"


def test_ypfd_no_es_variante_dolar():
    """YPFD termina en "D" de casualidad: es el ticker real de YPF en pesos.

    Bug original: el umbral de detección de la variante dólar lo marcaba como
    USD. Si aparece otro caso así, va a la lista de excepciones — no se toca
    la regla general.
    """
    ticker_currency = require("core.data.symbols","ticker_currency")
    assert ticker_currency("YPFD.BA") == "ARS"


def test_bono_dolar_sigue_circuito_ars():
    """Los bonos y ONs, aun en su variante "D", los devuelve Cocos EN PESOS.

    Es la excepción a la regla anterior y es contraintuitiva: la "D" de un
    CEDEAR significa "cotiza en dólares", pero la "D" de un bono es solo el
    nombre de la especie; el precio que llega sigue siendo ARS.
    """
    ticker_currency = require("core.data.symbols","ticker_currency")
    for t in ("AL30D.BA", "GD30D.BA"):
        assert ticker_currency(t) == "ARS", f"{t} viene de Cocos en pesos"


def test_base_del_cedear_no_come_letras_de_mas():
    """GLDD → GLD, no "GL".

    Bug original: se usaba rstrip("D"), que borra TODAS las D finales. El
    subyacente de GLDD.BA quedaba en "GL" y no resolvía contra nada.
    """
    base_symbol = require("core.data.symbols","base_symbol")
    assert base_symbol("GLDD.BA") == "GLD"
    assert base_symbol("KOD.BA") == "KO"
    assert base_symbol("AL30D.BA") == "AL30"
    assert base_symbol("METR.BA") == "METR"


# ══════════════════════════════════════════════════════════════════════════
#  BONOS — la división por 100
# ══════════════════════════════════════════════════════════════════════════

def test_bono_conocido_es_bono():
    """Los bonos y ONs de la tabla se reconocen por nombre."""
    is_bond = require("core.data.symbols","is_bond")
    for t in ("AL30.BA", "GD30.BA", "AN29.BA", "PLC4O.BA", "RUCDO.BA", "VSCXO.BA"):
        assert is_bond(t), f"{t} es un bono"


def test_source_cocos_manda_sobre_la_tabla():
    """Un bono que no está en ninguna tabla, pero declara source="cocos", ES bono.

    Bug original (Terminal Financiera, encontrado el 2026-09-02): TLCPO.BA no
    figura en la lista de ONs conocidas, así que no se dividía por 100 y la
    posición valía 100 VECES de más — pasó a dominar el 96% de una cartera de
    bonos y a clasificarse como renta variable.

    La ruta de PRECIOS ya respetaba el source explícito; la de NORMALIZACIÓN
    no. Las dos tienen que mirar el mismo dato.
    """
    is_bond = require("core.data.symbols","is_bond")
    assert is_bond("TLCPO.BA", source="cocos"), "source=cocos manda"
    assert not is_bond("AAPL", source=None)


def test_d_ticker_de_on_reemplaza_la_o_final():
    """PLC4O → PLC4D, no PLC4OD.

    Dos espacios de nombres distintos: en BYMA (.BA) la variante dólar es
    base+"D"; en la API interna de Cocos, las ONs reemplazan la "O" final por
    "D". Confundirlos devuelve precios de otra especie o ninguno.
    """
    d_ticker = require("core.models.bonds", "d_ticker")
    assert d_ticker("PLC4O") == "PLC4D"
    assert d_ticker("RUCDO") == "RUCDD"
    assert d_ticker("TLCTO") == "TLCTD"
    assert d_ticker("VSCXO") == "VSCXD"


def test_soberano_agrega_d_al_final():
    """Los soberanos sí siguen la regla simple: AL30 → AL30D."""
    d_ticker = require("core.models.bonds", "d_ticker")
    assert d_ticker("AL30") == "AL30D"
    assert d_ticker("GD35") == "GD35D"


def test_bono_a_la_par_rinde_su_cupon():
    """Precio limpio 100 → TIR ≈ tasa de cupón. Cualquier día del período.

    Es el invariante clásico de renta fija y el que detecta casi todos los
    errores posibles: base equivocada, interés corrido mal, conteo de días roto.
    Se prueba a mitad de período a propósito, porque el día del cupón se cumple
    incluso con la base mal.
    """
    from datetime import date, timedelta
    analizar_bono, especie = require("core.models.bonds", "analizar_bono", "especie")
    for ticker, cupon_base in (("AL30", date(2027, 1, 1)), ("AN29", date(2026, 11, 30))):
        cupon = especie(ticker)["coupon_rate"]
        for dias in (0, 91, 166):
            liq = cupon_base + timedelta(days=dias)
            tir = analizar_bono(ticker, 100.0, liq)["tir_pct"]
            assert abs(tir - cupon) < 0.15, (
                f"{ticker} a la par el día +{dias}: TIR {tir:.3f} % vs cupón {cupon} %")


def test_amortizante_usa_nominal_residual():
    """Los flujos de un bono que ya amortizó van por 100 de nominal RESIDUAL.

    Bug encontrado el 2026-09-02, presente también en Terminal Financiera: se
    comparaban flujos por 100 nominales ORIGINALES contra un precio expresado
    por 100 residuales. Para el AL30 a 68 daba 0,587 % de TIR en vez de un
    rendimiento de dos dígitos.

    Nunca se detectó porque las TIR se validaron con el AN29, que es bullet: su
    residual es siempre 100 y ahí la distinción no existe.
    """
    nominal_residual, flujos, analizar_bono = require(
        "core.models.bonds", "nominal_residual", "flujos", "analizar_bono")

    residual = nominal_residual("AL30")
    assert residual < 100, "el AL30 ya amortizó: su residual no puede ser 100"

    # Por 100 residuales, el capital que queda por cobrar es 100.
    total = sum(m for _, m in flujos("AL30"))
    assert total > 100, f"los flujos suman {total:.2f}: menos de 100 significa base equivocada"

    # Y el rendimiento tiene que ser el de un bono argentino, no ~0.
    tir = analizar_bono("AL30", 68.0)["tir_pct"]
    assert tir > 5.0, f"AL30 a 68 rinde {tir:.3f} %; con la base mal daba 0,587 %"


def test_bullet_no_amortiza_antes_del_vencimiento():
    """Contraparte: un bullet tiene residual 100 hasta el final."""
    nominal_residual = require("core.models.bonds", "nominal_residual")
    assert nominal_residual("AN29") == 100.0


# ══════════════════════════════════════════════════════════════════════════
#  SUBYACENTES — colisiones de tickers cortos
# ══════════════════════════════════════════════════════════════════════════

def test_kod_es_cocacola_no_kodiak():
    """Al resolver el subyacente de KOD.BA, "KO" va ANTES que "KOD".

    Bug original: se probaba "KOD" primero, que es el ticker real de Kodiak
    Sciences (biotech). El consenso de analistas que traía era de otra empresa
    y alimentaba las views de Black-Litterman con datos ajenos.
    """
    candidatos = require("core.models.targets", "underlying_candidates")
    c = candidatos("KOD.BA")
    assert "KO" in c, "falta el subyacente real"
    assert c.index("KO") < c.index("KOD"), "KO tiene que ir antes que KOD"


def test_etf_del_dow_es_dia():
    """El ETF del Dow Jones es DIA. "DOW" es Dow Inc., una química.

    Misma clase de error que KOD/Kodiak: un ticker corto que parece obvio y
    apunta a otra cosa.
    """
    futuros = require("core.models.targets", "FUTURES_MAP")
    assert "DIA" in futuros
    assert "DOW" not in futuros, "DOW es Dow Inc., no el ETF del índice"


# ══════════════════════════════════════════════════════════════════════════
#  PESOS — la caída silenciosa a equiponderado
# ══════════════════════════════════════════════════════════════════════════

def test_pesos_agregan_lotes_repetidos():
    """Dos lotes del mismo ticker son UNA posición.

    Bug original (QuantFolio): cuando el número de posiciones no coincidía con
    el de tickers con datos — por ejemplo con lotes repetidos — los pesos caían
    a equiponderado sin avisar. La cartera LEANDRO mostraba "20% cada uno"
    cuando en realidad era METR 95,7% y COME 4,3%.
    """
    value_weights = require("core.models.portfolio", "value_weights")
    posiciones = [
        {"ticker": "METR.BA", "qty": 100},
        {"ticker": "METR.BA", "qty": 300},
        {"ticker": "COME.BA", "qty": 50},
    ]
    precios = {"METR.BA": 2.0, "COME.BA": 4.0}
    w = value_weights(posiciones, precios, ["METR.BA", "COME.BA"])
    # METR: 400 × 2 = 800 · COME: 50 × 4 = 200 · total 1000
    assert casi(w[0], 0.8, 1e-6), f"METR debería pesar 80%, da {w[0]:.4f}"
    assert casi(w[1], 0.2, 1e-6), f"COME debería pesar 20%, da {w[1]:.4f}"


def test_pesos_nunca_caen_a_equiponderado():
    """Con una cartera claramente concentrada, jamás debe devolver 1/n."""
    value_weights = require("core.models.portfolio", "value_weights")
    posiciones = [
        {"ticker": "A", "qty": 1000},
        {"ticker": "B", "qty": 1},
        {"ticker": "C", "qty": 1},
    ]
    precios = {"A": 100.0, "B": 1.0, "C": 1.0}
    w = value_weights(posiciones, precios, ["A", "B", "C"])
    assert w[0] > 0.99, f"A domina la cartera, debería pesar >99%, da {w[0]:.4f}"
    assert not casi(w[0], 1 / 3, 1e-3), "cayó a equiponderado"


def test_pesos_suman_uno():
    value_weights = require("core.models.portfolio", "value_weights")
    posiciones = [{"ticker": "A", "qty": 3}, {"ticker": "B", "qty": 7}]
    w = value_weights(posiciones, {"A": 10.0, "B": 5.0}, ["A", "B"])
    assert casi(sum(w), 1.0, 1e-9)


# ══════════════════════════════════════════════════════════════════════════
#  RIESGO — fórmulas con resultado calculable a mano
# ══════════════════════════════════════════════════════════════════════════

def test_desviacion_a_la_baja_promedia_sobre_todas_las_observaciones():
    """La desviación a la baja divide por N, no por la cantidad de negativos.

    Error detectado el 2026-09-02 en QuantFolio: dividía por N_neg, lo que
    infla la desviación en torno a √2 y SUBESTIMA el Sortino de forma
    sistemática. Como el Sortino es uno de los ocho criterios que eligen la
    cartera ganadora, el error se propagaba a la decisión.

    Con retornos [+2%, −1%, +3%, −2%] y umbral 0:
        Σ min(r,0)² = 0.0001 + 0.0004 = 0.0005
        correcto  = √(0.0005 / 4) = 0.01118034
        el bug da = √(0.0005 / 2) = 0.01581139
    """
    dd = require("core.models.risk", "downside_deviation")
    rets = [0.02, -0.01, 0.03, -0.02]
    assert casi(dd(rets, 0.0), 0.011180339887, 1e-9), (
        f"da {dd(rets, 0.0):.10f}; si da 0.0158 está dividiendo por N_neg")


def test_contribuciones_al_riesgo_suman_la_volatilidad():
    """Identidad de Euler: Σ CR_i = σ_p, exactamente.

    Reemplaza la descomposición vieja, que ponderaba varianzas por CANTIDAD DE
    NOMINALES, ignoraba las covarianzas y omitía el término cruzado — sus
    porcentajes no sumaban 100%. Esta identidad es la prueba de que la nueva
    está bien planteada.
    """
    import numpy as np
    risk_contributions = require("core.models.risk", "risk_contributions")
    cov = np.array([[0.04, 0.006, 0.001],
                    [0.006, 0.09, 0.002],
                    [0.001, 0.002, 0.16]])
    w = np.array([0.5, 0.3, 0.2])
    cr = np.asarray(risk_contributions(w, cov))
    sigma_p = float(np.sqrt(w @ cov @ w))
    assert casi(cr.sum(), sigma_p, 1e-10), (
        f"las contribuciones suman {cr.sum():.10f} y σ_p es {sigma_p:.10f}")


def test_max_drawdown_de_caso_conocido():
    """Sube 10%, baja 20%, sube 5% → el peor drawdown es −20%."""
    max_drawdown = require("core.models.risk", "max_drawdown")
    assert casi(max_drawdown([0.10, -0.20, 0.05]), -0.20, 1e-12)


# ══════════════════════════════════════════════════════════════════════════
#  OPTIMIZACIÓN — el mismo resultado dos veces
# ══════════════════════════════════════════════════════════════════════════

def test_optimo_de_markowitz_es_determinista():
    """Dos corridas seguidas dan exactamente los mismos pesos.

    Bug original (Terminal Financiera, todavía vigente): el "óptimo" era el
    mejor de 2.000 carteras generadas al azar, así que se movía de lugar entre
    corridas. Con SLSQP el resultado es el óptimo real y es estable.
    """
    import numpy as np
    max_sharpe_weights = require("core.models.markowitz", "max_sharpe_weights")
    mu = np.array([0.12, 0.08, 0.15])
    cov = np.array([[0.04, 0.006, 0.001],
                    [0.006, 0.09, 0.002],
                    [0.001, 0.002, 0.16]])
    w1 = np.asarray(max_sharpe_weights(mu, cov, rf=0.043))
    w2 = np.asarray(max_sharpe_weights(mu, cov, rf=0.043))
    assert np.allclose(w1, w2, atol=1e-12), "dos corridas dieron pesos distintos"
    assert casi(w1.sum(), 1.0, 1e-6), "los pesos no suman 1"
    assert (w1 >= -1e-9).all(), "hay pesos negativos: falta la restricción w >= 0"


def test_tope_de_concentracion_se_respeta():
    """El excedente se reparte por ESPACIO LIBRE, no por peso actual.

    Repartir proporcional al peso actual deja fuera a los activos en 0%
    (0 × factor = 0) y el tope termina violado igual.
    """
    import numpy as np
    cap_weights = require("core.models.markowitz", "cap_weights")
    w = np.asarray(cap_weights(np.array([0.90, 0.10, 0.00]), cap=0.40))
    assert w.max() <= 0.40 + 1e-9, f"el tope se violó: {w.max():.4f}"
    assert casi(w.sum(), 1.0, 1e-9)
    assert w[2] > 0, "el activo que estaba en 0% tiene que recibir parte del excedente"


# ══════════════════════════════════════════════════════════════════════════
#  COMPARACIÓN — que el ganador sea un ganador
# ══════════════════════════════════════════════════════════════════════════

def test_dos_carteras_identicas_no_tienen_ganador():
    """Comparada consigo misma, ninguna cartera gana: p debe dar 1.

    Es el control de cordura de la prueba de Sharpe. Si una serie "le gana" a su
    propia copia, el estadístico está mal y todo veredicto sale contaminado.
    """
    import numpy as np
    test = require("core.models.comparacion", "test_diferencia_sharpe")
    rng = np.random.default_rng(3)
    r = rng.normal(0.0004, 0.012, 800)
    t = test(r, r.copy())
    assert abs(t["diferencia_anual"]) < 1e-9, "una serie no puede superarse a sí misma"
    assert t["p_valor"] > 0.99, f"p = {t['p_valor']}, debería ser 1"
    assert not t["concluyente"]


def test_diferencia_grande_y_sostenida_si_se_detecta():
    """Contraparte: una ventaja real y persistente tiene que dar p bajo.

    Sin este caso, un test que devolviera "no concluyente" siempre pasaría el
    control de arriba y parecería correcto.
    """
    import numpy as np
    test = require("core.models.comparacion", "test_diferencia_sharpe")
    rng = np.random.default_rng(4)
    mala = rng.normal(0.0000, 0.012, 1500)
    buena = rng.normal(0.0012, 0.012, 1500)     # mucho más retorno, misma volatilidad
    t = test(buena, mala)
    assert t["diferencia_anual"] > 0.5
    assert t["p_valor"] < 0.05, f"p = {t['p_valor']}: no detectó una ventaja real"
    assert t["concluyente"]


def test_la_correlacion_entra_en_la_prueba():
    """Dos carteras que comparten activos están correlacionadas, y eso cambia el p.

    Ignorar la correlación sobrestima la significancia: es el motivo por el que
    la prueba usa Jobson-Korkie-Memmel y no una comparación suelta de Sharpes.
    """
    import numpy as np
    test = require("core.models.comparacion", "test_diferencia_sharpe")
    rng = np.random.default_rng(5)
    base = rng.normal(0.0005, 0.012, 1000)
    parecida = base + rng.normal(0.0001, 0.002, 1000)      # muy correlacionada
    distinta = rng.normal(0.0006, 0.012, 1000)             # independiente
    t_par = test(parecida, base)
    t_dis = test(distinta, base)
    assert t_par["correlacion"] > 0.9
    assert abs(t_dis["correlacion"]) < 0.3


# ══════════════════════════════════════════════════════════════════════════
#  CSV — el contrato de entrada y salida
# ══════════════════════════════════════════════════════════════════════════

def test_plantilla_csv_tiene_las_columnas_del_contrato():
    """La plantilla que descarga el usuario define el formato. No puede driftear.

    `source` y `currency` son las dos columnas que hoy no existen en ninguna de
    las dos apps y son la causa de los dos errores de valuación conocidos: el
    bono sin dividir por 100 y el CEDEAR dividido por el MEP.
    """
    import csv
    ruta = Path(__file__).resolve().parent.parent / "examples" / "plantilla_cartera.csv"
    assert ruta.exists(), f"falta {ruta}"
    with open(ruta, encoding="utf-8-sig") as f:
        cols = next(csv.reader(f))
    # Se compara contra el módulo, no contra una lista escrita a mano acá: así
    # agregar una columna obliga a actualizar la plantilla y no al revés.
    esperadas = require("core.io.csv_native", "COLUMNAS")
    assert cols == esperadas, f"columnas {cols}"
    assert "source" in cols and "currency" in cols
    assert "record" in cols, "sin `record` no se distingue un dividendo de una compra"


def test_ida_y_vuelta_del_csv_no_pierde_nada():
    """Exportar e importar devuelve exactamente la misma cartera."""
    import io
    read_positions, write_positions = require(
        "core.io.csv_native", "read_positions", "write_positions")
    original = [
        {"ticker": "GGAL.BA", "buy_date": "2025-09-19", "buy_price": 2800.0,
         "qty": 2970.0, "commissions": 50311.8, "source": "",
         "currency": "", "asset_type": "", "notes": ""},
        {"ticker": "TLCPO.BA", "buy_date": "2026-05-20", "buy_price": 164780.0,
         "qty": 3324.0, "commissions": 0.0, "source": "cocos",
         "currency": "", "asset_type": "RF Privada (ON)", "notes": "canje"},
    ]
    buf = io.StringIO()
    write_positions(buf, original)
    buf.seek(0)
    vuelta = read_positions(buf)
    assert len(vuelta) == len(original)
    for a, b in zip(original, vuelta):
        for k in ("ticker", "buy_date", "source", "asset_type", "notes"):
            assert str(a[k]) == str(b[k]), f"{k}: {a[k]!r} != {b[k]!r}"
        for k in ("buy_price", "qty", "commissions"):
            assert casi(a[k], b[k], 1e-9), f"{k}: {a[k]} != {b[k]}"


def test_papel_y_dolar_suman_el_resultado_exacto():
    """El realizado se abre en dos y los dos suman el neto, sin residuo.

    Caso de manual: se gana 50 % en pesos mientras el MEP sube 50 %. El
    resultado en dólares es CERO, y esa forma de cero es lo que hay que poder
    leer: +33,33 que dejó el papel y −33,33 que se llevó el dólar.

    La ganancia se convierte al MEP de la VENTA, que es el dólar con el que se
    cobró. Valuarla a la de la compra deja un tercer término suelto que no
    cierra con nada.
    """
    pnl_realizado = require("core.models.portfolio", "pnl_realizado")
    mep = require("core.data.mep", "valor")

    trade = [{"ticker": "METR.BA", "buy_date": "2024-11-13", "sell_date": "2025-10-27",
              "buy_price": 100.0, "sell_price": 150.0, "qty": 1000.0,
              "buy_comm": 0.0, "sell_comm": 0.0, "pnl": 50000.0}]
    r = pnl_realizado(trade)
    mc = mep("2024-11-13")
    mv = mep("2025-10-27")
    if not mc or not mv:
        raise Pendiente("sin serie de MEP para las fechas del caso")

    esperado_activo = (150000.0 - 100000.0) / mv
    esperado_fx = 100000.0 * (1 / mv - 1 / mc)
    assert casi(r["total_activo_usd"], round(esperado_activo, 2), tol=0.02)
    assert casi(r["total_fx_usd"], round(esperado_fx, 2), tol=0.02)
    assert casi(r["total_activo_usd"] + r["total_fx_usd"], r["total_usd"], tol=0.02), \
        "papel + dólar tiene que dar el neto, sin término suelto"

    # Lo que ya estaba en dólares no tuvo exposición: todo es del papel.
    en_usd = pnl_realizado([{"ticker": "AAPLD.BA", "buy_date": "2025-01-10",
                             "sell_date": "2025-06-10", "buy_price": 10.0,
                             "sell_price": 12.0, "qty": 100.0, "buy_comm": 0.0,
                             "sell_comm": 0.0, "pnl": 200.0}])
    assert casi(en_usd["total_fx_usd"], 0.0), "un CEDEAR D no tiene riesgo de cambio acá"
    assert casi(en_usd["total_activo_usd"], en_usd["total_usd"])


def test_la_moneda_del_dividendo_manda_sobre_la_del_ticker():
    """Un CEDEAR D cotiza en dólares y su dividendo se acredita en pesos.

    TSMD.BA vale dólares, así que la convención del ticker diría USD. Si el
    cobro fue en pesos y el registro lo dice, se convierte con el MEP: dar por
    sentada la moneda del papel multiplica el importe por mil quinientos.
    """
    pnl_realizado = require("core.models.portfolio", "pnl_realizado")
    base = {"ticker": "TSMD.BA", "tipo": "dividendo",
            "buy_date": "2025-06-20", "sell_date": "2025-06-20",
            "buy_price": 0.0, "sell_price": 1000.0, "qty": 10.0,
            "buy_comm": 0.0, "sell_comm": 0.0, "pnl": 10000.0}

    sin_moneda = pnl_realizado([base])["total_usd"]
    en_pesos = pnl_realizado([{**base, "moneda": "ARS"}])["total_usd"]
    assert casi(sin_moneda, 10000.0), "sin dato explícito vale la convención del ticker (USD)"
    assert en_pesos < sin_moneda / 100, \
        f"declarado en pesos tiene que pasar por el MEP: {en_pesos} vs {sin_moneda}"


def test_el_csv_propio_lleva_dividendos_y_cerradas():
    """Exportar es respaldar TODO: si no, cada reimportación pierde lo cargado a mano.

    Un dividendo anotado a mano no está en ningún CSV de broker. Si la
    exportación propia no lo incluye, el respaldo miente y hay que volver a
    cargarlo después de cada importación.
    """
    import io
    write_todo = require("core.io.csv_native", "write_todo")
    read_positions = require("core.io.csv_native", "read_positions")
    read_realizado = require("core.io.csv_native", "read_realizado")

    pos = [{"ticker": "METR.BA", "buy_date": "2025-01-10", "buy_price": 2000.0,
            "qty": 500.0, "commissions": 10.0}]
    real = [{"ticker": "METR.BA", "tipo": "dividendo", "buy_date": "2025-06-20",
             "sell_date": "2025-06-20", "buy_price": 0.0, "sell_price": 70.0,
             "qty": 500.0, "buy_comm": 0.0, "sell_comm": 0.0, "pnl": 35000.0}]
    buf = io.StringIO()
    write_todo(buf, pos, real)
    texto = buf.getvalue()

    vuelta_pos = read_positions(io.StringIO(texto))
    vuelta_real = read_realizado(io.StringIO(texto))
    assert len(vuelta_pos) == 1, "el dividendo no puede colarse como posición abierta"
    assert casi(vuelta_pos[0]["qty"], 500.0)
    assert len(vuelta_real) == 1 and vuelta_real[0]["tipo"] == "dividendo"
    assert casi(vuelta_real[0]["pnl"], 35000.0), "500 × 70"


def test_reimportar_el_mismo_archivo_no_duplica_el_realizado():
    """Volver a subir un CSV pisa lo que ese archivo dejó, no se suma a ello.

    El deduplicado por clave no alcanza: al corregir el prorrateo de los splits,
    los mismos trades salieron con otras cantidades y otros precios, ninguna
    clave coincidió y el P&L de COME quedó contado dos veces.
    """
    import tempfile, os
    from pathlib import Path
    agregar = require("core.io.store", "agregar_realizado")
    import core.io.store as store
    original = store.REALIZADO
    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
    tmp.write(b"{}"); tmp.close()
    store.REALIZADO = Path(tmp.name)
    try:
        v1 = [{"ticker": "COME.BA", "buy_date": "2025-05-14", "buy_price": 175.5,
               "sell_date": "2026-02-27", "sell_price": 48.79, "qty": 8000.0,
               "buy_comm": 0.0, "sell_comm": 0.0, "pnl": -1013680.0}]
        v2 = [{**v1[0], "buy_price": 78.2, "qty": 17940.5, "pnl": -1013680.0}]
        agregar("X", v1, "yahoo:leandro1.csv")
        agregar("X", v2, "yahoo:leandro1.csv")
        quedan = store.cargar_realizado("X")
        assert len(quedan) == 1, f"el mismo archivo dos veces dejó {len(quedan)} registros"
        assert casi(quedan[0]["qty"], 17940.5), "queda la versión nueva, no la vieja"

        # Un dividendo cargado a mano no lleva lote: ninguna reimportación lo toca.
        agregar("X", [{"ticker": "METR.BA", "tipo": "dividendo",
                       "buy_date": "2025-06-20", "sell_date": "2025-06-20",
                       "buy_price": 0.0, "sell_price": 70.0, "qty": 500.0,
                       "pnl": 35000.0}])
        agregar("X", v2, "yahoo:leandro1.csv")
        assert len(store.cargar_realizado("X")) == 2, "la reimportación borró el dividendo"
    finally:
        store.REALIZADO = original
        os.unlink(tmp.name)


def test_split_reparte_el_costo_en_vez_de_regalar_acciones():
    """Un split no es una compra a precio cero: es el mismo costo en más papeles.

    Compra 100 a 200 y recibe 100 por un split 2×1. Debe quedar UN lote de 200
    unidades a 100 —el costo total sigue siendo 20.000—, no dos lotes donde uno
    figura gratis. Si después se vende la mitad a 120, la ganancia es
    100 × (120 − 100) = 2.000, y no los 12.000 que daría aparear la venta contra
    un lote regalado.
    """
    import io
    parse_yahoo = require("core.io.csv_yahoo", "parse_yahoo")
    csv_split = (
        "Symbol,Trade Date,Purchase Price,Quantity,Commission,Comment,Transaction Type\n"
        "COME.BA,2025-05-14,200.00,100,0,,Buy\n"
        "COME.BA,2025-08-14,0,100,0,split,Buy\n"
        "COME.BA,2026-02-27,120.00,100,0,,Sell\n"
    )
    abiertas, realizadas = parse_yahoo(io.StringIO(csv_split))
    assert len(abiertas) == 1, f"un solo lote abierto, hay {len(abiertas)}"
    assert casi(abiertas[0]["qty"], 100.0), "quedan 100 de las 200 post-split"
    assert casi(abiertas[0]["buy_price"], 100.0), "200 repartido en el doble de papeles"
    assert casi(sum(t["pnl"] for t in realizadas), 2000.0), \
        "100 × (120 − 100); un lote a costo cero daría 12.000"


def test_dividendo_es_resultado_realizado_sin_compra():
    """Un dividendo cobrado entra al P&L realizado y no toca la posición.

    Sin esto el resultado realizado queda corto contra el resumen del broker, y
    la diferencia es invisible: no hay ninguna operación que la explique.
    """
    import io
    parse_yahoo = require("core.io.csv_yahoo", "parse_yahoo")
    csv_div = (
        "Symbol,Trade Date,Purchase Price,Quantity,Commission,Comment,Transaction Type\n"
        "METR.BA,2025-01-10,2000.00,500,0,,Buy\n"
        "METR.BA,2025-06-20,70.00,500,0,dividendo en efectivo,Dividend\n"
    )
    abiertas, realizadas = parse_yahoo(io.StringIO(csv_div))
    assert casi(sum(a["qty"] for a in abiertas), 500.0), "el dividendo no agrega papeles"
    assert len(realizadas) == 1 and realizadas[0].get("tipo") == "dividendo"
    assert casi(realizadas[0]["pnl"], 35000.0), "500 × 70"


def test_yahoo_netea_ventas_fifo():
    """Del CSV de Yahoo solo entra lo que sigue ABIERTO; lo cerrado va al P&L.

    Compra 10 a 150, vende 5 a 160 → queda 1 lote abierto de 5 a 150, y un
    trade realizado de 5 unidades con 50 de ganancia.
    """
    import io
    parse_yahoo = require("core.io.csv_yahoo", "parse_yahoo")
    csv_yahoo = (
        "Symbol,Trade Date,Purchase Price,Quantity,Commission,Comment,Transaction Type\n"
        "AAPL,2025-01-10,150.00,10,0,,Buy\n"
        "AAPL,2025-03-05,160.00,5,0,,Sell\n"
        "$$CASH_TX,,,,,,Deposit\n"
        "NVDA,,,,,,\n"
    )
    abiertas, realizadas = parse_yahoo(io.StringIO(csv_yahoo))
    assert len(abiertas) == 1, f"debería quedar 1 lote abierto, hay {len(abiertas)}"
    assert casi(abiertas[0]["qty"], 5.0), "quedan 5 unidades abiertas"
    assert casi(abiertas[0]["buy_price"], 150.0)
    assert len(realizadas) == 1
    assert casi(realizadas[0]["pnl"], 50.0), "5 × (160 − 150) = 50"


def test_yahoo_repara_coma_suelta_en_comment():
    """Una coma sin comillas dentro de Comment corre la última columna.

    Si no se repara, "Transaction Type" se lee de otro campo y el neteo
    BUY/SELL trabaja sobre basura, en silencio.
    """
    import io
    parse_yahoo = require("core.io.csv_yahoo", "parse_yahoo")
    csv_yahoo = (
        "Symbol,Trade Date,Purchase Price,Quantity,Commission,Comment,Transaction Type\n"
        "AAPL,2025-01-10,150.00,10,0,1397,247706422,Buy\n"
    )
    abiertas, _ = parse_yahoo(io.StringIO(csv_yahoo))
    assert len(abiertas) == 1, "la fila con coma suelta se perdió o se leyó mal"
    assert casi(abiertas[0]["qty"], 10.0)



def test_eventos_del_mep_caen_dentro_del_rango():
    """Un hito fuera del rango pedido pinta un triángulo en el borde del gráfico.

    El filtro compara fechas como texto ISO, que ordena bien solo si todas tienen
    el mismo formato: un "2025-4-2" en el JSON se cuela en cualquier rango.
    """
    eventos = require("core.data.mep", "eventos")
    todos = eventos()
    assert todos, "data/eventos_mep.json vacío o ilegible."
    for e in todos:
        assert len(e["fecha"]) == 10 and e["fecha"][4] == e["fecha"][7] == "-", \
            f"Fecha no ISO: {e['fecha']}"
    recorte = eventos("2025-01-01", "2025-12-31")
    assert all("2025-01-01" <= e["fecha"] <= "2025-12-31" for e in recorte)
    assert len(recorte) < len(todos)



def test_pico_de_una_rueda_no_entra_en_la_serie():
    """Un valor que sube 15% y al día siguiente ya no está es un dato malo.

    Pasó de verdad: ArgentinaDatos publicó el MEP del 2025-05-02 en $1.363,60
    entre $1.182 y $1.170, y toda operación de esa fecha se valuaba 16% mal. El
    filtro por nivel no lo veía porque el pico no sale del rango del mes. Lo que
    NO puede hacer el filtro es comerse una devaluación real, que salta igual de
    fuerte pero se queda arriba.
    """
    filtrar = require("core.data.mep", "_filtrar_outliers")
    date_range, Series = require("pandas", "date_range", "Series")
    fechas = date_range("2025-04-01", periods=40, freq="D")

    pico = Series(1180.0, index=fechas)
    pico.iloc[20] = 1363.6
    assert fechas[20] not in filtrar(pico).index, "El pico de una rueda quedó en la serie."

    salto = Series(1180.0, index=fechas)
    salto.iloc[20:] = 1363.6
    assert fechas[20] in filtrar(salto).index, "Se comió una devaluación real."
    assert len(filtrar(salto)) == len(salto)



def test_el_mismo_trade_con_otro_formato_de_fecha_no_se_duplica():
    """Yahoo exporta "20250919" y el CSV propio "2025-09-19": es el mismo trade.

    Pasó en MAMI: 11 operaciones entraron dos veces porque la clave de duplicado
    comparaba las fechas como texto crudo, y el realizado dio 4.588 dólares en
    lugar de 2.300. Las dos copias se ven legítimas leyendo el archivo.
    """
    normalizar = require("core.io.store", "_normalizar_trade")
    crudo = {"ticker": "GLDD.BA", "buy_date": "20250919", "sell_date": "20260205",
             "buy_price": 6.93, "sell_price": 9.17, "qty": 356.0}
    iso = dict(crudo, buy_date="2025-09-19", sell_date="2026-02-05")
    clave = lambda t: (t["ticker"], t["buy_date"], t["sell_date"],                # noqa: E731
                       t["buy_price"], t["sell_price"], t["qty"])
    assert clave(normalizar(crudo)) == clave(normalizar(iso))


def test_bono_cargado_por_nominal_no_se_divide_de_nuevo():
    """AL30D a 0,643 ya viene por nominal; a 64,30 viene por 100 nominales.

    La fuente de precios publica los bonos cada 100 nominales, así que el núcleo
    divide por 100. Aplicarlo también a un precio que el usuario cargó por
    nominal convirtió una operación de 1.572 dólares en una de 15,72 —el AL30D
    de MAMI cerró en −0,19 cuando el broker decía −19,44—.
    """
    divisor = require("core.data.sources", "divisor_nominal")
    assert divisor("AL30D", 0.643) == 1.0, "Dividió un precio que ya era por nominal."
    assert divisor("AL30D", 64.30) == 100.0, "No dividió una paridad por 100 nominales."
    assert divisor("MELI.BA", 25580.0) == 1.0, "Una acción no se divide nunca."


def test_fci_cada_1000_cuotapartes():
    """Cocos cotiza los FCI cada 1000 cuotapartes: sin dividir, la tenencia sale
    mil veces más grande (COCOSPPA mostraba $3.377.811 sobre $3.371 reales, y
    COCOAUSD llegó a informar una tenencia de miles de millones).

    Los números son los del broker el 2026-09-04, con la cuotaparte verificada
    contra el propio movimiento de suscripción (3.371 / 2331,23929815 = 1,446012).
    """
    from core.broker.cocos import _normalizar_fci

    pos = _normalizar_fci([
        {"short_ticker": "COCOSPPA", "instrument_type": "FCI", "quantity": 2331.23929815,
         "last": 1448.934, "average_price": 1446.012, "result": 6.8118812291943},
        {"short_ticker": "COCOAUSD", "instrument_type": "FCI", "quantity": 3729.10407907,
         "last": None, "average_price": 1674338.3090890225, "result": None},
        {"short_ticker": "KO", "instrument_type": "CEDEARS", "quantity": 179,
         "last": 28320, "average_price": 20690.614525139667, "result": 1365660},
    ])

    assert abs(pos[0]["average_price"] - 1.446012) < 1e-9, \
        "El PPC de un FCI tiene que quedar por cuotaparte."
    assert abs(pos[0]["quantity"] * pos[0]["last"] - 3377.81) < 0.01, \
        "La tenencia de COCOSPPA son ~$3.378, no $3.377.811."
    assert pos[1]["last"] is None, \
        "Un `last` nulo se deja nulo: no hay precio del día que inventar."
    assert pos[2]["last"] == 28320 and pos[2]["average_price"] == 20690.614525139667, \
        "Un CEDEAR no se toca: la escala /1000 es sólo de los FCI."


def test_un_fci_no_es_un_bono_ni_cotiza_en_dolares():
    """Un lote de FCI importado del broker no puede entrar con source="cocos".

    Ese valor activa las dos reglas de los bonos: dividir el precio por 100 y
    tratar el ticker como renta fija. Un COCOSPPA a 1,4489 pasaría a valer
    0,014489. Por eso los lotes de FCI llevan su propio `source`.
    """
    from core.data.symbols import SOURCE_FCI, is_bond
    from core.data.sources import divisor_nominal

    assert SOURCE_FCI != "cocos", "El tag de los FCI tiene que ser distinto al de los bonos."
    for t in ("COCOSPPA", "COCOAUSD", "COCORMA", "COCOUSDPA"):
        assert not is_bond(t, SOURCE_FCI), f"{t} no cotiza cada 100 nominales."
        assert divisor_nominal(t, 1448.934, SOURCE_FCI) == 1.0, \
            f"El precio de {t} no se divide por 100."


def test_la_moneda_del_lote_manda_sobre_la_del_ticker():
    """COCOAUSD es un fondo en dólares y COCOSPPA en pesos, pero ninguno de los
    dos termina en .BA: `ticker_currency` los da a los dos por dólares. El lote
    trae su `currency` y es el que tiene que mandar, si no un fondo en pesos se
    valúa 1.500 veces de más.
    """
    from core.data.sources import ticker_currency

    assert ticker_currency("COCOSPPA") == "USD", \
        "Si esto cambia, revisar que valuar() siga prefiriendo la moneda del lote."
    lote = {"ticker": "COCOSPPA", "currency": "ARS"}
    moneda = (lote.get("currency") or ticker_currency(lote["ticker"])).upper()
    assert moneda == "ARS", "La moneda del lote tiene prioridad sobre la del ticker."



def test_un_precio_suelto_valua_pero_no_entra_en_los_modelos():
    """DELLD.BA, CEDEAR listado en septiembre de 2026: ni yfinance ni BYMA
    devuelven una sola rueda, solo la cotización del día. Sin fallback el lote
    quedaba sin precio y **fuera del total de la cartera**: la tenencia mostraba
    menos plata de la que había.

    Con el fallback valúa, pero un punto no es una serie: tiene que seguir
    quedando afuera del riesgo, de la optimización y del momentum, igual que un
    FCI. Si algún día entra, cualquier volatilidad o correlación que salga de
    ahí es ruido presentado como número.
    """
    import pandas as pd
    from core.data import cache, sources
    from core.models.portfolio import matriz_retornos

    original = cache.leer_respuesta
    cache.leer_respuesta = lambda clave, ttl_horas=24, default=None: 7.26
    try:
        df = sources._spot_yfinance("DELLD.BA")
    finally:
        cache.leer_respuesta = original

    assert len(df) == 1 and round(float(df["Close"].iloc[0]), 2) == 7.26, \
        "Sin serie, el spot tiene que devolver igual un punto valuable."

    original_usd = sources.precios_base
    sources.precios_base = lambda t, **kw: pd.Series(
        [7.26], index=[pd.Timestamp("2026-09-04")])
    try:
        ret_df, precios = matriz_retornos([{"ticker": "DELLD.BA", "qty": 146}])
    finally:
        sources.precios_base = original_usd

    assert ret_df.empty and "DELLD.BA" not in precios, \
        "Un solo punto no puede entrar en la matriz de retornos."

def test_un_fci_que_cocos_no_cotiza_vale_su_ppc_y_no_desaparece():
    """Un fondo sin cuotaparte publicada se valúa al PPC, no en cero.

    Cocos sólo publica la cuotaparte de los fondos que tenés HOY en la cuenta
    conectada. Un fondo rescatado, o el de otra cuenta de la familia, no tiene
    precio nunca — y la tenencia entera desaparecía del total de la cartera.
    Real: LEANDRO tenía COCOSPPA («Cocos Pesos Plus - Mami») mientras la cuenta
    conectada tenía COCORMA, y esa posición valía cero desde siempre.

    Se cae al PPC y queda marcada `precio_estimado`, para que la pantalla lo
    aclare y nadie lo lea como precio de mercado.
    """
    portfolio, sources = require("core.models", "portfolio"), require("core.data", "sources")

    original = sources.precios_base
    sources.precios_base = lambda t, **k: __import__("pandas").Series(dtype=float)
    try:
        r = portfolio.valuar([{"ticker": "COCOXX", "qty": 1000, "buy_price": 1.5,
                                 "buy_date": "2026-08-31", "currency": "ARS",
                                 "source": sources.SOURCE_FCI, "commissions": 0}])
    finally:
        sources.precios_base = original

    f = r["posiciones"][0]
    assert not f["sin_precio"], "el fondo no puede quedar sin precio y fuera del total"
    assert f["precio_estimado"] is True, "tiene que quedar marcado como estimado"
    assert f["valor_usd"] and f["valor_usd"] > 0, "y valer algo, no cero"
    assert r["sin_precio"] == [], "no puede figurar en la lista de sin precio"


def test_un_fci_sin_broker_vale_lo_ultimo_visto_y_no_cero():
    """Caído Cocos, el fondo sigue valuado con la última cuotaparte conocida.

    Antes no se cacheaba, con el argumento de que "es el precio de hoy y mañana
    es otro". El efecto era peor que un precio viejo: sin sesión de Cocos el FCI
    salía «sin precio» y quedaba **fuera del total de la cartera**, o sea una
    tenencia real valuada en nada. Un valor de ayer es una aproximación; cero es
    un error.
    """
    import pandas as pd
    from datetime import date

    sources = require("core.data", "sources")
    cocos = require("core.broker", "cocos")

    original = cocos.precio_fci
    with cache_aparte():
        try:
            cocos.precio_fci = lambda t: 1234.56        # broker vivo
            con = sources.precios_base("FCITEST", source=sources.SOURCE_FCI)
            assert len(con) == 1 and float(con.iloc[-1]) > 0, \
                "con broker tiene que haber precio"

            cocos.precio_fci = lambda t: None           # broker caído
            sin = sources.precios_base("FCITEST", source=sources.SOURCE_FCI)
        finally:
            cocos.precio_fci = original

    assert len(sin) == 1, "sin broker el fondo NO puede quedarse sin precio"
    assert casi(float(sin.iloc[-1]), float(con.iloc[-1])), \
        "tiene que ser exactamente la última cuotaparte que se vio"


# ══════════════════════════════════════════════════════════════════════════
#  SESIÓN WEB — la contraseña de otro no vive en nuestro disco
# ══════════════════════════════════════════════════════════════════════════

def test_sobre_reemitido_no_reinicia_el_reloj_del_2fa():
    """Renovar el access token NO puede correr la fecha de vencimiento.

    Bug de diseño, cazado antes de escribirlo: el access token de Cocos dura una
    hora y se renueva solo con el refresh token, y cada renovación obliga a
    reemitir el sobre. Si el sobre nuevo llevara timestamp nuevo, el usuario que
    entra todos los días nunca volvería a tipear el 2FA: la caducidad de 24 h
    sería decorativa y la sesión, eterna. El reloj cuelga de `login_ts`, que se
    arrastra intacto de sobre en sobre.
    """
    import time
    sesion = require("core.broker", "sesion")

    hace_23h = time.time() - 23 * 3600
    original = sesion.emitir({"access_token": "viejo"}, login_ts=hace_23h)

    # una hora después, Cocos renovó el token y reemitimos
    reemitido = sesion.emitir({"access_token": "nuevo"},
                              login_ts=sesion.leer(original)["login_ts"])
    abierto = sesion.leer(reemitido)

    assert abierto["access_token"] == "nuevo", "el sobre nuevo lleva el token nuevo"
    assert casi(abierto["login_ts"], hace_23h, tol=1), \
        "login_ts tiene que sobrevivir la reemisión, o el 2FA diario no llega nunca"
    assert sesion.vence_en(abierto) <= 3600, \
        "a 23 h del login le puede quedar 1 h como mucho, no 24 de nuevo"


def test_sobre_vencido_no_abre():
    """Pasadas las 24 h el sobre no sirve: vuelve a pedirse el 2FA.

    Es la única cosa que obliga al segundo factor a aparecer. Sin esto, un JWT
    robado del navegador vale hasta que Cocos lo caduque, que son días.
    """
    import time
    sesion = require("core.broker", "sesion")

    viejo = sesion.emitir({"access_token": "x"}, login_ts=time.time() - 25 * 3600)
    try:
        sesion.leer(viejo)
        assert False, "un sobre de hace 25 h no puede abrir"
    except sesion.SesionInvalida:
        pass
    assert sesion.vence_en(sesion.leer(viejo, max_age=99 * 3600)) == 0


def test_sobre_manipulado_no_abre():
    """Editar el sobre lo rompe: nadie se fabrica una sesión de otro."""
    sesion = require("core.broker", "sesion")

    sobre = sesion.emitir({"access_token": "mio", "account_number": "18320"})
    for mutado in (sobre + "x", sobre[:-1], sobre.replace("a", "b", 1)):
        try:
            sesion.leer(mutado)
            assert False, "un sobre manoseado no puede abrir"
        except sesion.SesionInvalida:
            pass


def test_rotar_el_secreto_tumba_las_sesiones():
    """Cambiar el secreto invalida todo lo vivo: es el botón de pánico.

    Si alguna vez sospechás que se filtraron sobres, esto es lo que los apaga
    sin tener que tocar nada del lado de Cocos.
    """
    import os
    sesion = require("core.broker", "sesion")

    previo = os.environ.get("PA_SECRETO_SESION")
    try:
        os.environ["PA_SECRETO_SESION"] = "secreto-de-hoy"
        sobre = sesion.emitir({"access_token": "x"})
        assert sesion.leer(sobre)["access_token"] == "x"

        os.environ["PA_SECRETO_SESION"] = "secreto-rotado"
        try:
            sesion.leer(sobre)
            assert False, "tras rotar el secreto no puede abrir ningún sobre viejo"
        except sesion.SesionInvalida:
            pass
    finally:
        if previo is None:
            os.environ.pop("PA_SECRETO_SESION", None)
        else:
            os.environ["PA_SECRETO_SESION"] = previo


def test_el_sobre_no_lleva_la_contrasena():
    """Lo que viaja al navegador son JWT, nunca las credenciales.

    El sobre está firmado, no cifrado: cualquiera que lo tenga lo lee. Que ahí
    adentro no haya contraseña ni semilla TOTP es lo que hace que eso no
    importe. Este test es el que se rompe si alguien, por comodidad, mete las
    credenciales en el sobre para "reconectar solo".
    """
    import base64
    sesion = require("core.broker", "sesion")

    sobre = sesion.emitir({"access_token": "a", "refresh_token": "b",
                           "account_number": "18320"})
    crudo = sobre.split(".")[0]
    claro = base64.urlsafe_b64decode(crudo + "=" * (-len(crudo) % 4)).decode()

    for prohibido in ("password", "contrasena", "totp_secret", "email"):
        assert prohibido not in claro.lower(), \
            f"el sobre lleva {prohibido!r} adentro y viaja en claro al navegador"


def test_la_renovacion_devuelve_el_sobre_por_la_cabecera():
    """Renovado el token, el sobre nuevo vuelve al navegador con el reloj VIEJO.

    Es el mismo peligro que `test_sobre_reemitido_no_reinicia_el_reloj_del_2fa`,
    pero un piso más arriba: ahí se prueba la función, acá el cableado HTTP de
    `api/app.py`, que es quien decide qué login_ts usar al reemitir. Si alguien
    "simplifica" ese emitir() sacándole el login_ts, la función sigue estando
    bien y la sesión se vuelve eterna igual.
    """
    import time
    sesion = require("core.broker", "sesion")
    broker = require("core.broker", "cocos")
    flask_app = require("api", "app").app

    hace_23h = time.time() - 23 * 3600
    sobre = sesion.emitir({"access_token": "viejo", "refresh_token": "r",
                           "token_expiration": 0, "account_number": "18320"},
                          login_ts=hace_23h)

    original = broker.restaurar
    broker.restaurar = lambda jwt: (
        {"conectado": True, "detalle": "sesión restaurada", "cuenta": "18320"},
        {**jwt, "access_token": "nuevo"})
    try:
        with modo_web():
            r = cliente_web(flask_app).get("/api/broker/estado",
                                           headers={"X-Sesion": sobre})
    finally:
        broker.restaurar = original

    assert r.status_code == 200, f"la sesión válida tiene que pasar ({r.status_code})"
    devuelto = r.headers.get("X-Sesion")
    assert devuelto, "el sobre renovado tiene que volver por la cabecera"

    abierto = sesion.leer(devuelto)
    assert abierto["access_token"] == "nuevo", "tiene que traer el token renovado"
    assert casi(abierto["login_ts"], hace_23h, tol=2), \
        "el sobre que vuelve arrastra el login_ts viejo, o el 2FA nunca se pide"


def test_restaurar_en_paralelo_no_dispara_el_login_de_verdad():
    """Dos hilos restaurando a la vez no pueden terminar logueándose.

    `_restaurar` neutraliza `Cocos._auth` —un atributo de CLASE— para que el
    constructor no autentique, y lo restaura al salir. Con requests en paralelo
    un hilo lo restauraba mientras otro todavía no había construido su cliente,
    y ese segundo corría el `_auth` de verdad con las credenciales de relleno
    ("-"). Cocos contestaba "Invalid login credentials" y desconectaba a alguien
    que acababa de conectarse. Pasó de verdad el 2026-09-08, en la primera
    prueba del modo web con una cuenta real.
    """
    import threading
    import time as _t
    broker = require("core.broker", "cocos")

    autenticados = []

    class FalsoCliente:
        def __init__(self, **kw):
            # La ventana de la carrera es el tiempo que tarda el constructor. En
            # el caso real la abre cloudscraper (~18 ms); sin esta espera el test
            # pasa aunque el lock no esté y no prueba nada. Medido: 1 de 12 hilos
            # se autentica sin lock, 0 con lock.
            _t.sleep(0.02)
            self._auth()                     # como hace pyCocos en su constructor
            self.client = type("C", (), {"update_session_headers": lambda s, h: None})()
            self.access_token = self.refresh_token = ""
            self.token_expiration = 0
            self.account_number = ""

        def _auth(self):
            autenticados.append(1)           # esto NO puede pasar nunca

    ses = {"access_token": "a", "refresh_token": "b",
           "token_expiration": 9e9, "account_number": "1"}
    fallas = []

    def restaurar():
        try:
            broker._restaurar(FalsoCliente, {}, ses)
        except Exception as e:
            fallas.append(e)

    hilos = [threading.Thread(target=restaurar) for _ in range(12)]
    for h in hilos: h.start()
    for h in hilos: h.join()

    assert not fallas, f"restaurar en paralelo falló: {fallas[0]}"
    assert not autenticados, \
        f"{len(autenticados)} hilos hicieron el login de verdad: el parche de _auth se pisó"
    assert FalsoCliente._auth is not None, "el método tiene que quedar restaurado"


def test_la_pagina_no_carga_scripts_de_terceros():
    """Ningún <script> de esta app puede venir de otro dominio.

    React y Plotly se servían desde cdnjs. Un script de terceros corre con
    acceso total a la página: lee el localStorage —donde vive el sobre de
    sesión de Cocos— y ve la contraseña que se tipea en el formulario del
    broker. Un CDN comprometido entregaba las sesiones de todos los usuarios.
    Están en `web/vendor/` por eso; este test se rompe si alguien vuelve a
    poner una URL de afuera por comodidad.
    """
    import re
    from pathlib import Path as _P

    html = (_P(__file__).resolve().parent.parent / "web" / "index.html").read_text()
    externos = [s for s in re.findall(r'<script[^>]*src="([^"]+)"', html)
                if s.startswith("http") or s.startswith("//")]
    assert not externos, f"scripts de terceros en index.html: {externos}"

    for f in ("react.production.min.js", "react-dom.production.min.js", "plotly.min.js"):
        ruta = _P(__file__).resolve().parent.parent / "web" / "vendor" / f
        assert ruta.exists() and ruta.stat().st_size > 1000, \
            f"falta {f} en web/vendor/: la página quedaría sin dibujar nada"


def test_la_csp_deja_pasar_el_avatar_y_no_deja_pasar_scripts_sueltos():
    """La política de contenido: permisiva con la foto, estricta con el código.

    Dos cosas distintas y las dos importan. `img-src` tiene que habilitar
    googleusercontent o la foto de perfil sale como un círculo vacío y nadie
    entiende por qué. Y `script-src` no puede tener 'unsafe-inline': esta página
    maneja sesiones de broker, y un script inyectado lee el sobre de Cocos del
    localStorage.
    """
    flask_app = require("api", "app").app
    r = flask_app.test_client().get("/api/modo")
    csp = r.headers.get("Content-Security-Policy", "")

    assert csp, "toda respuesta tiene que llevar CSP"
    img = [d for d in csp.split(";") if d.strip().startswith("img-src")][0]
    assert "googleusercontent.com" in img, \
        "sin esto la foto de perfil de Google queda bloqueada"

    script = [d for d in csp.split(";") if d.strip().startswith("script-src")][0]
    assert "unsafe-inline" not in script and "unsafe-eval" not in script, \
        "un script inline puede leer el sobre de Cocos del localStorage"
    assert script.strip() == "script-src 'self'", \
        f"nadie más que este servidor puede poner código en la página: {script!r}"
    assert "frame-ancestors 'none'" in csp, "nadie puede meter esto en un iframe"
    assert r.headers.get("X-Content-Type-Options") == "nosniff"


def test_sin_ingresar_no_se_llega_a_ningun_dato():
    """La sesión de la app es la puerta. Sin ella no hay datos de nadie.

    Es lo único que separa la cartera de un usuario de la de otro cuando la app
    se sirve a cualquiera que se registre.
    """
    flask_app = require("api", "app").app
    with modo_web():
        r = flask_app.test_client().get("/api/carteras")

    assert r.status_code == 401, f"sin ingresar no se pasa ({r.status_code})"
    assert r.get_json().get("ingresar") is True, \
        "el front tiene que saber que toca entrar con Google, no reconectar Cocos"


def test_un_sobre_de_cocos_vencido_no_bloquea_la_app():
    """Se cae el broker, no la aplicación.

    Antes, un sobre vencido devolvía 401 en TODO endpoint, así que a alguien se
    le vencía la sesión de Cocos —que es opcional— y dejaba de poder mirar sus
    propias carteras. Ahora el sobre se descarta, el servidor lo avisa por la
    cabecera para que el navegador lo tire, y el request sigue.
    """
    import time
    sesion = require("core.broker", "sesion")
    flask_app = require("api", "app").app

    viejo = sesion.emitir({"access_token": "x"}, login_ts=time.time() - 25 * 3600)
    with modo_web():
        r = cliente_web(flask_app).get("/api/carteras", headers={"X-Sesion": viejo})

    assert r.status_code == 200, \
        f"un sobre de Cocos vencido no puede tapar las carteras ({r.status_code})"
    assert r.headers.get("X-Sesion-Fin") == "1", \
        "el navegador tiene que enterarse de que ese sobre ya no vale"


def test_cocos_es_opcional_no_una_puerta():
    """Quien no conectó el broker usa la app igual.

    Cocos suma bonos, ONs, letras y las posiciones reales. Sin eso la aplicación
    funciona: cartera a mano o por CSV y precios de yfinance. Si la falta de
    sobre cortara el request, la app quedaría inservible para quien todavía no
    conectó el broker, que es la mayoría al registrarse.
    """
    flask_app = require("api", "app").app
    with modo_web():
        r = cliente_web(flask_app).get("/api/carteras")     # sin X-Sesion

    assert r.status_code == 200, \
        f"sin Cocos la app tiene que andar igual, no cortar con {r.status_code}"


def test_en_la_web_nadie_toca_el_vault_ni_la_clave_compartida():
    """Los endpoints de la app de escritorio no existen para un usuario web.

    El front no los muestra, pero un POST a mano llega igual. Del otro lado hay
    dos cosas que no son de quien entra: el vault del dueño de la máquina —que
    `/api/broker/borrar` elimina— y la API key de FMP, que la ponemos nosotros y
    la comparten todos. Sin este corte, cualquiera con sesión se la cambiaba a
    todo el mundo.
    """
    flask_app = require("api", "app").app

    for ruta in ("/api/broker/vault", "/api/broker/borrar", "/api/broker/conectar",
                 "/api/broker/desconectar", "/api/conectores/fmp"):
        with modo_web():
            r = cliente_web(flask_app).post(ruta, json={})
        assert r.status_code == 403, \
            f"{ruta} tiene que estar cerrado en la web, devolvió {r.status_code}"


def test_la_suite_no_escribe_en_los_datos_de_verdad():
    """Correr los tests no puede cambiar nada de `data/`.

    El 2026-09-08 la limpieza de un test hizo `rmtree(data/usuarios)` y borró la
    cartera que un usuario acababa de importar. Este test compara el contenido
    del directorio antes y después de guardar en uno temporal: si alguien vuelve
    a escribir en `data/`, se rompe acá.
    """
    store = require("core.io", "store")
    real = store._DATA
    antes = sorted(p.name for p in real.iterdir()) if real.exists() else []

    with datos_aparte():
        store.como("fulano")
        store.guardar("Prueba", [{"ticker": "AAPL", "qty": 1, "buy_price": 1,
                                  "buy_date": "2026-01-02", "currency": "USD"}])
        assert store.nombres() == ["Prueba"], "tiene que haber escrito en el temporal"

    despues = sorted(p.name for p in real.iterdir()) if real.exists() else []
    assert antes == despues, \
        f"la suite tocó data/: apareció o desapareció {set(antes) ^ set(despues)}"


def test_cada_usuario_ve_solo_sus_carteras():
    """Dos usuarios distintos, dos carpetas distintas. Nunca la misma.

    `store` guardaba en `data/portfolios.json`, uno solo para todo. Servida a
    varios usuarios eso le mostraría a cualquiera la cartera del anterior.
    """
    store = require("core.io", "store")

    with datos_aparte():
        store.como("1111")
        a = store._carteras()
        store.como("2222")
        b = store._carteras()
        store.como(None)
        local = store._carteras()

    assert a != b, "dos usuarios no pueden compartir archivo de carteras"
    assert "1111" in str(a) and "2222" in str(b)
    assert local == store.CARTERAS, "sin usuario (app local) sigue siendo data/"


def test_la_cuenta_de_cocos_de_uno_no_es_la_de_otro():
    """El mapa comitente→cartera es de cada usuario, no de todos.

    Vivía en `data/connectors.json`, compartido. Ahí había dos problemas: el
    nombre de la cartera de alguien quedaba a la vista de cualquiera, y ese
    archivo guarda además el client secret de Google — escribirlo desde una
    acción del usuario, sin lock, es una forma de perderlo si dos importan FCI
    a la vez. La app local sigue leyendo la asociación vieja para no perderla.
    """
    store = require("core.io", "store")

    with datos_aparte():
        store.como("aaa")
        store.asociar_cuenta("999", "De A")
        assert store.cartera_de_cuenta("999") == "De A"

        store.como("bbb")
        assert store.cartera_de_cuenta("999") is None, \
            "la cuenta de un usuario no puede aparecerle a otro"


def test_la_carpeta_del_usuario_no_se_arma_con_lo_que_venga():
    """El identificador nombra un directorio: no puede traer barras ni puntos.

    Viene de Google firmado por nosotros, así que hoy no hay por dónde meter
    basura. Igual se valida: el día que la identidad venga de otro lado, este
    test es lo que evita un `../` que se lleve puesta la carpeta de otro.
    """
    usuarios = require("core", "usuarios")

    assert usuarios.carpeta({"sub": "1234567890"}) == "1234567890"
    for veneno in ("../otro", "a/b", "..", "", "con espacio", "punto.punto"):
        try:
            usuarios.carpeta({"sub": veneno})
            assert False, f"{veneno!r} no puede pasar como nombre de carpeta"
        except usuarios.NoAutenticado:
            pass


def test_el_state_del_ingreso_lo_firmamos_nosotros():
    """La vuelta de Google sólo vale si el `state` salió de acá.

    Sin esa firma, cualquiera puede armar una URL de callback y hacer que el
    navegador de la víctima quede logueado con una cuenta ajena (CSRF de login).
    """
    usuarios = require("core", "usuarios")

    url = usuarios.url_de_ingreso("http://localhost/api/entrar/google", "/carteras")
    state = url.split("state=")[1].split("&")[0]
    assert usuarios.leer_estado(state) == "/carteras", "el destino tiene que volver intacto"

    for falso in (state + "x", "inventado", ""):
        try:
            usuarios.leer_estado(falso)
            assert False, "un state que no firmamos no puede pasar"
        except usuarios.NoAutenticado:
            pass


def test_el_401_del_broker_tambien_pide_reautenticar():
    """Token revocado del lado de Cocos = 401 con `reautenticar`, no un 200 raro.

    Estos endpoints devuelven lo crudo del broker o {"error": ...} adentro de un
    200, que es la convención vieja del archivo. Con un token que Cocos rechaza
    —revocado, o el usuario cerró sesión desde el celular— eso deja al front
    mostrando "ApiException: ... 401" sin saber que tiene que pedir contraseña y
    2FA otra vez. Verificado en vivo el 2026-09-08: devolvía 200.
    """
    sesion = require("core.broker", "sesion")
    broker = require("core.broker", "cocos")
    flask_app = require("api", "app").app

    sobre = sesion.emitir({"access_token": "revocado", "refresh_token": "r",
                           "token_expiration": 9e9, "account_number": "1"})
    restaurar, muerta = broker.restaurar, broker.sesion_muerta
    broker.restaurar = lambda jwt: ({"conectado": True, "detalle": "ok",
                                     "cuenta": "1"}, None)
    broker.sesion_muerta = lambda: True          # como si Cocos hubiera dado 401
    try:
        with modo_web():
            r = cliente_web(flask_app).get("/api/broker/estado",
                                           headers={"X-Sesion": sobre})
    finally:
        broker.restaurar, broker.sesion_muerta = restaurar, muerta

    assert r.status_code == 401, \
        f"un 401 del broker tiene que llegar como 401, no como {r.status_code}"
    assert r.get_json().get("reautenticar") is True, \
        "sin esta señal el front muestra un error genérico y no vuelve a pedir 2FA"


def test_la_marca_de_401_no_sobrevive_al_request():
    """La marca se limpia al restaurar: un 401 de hace rato no tumba al siguiente.

    Si quedara pegada, el primer 401 de un usuario dejaría todos sus requests
    posteriores devolviendo "reautenticar" aunque la sesión ya se haya arreglado.
    """
    patch = require("core.broker", "_cocos_patch")

    class Resp:
        status_code = 401

    patch.olvidar_401()
    patch._marcar(Resp())
    assert patch.hubo_401(), "el hook tiene que marcar el 401"
    patch.olvidar_401()
    assert not patch.hubo_401(), "y restaurar() tiene que limpiar la marca"


def test_sesion_vencida_pide_reautenticar():
    """Un sobre viejo corta con 401 y una señal explícita, no con un 500 raro.

    El front necesita distinguir "se venció, pedile la contraseña y el 2FA" de
    "Cocos está caído". Sin `reautenticar`, la pantalla queda mostrando un error
    genérico y el usuario no sabe que tiene que volver a entrar.
    """
    import time
    sesion = require("core.broker", "sesion")
    flask_app = require("api", "app").app

    viejo = sesion.emitir({"access_token": "x"}, login_ts=time.time() - 25 * 3600)
    with modo_web():
        r = cliente_web(flask_app).get("/api/broker/estado", headers={"X-Sesion": viejo})

    assert r.status_code == 401, f"un sobre vencido no puede pasar ({r.status_code})"
    assert r.get_json().get("reautenticar") is True, \
        "el front tiene que saber que toca pedir contraseña y 2FA de nuevo"


def test_en_modo_local_el_sobre_se_ignora():
    """Un sobre válido no puede tocar nada en la app de todos los días.

    Los dos modos comparten el global `_cliente` de cocos.py: en modo local, una
    request con sobre restauraba el cliente desde los JWT y al terminar lo
    soltaba, dejando la sesión del vault colgada en "sin conectar". Pasó de
    verdad probando esto el 2026-09-08. El flag PA_MODO es lo que los separa.
    """
    sesion = require("core.broker", "sesion")
    flask_app = require("api", "app").app

    sobre = sesion.emitir({"access_token": "x", "refresh_token": "y",
                           "token_expiration": 0, "account_number": "1"})
    r = flask_app.test_client().get("/api/broker/estado", headers={"X-Sesion": sobre})

    assert r.status_code == 200, "en modo local la cabecera se ignora, no corta"
    assert "X-Sesion" not in r.headers, "en modo local no se emite ningún sobre"


def test_sin_cabecera_el_modo_local_sigue_intacto():
    """Sin `X-Sesion` no se toca nada: la app en tu máquina sigue con el vault.

    El modo web se agregó como camino paralelo. Si el before_request empezara a
    exigir sobre, la app de todos los días dejaría de arrancar.
    """
    flask_app = require("api", "app").app
    r = flask_app.test_client().get("/api/broker/estado")

    assert r.status_code == 200, "sin cabecera tiene que responder normal"
    assert "X-Sesion" not in r.headers, "sin sesión web no se emite ningún sobre"
    assert "vault_cargado" in r.get_json(), "el modo local sigue reportando el vault"


# ══════════════════════════════════════════════════════════════════════════

def test_una_venta_simulada_no_deja_posiciones_negativas():
    """Vender en simulación descuenta lotes FIFO; nunca crea cantidad negativa.

    La forma obvia de simular una venta es un lote con cantidad negativa, y es
    la equivocada: `value_weights` sumaría un valor negativo, el peso del papel
    daría negativo y Markowitz —que asume posiciones largas— optimizaría sobre
    una cartera que no puede existir. La venta se descuenta de los lotes que ya
    están, del más viejo al más nuevo, igual que netea una venta real.

    Y vender más de lo que tenés deja la posición en cero, no en negativo: es
    una simulación, no un descubierto.
    """
    sim = require("api", "sim")

    cartera = [{"ticker": "GGAL.BA", "qty": 100, "buy_date": "2024-01-10", "buy_price": 1.0},
               {"ticker": "GGAL.BA", "qty": 50, "buy_date": "2025-06-01", "buy_price": 2.0},
               {"ticker": "METR.BA", "qty": 300, "buy_date": "2023-05-05", "buy_price": 3.0}]

    r = sim.aplicar(cartera, [("GGAL.BA", -120)])
    ggal = [p for p in r if p["ticker"] == "GGAL.BA"]
    assert len(ggal) == 1, "el lote más viejo se consume entero y se va de la lista"
    assert casi(ggal[0]["qty"], 30), f"tenía 150, vendió 120, quedan 30 — quedaron {ggal[0]['qty']}"
    assert ggal[0]["buy_date"] == "2025-06-01", "FIFO: el que sobrevive es el más nuevo"

    entera = sim.aplicar(cartera, [("METR.BA", -1000)])
    assert all(p["ticker"] != "METR.BA" for p in entera), \
        "vender más de lo que hay saca la posición; no la deja en negativo"
    assert all(float(p["qty"]) > 0 for p in entera), "ninguna cantidad negativa ni en cero"

    assert cartera[0]["qty"] == 100, "la cartera original no se toca: la simulación es una copia"


def test_una_compra_simulada_no_inventa_pnl():
    """El lote simulado entra a precio de hoy: costo = valor, P&L = 0.

    Si la compra entrara a cualquier otro precio, la simulación mostraría una
    ganancia o una pérdida que nunca pasó, y el P&L de la cartera —el número que
    el usuario mira primero— dejaría de ser el suyo. Lo que sí tiene que mover
    es el peso de todo lo demás: para eso se simula.
    """
    import pandas as pd

    sim = require("api", "sim")
    portfolio, sources = require("core.models", "portfolio"), require("core.data", "sources")

    fechas = pd.date_range("2026-01-01", periods=40, freq="D")
    original = sources.precios_base
    sources.precios_base = lambda t, **k: pd.Series(
        [10.0] * 39 + [12.5], index=fechas)
    try:
        con_sim = sim.aplicar(
            [{"ticker": "VIEJO", "qty": 10, "buy_price": 5.0, "buy_date": "2025-01-02",
              "currency": "USD", "commissions": 0}],
            [("NUEVO", 4)])
        r = portfolio.valuar(con_sim)
    finally:
        sources.precios_base = original

    fila = next(f for f in r["posiciones"] if f["ticker"] == "NUEVO")
    assert fila["sim"] is True, "la fila simulada va marcada: no es tenencia real"
    assert casi(fila["buy_price_usd"], 12.5), "entra al último precio, no a cualquiera"
    assert casi(fila["pnl_usd"], 0), f"la compra simulada no puede aportar P&L ({fila['pnl_usd']})"

    viejo = next(f for f in r["posiciones"] if f["ticker"] == "VIEJO")
    assert casi(viejo["pnl_usd"], 75), "el P&L de lo que ya tenías queda intacto"
    assert casi(r["valor_total"], 175), "pero el valor total sí incluye lo simulado"


def test_el_usuario_nuevo_estrena_con_la_cartera_modelo_y_si_la_borra_no_vuelve():
    """Quien entra por primera vez encuentra datos; quien la borró, no la ve más.

    Una app de carteras vacía no se puede recorrer: sin posiciones no hay riesgo,
    ni frontera, ni Monte Carlo, y el que entra no ve qué hace la herramienta
    hasta después de cargar diez lotes a mano.

    La otra mitad es la que importa: la condición de siembra es que el archivo de
    carteras NO exista. Borrar la modelo escribe ese archivo aunque quede vacío,
    así que no reaparece en el próximo ingreso. Sembrar "si no hay ninguna
    cartera" —que es la condición obvia— haría exactamente eso: devolverle al
    usuario, cada vez que entra, la cartera que ya decidió borrar.
    """
    store = require("core.io", "store")

    with datos_aparte():
        store.como("usuario-nuevo")
        mercado = require("core", "mercado")
        assert store.sembrar(), "un usuario sin nada tiene que estrenar con las modelo"
        # Una por plaza: con una sola cartera argentina, Europa y EE.UU. no se
        # pueden ni mirar.
        assert sorted(store.nombres()) == sorted(store.MODELOS), \
            f"tienen que sembrarse las tres, salieron {store.nombres()}"
        plazas = {mercado.de_posiciones(store.cargar(n)) for n in store.nombres()}
        assert plazas == {"AR", "EU", "US"}, f"una por plaza, salieron {plazas}"
        for n in store.nombres():
            assert len(store.cargar(n)) > 0, f"{n} sin posiciones no sirve de ejemplo"
        assert len(store.cargar_realizado("Modelo Argentina")) > 0, \
            "la argentina trae historia: cerradas y dividendos"

        assert not store.sembrar(), "no se siembra dos veces sobre el mismo usuario"

        for n in list(store.nombres()):
            store.borrar(n)
        assert not store.sembrar(), "borradas es borradas: no vuelven en el próximo ingreso"
        assert store.nombres() == []

        # Y no pisa lo de nadie: quien ya tiene carteras no recibe la modelo.
        store.como("usuario-con-cartera")
        store.guardar("La mía", [{"ticker": "AAPL", "qty": 1, "buy_price": 100,
                                  "buy_date": "2025-01-02"}])
        assert not store.sembrar()
        assert store.nombres() == ["La mía"]


def test_el_mep_no_se_queda_pegado_en_el_de_ayer():
    """La serie se pide sola, y "al día" es tener HOY con la rueda cerrada.

    Tres bugs, uno arriba del otro, todos con la misma cara: la cartera valuada
    con un dólar que no es el de hoy.

      1. Servida con gunicorn `main()` no se ejecuta NUNCA, así que el servidor
         quedó con cero ruedas de MEP y la pestaña del dólar vacía (2026-09-08).
      2. Alcanzaba con tener la rueda de AYER para darse por al día, así que un
         proceso largo se quedaba con el dólar de ayer hasta el día siguiente. El
         2026-09-09 la VM mostraba KARIN en US$22.021 y la misma cartera en local
         US$21.998: la diferencia era el MEP, 1524,30 contra 1530,40.
      3. El valor del día en curso se mueve, y el que se guarda a la mañana es
         intradía: ese mismo día la VM tenía el 08 en 1524,30 cuando el cierre
         terminó siendo 1533,70.

    Y no en cada lectura: `serie()` se llama muchas veces por request.
    """
    import time

    import pandas as pd

    mep = require("core.data", "mep")
    salidas = []
    serie_falsa = pd.Series([1000.0], index=[pd.Timestamp("2026-09-01")])

    o_arg, o_dolar = mep._desde_argentinadatos, mep._desde_dolarapi
    o_leer, o_guardar, o_ultima = mep.cache.leer_mep, mep.cache.guardar_mep, mep.cache.ultima_fecha_mep
    o_cerrada, o_hoy, o_mem = mep._rueda_cerrada, mep._hoy_ba, dict(mep._memoria)
    estado = {"ultima": None, "cerrada": True}

    mep._desde_argentinadatos = lambda: (salidas.append(1), serie_falsa)[1]
    mep._desde_dolarapi = lambda: pd.Series(dtype=float)
    mep.cache.leer_mep = lambda *a, **k: serie_falsa
    mep.cache.guardar_mep = lambda s, f: 0
    mep.cache.ultima_fecha_mep = lambda: estado["ultima"]
    mep._rueda_cerrada = lambda: estado["cerrada"]
    mep._hoy_ba = lambda: "2026-09-09"
    try:
        # 1 · Sin nada guardado: sale a buscar, y una sola vez aunque se lea tres.
        mep._memoria.update({"serie": None, "intento": 0.0})
        mep.serie(); mep.serie(); mep.serie()
        assert len(salidas) == 1, f"una salida a la red, no {len(salidas)}"

        # 2 · Tiene la de ayer y la rueda ya cerró: eso NO es estar al día.
        estado["ultima"] = "2026-09-08"
        mep._memoria["intento"] = 0.0
        mep.serie()
        assert len(salidas) == 2, "con la rueda de ayer hay que salir a buscar la de hoy"

        # 3 · Tiene la de hoy pero el mercado sigue abierto: el valor se mueve.
        estado.update({"ultima": "2026-09-09", "cerrada": False})
        mep._memoria["intento"] = 0.0
        mep.serie()
        assert len(salidas) == 3, "hasta que cierra la rueda, el valor de hoy se refresca"

        # 4 · Tiene la de hoy y la rueda cerró: recién ahí se queda quieto.
        estado["cerrada"] = True
        mep._memoria["intento"] = 0.0
        mep.serie()
        assert len(salidas) == 3, "con la rueda cerrada y el día completo, no se pregunta más"

        # 5 · El candado: dos lecturas seguidas no vuelven a preguntar.
        estado["ultima"] = "2026-09-08"
        mep._memoria["intento"] = time.time()
        mep.serie(); mep.serie()
        assert len(salidas) == 3, "el candado de una hora evita preguntar en cada lectura"
    finally:
        mep._desde_argentinadatos, mep._desde_dolarapi = o_arg, o_dolar
        mep.cache.leer_mep, mep.cache.guardar_mep, mep.cache.ultima_fecha_mep = o_leer, o_guardar, o_ultima
        mep._rueda_cerrada, mep._hoy_ba = o_cerrada, o_hoy
        mep._memoria.clear(); mep._memoria.update(o_mem)


def test_cache_no_alcanza_si_le_falta_la_ultima_rueda():
    """Una caché que corta en la rueda anterior NO alcanza, aunque sea de ayer.

    Bug original (2026-09-09): la app mostraba KOD.BA a 18,50 y Yahoo a 18,46.
    Se juntaban dos cosas. `end` es exclusivo en Yahoo, así que la corrida del
    día D bajaba hasta D-1; y `_suficiente` toleraba 3 días de atraso, así que
    al día siguiente perdonaba el agujero en vez de ir a buscarlo. La caché
    quedaba una rueda atrás PARA SIEMPRE, en todos los activos de la cartera.

    Fechas fijas a propósito: 2026-09-04 viernes, 09-05 sábado, 09-06 domingo,
    09-07 lunes, 09-08 martes. Nada que dependa de hoy.
    """
    import datetime as dt

    import pandas as pd

    ultima_rueda, suficiente = require("core.data.sources",
                                      "_ultima_rueda", "_suficiente")

    assert ultima_rueda("2026-09-05") == dt.date(2026, 9, 4), "el sábado no es rueda"
    assert ultima_rueda("2026-09-06") == dt.date(2026, 9, 4), "el domingo tampoco"
    assert ultima_rueda("2026-09-08") == dt.date(2026, 9, 8), "martes cerrado es rueda"

    def serie(hasta):
        idx = pd.to_datetime(["2026-09-03", "2026-09-04", "2026-09-07", "2026-09-08"])
        idx = idx[idx <= pd.Timestamp(hasta)]
        return pd.DataFrame({"Close": [1.0] * len(idx)}, index=idx)

    assert suficiente(serie("2026-09-08"), "2026-09-08") is True, \
        "llega a la última rueda: no hay que salir a buscar"
    assert suficiente(serie("2026-09-07"), "2026-09-08") is False, \
        "le falta el 08: esto es exactamente el bug de los 18,50 contra 18,46"
    assert suficiente(pd.DataFrame(), "2026-09-08") is False, "vacía nunca alcanza"

    # El server de producción corre en UTC, así que `date.today()` allá ya es
    # mañana durante la noche argentina. Una fecha futura tiene que recortarse a
    # la última rueda real: si no, la caché nunca alcanza y se sale a buscar en
    # cada request un día que todavía no existe.
    from core.data.sources import TZ_BYMA
    hoy_ba = dt.datetime.now(TZ_BYMA).date()
    assert ultima_rueda("2099-01-01") <= hoy_ba, "una fecha futura se recorta a hoy"
    assert ultima_rueda("2099-01-01").weekday() < 5, "y cae en día hábil"


def test_la_cuotaparte_del_fci_se_convierte_con_el_mep_de_t_menos_1():
    """La cuotaparte que publica Cocos es de T-1 y se convierte con el MEP de T-1.

    Bug original: `_fci_usd` la sellaba con `date.today()`, así que tomaba pesos
    del cierre anterior y los dividía por el MEP de hoy. Un día de salto del MEP
    valuaba el fondo mal, y el punto quedaba cacheado un día adelantado. Es el
    mismo error de corrimiento que tenía la caché de cierres.

    Y el lunes T-1 tiene que caer en el viernes, no en el domingo: sin MEP de
    domingo la conversión volvía None y el fondo desaparecía del total.
    """
    import datetime as dt

    fci_usd, ultima_rueda = require("core.data.sources", "_fci_usd", "_ultima_rueda")
    sources = __import__("core.data.sources", fromlist=["_"])
    from core.broker import cocos
    from core.data import cache, mep

    visto = {}
    orig = (cocos.precio_fci, cache.guardar_precios, mep.a_usd)
    cocos.precio_fci = lambda t: 1234.5                      # cuotaparte en pesos
    cache.guardar_precios = lambda t, df: visto.update(cacheado=df.index[-1].date())
    mep.a_usd = lambda ars, fecha, *a, **k: visto.update(ars=ars, fecha=fecha) or 2.0
    try:
        s = fci_usd("COCOSPPA")
    finally:
        cocos.precio_fci, cache.guardar_precios, mep.a_usd = orig

    esperado = ultima_rueda((dt.date.today() - dt.timedelta(days=1)).isoformat())
    assert visto["ars"] == 1234.5, "tiene que convertir la cuotaparte que dio el broker"
    assert visto["fecha"] == esperado, f"convirtió con el MEP de {visto['fecha']}, no de T-1"
    assert visto["fecha"] < dt.date.today(), "T-1 nunca puede ser hoy"
    assert visto["fecha"].weekday() < 5, "T-1 tiene que ser día hábil"
    assert visto["cacheado"] == esperado, "el punto se cachea con la fecha de T-1"
    assert s.index[-1].date() == esperado, "la serie sale fechada en T-1"


def test_mercado_euro_mide_en_euros_y_no_solo_lo_muestra():
    """Mirar la cartera desde Europa no es cambiar el signo $ por el €.

    Si la conversión se hiciera al formatear los números, la volatilidad, el
    Sharpe y el beta seguirían siendo los del inversor en dólares: el europeo
    carga además el movimiento del EURUSD, y eso sólo entra si la serie se
    convierte ANTES de calcular los retornos. Este test lo fija: con un tipo de
    cambio que se mueve y un precio que no, en dólares el retorno es cero y en
    euros no.
    """
    import pandas as pd
    mercado = require("core", "mercado")
    sources = require("core.data", "sources")

    idx = pd.date_range("2026-01-01", periods=4, freq="D")
    quieto = pd.DataFrame({"Close": [100.0] * 4}, index=idx)
    fx = pd.Series([1.00, 1.10, 1.05, 1.20], index=idx)      # USD por euro

    plaza_previa = mercado.actual()
    original_precios, original_fx = sources.precios, mercado._fx
    sources.precios = lambda t, *a, **k: quieto
    mercado._fx = lambda: fx
    try:
        mercado.poner("US")
        en_usd = sources.precios_base("AAPL")
        mercado.poner("EU")
        en_eur = sources.precios_base("AAPL")
    finally:
        sources.precios, mercado._fx = original_precios, original_fx
        mercado.poner(plaza_previa)

    assert casi(en_usd.pct_change().dropna().std(), 0.0), \
        "en dólares el precio no se movió: el retorno tiene que ser cero"
    assert casi(en_eur.iloc[1], 100 / 1.10, 1e-9), "cada fecha con SU tipo de cambio"
    assert en_eur.pct_change().dropna().std() > 0, \
        "en euros el EURUSD mueve la serie: la volatilidad no puede ser cero"


def test_mercado_fija_tasa_libre_e_indice_de_apertura():
    """La tasa libre de riesgo la manda la moneda de medición, no el índice.

    Medir en euros y descontar con la letra del Tesoro americano mezcla dos
    monedas dentro del mismo Sharpe. Y el índice con el que abre cada plaza es
    el suyo —Merval, STOXX, S&P—, aunque después gane el de mayor R².
    """
    mercado = require("core", "mercado")
    rates = require("core.models", "rates")

    previa = mercado.actual()
    try:
        for plaza, indice, region in (("AR", "MERVAL", "US"),
                                      ("EU", "STOXX600", "EU"),
                                      ("US", "SP500", "US")):
            mercado.poner(plaza)
            assert mercado.cfg()["benchmark"] == indice, f"{plaza} abre con {indice}"
            assert mercado.cfg()["rf"] == region, f"{plaza} descuenta con la tasa {region}"
        # El argumento viejo ya no decide: pedir el S&P midiendo en euros sigue
        # dando la tasa europea.
        mercado.poner("EU")
        _, etiqueta = rates.risk_free_para("SP500")
        assert "Bund" in etiqueta, f"midiendo en euros la tasa es el Bund, salió: {etiqueta}"
    finally:
        mercado.poner(previa)


def test_ticker_europeo_no_cotiza_en_dolares():
    """ASML.AS cotiza en euros. Darlo por dólares infla la posición un 16 %.

    Es el mismo bug que KOD.BA pero al revés y en otra plaza: la app dio por
    dólares todo lo que no terminara en .BA, y con el mercado europeo eso pasó
    de ser cierto a ser un error de valuación silencioso. La moneda de un ticker
    con sufijo de bolsa la declara la fuente; los que no tienen punto son de
    EE.UU. y NO se preguntan —salir a la red por un AAPL o por un FCI de Cocos
    cuesta segundos y no aporta nada.
    """
    sources = require("core.data", "sources")
    symbols = require("core.data", "symbols")

    preguntados = []
    original = sources.info

    def espia(ticker, *a, **k):
        preguntados.append(ticker)
        return {"currency": "EUR"} if ticker.endswith((".AS", ".MC")) else {}

    sources.info = espia
    try:
        assert symbols.ticker_currency("ASML.AS") == "EUR", "Ámsterdam cotiza en euros"
        assert symbols.ticker_currency("SAN.MC") == "EUR", "Madrid cotiza en euros"
        assert symbols.ticker_currency("AAPL") == "USD"
        assert symbols.ticker_currency("COCOSPPA") == "USD", "un FCI de Cocos, sin red"
        assert symbols.ticker_currency("METR.BA") == "ARS"
        assert symbols.ticker_currency("KOD.BA") == "USD"
    finally:
        sources.info = original

    assert preguntados == ["ASML.AS", "SAN.MC"], \
        f"sólo se pregunta por los que tienen sufijo de bolsa, se preguntó: {preguntados}"


def test_precio_en_euros_entra_al_nucleo_en_dolares():
    """Un papel europeo se convierte a dólares para calcular, y no dos veces.

    El núcleo mide en dólares: un precio en euros entra multiplicado por el
    EURUSD de cada fecha. Y mirando la cartera DESDE Europa el mismo papel tiene
    que salir con su número de pantalla, no con un ida y vuelta que le agregue
    ruido: si ya cotiza en la moneda de medición, no se toca.
    """
    import pandas as pd
    mercado = require("core", "mercado")
    sources = require("core.data", "sources")

    idx = pd.date_range("2026-01-01", periods=3, freq="D")
    precio = pd.DataFrame({"Close": [100.0, 100.0, 100.0]}, index=idx)
    fx = pd.Series([1.10, 1.10, 1.10], index=idx)          # USD por euro

    plaza_previa = mercado.actual()
    o_precios, o_info, o_par = sources.precios, sources.info, mercado._par
    sources.precios = lambda t, *a, **k: precio
    sources.info = lambda t, *a, **k: {"currency": "EUR"}
    mercado._par = lambda mon: fx if mon == "EUR" else pd.Series(dtype=float)
    try:
        mercado.poner("US")
        en_usd = sources.precios_base("ASML.AS")
        mercado.poner("EU")
        en_eur = sources.precios_base("ASML.AS")
    finally:
        sources.precios, sources.info, mercado._par = o_precios, o_info, o_par
        mercado.poner(plaza_previa)

    assert casi(en_usd.iloc[-1], 110.0, 1e-9), "100 € a 1,10 son 110 dólares"
    assert casi(en_eur.iloc[-1], 100.0, 1e-9), \
        "midiendo en euros el papel europeo ya está en su moneda: no se convierte"


def test_la_plaza_de_una_cartera_sale_de_donde_cotiza():
    """Una cartera de CEDEARs es argentina aunque coticen en dólares.

    La plaza es dónde se opera, no en qué moneda: KARIN tiene GLDD.BA y KOD.BA
    —dólares— junto a METR.BA, y toda ella se mira desde Argentina, con MEP,
    Conectores y Cocos. Contar monedas en vez de plazas la mandaba a Estados
    Unidos y le escondía las tres pestañas que sí usa.
    """
    mercado = require("core", "mercado")

    argentina = [{"ticker": "GLDD.BA"}, {"ticker": "KOD.BA"}, {"ticker": "METR.BA"}]
    europea = [{"ticker": "ASML.AS", "currency": "EUR"},
               {"ticker": "SAP.DE", "currency": "EUR"},
               {"ticker": "AAPL"}]
    yanqui = [{"ticker": "AAPL"}, {"ticker": "MSFT"}]
    bonos = [{"ticker": "AL30", "source": "cocos"}, {"ticker": "PLC4O", "source": "cocos"}]

    assert mercado.de_posiciones(argentina) == "AR", "los CEDEARs en dólares son BYMA"
    assert mercado.de_posiciones(europea) == "EU", "manda la mayoría, no el primero"
    assert mercado.de_posiciones(yanqui) == "US"
    assert mercado.de_posiciones(bonos) == "AR", "los bonos de Cocos no se van del país"
    assert mercado.de_posiciones([]) == "AR", "una cartera vacía abre donde nació la app"


def test_la_plaza_elegida_a_mano_le_gana_a_la_deducida():
    """Un europeo con acciones de EE.UU. las mide igual en euros.

    Es lo único que las posiciones no pueden contar: una cartera de AAPL y MSFT
    se deduce como estadounidense y para su dueño en Madrid es europea. Lo
    elegido manda, se guarda aparte de las carteras —el formato del CSV no se
    toca— y se borra con la cartera; volver a "automática" no deja rastro.
    """
    mercado = require("core", "mercado")
    store = require("core.io", "store")
    yanqui = [{"ticker": "AAPL", "qty": 1, "buy_price": 100, "buy_date": "2025-01-02"},
              {"ticker": "MSFT", "qty": 1, "buy_price": 100, "buy_date": "2025-01-02"}]

    with datos_aparte():
        store.como("test-plazas")
        store.guardar("mia", yanqui)
        assert mercado.de_posiciones(store.cargar("mia")) == "US"
        assert store.plaza("mia") is None, "sin elegir nada, no hay nada guardado"

        store.fijar_plaza("mia", "EU")
        assert store.plaza("mia") == "EU", "lo elegido a mano manda"

        store.fijar_plaza("mia", None)
        assert store.plaza("mia") is None, "volver a automática no deja rastro"

        store.fijar_plaza("mia", "EU")
        store.duplicar("mia", "copia")
        assert store.plaza("copia") == "EU", "la copia se mira desde donde la original"

        store.borrar("mia")
        assert store.plaza("mia") is None, "la plaza se va con la cartera"
        assert store.plaza("copia") == "EU", "y sólo la de esa cartera"


def test_los_once_modelos_terminan_y_con_la_plaza_puesta():
    """Los modelos corren en un pool, y ahí se perdieron las dos cosas a la vez.

    Bug real del 2026-09-09: para que la plaza elegida cruzara al pool se copiaba
    el contexto del request… **una sola vez para los once modelos**. Un `Context`
    no se puede entrar dos veces a la vez: el primero corría y los otros diez
    morían con `RuntimeError: cannot enter context`. Como esa excepción se la
    queda el Future y nadie la miraba, quedaban en "corriendo" para siempre: la
    pantalla decía "1 de 11 modelos listos" y ahí se quedaba, sin un solo error.

    Las dos mitades tienen que valer: que TODOS terminen, y que todos vean la
    plaza del request. Los modelos de mentira duermen para forzar el solape, que
    es la única condición en la que el bug aparece.
    """
    import time
    jobs = require("api", "jobs")
    mercado = require("core", "mercado")

    def lento(posiciones, cartera):
        time.sleep(0.15)
        return {"plaza": mercado.actual(), "cartera": cartera}

    previos = dict(jobs.MODELOS)
    plaza_previa = mercado.actual()
    estado = None
    try:
        jobs.MODELOS.clear()
        jobs.MODELOS.update({f"m{i}": (f"Modelo {i}", lento) for i in range(8)})
        mercado.poner("EU")
        run = jobs.lanzar("test", [{"ticker": "X"}])
        mercado.poner(plaza_previa)      # el request terminó; el pool sigue solo
        for _ in range(150):
            estado = jobs.estado(run)
            if estado["estado"] == "terminado":
                break
            time.sleep(0.1)
    finally:
        jobs.MODELOS.clear()
        jobs.MODELOS.update(previos)
        mercado.poner(plaza_previa)

    colgados = {m: v["estado"] for m, v in estado["modelos"].items() if v["estado"] != "listo"}
    assert not colgados, f"modelos que no terminaron: {colgados}"
    plazas = {r["plaza"] for r in estado["resultados"].values()}
    assert plazas == {"EU"}, f"los modelos perdieron la plaza del request: {plazas}"
    carteras = {r["cartera"] for r in estado["resultados"].values()}
    assert carteras == {"test"}, f"y cada modelo sabe de qué cartera es: {carteras}"


def test_el_precio_de_objetivos_es_el_mismo_que_valua_la_cartera():
    """Dos paneles de la misma pantalla no pueden mostrar dos precios distintos.

    El consenso de analistas se cachea 24 h y el `.info` de yfinance trae el
    precio adentro: quedaba congelado con el valor del momento en que se pidió.
    El 2026-09-09 la misma cartera mostraba GLDD.BA a 8,55 en una máquina y 8,38
    en otra, y la tabla de tenencias decía 8,37 en las dos. Peor: METR.BA salía
    en PESOS (2.359) en una columna que muestra todo lo demás en dólares.

    El objetivo sí se cachea —se mueve de semana en semana—; el precio de hoy no.
    """
    import pandas as pd

    targets = require("core.models", "targets")
    sources = require("core.data", "sources")

    o_precios, o_obj = sources.precios_base, targets._objetivo_yfinance
    # El consenso viejo: precio de ayer y objetivo medido contra ese precio.
    sources.precios_base = lambda t, **k: pd.Series(
        [8.37], index=[pd.Timestamp("2026-09-09")])
    targets._objetivo_yfinance = lambda s: {
        "actual": 8.55, "objetivo_medio": 8.85, "upside_pct": 3.5, "fuente": "yfinance"}
    try:
        r = targets.objetivo("GLDD.BA")
    finally:
        sources.precios_base, targets._objetivo_yfinance = o_precios, o_obj

    assert casi(r["actual"], 8.37), \
        f"el precio tiene que ser el de la serie de cierres, salió {r['actual']}"
    assert casi(r["objetivo_medio"], 8.66, 0.01), \
        f"el objetivo se lleva a la escala del precio de hoy, salió {r['objetivo_medio']}"
    assert casi(r["upside_pct"], 3.5, 0.2), \
        "el upside es invariante al cambio de escala"




def test_variacion_del_dia_solo_compara_lo_comparable():
    """La variación del día se mide contra el cierre anterior, y sólo sobre los
    lotes que tienen los dos precios.

    Un lote sin cierre previo —un FCI, un papel que empezó a cotizar ayer— no
    puede entrar al total de ayer: si entrara, la 'variación' incluiría su
    tenencia entera y diría que la cartera se movió miles de dólares.
    """
    from core.models import portfolio

    posiciones = [
        {"ticker": "AAA", "qty": 10, "buy_price": 5, "currency": "USD", "buy_date": "2024-01-02"},
        {"ticker": "BBB", "qty": 4, "buy_price": 20, "currency": "USD", "buy_date": "2024-01-02"},
    ]
    # AAA subió de 10 a 11; BBB no tiene cierre anterior y queda afuera.
    d = portfolio.valuar(posiciones,
                         precios={"AAA": 11.0, "BBB": 50.0},
                         previos={"AAA": 10.0})

    assert d["pnl_dia"] == 10.0            # 10 unidades × 1 dólar, sólo AAA
    assert d["pnl_dia_pct"] == 10.0        # 110 contra 100, no contra 310


def test_variacion_del_dia_sobrevive_al_cierre_del_mercado():
    """Con el mercado cerrado el KPI sigue mostrando la última rueda operada.

    Bug: yfinance con el mercado cerrado devuelve el último precio negociado,
    que es el último cierre de la serie. Se lo tomaba por el precio "de hoy" y
    se lo restaba contra ese mismo cierre: un finde, un feriado o la madrugada
    del día siguiente mostraban 0,00 en vez del movimiento del viernes.
    """
    import pandas as pd

    portfolio = require("core.models", "portfolio")
    sources = require("core.data", "sources")

    cierres = pd.Series([10.0, 11.0],
                        index=[pd.Timestamp("2026-09-10"), pd.Timestamp("2026-09-11")])
    o_base, o_spot, o_nueva = (sources.precios_base, sources.spot_base,
                               sources.spot_rueda_nueva)
    sources.precios_base = lambda t, **k: cierres
    sources.spot_base = lambda t, s=None: 11.0      # el viernes, otra vez
    sources.spot_rueda_nueva = lambda t, s=None, h=None: False
    try:
        previos, fechas = {}, {}
        pr = portfolio.precios_actuales(
            [{"ticker": "AAA", "qty": 1, "buy_price": 5, "currency": "USD",
              "buy_date": "2024-01-02"}],
            previos=previos, fechas=fechas, vivo=True)
    finally:
        (sources.precios_base, sources.spot_base,
         sources.spot_rueda_nueva) = o_base, o_spot, o_nueva

    assert casi(pr["AAA"], 11.0), f"el precio es el último cierre, salió {pr['AAA']}"
    assert casi(previos["AAA"], 10.0), \
        f"el previo es el cierre ANTERIOR al último, no el mismo: salió {previos['AAA']}"
    assert fechas["_ultima"] == "2026-09-11", \
        f"la rueda mostrada es la última operada, no hoy: salió {fechas['_ultima']}"


def main():
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    ok = fallas = pendientes = 0
    ancho = max(len(n) for n, _ in tests)

    print(f"\n  \033[1mVerdades de Portfolio Analyzer\033[0m — {len(tests)} casos\n")
    for nombre, fn in tests:
        try:
            fn()
        except Pendiente as e:
            print(f"  \033[90m·  {nombre.ljust(ancho)}  pendiente — {e}\033[0m")
            pendientes += 1
        except AssertionError as e:
            print(f"  \033[31m✗  {nombre.ljust(ancho)}  {e}\033[0m")
            fallas += 1
        except Exception as e:
            print(f"  \033[31m✗  {nombre.ljust(ancho)}  {type(e).__name__}: {e}\033[0m")
            fallas += 1
        else:
            print(f"  \033[32m✓\033[0m  {nombre.ljust(ancho)}")
            ok += 1

    print(f"\n  {ok} en verde · {fallas} en rojo · {pendientes} sin implementar\n")
    if fallas:
        print("  Hay una verdad rota. Es un bug que ya pagamos una vez.\n")
    elif pendientes and not ok:
        print("  Todavía no hay núcleo. Fase 0 terminada: esto es la lista de trabajo.\n")
    elif not pendientes:
        print("  Núcleo completo y todas las verdades en pie.\n")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
