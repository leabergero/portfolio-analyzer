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


# ══════════════════════════════════════════════════════════════════════════

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
