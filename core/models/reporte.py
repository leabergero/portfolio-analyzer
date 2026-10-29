"""
reporte.py — El PDF de la cartera.

Los gráficos se dibujan **en el servidor con matplotlib**, a partir de los
resultados de los modelos. Las apps anteriores capturaban las imágenes desde el
navegador y las mandaban en base64: eso ataba el reporte a que hubiera una
pantalla abierta, hacía viajar megabytes por request y producía un PDF con la
resolución del monitor del usuario. Acá el PDF se puede generar desde la API,
desde un script o desde una tarea programada, sin navegador.

Sale sobre fondo claro a propósito: es para imprimir o adjuntar, no una
captura de la interfaz. Y se escribe para alguien que no sabe finanzas.
"""

import io
from datetime import date
from pathlib import Path

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


# ── Para leer sin saber finanzas ─────────────────────────────────────────────
# Cada página arranca con una pregunta y la contesta en una frase; las cifras
# van en castellano llano y lo técnico queda en letra chica, al pie.

AMBAR = "#C9922E"
FONDO = "#F4F7F8"
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def _num(v, dec=0):
    return f"{abs(v):,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _usd(v, dec=0, signo=False):
    # El `$` escapado: dos en el mismo texto, matplotlib lo lee como fórmula.
    pre = "−" if v < 0 else ("+" if signo and v > 0 else "")
    return f"{pre}US\\$ {_num(v, dec)}"


def _pct(v, dec=1, signo=False):
    pre = "−" if v < 0 else ("+" if signo and v > 0 else "")
    return f"{pre}{_num(v, dec)} %"


def _eje_pct(v, _=None):
    return f"{_num(v, 0 if float(v).is_integer() else 1)} %"


def _tono(v):
    return POSITIVO if v > 0 else NEGATIVO if v < 0 else TINTA


def _mes(fecha):
    return f"{MESES[int(fecha[5:7]) - 1]} de {fecha[:4]}"


def _pregunta(fig, pregunta, frase):
    fig.text(0.06, 0.905, pregunta, fontsize=12, weight="bold", color=ACENTO)
    fig.text(0.06, 0.893, frase, fontsize=10.5, color=TINTA, va="top", linespacing=1.5)


def _tarjeta(fig, x, y, w, h, etiqueta, valor, color, linea, linea2=None):
    from matplotlib.patches import FancyBboxPatch
    fig.add_artist(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.008",
                                  transform=fig.transFigure, facecolor=FONDO, edgecolor="none"))
    fig.text(x + 0.018, y + h - 0.022, etiqueta, fontsize=8.5, color=SUAVE)
    fig.text(x + 0.018, y + h - 0.054, valor, fontsize=17, weight="bold", color=color)
    fig.text(x + 0.018, y + 0.024 if linea2 else y + 0.014, linea, fontsize=7.5, color=TINTA)
    if linea2:
        fig.text(x + 0.018, y + 0.010, linea2, fontsize=7.5, color=SUAVE)


