"""
reporte.py — El PDF de la cartera.

Los gráficos se dibujan **en el servidor con matplotlib**, a partir de los
resultados de los modelos. Las apps anteriores capturaban las imágenes desde el
navegador y las mandaban en base64: eso ataba el reporte a que hubiera una
pantalla abierta, hacía viajar megabytes por request y producía un PDF con la
resolución del monitor del usuario. Acá el PDF se puede generar desde la API,
desde un script o desde una tarea programada, sin navegador.

Sale en blanco y negro sobre fondo claro a propósito: es para imprimir o
adjuntar, no una captura de la interfaz.
"""

import io
from datetime import date

import matplotlib
matplotlib.use("Agg")                       # sin ventana: corre en un servidor
import matplotlib.pyplot as plt             # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402

TINTA = "#16202A"
SUAVE = "#6B7A86"
LINEA = "#D2DAE0"
ACENTO = "#12695A"
POSITIVO = "#1F7A4D"
NEGATIVO = "#B23B24"
SERIES = ["#12695A", "#C07A2A", "#3D6CA8", "#9A4257", "#6B5B95", "#2E8B8B"]

A4 = (8.27, 11.69)


def _estilo(ax):
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        ax.spines[lado].set_color(LINEA)
    ax.tick_params(colors=SUAVE, labelsize=8)
    ax.grid(True, color=LINEA, linewidth=0.6, alpha=0.7)
    ax.set_axisbelow(True)


def _encabezado(fig, titulo, subtitulo=""):
    fig.text(0.06, 0.965, titulo, fontsize=15, weight="bold", color=TINTA)
    if subtitulo:
        fig.text(0.06, 0.945, subtitulo, fontsize=9, color=SUAVE)
    fig.text(0.06, 0.028, "Portfolio Analyzer · Leandro R. Bergero · "
                          "Msc Finance and Banking BSM-UPF", fontsize=7, color=SUAVE)
    fig.text(0.94, 0.028, date.today().isoformat(), fontsize=7, color=SUAVE, ha="right")


def _tabla(ax, encabezados, filas, anchos=None):
    ax.axis("off")
    if not filas:
        ax.text(0.5, 0.5, "Sin datos", ha="center", color=SUAVE, fontsize=9)
        return
    t = ax.table(cellText=filas, colLabels=encabezados, loc="upper center",
                 cellLoc="right", colWidths=anchos)
    t.auto_set_font_size(False)
    t.set_fontsize(7.5)
    t.scale(1, 1.45)
    for (fila, _col), celda in t.get_celld().items():
        celda.set_edgecolor(LINEA)
        celda.set_linewidth(0.5)
        if fila == 0:
            celda.set_text_props(weight="bold", color=SUAVE)
            celda.set_facecolor("#EDF1F4")
        else:
            celda.set_text_props(color=TINTA)