def _pagina_hoy(pdf, nombre, pos, ev, real, rf):
    fig = plt.figure(figsize=A4)
    fig.patch.set_facecolor("white")
    _encabezado(fig, f"Cartera {nombre}",
                "En dólares: cada operación en pesos se pasó al MEP de su propia fecha")

    filas = pos["posiciones"]
    es_fci = lambda f: f["source"] == "cocos-fci"
    bolsa = [f for f in filas if not es_fci(f) and f["valor_usd"] is not None]
    invertido = sum(f["valor_usd"] for f in bolsa)
    caja = sum(f["valor_usd"] or 0 for f in filas if es_fci(f))
    con_costo = [f for f in bolsa if f["costo_usd"] is not None]
    costo = sum(f["costo_usd"] for f in con_costo)
    abierto = sum(f["valor_usd"] - f["costo_usd"] for f in con_costo)
    trades = real.get("trades", [])
    cerrado = sum(t["pnl_usd"] for t in trades if t.get("tipo") != "fci")
    cerrado_fci = real.get("total_usd", 0.0)

    ok = ev and "error" not in ev
    rend = (ev.get("rendimiento_capital_pct") if ok else None)
    rend = rend if rend is not None else (ev.get("rendimiento_pct") if ok else None)
    rend_fci = ev.get("rendimiento_con_fci_pct") if ok else None
    tir = ((ev.get("cartera_12m") or {}).get("tir_pct")
           or (ev.get("ultimos_12m") or {}).get("tir_pct")) if ok else None
    desde = ev.get("desde") if ok else None

    frase = (f"Tenés {_usd(invertido + caja)}: {_usd(invertido)} invertidos en bolsa "
             f"y {_usd(caja)} en caja.")
    if rend is not None and desde:
        frase += (f"\nDesde que empezaste, en {_mes(desde)}, la cartera ganó "
                  f"{_pct(rend)} sobre lo que pusiste.")
    if tir is not None:
        frase += f"\nLo que tenés hoy habría rendido {_pct(tir)} en el último año."
    _pregunta(fig, "¿Cómo está la cartera?", frase)

    activos = len({f["ticker"] for f in bolsa})
    tarjetas = [
        ("Invertido en bolsa", _usd(invertido), TINTA,
         f"{len(bolsa)} posiciones en {activos} activos",
         "acciones, CEDEARs y bonos al precio de hoy"),
        ("En caja (FCI)", _usd(caja), TINTA,
         "fondos de liquidez: plata disponible",
         "no entra en los rendimientos de abajo"),
        ("Ganancia de lo que tenés", _usd(abierto, signo=True), _tono(abierto),
         f"{_pct(abierto / costo * 100 if costo else 0, signo=True)} sobre lo que costó",
         "es lo que ganarías si vendieras todo hoy"),
        ("Ganancia ya cobrada", _usd(cerrado, signo=True), _tono(cerrado),
         f"ventas y dividendos · contando los FCI, {_usd(cerrado_fci, signo=True)}",
         "ya está en tu bolsillo: no cambia con el mercado"),
    ]
    if rend is not None:
        tarjetas.append(("Rendimiento desde el inicio", _pct(rend, signo=True), _tono(rend),
                         f"sin FCI · contando los FCI, {_pct(rend_fci, signo=True)}"
                         if rend_fci is not None else "sin FCI",
                         f"todo lo ganado sobre lo invertido, desde {_mes(desde)}"))
    if tir is not None:
        tarjetas.append(("Rinde la cartera de hoy", f"{_pct(tir, signo=True)} al año", _tono(tir),
                         "lo que tenés hoy, tenido los últimos doce meses",
                         f"para comparar: una letra del Tesoro de EE.UU. paga {_pct(rf * 100)}"))

    for i, t in enumerate(tarjetas):
        _tarjeta(fig, 0.06 + (i % 2) * 0.45, 0.735 - (i // 2) * 0.105, 0.43, 0.093, *t)

    abajo = 0.735 - ((len(tarjetas) - 1) // 2) * 0.105
    fig.text(0.06, abajo - 0.035, "Qué tenés", fontsize=11, weight="bold", color=TINTA)
    orden = sorted(filas, key=lambda f: -(f["valor_usd"] or 0))
    tabla = [[f["ticker"], f["buy_date"], _num(f["qty"]),
              _usd(f["valor_usd"]) if f["valor_usd"] is not None else "—",
              _usd(f["pnl_usd"], signo=True) if f.get("pnl_usd") is not None else "—",
              _pct(f["pnl_pct"], signo=True) if f.get("pnl_pct") is not None else "—"]
             for f in orden]
    # Alto fijo por fila y anclada arriba: con `loc` matplotlib la estira y la
    # monta sobre las tarjetas. Con muchas posiciones, las filas se achican.
    alto = abajo - 0.05 - 0.07
    ax = fig.add_axes([0.06, 0.07, 0.88, alto])
    ax.axis("off")
    h = min(1.0, (len(tabla) + 1) * 0.021 / alto)
    t = ax.table(cellText=tabla, colLabels=["Activo", "Comprado", "Cantidad", "Vale hoy", "Ganancia", "%"],
                 cellLoc="right", colWidths=[0.20, 0.16, 0.14, 0.18, 0.18, 0.14], bbox=[0, 1 - h, 1, h])
    t.auto_set_font_size(False)
    t.set_fontsize(7.5)
    for (fila, col), celda in t.get_celld().items():
        celda.set_edgecolor(LINEA)
        celda.set_linewidth(0.5)
        if fila == 0:
            celda.set_text_props(weight="bold", color=SUAVE)
            celda.set_facecolor(FONDO)
        elif col in (4, 5) and orden[fila - 1].get("pnl_usd") is not None:
            celda.set_text_props(color=_tono(orden[fila - 1]["pnl_usd"]))
    pdf.savefig(fig); plt.close(fig)


# Las mismas zonas que la barra de la web (ZONAS en app.jsx): son una política
# —cuánto se tolera perder en un día—, no un cálculo.
ZONAS = [(1.5, POSITIVO, "Tranquilo",
          "el riesgo de un día es bajo para una cartera de acciones."),
         (2.5, POSITIVO, "Normal",
          "se mueve como cualquier cartera de acciones: hay días de baja, y se recuperan."),
         (3.0, AMBAR, "Atento",
          "está cerca del límite de lo que conviene tolerar en un día."),
         (float("inf"), NEGATIVO, "Por encima del límite",
          "un día malo pega más de lo que conviene tolerar.")]
LIMITE = 3.0


def _pagina_cuanto_baja(pdf, nombre, riesgo):
    if not riesgo or "error" in riesgo:
        return
    fig = plt.figure(figsize=A4)
    fig.patch.set_facecolor("white")
    _encabezado(fig, "Riesgo", f"Cartera {nombre}")
    d = riesgo.get("var_fhs") or riesgo
    var, cvar = abs(d["var95_pct"]), abs(d["cvar95_pct"])
    _pregunta(fig, "¿Cuánto puede bajar?",
              f"En un día malo —uno de cada veinte— la cartera puede bajar {_usd(abs(d['var95_usd']))}.\n"
              f"Si el día es muy malo, la baja promedio es de {_usd(abs(d['cvar95_usd']))}.\n"
              f"Son bajas de un día: la cartera no pierde eso cada vez que el mercado cae.")

    tope, color, titulo, texto = next(z for z in ZONAS if var <= z[0])
    from matplotlib.patches import FancyBboxPatch
    fig.add_artist(FancyBboxPatch((0.06, 0.765), 0.88, 0.05, boxstyle="round,pad=0,rounding_size=0.008",
                                  transform=fig.transFigure, facecolor=FONDO, edgecolor="none"))
    fig.text(0.08, 0.79, "●", fontsize=16, color=color, va="center")
    fig.text(0.115, 0.79, f"{titulo}: {texto}", fontsize=9.5, color=TINTA, va="center")

    escala = max(4.0, -(-max(var, cvar) * 1.15 // 1))
    ax = fig.add_axes([0.25, 0.62, 0.69, 0.11])
    previo = 0
    for hasta, tinte in ((1.5, "#E3F1E9"), (2.5, "#EEF4E6"), (3.0, "#F8EEDB"), (escala, "#F6E1DC")):
        ax.axvspan(previo, min(hasta, escala), color=tinte, lw=0)
        previo = hasta
    ax.axvline(LIMITE, color=NEGATIVO, lw=1, ls="--")
    ax.text(LIMITE, -0.55, "límite", color=NEGATIVO, fontsize=7, ha="center", va="bottom")
    for i, (v, usd_) in enumerate(((var, d["var95_usd"]), (cvar, d["cvar95_usd"]))):
        ax.barh(i, v, height=0.42, color=TINTA)
        ax.text(v + escala * 0.015, i, f"{_pct(v)} · {_usd(abs(usd_))}", va="center", fontsize=8.5, color=TINTA)
    ax.set_xlim(0, escala); ax.set_ylim(1.5, -0.5)
    ax.set_yticks([]); ax.set_xticks(range(int(escala) + 1))
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0f} %")
    for lado in ax.spines.values():
        lado.set_visible(False)
    ax.tick_params(colors=SUAVE, labelsize=7.5, length=0)
    fig.text(0.06, 0.6935, "Un día malo", fontsize=9.5, weight="bold", color=TINTA, va="center")
    fig.text(0.06, 0.678, "1 de cada 20", fontsize=7.5, color=SUAVE, va="center")
    fig.text(0.06, 0.6465, "Un día muy malo", fontsize=9.5, weight="bold", color=TINTA, va="center")
    fig.text(0.06, 0.6315, "promedio de esos días", fontsize=7.5, color=SUAVE, va="center")
    fig.text(0.06, 0.585, "Verde: tranquilo · amarillo: atento · rojo: más de lo que conviene "
             "perder en un día.", fontsize=7.5, color=SUAVE)

    contrib = [c for c in riesgo.get("contribucion_riesgo", []) if c.get("riesgo_pct") is not None][:10]
    if contrib:
        fig.text(0.06, 0.535, "¿Qué activos la mueven más?", fontsize=11, weight="bold", color=TINTA)
        ax = fig.add_axes([0.20, 0.27, 0.74, 0.25])
        y = range(len(contrib))
        ax.barh([i + 0.2 for i in y], [c["riesgo_pct"] for c in contrib],
                height=0.38, color=NEGATIVO, label="cuánto mueve la cartera")
        ax.barh([i - 0.2 for i in y], [c["peso_pct"] for c in contrib],
                height=0.38, color=SERIES[2], label="cuánto pesa en la cartera")
        ax.set_yticks(list(y)); ax.set_yticklabels([c["ticker"] for c in contrib], fontsize=8)
        ax.invert_yaxis(); ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0f} %")
        ax.legend(fontsize=7.5, frameon=False, loc="lower right")
        _estilo(ax)
        mayor = contrib[0]
        fig.text(0.06, 0.235,
                 f"{mayor['ticker']} pesa {_pct(mayor['peso_pct'], 0)} de la cartera pero explica "
                 f"{_pct(mayor['riesgo_pct'], 0)} de sus movimientos. Cuando la barra roja es más larga\n"
                 "que la azul, ese activo mueve la cartera más de lo que pesa.",
                 fontsize=8, color=TINTA, va="top", linespacing=1.5)

    fig.text(0.06, 0.165, "Lo peor que pasó", fontsize=11, weight="bold", color=TINTA)
    fig.text(0.06, 0.15,
             f"En los últimos tres años, lo que tenés hoy llegó a caer {_pct(abs(riesgo['max_drawdown_pct']))} "
             "desde su punto más alto antes de recuperarse.\n"
             "Es la baja que hubo que aguantar sin vender: por eso la bolsa se mira a varios años.",
             fontsize=8, color=TINTA, va="top", linespacing=1.5)

    fig.text(0.06, 0.065,
             f"Para especialistas: VaR 95 % {_pct(-var, 2)} y CVaR 95 % {_pct(-cvar, 2)} "
             f"(simulación histórica filtrada, de un día)\nvolatilidad anual "
             f"{_pct(riesgo['volatilidad_anual_pct'])} · Sharpe {_num(riesgo['sharpe'], 2)} · "
             f"Sortino {_num(riesgo['sortino'], 2)} · {riesgo['n_ruedas']} ruedas.",
             fontsize=6.5, color=SUAVE)
    pdf.savefig(fig); plt.close(fig)


def _ejes_llanos(ax):
    _estilo(ax)
    ax.tick_params(length=0)


def _pagina_decisiones(pdf, nombre, dec):
    velas = [v for v in (dec or {}).get("velas", [])
             if v["var_antes"] is not None and v["var_despues"] is not None]
    if not velas:
        return
    fig = plt.figure(figsize=A4)
    fig.patch.set_facecolor("white")
    _encabezado(fig, "Tus decisiones", f"Cartera {nombre}")
    sube = sum(max(0, v["var_despues"] - v["var_antes"]) for v in velas)
    baja = sum(max(0, v["var_antes"] - v["var_despues"]) for v in velas)
    hoy = dec.get("hoy")
    frase = (f"Operaste {len(velas)} días. Sumadas, tus compras y ventas subieron el riesgo de un día\n"
             f"malo {_num(sube, 2)} puntos y lo bajaron {_num(baja, 2)}.")
    if hoy:
        _, _, titulo, _ = next(z for z in ZONAS if hoy["var95_pct"] <= z[0])
        frase += f"\nHoy un día malo es una baja de {_pct(hoy['var95_pct'])}: {titulo.lower()}."
    _pregunta(fig, "¿Tus compras y ventas subieron o bajaron el riesgo?", frase)

    ax = fig.add_axes([0.10, 0.50, 0.80, 0.30])
    x = list(range(len(velas)))
    tope = 1.1 * max(LIMITE, *(max(v["var_antes"], v["var_despues"]) for v in velas))
    previo = 0
    for hasta, tinte in ((1.5, "#E3F1E9"), (2.5, "#EEF4E6"), (3.0, "#F8EEDB"), (tope, "#F6E1DC")):
        ax.axhspan(previo, min(hasta, tope), color=tinte, lw=0)
        previo = hasta
    for i, v in enumerate(velas):
        a, b = v["var_antes"], v["var_despues"]
        ax.bar(i, max(abs(b - a), 0.02), bottom=min(a, b), width=0.6,
               color=NEGATIVO if b > a else POSITIVO)
    if hoy:
        ax.axhline(hoy["var95_pct"], color=SUAVE, lw=0.8, ls=":")
        ax.text(len(velas) - 0.5, hoy["var95_pct"], f" hoy {_pct(hoy['var95_pct'])}",
                fontsize=7, color=SUAVE, va="bottom", ha="right")
    ax.set_ylim(0, tope); ax.set_xlim(-0.7, len(velas) - 0.3)
    ax.yaxis.set_major_formatter(_eje_pct)
    ax.set_ylabel("un día malo", fontsize=8, color=SUAVE)
    paso = max(1, len(velas) // 8)
    ax.set_xticks(x[::paso])
    ax.set_xticklabels([v["fecha"][2:7].replace("-", "/") for v in velas[::paso]], fontsize=7)
    _ejes_llanos(ax)
    ax.grid(False)
    esperado = [v["esperado_despues"] for v in velas]
    if all(e is not None for e in esperado):
        ax2 = ax.twinx()
        ax2.plot(x, esperado, color=SERIES[2], lw=1.2, marker="o", ms=2.5, alpha=0.8)
        ax2.yaxis.set_major_formatter(_eje_pct)
        ax2.set_ylabel("lo que se espera que rinda en un año", fontsize=8, color=SERIES[2])
        ax2.tick_params(colors=SERIES[2], labelsize=7.5, length=0)
        for lado in ax2.spines.values():
            lado.set_visible(False)
    fig.text(0.10, 0.465, "Cada barra es un día en que operaste: roja si después el día malo quedó peor, verde si "
             "quedó mejor.\nLa línea azul es lo que se espera que rinda en un año la cartera que quedó.",
             fontsize=7.5, color=SUAVE, va="top", linespacing=1.5)

    def lista(titulo, y, filas, color):
        fig.text(0.06, y, titulo, fontsize=10, weight="bold", color=TINTA)
        for j, v in enumerate(filas):
            d = v["var_despues"] - v["var_antes"]
            ops = ", ".join(("compró " if o[0] == "+" else "vendió ") + o[1:] for o in v["operaciones"][:4])
            fig.text(0.06, y - 0.025 - j * 0.02, v["fecha"], fontsize=8, color=SUAVE)
            fig.text(0.19, y - 0.025 - j * 0.02, f"{'+' if d > 0 else '−'}{_num(d, 2)} pts",
                     fontsize=8, color=color, weight="bold")
            fig.text(0.30, y - 0.025 - j * 0.02, ops, fontsize=8, color=TINTA)

    orden = sorted(velas, key=lambda v: v["var_despues"] - v["var_antes"])
    suben = [v for v in orden[::-1] if v["var_despues"] > v["var_antes"]][:4]
    bajan = [v for v in orden if v["var_despues"] < v["var_antes"]][:4]
    if suben:
        lista("Las que más lo subieron", 0.39, suben, NEGATIVO)
    if bajan:
        lista("Las que más lo bajaron", 0.25, bajan, POSITIVO)
    fig.text(0.06, 0.09, "Subir el riesgo no es malo en sí: puede ser una apuesta que vale la pena. "
             "Conviene que sea a propósito.", fontsize=8, color=TINTA)
    pdf.savefig(fig); plt.close(fig)


def _pagina_markowitz(pdf, nombre, mk):
    if not mk or "error" in mk or not mk.get("frontera"):
        return
    fig = plt.figure(figsize=A4)
    fig.patch.set_facecolor("white")
    _encabezado(fig, "Cómo está armada", f"Cartera {nombre}")
    act, ms, mv = mk["actual"], mk["max_sharpe"], mk["min_varianza"]
    mismo = max((p for p in mk["frontera"] if p["vol"] <= act["vol_pct"] + 1e-9),
                key=lambda p: p["ret"], default=None)
    if mismo and mismo["ret"] - act["ret_pct"] > 0.5:
        frase = (f"Con el mismo riesgo que hoy, otra mezcla de estos mismos activos podría esperar\n"
                 f"{_pct(mismo['ret'])} al año en vez de {_pct(act['ret_pct'])}. "
                 f"La de menos riesgo posible oscilaría {_pct(mv['vol_pct'])} al año en vez de {_pct(act['vol_pct'])}.")
    else:
        frase = (f"Está bien armada: con estos activos no hay una mezcla que espere más\n"
                 f"con el mismo riesgo. Hoy se espera {_pct(act['ret_pct'])} al año, oscilando {_pct(act['vol_pct'])}.")
    _pregunta(fig, "¿Está bien armada?", frase)

    ax = fig.add_axes([0.10, 0.44, 0.84, 0.38])
    fr, ine = mk["frontera"], mk.get("frontera_ineficiente") or []
    if ine:
        ax.plot([p["vol"] for p in ine], [p["ret"] for p in ine], color=LINEA, lw=1.5, ls="--")
    ax.plot([p["vol"] for p in fr], [p["ret"] for p in fr], color=ACENTO, lw=2.2,
            label="las mejores mezclas posibles")
    for a in mk.get("activos", []):
        ax.scatter(a["vol_pct"], a["ret_pct"], s=14, color=SUAVE, zorder=3)
        ax.annotate(a["ticker"].replace(".BA", ""), (a["vol_pct"], a["ret_pct"]), fontsize=6.5,
                    color=SUAVE, xytext=(3, 2), textcoords="offset points")
    for pto, color, marca, texto in ((mv, SERIES[2], "D", "menos riesgo"),
                                     (ms, POSITIVO, "*", "mejor relación"),
                                     (act, NEGATIVO, "o", "tu cartera")):
        ax.scatter(pto["vol_pct"], pto["ret_pct"], s=140 if marca == "*" else 70, color=color,
                   marker=marca, zorder=5, edgecolor="white", linewidth=1)
        ax.annotate(texto, (pto["vol_pct"], pto["ret_pct"]), fontsize=8.5, weight="bold", color=color,
                    xytext=(7, -10), textcoords="offset points")
    ax.xaxis.set_major_formatter(_eje_pct)
    ax.yaxis.set_major_formatter(_eje_pct)
    ax.set_xlabel("cuánto oscila en un año  →  más riesgo", fontsize=8, color=SUAVE)
    ax.set_ylabel("lo que se espera que rinda en un año", fontsize=8, color=SUAVE)
    _ejes_llanos(ax)
    fig.text(0.10, 0.395, "Cada punto gris es uno de tus activos. La curva verde son las mezclas que, para cada "
             "nivel de riesgo,\nesperan rendir más: estar arriba y a la izquierda es mejor.",
             fontsize=7.5, color=SUAVE, va="top", linespacing=1.5)

    from matplotlib.patches import FancyBboxPatch
    fig.text(0.06, 0.335, "Las tres, lado a lado", fontsize=10, weight="bold", color=TINTA)
    filas = [("Se espera que rinda", lambda p: f"{_pct(p['ret_pct'])} al año"),
             ("Cuánto oscila", lambda p: f"{_pct(p['vol_pct'])} al año"),
             ("Rinde por riesgo (Sharpe)", lambda p: _num(p["sharpe"], 2))]
    for k, (pto, color, titulo) in enumerate(((act, NEGATIVO, "Tu cartera"),
                                              (ms, POSITIVO, "Mejor relación"),
                                              (mv, SERIES[2], "Menos riesgo"))):
        x = 0.30 + k * 0.22
        fig.add_artist(FancyBboxPatch((x - 0.01, 0.2), 0.2, 0.12,
                                      boxstyle="round,pad=0,rounding_size=0.008",
                                      transform=fig.transFigure, facecolor=FONDO, edgecolor="none"))
        fig.text(x, 0.30, titulo, fontsize=9.5, weight="bold", color=color)
        for j, (_, valor) in enumerate(filas):
            fig.text(x, 0.272 - j * 0.026, valor(pto), fontsize=9, color=TINTA)
    for j, (etiqueta, _) in enumerate(filas):
        fig.text(0.06, 0.272 - j * 0.026, etiqueta, fontsize=8.5, color=SUAVE)
    fig.text(0.06, 0.165, "Es una cuenta con la historia de cada activo, no una recomendación: supone que lo que "
             "se espera de cada uno\nse cumple, y la mezcla «óptima» suele concentrarse en pocos activos.",
             fontsize=7.5, color=SUAVE, va="top", linespacing=1.5)
    fig.text(0.06, 0.065, f"Para especialistas: frontera media-varianza de Markowitz · tu cartera Sharpe "
             f"{_num(act['sharpe'], 2)}, máximo Sharpe {_num(ms['sharpe'], 2)} · tasa libre "
             f"{_pct(mk['rf'] * 100)}.", fontsize=6.5, color=SUAVE)
    pdf.savefig(fig); plt.close(fig)


def _pagina_mercado(pdf, nombre, cp):
    if not cp or "error" in cp:
        return
    fig = plt.figure(figsize=A4)
    fig.patch.set_facecolor("white")
    _encabezado(fig, "Contra el mercado", f"Cartera {nombre} · comparada con el {cp['benchmark_nombre']}")
    rc, rb, beta, alfa = (cp["retorno_cartera_pct"], cp["retorno_benchmark_pct"],
                          cp["beta"], cp["alpha_anual_pct"])
    anios = cp["n_ruedas"] / 252
    gana = rc >= rb
    _pregunta(fig, "¿Le gana al mercado?",
              f"En los últimos {_num(anios, 0 if anios >= 1.95 else 1)} años, lo que tenés hoy rindió "
              f"{_pct(rc)} al año, contra {_pct(rb)} del {cp['benchmark_nombre']}:\n"
              f"{'le ganó' if gana else 'perdió'} por {_num(abs(rc - rb), 1)} puntos por año. "
              f"Cuando el índice sube 10 %, tu cartera tiende a subir {_pct(beta * 10)}."
              + (f"\nOjo: el {cp['benchmark_nombre']} no incluye dividendos y tu cartera sí; "
                 f"la comparación te favorece un poco." if cp.get("indice_sin_dividendos") else ""))

    serie = cp.get("acumulado") or []
    if serie:
        from matplotlib.dates import DateFormatter
        import pandas as pd
        fechas = pd.to_datetime([p["fecha"] for p in serie])
        ax = fig.add_axes([0.10, 0.53, 0.84, 0.29])
        ax.plot(fechas, [p["indice"] for p in serie], color=SUAVE, lw=1.4, label=cp["benchmark_nombre"])
        ax.plot(fechas, [p["cartera"] for p in serie], color=ACENTO, lw=2, label="tu cartera")
        ax.axhline(100, color=LINEA, lw=0.8)
        ax.xaxis.set_major_formatter(DateFormatter("%m/%y"))
        ax.legend(fontsize=8, frameon=False, loc="upper left")
        ax.set_ylabel("cada 100 dólares invertidos al principio", fontsize=8, color=SUAVE)
        _ejes_llanos(ax)
        fin_c, fin_b = serie[-1]["cartera"], serie[-1]["indice"]
        fig.text(0.10, 0.495, f"100 dólares puestos al principio en lo que tenés hoy serían {_num(fin_c)}; "
                 f"en el índice, {_num(fin_b)}.", fontsize=8, color=TINTA)

    r2 = cp["r2"]
    tarjetas = [
        ("Rindió por año", _pct(rc, signo=True), _tono(rc),
         f"el {cp['benchmark_nombre']}, {_pct(rb, signo=True)}", "con lo que tenés hoy, mirando atrás"),
        ("Cuánto la mueve el mercado", _num(beta, 2), TINTA,
         "1 = se mueve igual que el índice",
         "más de 1 amplifica sus subas y bajas" if beta > 1 else "menos de 1 las amortigua"),
        ("Lo que suma tu elección", f"{_pct(alfa, signo=True)} al año", _tono(alfa),
         "lo ganado de más (o de menos) que el mercado,", "descontado el riesgo que toma"),
        ("Cuánto la explica el índice", _pct(r2 * 100, 0), TINTA,
         "alto: los números de esta página valen" if r2 >= 0.5 else
         "a medias: leelos con reservas" if r2 >= 0.2 else "poco: el índice no es buen espejo",
         "de lo que hace la cartera, cuánto es el mercado"),
    ]
    for i, t in enumerate(tarjetas):
        _tarjeta(fig, 0.06 + (i % 2) * 0.45, 0.36 - (i // 2) * 0.105, 0.43, 0.093, *t)
    fig.text(0.06, 0.21, "Rendir menos que el índice no es un fracaso si la cartera también se mueve menos: "
             "la cuenta justa es la de\n«lo que suma tu elección», que compara contra lo que el mercado "
             "paga por ese mismo riesgo.", fontsize=7.5, color=SUAVE, va="top", linespacing=1.5)
    fig.text(0.06, 0.065, f"Para especialistas: CAPM contra {cp['benchmark_nombre']} · β {_num(beta, 2)} · "
             f"α {_pct(alfa, 2)} anual · R² {_num(r2, 2)} · tracking error {_pct(cp['tracking_error_pct'])} · "
             f"{cp['n_ruedas']} ruedas · tasa libre {_pct(cp['rf'] * 100)}.", fontsize=6.5, color=SUAVE)
    pdf.savefig(fig); plt.close(fig)


def _pagina_montecarlo(pdf, nombre, mc, mca):
    escenarios = [(t, d) for t, d in (("Según el modelo", mc), ("Según los analistas", mca))
                  if d and "error" not in d]
    if not escenarios:
        return
    fig = plt.figure(figsize=A4)
    fig.patch.set_facecolor("white")
    _encabezado(fig, "El año que viene", f"Cartera {nombre} · {escenarios[0][1]['n_simulaciones']:,} "
                "simulaciones por escenario".replace(",", "."))
    base = escenarios[0][1]
    f, v0 = base["final"], base["valor_inicial"]
    _pregunta(fig, "¿Qué puede pasar en un año?",
              f"Hoy la cartera vale {_usd(v0)}. Dentro de un año, lo más probable es que valga cerca de\n"
              f"{_usd(f['mediana'])}. En un año malo —uno de cada veinte— podría valer {_usd(f['p5'])}, y en uno\n"
              f"muy bueno {_usd(f['p95'])}. Las chances de terminar el año ganando son {_pct(f['prob_ganancia'], 0)}.")

    tope = max(d["abanico"]["p95"][-1] for _, d in escenarios) * 1.03
    piso = min(d["abanico"]["p5"][-1] for _, d in escenarios) * 0.97
    for i, (titulo, d) in enumerate(escenarios):
        x0 = 0.08 + i * 0.46
        ax = fig.add_axes([x0, 0.50, 0.38, 0.27])
        ab = d["abanico"]
        meses = [dd / 21 for dd in ab["dias"]]
        ax.fill_between(meses, ab["p5"], ab["p95"], color=SERIES[0], alpha=0.12, lw=0)
        ax.fill_between(meses, ab["p25"], ab["p75"], color=SERIES[0], alpha=0.25, lw=0)
        ax.plot(meses, ab["p50"], color=SERIES[0], lw=1.8)
        ax.axhline(d["valor_inicial"], color=SUAVE, lw=0.8, ls=":")
        ax.set_ylim(piso, tope); ax.set_xlim(0, 12)
        ax.set_xticks([0, 3, 6, 9, 12])
        ax.set_xticklabels(["hoy", "3 m", "6 m", "9 m", "1 año"], fontsize=7)
        ax.yaxis.set_major_formatter(
            lambda v, _: f"{_num(v / 1000, 0 if (v / 1000).is_integer() else 1)} mil")
        _ejes_llanos(ax)
        fig.text(x0, 0.79, titulo, fontsize=10.5, weight="bold", color=TINTA)
        fd = d["final"]
        filas = [("Año malo", "1 de cada 20", fd["p5"], NEGATIVO),
                 ("Lo más probable", "la mitad de las veces, más", fd["mediana"], TINTA),
                 ("Año muy bueno", "1 de cada 20", fd["p95"], POSITIVO)]
        for j, (et, sub, val, color) in enumerate(filas):
            y = 0.43 - j * 0.052
            fig.text(x0, y, et, fontsize=8.5, color=TINTA, weight="bold")
            fig.text(x0, y - 0.016, sub, fontsize=7, color=SUAVE)
            fig.text(x0 + 0.38, y, _usd(val), fontsize=11, color=color, weight="bold", ha="right")
            fig.text(x0 + 0.38, y - 0.017, _pct((val / d["valor_inicial"] - 1) * 100, signo=True),
                     fontsize=7.5, color=color, ha="right")
        fig.text(x0, 0.27, f"Chances de ganar: {_pct(fd['prob_ganancia'], 0)}", fontsize=9, color=TINTA)

    fig.text(0.08, 0.465, "La franja oscura es donde cae la mitad de los resultados; la clara, nueve de cada "
             "diez. La línea punteada es el valor de hoy.", fontsize=7.5, color=SUAVE)
    fig.text(0.06, 0.20,
             "Según el modelo: lo que se espera de cada activo sale de su historia y del riesgo de su mercado, "
             "probado\ncontra veinte años de datos. Según los analistas: lo mismo, corregido con los precios "
             "objetivo de los\nanalistas y los que fijaste vos. Los analistas suelen ser optimistas, y eso no se "
             "puede probar con la historia.",
             fontsize=7.5, color=TINTA, va="top", linespacing=1.5)
    fig.text(0.06, 0.09, "No es una promesa: son miles de años posibles armados con cómo se movieron estos "
             "activos en el pasado.", fontsize=8, color=TINTA)
    pdf.savefig(fig); plt.close(fig)


# ── Mapamundi: el mismo atlas que la web (web/vendor/topojson) ───────────────
_ATLAS = Path(__file__).resolve().parents[2] / "web/vendor/topojson/world_110m.json"
PAISES = {
    "United States": ("USA", "Estados Unidos"), "Argentina": ("ARG", "Argentina"),
    "Brazil": ("BRA", "Brasil"), "China": ("CHN", "China"), "Hong Kong": ("CHN", "Hong Kong"),
    "Taiwan": ("TWN", "Taiwán"), "Japan": ("JPN", "Japón"), "South Korea": ("KOR", "Corea del Sur"),
    "India": ("IND", "India"), "Canada": ("CAN", "Canadá"), "Mexico": ("MEX", "México"),
    "United Kingdom": ("GBR", "Reino Unido"), "Germany": ("DEU", "Alemania"),
    "France": ("FRA", "Francia"), "Netherlands": ("NLD", "Países Bajos"),
    "Switzerland": ("CHE", "Suiza"), "Spain": ("ESP", "España"), "Italy": ("ITA", "Italia"),
    "Ireland": ("IRL", "Irlanda"), "Belgium": ("BEL", "Bélgica"), "Denmark": ("DNK", "Dinamarca"),
    "Sweden": ("SWE", "Suecia"), "Norway": ("NOR", "Noruega"), "Finland": ("FIN", "Finlandia"),
    "Austria": ("AUT", "Austria"), "Portugal": ("PRT", "Portugal"), "Israel": ("ISR", "Israel"),
    "Australia": ("AUS", "Australia"), "Chile": ("CHL", "Chile"), "Colombia": ("COL", "Colombia"),
    "Peru": ("PER", "Perú"), "Uruguay": ("URY", "Uruguay"), "Paraguay": ("PRY", "Paraguay"),
    "Bolivia": ("BOL", "Bolivia"), "Ecuador": ("ECU", "Ecuador"), "Venezuela": ("VEN", "Venezuela"),
    "Panama": ("PAN", "Panamá"), "Costa Rica": ("CRI", "Costa Rica"), "Nicaragua": ("NIC", "Nicaragua"),
    "Honduras": ("HND", "Honduras"), "El Salvador": ("SLV", "El Salvador"),
    "Guatemala": ("GTM", "Guatemala"), "South Africa": ("ZAF", "Sudáfrica"),
    "Luxembourg": ("LUX", "Luxemburgo"), "Greece": ("GRC", "Grecia"), "Turkey": ("TUR", "Turquía"),
    "Poland": ("POL", "Polonia"), "Russia": ("RUS", "Rusia"), "Indonesia": ("IDN", "Indonesia"),
    "Saudi Arabia": ("SAU", "Arabia Saudita"), "New Zealand": ("NZL", "Nueva Zelanda"),
    "Kazakhstan": ("KAZ", "Kazajistán"),
}
# Un ETF regional se pinta en todo su continente, como en la web (CONTINENTES).
REGIONES = {
    "Europe": ("Europa", ["Austria", "Belgium", "Denmark", "Finland", "France", "Germany", "Ireland",
                          "Italy", "Netherlands", "Norway", "Portugal", "Spain", "Sweden",
                          "Switzerland", "United Kingdom"]),
    "Eurozone": ("Eurozona", ["Austria", "Belgium", "Finland", "France", "Germany", "Ireland",
                              "Italy", "Netherlands", "Portugal", "Spain"]),
    "Latin America": ("Latinoamérica", ["Mexico", "Guatemala", "Honduras", "El Salvador", "Nicaragua",
                                        "Costa Rica", "Panama", "Colombia", "Venezuela", "Ecuador",
                                        "Peru", "Brazil", "Bolivia", "Paraguay", "Chile",
                                        "Argentina", "Uruguay"]),
}
SECTORES = {
    "Technology": "Tecnología", "Consumer Defensive": "Consumo básico",
    "Consumer Cyclical": "Consumo discrecional", "Healthcare": "Salud", "Energy": "Energía",
    "Financial Services": "Finanzas", "Communication Services": "Comunicaciones",
    "Industrials": "Industria", "Basic Materials": "Materiales", "Utilities": "Servicios públicos",
    "Real Estate": "Inmobiliario", "Sin clasificar": "Sin clasificar",
}


def _atlas():
    """Polígonos (lon, lat) por código ISO-3, decodificando el TopoJSON a mano:
    son arcos con coordenadas cuantizadas y delta-codificadas."""
    import json
    d = json.loads(_ATLAS.read_text())
    (sx, sy), (tx, ty) = d["transform"]["scale"], d["transform"]["translate"]
    arcos = []
    for arco in d["arcs"]:
        x = y = 0
        puntos = []
        for dx, dy in arco:
            x += dx; y += dy
            puntos.append((x * sx + tx, y * sy + ty))
        arcos.append(puntos)

    def anillo(indices):
        puntos = []
        for i in indices:
            a = arcos[i] if i >= 0 else arcos[~i][::-1]
            puntos.extend(a[1:] if puntos else a)
        # Rusia y Fiji cruzan el meridiano 180: sin desenrollar la longitud,
        # el polígono vuelve por todo el mapa y deja una raya horizontal.
        for j in range(1, len(puntos)):
            lon, lat = puntos[j]
            while lon - puntos[j - 1][0] > 180:
                lon -= 360
            while lon - puntos[j - 1][0] < -180:
                lon += 360
            puntos[j] = (lon, lat)
        return puntos

    salida = {}
    for g in d["objects"]["countries"]["geometries"]:
        partes = [g["arcs"]] if g["type"] == "Polygon" else g.get("arcs", [])
        salida[g.get("id")] = [anillo(p[0]) for p in partes]
    return salida


def _mercator(lat):
    import math
    return math.degrees(math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)))


def _pagina_donde(pdf, nombre, comp):
    if not comp or "error" in comp:
        return
    from matplotlib.colors import to_rgb
    from matplotlib.patches import Polygon
    fig = plt.figure(figsize=A4)
    fig.patch.set_facecolor("white")
    _encabezado(fig, "Dónde está invertida", f"Cartera {nombre}")

    paises = comp.get("por_pais") or []
    peso, nombres, sin_mapa = {}, [], []
    for x in paises:
        if x["etiqueta"] in REGIONES:
            es, miembros = REGIONES[x["etiqueta"]]
            for m in miembros:
                peso[PAISES[m][0]] = peso.get(PAISES[m][0], 0) + x["pct"]
        elif x["etiqueta"] in PAISES:
            iso, es = PAISES[x["etiqueta"]]
            peso[iso] = peso.get(iso, 0) + x["pct"]
        else:
            es = x["etiqueta"]
            sin_mapa.append(es)
        nombres.append(f"{_pct(x['pct'], 0)} en {es}")
    _pregunta(fig, "¿En qué países y sectores está tu plata?",
              ", ".join(nombres[:3]) + (" y el resto en otros." if len(nombres) > 3 else ".")
              if nombres else "Sin datos de país para estos activos.")

    ax = fig.add_axes([0.04, 0.53, 0.92, 0.33])
    maximo = max(peso.values(), default=1)
    r, g, b = to_rgb(AMBAR)
    for iso, anillos in _atlas().items():
        if iso == "ATA":
            continue
        p = peso.get(iso)
        color = ((1 - (0.15 + 0.85 * p / maximo)) + (0.15 + 0.85 * p / maximo) * r,
                 (1 - (0.15 + 0.85 * p / maximo)) + (0.15 + 0.85 * p / maximo) * g,
                 (1 - (0.15 + 0.85 * p / maximo)) + (0.15 + 0.85 * p / maximo) * b) if p else "#E8EDF0"
        for puntos in anillos:
            ax.add_patch(Polygon([(lon, _mercator(max(min(lat, 84), -84))) for lon, lat in puntos],
                                 closed=True, facecolor=color, edgecolor="white", linewidth=0.3))
    ax.set_xlim(-170, 190); ax.set_ylim(_mercator(-56), _mercator(75))
    ax.set_aspect("equal"); ax.axis("off")
    if sin_mapa:
        fig.text(0.06, 0.515, f"Sin lugar en el mapa: {', '.join(sin_mapa)}.", fontsize=7, color=SUAVE)
    fig.text(0.94, 0.515, "más intenso = más plata en ese país", fontsize=7, color=SUAVE, ha="right")

    sectores = [x for x in (comp.get("por_sector") or []) if x["pct"] >= 0.05][:10]
    if sectores:
        fig.text(0.06, 0.465, "Por sector", fontsize=11, weight="bold", color=TINTA)
        ax = fig.add_axes([0.30, 0.47 - 0.032 * len(sectores) - 0.02, 0.56, 0.032 * len(sectores)])
        y = range(len(sectores))
        ax.barh(list(y), [x["pct"] for x in sectores], height=0.6, color=ACENTO)
        ax.set_yticks(list(y))
        ax.set_yticklabels([SECTORES.get(x["etiqueta"], x["etiqueta"]) for x in sectores], fontsize=8.5,
                           color=TINTA)
        for i, x in enumerate(sectores):
            ax.text(x["pct"] + 0.8, i, _pct(x["pct"]), va="center", fontsize=8, color=TINTA)
        ax.invert_yaxis(); ax.set_xticks([])
        ax.set_xlim(0, max(x["pct"] for x in sectores) * 1.18)
        for lado in ax.spines.values():
            lado.set_visible(False)
        ax.tick_params(length=0)
        fig.text(0.06, 0.47 - 0.032 * len(sectores) - 0.05,
                 "Un ETF no es una empresa, así que no tiene sector: se muestra su categoría (por ejemplo, "
                 "«Large Growth»).", fontsize=7.5, color=SUAVE)
    pdf.savefig(fig); plt.close(fig)


def generar(nombre_cartera: str, posiciones: list, datos: dict) -> bytes:
    """Devuelve el PDF completo en memoria.

    `datos` son los resultados que la pantalla ya calculó (evolución, riesgo,
    CAPM, Markowitz, los dos Monte Carlo…): ver `jobs.para_reporte`."""
    from core.models import portfolio

    pos = portfolio.valuar(posiciones)
    if "error" in pos:
        raise ValueError(pos["error"])
    riesgo = datos["riesgo"]

    buffer = io.BytesIO()
    with PdfPages(buffer) as pdf:
        _pagina_hoy(pdf, nombre_cartera, pos, datos["evolucion"],
                    portfolio.pnl_realizado(datos["realizado"]),
                    riesgo.get("rf", 0.0) if "error" not in riesgo else 0.0)
        _pagina_donde(pdf, nombre_cartera, datos["composicion"])
        _pagina_mercado(pdf, nombre_cartera, datos["capm"])
        _pagina_markowitz(pdf, nombre_cartera, datos["markowitz"])
        _pagina_cuanto_baja(pdf, nombre_cartera, riesgo)
        _pagina_decisiones(pdf, nombre_cartera, datos["decisiones"])
        _pagina_montecarlo(pdf, nombre_cartera, datos["montecarlo"], datos["mc_analistas"])
        info = pdf.infodict()
        info["Title"] = f"Portfolio Analyzer — {nombre_cartera}"
        info["Author"] = "Leandro R. Bergero"
        info["Subject"] = "Análisis de cartera en dólares"
    return buffer.getvalue()