def _pagina_resumen(pdf, nombre, posicion, riesgo, concentracion):
    fig = plt.figure(figsize=A4)
    fig.patch.set_facecolor("white")
    _encabezado(fig, f"Cartera {nombre}",
                "Todos los valores en dólares, convertidos con el MEP de la fecha de cada operación")

    kpis = [
        ("Valor total", f"${posicion['valor_total']:,.2f}", TINTA),
        ("Resultado", f"${posicion['pnl']:,.2f}",
         POSITIVO if posicion["pnl"] >= 0 else NEGATIVO),
        ("Rendimiento", f"{posicion['pnl_pct']:.2f} %",
         POSITIVO if posicion["pnl_pct"] >= 0 else NEGATIVO),
    ]
    if riesgo and "error" not in riesgo:
        kpis += [("Sharpe", f"{riesgo['sharpe']:.3f}", TINTA),
                 ("Volatilidad", f"{riesgo['volatilidad_anual_pct']:.2f} %", TINTA),
                 ("Peor caída", f"{riesgo['max_drawdown_pct']:.2f} %", NEGATIVO)]

    for i, (etiqueta, valor, color) in enumerate(kpis):
        x = 0.06 + (i % 3) * 0.31
        y = 0.87 - (i // 3) * 0.075
        fig.text(x, y, etiqueta.upper(), fontsize=7, color=SUAVE)
        fig.text(x, y - 0.028, valor, fontsize=15, color=color, weight="bold")

    if concentracion:
        fig.text(0.06, 0.71,
                 f"Diversificación: {concentracion['n_posiciones']} activos, "
                 f"pero {concentracion['n_efectivo']} efectivos "
                 f"(el mayor pesa {concentracion['peso_maximo']} %).",
                 fontsize=8.5, color=SUAVE)

    filas = [[p["ticker"], p["buy_date"], f"{p['qty']:,.0f}",
              f"${p['buy_price_usd']:,.4f}" if p["buy_price_usd"] else "—",
              f"${p['precio_usd']:,.4f}" if p["precio_usd"] else "—",
              f"${p['valor_usd']:,.2f}" if p["valor_usd"] else "—",
              f"${p['pnl_usd']:,.2f}" if p.get("pnl_usd") is not None else "—",
              f"{p['pnl_pct']:.1f} %" if p.get("pnl_pct") is not None else "—"]
             for p in posicion["posiciones"]]
    ax = fig.add_axes([0.05, 0.10, 0.90, 0.58])
    _tabla(ax, ["Ticker", "Compra", "Cantidad", "P. compra", "P. hoy",
                "Valor", "Resultado", "%"], filas,
           [0.12, 0.11, 0.11, 0.12, 0.12, 0.14, 0.14, 0.09])
    pdf.savefig(fig); plt.close(fig)


def _pagina_riesgo(pdf, nombre, riesgo):
    if not riesgo or "error" in riesgo:
        return
    fig = plt.figure(figsize=A4)
    fig.patch.set_facecolor("white")
    _encabezado(fig, "Riesgo", f"Cartera {nombre} · {riesgo['n_ruedas']} ruedas · {riesgo['rf_label']}")

    contrib = riesgo.get("contribucion_riesgo", [])[:12]
    if contrib:
        ax = fig.add_axes([0.16, 0.58, 0.78, 0.30])
        y = range(len(contrib))
        ax.barh([i + 0.2 for i in y], [c["riesgo_pct"] for c in contrib],
                height=0.38, color=NEGATIVO, label="aporte al riesgo")
        ax.barh([i - 0.2 for i in y], [c["peso_pct"] for c in contrib],
                height=0.38, color=SERIES[2], label="peso en la cartera")
        ax.set_yticks(list(y)); ax.set_yticklabels([c["ticker"] for c in contrib], fontsize=8)
        ax.invert_yaxis(); ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0f} %")
        ax.legend(fontsize=7.5, frameon=False, loc="lower right")
        _estilo(ax)
        fig.text(0.06, 0.905, "Quién trae el riesgo", fontsize=11, weight="bold", color=TINTA)
        fig.text(0.06, 0.515,
                 "Las contribuciones suman exactamente la volatilidad de la cartera "
                 "(identidad de Euler).\nUn activo cuya barra roja supera a la azul aporta "
                 "más riesgo del que su peso sugiere.", fontsize=7.5, color=SUAVE,
                 verticalalignment="top")

    filas = [
        ["Sharpe", f"{riesgo['sharpe']:.3f}", "Retorno por unidad de riesgo. Arriba de 1 es bueno."],
        ["Sortino", f"{riesgo['sortino']:.3f}", "Como el Sharpe, castigando solo las caídas."],
        ["Calmar", f"{riesgo['calmar']:.3f}", "Retorno anual sobre la peor caída."],
        ["Volatilidad anual", f"{riesgo['volatilidad_anual_pct']:.2f} %", "Cuánto oscila la cartera en un año."],
        ["Pérdida día malo", f"${riesgo['var95_usd']:,.2f}", "1 de cada 20 ruedas es al menos así."],
        ["Pérdida día muy malo", f"${riesgo['cvar95_usd']:,.2f}", "Promedio de ese 5 % de días peores."],
        ["Con colas gordas", f"${riesgo['var95_cornish_fisher_usd']:,.2f}", "Cornish-Fisher: corrige por asimetría y curtosis."],
        ["Peor caída", f"{riesgo['max_drawdown_pct']:.2f} %", "Lo que hubo que aguantar sin vender."],
        ["Curtosis en exceso", f"{riesgo['curtosis_exceso']:.2f}", "Arriba de 3: los días extremos son frecuentes."],
    ]
    ax2 = fig.add_axes([0.05, 0.10, 0.90, 0.38])
    _tabla(ax2, ["Métrica", "Valor", "Cómo se lee"], filas, [0.22, 0.16, 0.62])
    for (fila, col), celda in ax2.tables[0].get_celld().items():
        if col == 2 and fila > 0:
            celda.set_text_props(ha="left", color=SUAVE, fontsize=7)
    pdf.savefig(fig); plt.close(fig)


def _pagina_composicion(pdf, nombre, comp):
    if not comp or "error" in comp:
        return
    fig = plt.figure(figsize=A4)
    fig.patch.set_facecolor("white")
    _encabezado(fig, "Composición", f"Cartera {nombre}")

    for i, (clave, titulo) in enumerate([("por_tipo", "Por tipo de activo"),
                                          ("por_sector", "Por sector")]):
        items = (comp.get(clave) or [])[:8]
        if not items:
            continue
        ax = fig.add_axes([0.08, 0.60 - i * 0.30, 0.36, 0.26])
        ax.pie([x["pct"] for x in items], colors=SERIES, startangle=90,
               wedgeprops={"width": 0.45, "edgecolor": "white", "linewidth": 1.5})
        ax.set_title(titulo, fontsize=9.5, color=TINTA, weight="bold", pad=6)
        leyenda = fig.add_axes([0.47, 0.60 - i * 0.30, 0.45, 0.26])
        leyenda.axis("off")
        for j, x in enumerate(items):
            leyenda.text(0, 0.92 - j * 0.115, "■", color=SERIES[j % len(SERIES)], fontsize=9)
            leyenda.text(0.06, 0.92 - j * 0.115,
                         f"{x['etiqueta']} — {x['pct']:.1f} %", fontsize=8, color=TINTA)

    fig.text(0.06, 0.20,
             "Un ETF no tiene sector GICS: es una canasta, no una empresa. En esos casos se\n"
             "muestra la categoría del fondo, que es el dato equivalente.",
             fontsize=7.5, color=SUAVE)
    pdf.savefig(fig); plt.close(fig)


def generar(nombre_cartera: str, posiciones: list) -> bytes:
    """Devuelve el PDF completo en memoria."""
    from core.models import composicion, portfolio, risk

    pos = portfolio.valuar(posiciones)
    if "error" in pos:
        raise ValueError(pos["error"])

    precios = {p["ticker"]: p["precio_usd"] for p in pos["posiciones"] if p["precio_usd"]}
    tickers = sorted(precios)
    conc = (portfolio.concentracion(portfolio.value_weights(posiciones, precios, tickers))
            if tickers else None)

    riesgo = risk.analizar(posiciones)
    comp = composicion.analizar(posiciones, precios)

    buffer = io.BytesIO()
    with PdfPages(buffer) as pdf:
        _pagina_resumen(pdf, nombre_cartera, pos, riesgo, conc)
        _pagina_riesgo(pdf, nombre_cartera, riesgo)
        _pagina_composicion(pdf, nombre_cartera, comp)
        info = pdf.infodict()
        info["Title"] = f"Portfolio Analyzer — {nombre_cartera}"
        info["Author"] = "Leandro R. Bergero"
        info["Subject"] = "Análisis de cartera en dólares"
    return buffer.getvalue()
