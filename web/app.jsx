/*
 * app.jsx — Interfaz de Portfolio Analyzer.
 *
 * Se precompila a app.js con `npm run build`. No hay compilador en el
 * navegador: son 2.914 KB que no dibujan nada.
 *
 * Dos reglas que atraviesan todo el archivo:
 *
 *   1. Ningún color literal. Todos salen de las variables CSS, Plotly incluido
 *      (ver `colores()`). Es lo que hace que el tema claro/oscuro funcione sin
 *      mantener dos paletas en paralelo.
 *
 *   2. Todo KPI lleva su explicación: qué mide, cómo se lee el número que estás
 *      viendo y a partir de qué valor conviene prestar atención. En lenguaje
 *      llano, no en fórmulas.
 */

const { useState, useEffect, useRef, useCallback } = React;

/* ═══════════════ utilidades ═══════════════ */

const api = async (ruta, opciones) => {
  const r = await fetch(ruta, opciones);
  const d = await r.json().catch(() => ({ error: "Respuesta ilegible del servidor." }));
  if (!r.ok && !d.error) d.error = `Error ${r.status}`;
  return d;
};

const usd = (n, dec = 2) =>
  n == null ? "—" : "$" + Number(n).toLocaleString("es-AR",
    { minimumFractionDigits: dec, maximumFractionDigits: dec });
const pct = (n, dec = 2) => (n == null ? "—" : Number(n).toFixed(dec) + " %");
const num = (n, dec = 2) => (n == null ? "—" : Number(n).toFixed(dec));
const signo = (n) => (n == null ? "" : n > 0 ? "pos" : n < 0 ? "neg" : "");

/* Lee la paleta del CSS para que los gráficos sigan el tema. */
function colores() {
  const c = getComputedStyle(document.documentElement);
  const v = (n) => c.getPropertyValue(n).trim();
  return {
    texto: v("--texto"), texto2: v("--texto-2"), texto3: v("--texto-3"),
    borde: v("--borde"), panel: v("--panel"), acento: v("--acento"),
    positivo: v("--positivo"), negativo: v("--negativo"), alerta: v("--alerta"),
    series: [1,2,3,4,5,6,7,8].map((i) => v(`--serie-${i}`)),
  };
}

/* ═══════════════ Gráfico ═══════════════ */

function Grafico({ datos, layout, alto = 280 }) {
  const nodo = useRef(null);
  const tema = document.documentElement.dataset.theme || "auto";

  useEffect(() => {
    if (!nodo.current || !window.Plotly || !datos) return;
    const c = colores();
    const base = {
      paper_bgcolor: "transparent", plot_bgcolor: "transparent",
      font: { family: '"Public Sans",sans-serif', size: 11, color: c.texto2 },
      margin: { t: 10, r: 12, b: 38, l: 54 },
      xaxis: { gridcolor: c.borde, linecolor: c.borde, zerolinecolor: c.borde, automargin: true },
      yaxis: { gridcolor: c.borde, linecolor: c.borde, zerolinecolor: c.borde, automargin: true },
      legend: { bgcolor: "transparent", font: { size: 11 }, orientation: "h", y: -0.22 },
      hoverlabel: { bgcolor: c.panel, bordercolor: c.borde,
                    font: { color: c.texto, family: '"Public Sans",sans-serif' } },
      colorway: c.series,
      height: alto,
    };
    const mezcla = { ...base, ...layout,
      xaxis: { ...base.xaxis, ...(layout?.xaxis || {}) },
      yaxis: { ...base.yaxis, ...(layout?.yaxis || {}) } };
    Plotly.react(nodo.current, datos, mezcla,
                 { displayModeBar: false, responsive: true });
  }, [datos, layout, alto, tema]);

  useEffect(() => () => { if (nodo.current) Plotly.purge(nodo.current); }, []);
  return <div ref={nodo} style={{ height: alto }} />;
}

/* ═══════════════ KPI con explicación ═══════════════ */

function Kpi({ etiqueta, valor, sub, tono, ayuda }) {
  const [abierto, setAbierto] = useState(false);
  return (
    <div className={"kpi " + (tono || "")}
         onMouseLeave={() => setAbierto(false)}>
      <div className="et">
        {etiqueta}
        {ayuda && (
          <button className="ayuda" aria-label="Qué significa"
                  onMouseEnter={() => setAbierto(true)}
                  onClick={(e) => { e.stopPropagation(); setAbierto(!abierto); }}>?</button>
        )}
      </div>
      <div className="val mono">{valor}</div>
      {sub && <div className="sub">{sub}</div>}
      {abierto && ayuda && (
        <div className="globo">
          <b>{ayuda.que}</b>
          {ayuda.como}
          {ayuda.umbral && <div className="umbral">{ayuda.umbral}</div>}
        </div>
      )}
    </div>
  );
}

/* Explicaciones. Qué mide · cómo se lee · desde qué valor mirar con atención. */
const AYUDA = {
  valor: { que: "Valor de la cartera",
    como: "Cuánto valen hoy todas tus posiciones, en dólares, usando el precio de cierre más reciente de cada activo." },
  pnl: { que: "Ganancia o pérdida no realizada",
    como: "La diferencia entre lo que valen hoy y lo que te costaron, comisiones incluidas. Cada compra se convirtió a dólares con el MEP del día en que la hiciste, no con el de hoy.",
    umbral: "Es lo que ganarías o perderías si vendieras todo ahora." },
  sharpe: { que: "Sharpe",
    como: "Cuánto retorno conseguís por cada unidad de riesgo que asumís. Compara tu ganancia contra la de una letra del Tesoro, que no tiene riesgo.",
    umbral: "Por debajo de 0,5 el riesgo no se está pagando. Arriba de 1 es bueno; arriba de 2, excelente y poco frecuente." },
  sortino: { que: "Sortino",
    como: "Como el Sharpe, pero solo castiga la volatilidad hacia abajo. Que la cartera suba mucho un día no es un problema, y el Sharpe lo trata como si lo fuera.",
    umbral: "Suele ser mayor que el Sharpe. Si son parecidos, las caídas pesan tanto como las subas." },
  vol: { que: "Volatilidad anual",
    como: "Cuánto oscila la cartera. Es la banda dentro de la cual se mueve en un año normal.",
    umbral: "Hasta 15 % es conservadora, 15-25 % moderada, más de 25 % agresiva." },
  var95: { que: "Pérdida en un día malo",
    como: "De cada veinte ruedas, una es al menos así de mala. No es el peor caso: es el umbral a partir del cual empieza el 5 % peor.",
    umbral: "Mirá también la pérdida en un día muy malo, que es cuánto se pierde cuando ese día llega." },
  cvar: { que: "Pérdida en un día muy malo",
    como: "El promedio de lo que se pierde en ese 5 % de días peores. Responde qué tan grave es cuando efectivamente sale mal." },
  maxdd: { que: "Peor caída",
    como: "La caída más grande desde un máximo hasta el piso siguiente, en toda la historia de la cartera. Es lo que había que aguantar sin vender." },
  calmar: { que: "Calmar",
    como: "Cuánto rinde la cartera por cada punto de su peor caída. Junta rendimiento y sufrimiento en un solo número.",
    umbral: "Por encima de 1 el retorno anual supera a la peor caída histórica." },
  curtosis: { que: "Curtosis en exceso",
    como: "Cuán frecuentes son los movimientos extremos comparado con una campana normal. Está medida en exceso: una distribución normal da 0.",
    umbral: "Arriba de 3 hay colas gordas: los días muy malos pasan más seguido de lo que supone cualquier modelo normal." },
  concentracion: { que: "Activos efectivos",
    como: "Cuántos activos realmente diversifican. Se calcula como 1 dividido la suma de los pesos al cuadrado.",
    umbral: "Si tenés nueve posiciones pero este número da 2, la cartera se comporta casi como si tuviera dos." },
  beta: { que: "Beta",
    como: "Cuánto amplifica la cartera los movimientos del índice. Con beta 1,2, si el índice sube 10 % la cartera tiende a subir 12 %.",
    umbral: "Solo significa algo si el R² es alto: si el índice no explica la cartera, el beta es ruido." },
  alpha: { que: "Alpha",
    como: "El rendimiento que la cartera consiguió por encima de lo que le correspondía por el riesgo de mercado que asumió." },
  r2: { que: "R²",
    como: "Cuánto de lo que hace la cartera explica ese índice. Va de 0 a 1.",
    umbral: "Debajo de 0,2 el índice no es un comparable válido y beta y alpha no se sostienen." },
  tir: { que: "TIR",
    como: "El rendimiento anual que obtenés si comprás el bono a este precio y lo mantenés hasta el vencimiento, cobrando todos sus pagos." },
  duracion: { que: "Duración modificada",
    como: "Cuánto cae el precio del bono si la tasa sube un punto porcentual. Duración 3 significa que sube la tasa 1 % y el precio cae cerca de 3 %." },
  dv01: { que: "DV01",
    como: "Cuántos dólares pierde la cartera si toda la curva de tasas sube un punto básico, o sea una centésima de punto porcentual." },
};

/* ═══════════════ Barra superior ═══════════════ */

function Barra({ modo, setModo, tema, setTema, carteras, cartera, setCartera }) {
  const iconos = { auto: "◐", light: "☀", dark: "☾" };
  const siguiente = { auto: "light", light: "dark", dark: "auto" };
  return (
    <div className="barra">
      <div className="marca">Portfolio <span>Analyzer</span></div>
      <div className="modos">
        {[["analisis", "Análisis"], ["comparacion", "Comparación"],
          ["carteras", "Carteras"], ["mercado", "Mercado"],
          ["conectores", "Conectores"]].map(([k, t]) => (
          <button key={k} className={"modo" + (modo === k ? " on" : "")}
                  onClick={() => setModo(k)}>{t}</button>
        ))}
      </div>
      {(modo === "analisis") && (
        <select value={cartera || ""} onChange={(e) => setCartera(e.target.value)}>
          <option value="">— elegí una cartera —</option>
          {carteras.map((c) => <option key={c.nombre} value={c.nombre}>{c.nombre}</option>)}
        </select>
      )}
      <div className="der">
        <button className="btn tema" title={`Tema: ${tema}`}
                onClick={() => setTema(siguiente[tema])}>{iconos[tema]}</button>
      </div>
    </div>
  );
}

/* ═══════════════ Modo 1 · Análisis ═══════════════ */

// Stress y Momentum viven DENTRO de Riesgo, y Black-Litterman debajo de
// Objetivos: son lecturas de lo mismo y separarlas obligaba a saltar de pestaña
// para responder una sola pregunta.
// Posición es el resumen rápido de la cartera y absorbe todo lo que responde
// "qué tengo y cómo se comporta": KPIs de riesgo, tenencias, composición,
// correlaciones, distribución de retornos y momentum. Riesgo queda solo con lo
// que profundiza. Menos pestañas, y cada una con una pregunta entera adentro.
const PESTANAS = [
  ["posicion", "Posición"], ["riesgo", "Riesgo"],
  ["markowitz", "Markowitz"], ["montecarlo", "Monte Carlo"], ["capm", "Benchmark"],
  ["objetivos", "Objetivos"], ["regimenes", "Regímenes"],
];

const BENCHMARKS = [["SP500", "S&P 500"], ["MERVAL", "Merval"], ["STOXX600", "STOXX 600"]];

function Analisis({ cartera, recargar }) {
  const [run, setRun] = useState(null);
  const [estado, setEstado] = useState(null);
  const [tab, setTab] = useState("posicion");
  const [bench, setBench] = useState("SP500");

  useEffect(() => {
    if (!cartera) return;
    setEstado(null); setRun(null);
    api(`/api/analisis/${encodeURIComponent(cartera)}`,
        { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" })
      .then((d) => d.run_id && setRun(d.run_id));
  }, [cartera]);

  useEffect(() => {
    if (!run || !cartera) return;
    let vivo = true;
    const consultar = async () => {
      const d = await api(`/api/analisis/${encodeURIComponent(cartera)}/${run}`);
      if (!vivo) return;
      setEstado(d);
      if (d.estado !== "terminado") setTimeout(consultar, 1200);
    };
    consultar();
    return () => { vivo = false; };
  }, [run, cartera]);

  if (!cartera) return <div className="vacio">Elegí una cartera arriba para analizarla.</div>;
  if (!estado) return <div className="cargando">Lanzando los modelos…</div>;

  const R = estado.resultados || {};
  const M = estado.modelos || {};
  const listos = Object.values(M).filter((m) => m.estado === "listo").length;

  return (
    <>
      {estado.estado !== "terminado" && (
        <div className="aviso ojo">
          Calculando: <b>{listos} de {Object.keys(M).length}</b> modelos listos.
          Cada panel aparece apenas termina — no hace falta esperar a todos.
        </div>
      )}
      <div className="tabs">
        {PESTANAS.filter(([k]) => k in M).map(([k, t]) => (
          <button key={k} className={"tab" + (tab === k ? " on" : "")} onClick={() => setTab(k)}>
            {t}<span className={"pin " + (M[k]?.estado === "listo" ? "listo"
                 : M[k]?.estado === "error" ? "error" : "corriendo")} />
          </button>
        ))}
        <span style={{ marginLeft: "auto", display: "flex", alignItems: "center",
                       gap: 7, paddingBottom: 6 }}>
          <span style={{ fontSize: 12, color: "var(--texto-3)" }}>Comparar contra</span>
          <select value={bench} onChange={(e) => setBench(e.target.value)}>
            {BENCHMARKS.map(([k, t]) => <option key={k} value={k}>{t}</option>)}
          </select>
        </span>
      </div>
      <Panel tab={tab} R={R} M={M} cartera={cartera} bench={bench} recargar={recargar} />
    </>
  );
}

function Panel({ tab, R, M, cartera, bench, recargar }) {
  const d = R[tab];
  if (M[tab]?.estado === "corriendo" || M[tab]?.estado === "en cola")
    return <div className="cargando">Calculando {M[tab]?.nombre}…</div>;
  if (!d) return <div className="cargando">Sin datos.</div>;
  if (d.error) return <div className="aviso mal"><b>No se pudo calcular.</b> {d.error}</div>;

  const vistas = {
    posicion: <Posicion d={{ ...d, cartera_nombre: cartera }} cartera={cartera}
                        recargar={recargar} extras={{ composicion: R.composicion,
                        riesgo: R.riesgo, momentum: R.momentum }} />,
    riesgo: <Riesgo d={d} cartera={cartera} extras={{ stress: R.stress }} />,
    markowitz: <Markowitz d={d} cartera={cartera} bench={bench} />,
    montecarlo: <MonteCarlo d={d} cartera={cartera} />,
    capm: <Capm d={d} cartera={cartera} bench={bench} />,
    objetivos: <Objetivos d={d} bl={R.blacklitterman} />,
    regimenes: <Regimenes d={d} cartera={cartera} />,
  };
  return vistas[tab] || <div className="cargando">—</div>;
}

/* ── Posición ── */
function AltaRapida({ cartera, recargar }) {
  const vacio = { ticker: "", buy_date: new Date().toISOString().slice(0, 10),
                  buy_price: "", qty: "", commissions: "0", source: "" };
  const [f, setF] = useState(vacio);
  const [check, setCheck] = useState(null);
  const [msg, setMsg] = useState(null);
  const [abierto, setAbierto] = useState(false);

  const validar = async () => {
    const t = f.ticker.trim().toUpperCase();
    if (!t) return;
    setCheck({ cargando: true });
    setCheck(await api(`/api/validar/${encodeURIComponent(t)}`));
  };
  const agregar = async () => {
    const t = f.ticker.trim().toUpperCase();
    if (!t || !f.buy_price || !f.qty) { setMsg({ mal: "Faltan ticker, precio o cantidad." }); return; }
    const actuales = await api(`/api/carteras/${encodeURIComponent(cartera)}`);
    const nuevas = [...actuales, { ...f, ticker: t, buy_price: +f.buy_price,
                                   qty: +f.qty, commissions: +f.commissions || 0 }];
    const r = await api(`/api/carteras/${encodeURIComponent(cartera)}`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ posiciones: nuevas }) });
    if (r.error) { setMsg({ mal: r.error }); return; }
    setMsg({ ok: `${t} agregado. Recargá el análisis para verlo reflejado.` });
    setF(vacio); setCheck(null); recargar && recargar();
  };

  if (!abierto) return (
    <button className="btn" style={{ marginBottom: 14 }}
            onClick={() => setAbierto(true)}>+ Agregar una posición</button>);

  return (
    <div className="panel" style={{ marginBottom: 14 }}>
      <h3>Agregar una posición a {cartera}
        <button className="btn" style={{ marginLeft: "auto", padding: "3px 10px", fontSize: 12 }}
                onClick={() => setAbierto(false)}>Cerrar</button>
      </h3>
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "flex-end", marginTop: 10 }}>
        {[["ticker", "Ticker", "text", 120, "GGAL.BA"],
          ["buy_date", "Fecha de compra", "text", 120, "2025-09-19"],
          ["buy_price", "Precio pagado", "number", 110, ""],
          ["qty", "Cantidad", "number", 100, ""],
          ["commissions", "Comisiones", "number", 100, ""]].map(([k, et, tipo, w, ph]) => (
          <label key={k} style={{ fontSize: 11.5, color: "var(--texto-3)" }}>
            {et}<br />
            <input type={tipo} value={f[k]} placeholder={ph} style={{ width: w, marginTop: 3 }}
                   onChange={(e) => setF({ ...f, [k]: e.target.value })}
                   onBlur={k === "ticker" ? validar : undefined} />
          </label>))}
        <label style={{ fontSize: 11.5, color: "var(--texto-3)" }}>
          Origen<br />
          <select value={f.source} style={{ marginTop: 3 }}
                  onChange={(e) => setF({ ...f, source: e.target.value })}>
            <option value="">automático</option>
            <option value="cocos">cocos (bono / ON)</option>
          </select>
        </label>
        <button className="btn primario" onClick={agregar}>Agregar</button>
      </div>
      {check && !check.cargando && (
        <div className={"aviso " + (check.valido && check.alcanza_para_analisis ? "ok"
                                    : check.valido ? "ojo" : "mal")}>
          {check.valido
            ? <>Cotiza en <b>{check.moneda}</b>{check.subyacente !== check.ticker &&
                <> (subyacente <b>{check.subyacente}</b>)</>}, último <b>{usd(check.ultimo_usd, 4)}</b>,
               {" "}{check.ruedas} ruedas de historia. {check.detalle}</>
            : <>{check.detalle} Si es un bono u ON, elegí origen <b>cocos</b>.</>}
        </div>)}
      {msg && <div className={"aviso " + (msg.mal ? "mal" : "ok")}>{msg.mal || msg.ok}</div>}
      <div className="pie">
        El precio va en la moneda en que cotiza el activo. Se valida el ticker al salir del
        campo, para no descubrir que no hay historia cuando ya cargaste todo.
      </div>
    </div>
  );
}

function Posicion({ d, cartera, recargar, extras }) {
  const filas = d.posiciones || [];
  const [corr, setCorr] = useState(null);
  const r = extras?.riesgo;
  useEffect(() => { setCorr(null);
    api(`/api/correlaciones/${encodeURIComponent(cartera)}`).then(setCorr); }, [cartera]);

  return (
    <>
      {/* 1 · Cómo se comporta la cartera, antes que el detalle de qué tiene */}
      {r && !r.error && <KpisRiesgo d={r} />}

      {/* 2 · Qué tengo */}
      <div className="kpis">
        <Kpi etiqueta="Valor total" valor={usd(d.valor_total)} ayuda={AYUDA.valor}
             sub={d.mep_hoy ? `MEP $${d.mep_hoy}` : null} />
        <Kpi etiqueta="Costo" valor={usd(d.costo_total)} sub="comisiones incluidas" />
        <Kpi etiqueta="Resultado" valor={usd(d.pnl)} tono={signo(d.pnl)} ayuda={AYUDA.pnl}
             sub={pct(d.pnl_pct)} />
        <Kpi etiqueta="Posiciones" valor={filas.length} sub={`${new Set(filas.map(f=>f.ticker)).size} activos`} />
      </div>
      <AltaRapida cartera={cartera} recargar={recargar} />
      {d.sin_precio?.length > 0 && (
        <div className="aviso ojo">
          <b>{d.sin_precio.length} posiciones sin precio</b> y quedaron fuera del total:{" "}
          {d.sin_precio.join(", ")}. Los bonos y ONs necesitan Cocos conectado.
        </div>
      )}
      <div className="panel">
        <h3>Tenencias
          <a className="btn" style={{ marginLeft: "auto", textDecoration: "none", fontSize: 12.5 }}
             href={`/api/reporte/${encodeURIComponent(d.cartera_nombre || "")}`}>Descargar PDF</a>
        </h3>
        <div className="tabla-wrap"><table>
          <thead><tr>
            <th>Ticker</th><th>Compra</th><th className="n">Cantidad</th>
            <th className="n">Precio compra</th><th className="n">Precio hoy</th>
            <th className="n">Valor</th><th className="n">Resultado</th><th className="n">%</th>
          </tr></thead>
          <tbody>{filas.map((f, i) => (
            <tr key={i}>
              <td className="mono">{f.ticker}{f.es_bono && <span className="chip" style={{marginLeft:6}}>bono</span>}</td>
              <td className="mono">{f.buy_date}</td>
              <td className="n">{num(f.qty, 0)}</td>
              <td className="n">{usd(f.buy_price_usd, 4)}</td>
              <td className="n">{f.precio_usd == null ? "—" : usd(f.precio_usd, 4)}</td>
              <td className="n">{usd(f.valor_usd)}</td>
              <td className={"n " + signo(f.pnl_usd)}>{usd(f.pnl_usd)}</td>
              <td className={"n " + signo(f.pnl_pct)}>{pct(f.pnl_pct, 1)}</td>
            </tr>))}
          </tbody>
        </table></div>
        <div className="pie">
          Cada lote se valuó con el precio de hoy, y su costo con el dólar MEP del día
          en que lo compraste. Convertir una compra vieja al dólar de hoy mediría el tipo
          de cambio, no el rendimiento del activo.
        </div>
      </div>

      {/* 3 · En qué está invertida */}
      <Seccion titulo="En qué está invertida" />
      {extras?.composicion
        ? (extras.composicion.error
            ? <div className="aviso mal">{extras.composicion.error}</div>
            : <Composicion d={extras.composicion} />)
        : <div className="cargando">Clasificando los activos…</div>}

      {/* 4 · Se mueven juntos o no */}
      <Seccion titulo="¿Se mueven juntos?" />
      {corr ? (corr.error ? <div className="aviso mal">{corr.error}</div>
                          : <MatrizCorrelaciones corr={corr} />)
            : <div className="cargando">Calculando correlaciones…</div>}

      {/* 5 · Cómo son los días */}
      <Seccion titulo="Cómo son los días de esta cartera" />
      {r && !r.error ? <Distribucion d={r} /> : <div className="cargando">Calculando…</div>}

      {/* 6 · Es momento de entrar o esperar */}
      <Seccion titulo="¿Viento a favor o en contra?" />
      {extras?.momentum
        ? (extras.momentum.error
            ? <div className="aviso mal">{extras.momentum.error}</div>
            : <Momentum d={extras.momentum} />)
        : <div className="cargando">Midiendo el momentum…</div>}
    </>
  );
}

function Seccion({ titulo }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12, margin: "26px 0 12px" }}>
      <h3 style={{ margin: 0, fontSize: 16.5, whiteSpace: "nowrap" }}>{titulo}</h3>
      <div style={{ flex: 1, height: 1, background: "var(--borde)" }} />
    </div>
  );
}

/* Distribución de retornos diarios, con las dos curvas teóricas y las barras
   pintadas por zona. Reemplaza a la versión que se armaba en el cliente: los
   ajustes salen del backend, que es donde está scipy. */
function Distribucion({ d }) {
  const c = colores();
  const dist = d.distribucion;
  if (!dist || !dist.x) return <div className="aviso ojo">Sin datos suficientes para la distribución.</div>;

  const colorZona = { grave: c.negativo, mala: c.alerta,
                      extrema: c.series[1], normal: c.series[2] };
  const ganaT = dist.mejor_ajuste === "t-student";
  const peor = dist.extremos?.find((e) => e.sigmas === 4) || dist.extremos?.[dist.extremos.length - 1];

  const linea = (x, color, ancho = 1.6) => ({
    type: "line", x0: x, x1: x, yref: "paper", y0: 0, y1: 0.93,
    line: { color, width: ancho, dash: "dash" } });

  return (
    <>
      <div className="panel">
        <h3>Distribución de los retornos diarios
          <span className={"chip " + (ganaT ? "ojo" : "ok")} style={{ marginLeft: 8 }}>
            se ajusta mejor a {dist.mejor_ajuste}</span>
        </h3>
        <Grafico alto={400}
          datos={[
            { type: "bar", x: dist.x, y: dist.y, name: "días que pasaron",
              marker: { color: dist.zonas.map((z) => colorZona[z]), opacity: 0.85 },
              hovertemplate: "%{x:.2f} %: %{y} días<extra></extra>" },
            { type: "scatter", mode: "lines", x: dist.x, y: dist.normal,
              name: "si fuera una campana normal",
              line: { color: c.texto3, width: 2, dash: "dot" } },
            ...(dist.grados_libertad ? [{ type: "scatter", mode: "lines", x: dist.x,
              y: dist.tstudent, name: `t de Student (ν = ${dist.grados_libertad})`,
              line: { color: c.acento, width: 2.4 } }] : []),
          ]}
          layout={{
            bargap: 0.02,
            xaxis: { title: "Retorno de un día", ticksuffix: " %" },
            yaxis: { title: "Cantidad de días" },
            shapes: [linea(d.var95_pct, c.alerta), linea(d.var99_pct, c.negativo),
                     linea(dist.media_pct, c.texto3, 1)],
            annotations: [
              { x: d.var95_pct, y: 1, yref: "paper", text: "día malo", showarrow: false,
                font: { size: 10, color: c.alerta }, yanchor: "bottom" },
              { x: d.var99_pct, y: 1, yref: "paper", text: "1 de cada 100", showarrow: false,
                font: { size: 10, color: c.negativo }, yanchor: "bottom" },
              { x: dist.media_pct, y: 1, yref: "paper", text: "día promedio", showarrow: false,
                font: { size: 10, color: c.texto3 }, yanchor: "bottom" }] }} />
        <div className="pie">
          Cada barra es la cantidad de ruedas que terminaron con ese retorno, sobre{" "}
          {dist.n_dias} días. En <span style={{ color: c.negativo }}>rojo</span> las pérdidas
          graves, en <span style={{ color: c.alerta }}>ámbar</span> los días malos, en{" "}
          <span style={{ color: c.series[1] }}>dorado</span> lo que se aparta más de dos
          desvíos, y en <span style={{ color: c.series[2] }}>azul</span> el comportamiento
          habitual. Día promedio {pct(dist.media_pct, 3)}, desvío {pct(dist.sigma_pct)}.
        </div>
      </div>

      <div className="fila f2">
        <div className="panel">
          <h3>Los días extremos pasan más seguido de lo que un modelo normal supone</h3>
          <div className="tabla-wrap"><table>
            <thead><tr><th>Días peores que</th><th className="n">Umbral</th>
              <th className="n">Pasaron</th><th className="n">Si fuera normal</th>
              <th className="n">Exceso</th></tr></thead>
            <tbody>{(dist.extremos || []).map((e) => (
              <tr key={e.sigmas}>
                <td>−{e.sigmas} desvíos</td>
                <td className="n neg">{pct(e.umbral_pct)}</td>
                <td className="n">{e.observados}</td>
                <td className="n">{e.si_fuera_normal}</td>
                <td className={"n " + (e.veces > 1.5 ? "neg" : "")}>
                  {e.veces == null ? "—" : `${e.veces}×`}</td>
              </tr>))}</tbody>
          </table></div>
          <div className="pie">
            A dos desvíos la campana acierta. Es <b>más allá</b> donde se rompe:
            {peor && peor.veces > 1 && <> los días peores que −{peor.sigmas} desvíos pasaron{" "}
              <b>{peor.veces} veces más seguido</b> de lo que predice.</>}{" "}
            Por eso el VaR calculado con la campana subestima el escenario grave, y por eso
            se muestra también el de Cornish-Fisher.
          </div>
        </div>

        <div className="panel">
          <h3>La forma de la distribución</h3>
          <div className="kpis" style={{ gridTemplateColumns: "1fr 1fr" }}>
            <Kpi etiqueta="Asimetría" valor={num(d.asimetria, 3)}
                 tono={d.asimetria < -0.3 ? "neg" : d.asimetria > 0.3 ? "pos" : ""}
                 ayuda={{ que: "Asimetría",
                          como: "Hacia qué lado se estira la distribución. Negativa: las caídas grandes son más frecuentes que las subas grandes.",
                          umbral: "Cerca de 0 es simétrica. Por debajo de −0,5 hay sesgo claro a pérdidas." }} />
            <Kpi etiqueta="Curtosis" valor={num(d.curtosis_exceso, 2)} sub="en exceso"
                 tono={d.curtosis_exceso > 3 ? "neg" : ""} ayuda={AYUDA.curtosis} />
          </div>
          <div className={"aviso " + (d.asimetria < -0.3 ? "ojo" : "")}>
            {d.asimetria < -0.3
              ? "La cola izquierda es más larga: cuando esta cartera se mueve fuerte, tiende a ser para abajo."
              : d.asimetria > 0.3
              ? "La cola derecha es más larga: los movimientos fuertes tienden a ser al alza."
              : "La distribución es bastante simétrica: subidas y bajadas grandes son igual de frecuentes."}
          </div>
          <div className={"aviso " + (d.curtosis_exceso > 3 ? "mal" : "ok")}>
            {d.curtosis_exceso > 3
              ? `Curtosis en exceso de ${num(d.curtosis_exceso, 1)}: hay colas gordas. Los días
                 excepcionales —buenos y malos— pasan mucho más seguido de lo que supone
                 cualquier modelo basado en la campana normal.`
              : "Curtosis moderada: los movimientos extremos no son más frecuentes de lo esperable."}
          </div>
          {ganaT && (
            <div className="pie">
              El test de Kolmogórov-Smirnov elige la <b>t de Student con {dist.grados_libertad} grados
              de libertad</b> por sobre la normal. Menos grados de libertad = colas más gordas;
              por debajo de 5 la diferencia con la campana ya es grande.
            </div>)}
        </div>
      </div>
    </>
  );
}

/* ── Composición ── */
function Composicion({ d }) {
  const c = colores();
  const dona = (items, titulo) => ({
    datos: [{ type: "pie", hole: 0.5, labels: items.map((x) => x.etiqueta),
              values: items.map((x) => x.pct), textinfo: "label+percent",
              textposition: "outside", automargin: true, textfont: { size: 10 },
              marker: { colors: c.series },
              hovertemplate: "%{label}: %{value:.1f} %<extra></extra>" }],
    layout: { showlegend: false, margin: { t: 8, r: 8, b: 8, l: 8 } }, titulo,
  });
  const cortes = [["por_tipo", "Por tipo de activo"], ["por_sector", "Por sector"],
                  ["por_industria", "Por industria"]];
  return (
    <>
      <div className="fila f3">
        {cortes.map(([k, t]) => {
          const g = dona(d[k] || [], t);
          return (
            <div className="panel" key={k}>
              <h3>{t}</h3>
              <Grafico datos={g.datos} layout={g.layout} alto={300} />
            </div>
          );
        })}
      </div>
      <div className="panel">
        <h3>Detalle por activo</h3>
        <div className="tabla-wrap"><table>
          <thead><tr><th>Ticker</th><th>Nombre</th><th>Tipo</th><th>Sector</th>
                     <th>Industria</th><th className="n">Valor</th></tr></thead>
          <tbody>{(d.detalle || []).map((x) => (
            <tr key={x.ticker}>
              <td className="mono">{x.ticker}</td><td>{x.nombre || "—"}</td>
              <td>{x.tipo}</td><td>{x.sector}</td><td>{x.industria}</td>
              <td className="n">{usd(x.valor_usd)}</td>
            </tr>))}</tbody>
        </table></div>
        <div className="pie">
          Un ETF no tiene sector: es una canasta, no una empresa. En esos casos se muestra
          la categoría del fondo, que es el dato equivalente.
        </div>
      </div>
    </>
  );
}

/* ── Riesgo ── */
// Correlaciones, distribución y momentum se mudaron a Posición: son parte del
// retrato de la cartera, no de la profundización del riesgo.
const SUB_RIESGO = [["resumen","Resumen"],["activos","Por activo"],
                    ["evolucion","Evolución del riesgo"],["cambiario","Tipo de cambio"],
                    ["stress","Stress"],["limite","Poner un límite"]];

function Riesgo({ d, cartera, extras }) {
  const [sub, setSub] = useState("resumen");
  return (
    <>
      <KpisRiesgo d={d} />
      <div className="tabs" style={{ marginTop: 4 }}>
        {SUB_RIESGO.map(([k, t]) => (
          <button key={k} className={"tab" + (sub === k ? " on" : "")}
                  onClick={() => setSub(k)}>{t}</button>))}
      </div>
      {sub === "resumen" && <RiesgoResumen d={d} />}
      {sub === "activos" && <RiesgoActivos cartera={cartera} />}
      {sub === "evolucion" && <RiesgoEvolucion cartera={cartera} />}
      {sub === "cambiario" && <RiesgoCambiario cartera={cartera} />}
      {sub === "stress" && (extras.stress ? <Stress d={extras.stress} /> : <div className="cargando">Calculando…</div>)}
      {sub === "limite" && <RiesgoLimite cartera={cartera} d={d} />}
    </>
  );
}

function KpisRiesgo({ d }) {
  return (
    <div className="kpis">
      <Kpi etiqueta="Sharpe" valor={num(d.sharpe, 3)} ayuda={AYUDA.sharpe}
           tono={d.sharpe > 1 ? "pos" : d.sharpe < 0.5 ? "neg" : ""} sub={d.rf_label} />
      <Kpi etiqueta="Sortino" valor={num(d.sortino, 3)} ayuda={AYUDA.sortino} />
      <Kpi etiqueta="Calmar" valor={num(d.calmar, 3)} ayuda={AYUDA.calmar} />
      <Kpi etiqueta="Volatilidad" valor={pct(d.volatilidad_anual_pct)} ayuda={AYUDA.vol} />
      <Kpi etiqueta="Día malo" valor={usd(d.var95_usd)} tono="neg" ayuda={AYUDA.var95}
           sub={pct(d.var95_pct) + " · 1 de cada 20"} />
      <Kpi etiqueta="Día muy malo" valor={usd(d.cvar95_usd)} tono="neg" ayuda={AYUDA.cvar}
           sub={pct(d.cvar95_pct)} />
      <Kpi etiqueta="Peor caída" valor={pct(d.max_drawdown_pct)} tono="neg" ayuda={AYUDA.maxdd} />
      <Kpi etiqueta="Curtosis" valor={num(d.curtosis_exceso)} ayuda={AYUDA.curtosis}
           tono={d.curtosis_exceso > 3 ? "neg" : ""} sub="en exceso" />
    </div>
  );
}

function RiesgoResumen({ d }) {
  const c = colores();
  const contrib = d.contribucion_riesgo || [];
  const desbalance = contrib.filter((x) => x.ratio && x.ratio > 1.5);

  return (
    <>
      <div className="fila f2">
        <div className="panel">
          <h3>Quién trae el riesgo</h3>
          <Grafico alto={Math.max(220, contrib.length * 46)}
            datos={[
              { type: "bar", orientation: "h", name: "aporte al riesgo",
                y: contrib.map((x) => x.ticker).reverse(),
                x: contrib.map((x) => x.riesgo_pct).reverse(), marker: { color: c.negativo },
                hovertemplate: "%{y}: %{x:.1f} % del riesgo<extra></extra>" },
              { type: "bar", orientation: "h", name: "peso en la cartera",
                y: contrib.map((x) => x.ticker).reverse(),
                x: contrib.map((x) => x.peso_pct).reverse(), marker: { color: c.series[2] },
                hovertemplate: "%{y}: %{x:.1f} % de peso<extra></extra>" }]}
            layout={{ barmode: "group", margin: { l: 82 }, xaxis: { ticksuffix: " %" } }} />
          <div className="pie">
            Las contribuciones suman exactamente la volatilidad de la cartera (identidad
            de Euler). Barra roja mayor que la azul = aporta más riesgo del que su peso sugiere.
          </div>
        </div>
        <div className="panel">
          <h3>Cuánto esconde suponer normalidad</h3>
          <div className="tabla-wrap"><table>
            <thead><tr><th>Método</th><th className="n">Un día malo</th><th className="n">En dólares</th></tr></thead>
            <tbody>
              <tr><td>Histórico (95 %)</td><td className="n">{pct(d.var95_pct)}</td><td className="n neg">{usd(d.var95_usd)}</td></tr>
              <tr><td>Cornish-Fisher (95 %)</td><td className="n">{pct(d.var95_cornish_fisher_pct)}</td><td className="n neg">{usd(d.var95_cornish_fisher_usd)}</td></tr>
              <tr><td>Histórico (99 %)</td><td className="n">{pct(d.var99_pct)}</td><td className="n neg">{usd(d.var99_usd)}</td></tr>
            </tbody>
          </table></div>
          <div className="pie">
            Cornish-Fisher ajusta el cuantil por la asimetría y las colas gordas reales.
            La diferencia con el histórico es cuánto riesgo queda oculto.
          </div>
        </div>
      </div>

      {desbalance.length > 0 && (
        <div className="aviso ojo"><b>Riesgo concentrado.</b>{" "}
          {desbalance.map((x) => `${x.ticker} pesa ${x.peso_pct} % y aporta ${x.riesgo_pct} % del riesgo`).join(" · ")}.
        </div>
      )}
    </>
  );
}

function MatrizCorrelaciones({ corr }) {
  const c = colores();
  const [enCaidas, setEnCaidas] = useState(false);
  const m = enCaidas && corr.matriz_caidas ? corr.matriz_caidas : corr.matriz;
  const tono = { defensiva: "ok", mixta: "ojo", agresiva: "mal" }[corr.caracter];
  return (
    <div className="panel" style={{ marginTop: 14 }}>
      <h3>¿Defensiva o agresiva?
        <span className={"chip " + tono} style={{ marginLeft: 8 }}>{corr.caracter}</span>
        {corr.matriz_caidas && (
          <button className="btn" style={{ marginLeft: "auto", padding: "3px 10px", fontSize: 12 }}
                  onClick={() => setEnCaidas(!enCaidas)}>
            {enCaidas ? "Ver días normales" : "Ver solo días de caída"}</button>)}
      </h3>
      <div className="fila f2" style={{ marginTop: 10, marginBottom: 0 }}>
        <Grafico alto={Math.max(260, corr.tickers.length * 44)}
          datos={[{ type: "heatmap", z: m, x: corr.tickers, y: corr.tickers,
                    zmin: -1, zmax: 1, colorscale: [[0, c.negativo], [0.5, c.panel], [1, c.acento]],
                    text: m.map((f) => f.map((v) => v.toFixed(2))),
                    texttemplate: "%{text}", textfont: { size: 10 },
                    hovertemplate: "%{y} ↔ %{x}: %{z:.2f}<extra></extra>",
                    colorbar: { thickness: 10, len: 0.8 } }]}
          layout={{ margin: { l: 80, b: 70, t: 10, r: 10 } }} />
        <div>
          <div className="kpis" style={{ gridTemplateColumns: "1fr 1fr" }}>
            <Kpi etiqueta="Correlación media" valor={num(corr.correlacion_media, 3)}
                 ayuda={{ que: "Correlación media entre pares",
                          como: "Cuánto se mueven juntos tus activos, en promedio. Va de −1 a 1.",
                          umbral: "Debajo de 0,3 la cartera es defensiva; arriba de 0,6, agresiva: casi todo se mueve junto." }} />
            <Kpi etiqueta="En días de caída" valor={num(corr.correlacion_media_en_caidas, 3)}
                 tono={corr.aviso_caidas ? "neg" : ""} sub="el 10 % de días peores" />
          </div>
          <div className={"aviso " + tono}>{corr.lectura}</div>
          {corr.aviso_caidas && <div className="aviso mal">{corr.aviso_caidas}</div>}
          {corr.par_mas_correlacionado && (
            <div className="pie">
              El par que más se mueve junto: <b>{corr.par_mas_correlacionado.a} ↔ {corr.par_mas_correlacionado.b}</b> ({corr.par_mas_correlacionado.corr}).
              El que menos: <b>{corr.par_menos_correlacionado.a} ↔ {corr.par_menos_correlacionado.b}</b> ({corr.par_menos_correlacionado.corr}).
            </div>)}
        </div>
      </div>
    </div>
  );
}

function RiesgoActivos({ cartera }) {
  const c = colores();
  const [d, setD] = useState(null);
  const [sel, setSel] = useState("__todos__");
  useEffect(() => { setD(null); api(`/api/riesgo/${encodeURIComponent(cartera)}/por-activo`).then(setD); }, [cartera]);
  if (!d) return <div className="cargando">Midiendo el riesgo de cada activo…</div>;
  if (d.error) return <div className="aviso mal">{d.error}</div>;

  const todos = [...d.por_activo, d.cartera];
  const serie = sel === "__todos__" ? d.serie_cartera : (d.series[sel] || []);
  const foco = sel === "__todos__" ? d.cartera : d.por_activo.find((x) => x.ticker === sel);

  return (
    <>
      <div className="panel" style={{ marginBottom: 14 }}>
        <h3>Riesgo de cada activo por separado</h3>
        <div className="tabla-wrap"><table>
          <thead><tr><th>Activo</th><th className="n">Peso</th><th className="n">Retorno anual</th>
            <th className="n">Volatilidad</th><th className="n">Día malo</th><th className="n">Día muy malo</th>
            <th className="n">1 de 100</th><th className="n">Peor caída</th><th className="n">Sharpe</th></tr></thead>
          <tbody>{todos.map((f) => (
            <tr key={f.ticker} style={f.ticker === "CARTERA"
                  ? { borderTop: "2px solid var(--acento)", fontWeight: 600 } : null}>
              <td className="mono">{f.ticker}</td>
              <td className="n">{pct(f.peso_pct, 1)}</td>
              <td className={"n " + signo(f.retorno_anual_pct)}>{pct(f.retorno_anual_pct, 1)}</td>
              <td className="n">{pct(f.volatilidad_pct, 1)}</td>
              <td className="n neg">{pct(f.var95_pct)}</td>
              <td className="n neg">{pct(f.cvar95_pct)}</td>
              <td className="n neg">{pct(f.var99_pct)}</td>
              <td className="n neg">{pct(f.max_drawdown_pct, 1)}</td>
              <td className="n">{num(f.sharpe, 2)}</td>
            </tr>))}</tbody>
        </table></div>
        <div className="aviso ok">
          <b>Diversificar ahorra {pct(d.beneficio_diversificacion_pct, 1)} de volatilidad.</b>{" "}
          El activo más riesgoso cae hasta {pct(d.por_activo[0]?.max_drawdown_pct, 1)} por su cuenta,
          pero la cartera entera solo {pct(d.cartera.max_drawdown_pct, 1)}: eso es lo que aporta
          combinarlos. Ventana común: {d.ventana.desde} → {d.ventana.hasta}.
        </div>
      </div>

      <div className="panel">
        <h3>Cómo se comportan los días
          <select value={sel} onChange={(e) => setSel(e.target.value)} style={{ marginLeft: "auto" }}>
            <option value="__todos__">Cartera completa</option>
            {d.por_activo.map((x) => <option key={x.ticker} value={x.ticker}>{x.ticker}</option>)}
          </select>
        </h3>
        <Grafico alto={300}
          datos={[{ type: "bar", x: serie.map((p) => p.fecha), y: serie.map((p) => p.ret),
                    marker: { color: serie.map((p) => p.ret >= 0 ? c.positivo : c.negativo) },
                    hovertemplate: "%{x}: %{y:.2f} %<extra></extra>" }]}
          layout={{ yaxis: { title: "Retorno diario", ticksuffix: " %" },
                    shapes: foco ? [{ type: "line", xref: "paper", x0: 0, x1: 1,
                      y0: foco.var95_pct, y1: foco.var95_pct,
                      line: { color: c.alerta, width: 1.5, dash: "dash" } }] : [] }} />
        <div className="pie">
          Cada barra es una rueda, acotado a la ventana de la cartera. La línea punteada es
          el umbral del día malo ({pct(foco?.var95_pct)}): todo lo que la cruza es ese 5 % peor.
        </div>
      </div>
    </>
  );
}

function RiesgoEvolucion({ cartera }) {
  const c = colores();
  const [d, setD] = useState(null);
  useEffect(() => { setD(null); api(`/api/riesgo/${encodeURIComponent(cartera)}/rolling`).then(setD); }, [cartera]);
  if (!d) return <div className="cargando">Calculando la ventana móvil…</div>;
  if (d.error) return <div className="aviso mal">{d.error}</div>;

  const marcas = (d.eventos || []).map((e) => ({
    type: "line", x0: e.fecha, x1: e.fecha, yref: "paper", y0: 0, y1: 1,
    line: { color: e.alcance === "AR" ? c.series[3] : c.series[4], width: 1, dash: "dot" },
  }));
  return (
    <>
      <div className="panel">
        <h3>Cuándo se disparó el riesgo</h3>
        <Grafico alto={360}
          datos={[
            { type: "scatter", mode: "lines", name: "pérdida en un día malo",
              x: d.serie.map((p) => p.fecha), y: d.serie.map((p) => p.var95_pct),
              line: { color: c.negativo, width: 1.8 } },
            { type: "scatter", mode: "lines", name: "pérdida en un día muy malo",
              x: d.serie.map((p) => p.fecha), y: d.serie.map((p) => p.cvar95_pct),
              line: { color: c.alerta, width: 1.2, dash: "dot" } }]}
          layout={{ shapes: marcas, yaxis: { title: "Pérdida diaria", ticksuffix: " %" } }} />
        <div className="pie">
          VaR 95 % sobre las últimas {d.ventana_ruedas} ruedas en cada punto. Las líneas
          verticales son eventos macro: violeta los argentinos, lila los mundiales.
        </div>
      </div>
      <div className="panel">
        <h3>Eventos del período</h3>
        <div className="tabla-wrap"><table>
          <thead><tr><th>Fecha</th><th>Alcance</th><th>Qué pasó</th></tr></thead>
          <tbody>{(d.eventos || []).slice().reverse().map((e, i) => (
            <tr key={i}><td className="mono">{e.fecha}</td>
              <td><span className="chip">{e.alcance}</span></td><td>{e.descripcion}</td></tr>))}</tbody>
        </table></div>
        <div className="pie">{d.nota}</div>
      </div>
    </>
  );
}

function RiesgoCambiario({ cartera }) {
  const c = colores();
  const [d, setD] = useState(null);
  useEffect(() => { setD(null); api(`/api/riesgo/${encodeURIComponent(cartera)}/cambiario`).then(setD); }, [cartera]);
  if (!d) return <div className="cargando">Separando el riesgo del activo del riesgo del dólar…</div>;
  if (d.error) return <div className="aviso mal">{d.error}</div>;
  const enPesos = d.por_activo.filter((x) => x.moneda === "ARS");
  return (
    <>
      <div className="kpis">
        <Kpi etiqueta="Riesgo del tipo de cambio" valor={pct(d.fx_pct, 1)}
             tono={d.fx_pct > 50 ? "neg" : ""}
             ayuda={{ que: "Riesgo cambiario",
                      como: "De todo lo que hace oscilar tu cartera medida en dólares, cuánto viene del movimiento del MEP y no de los activos.",
                      umbral: "Arriba del 50 % estás apostando más al dólar que a las empresas." }} />
        <Kpi etiqueta="Riesgo de los activos" valor={pct(d.activo_pct, 1)} />
        <Kpi etiqueta="Expuesto al peso" valor={pct(d.pct_expuesto_al_peso, 1)}
             sub={`${usd(d.valor_en_pesos)} de ${usd(d.valor_en_pesos + d.valor_en_dolares)}`} />
      </div>
      {enPesos.length > 0 && (
        <div className="panel">
          <h3>De dónde viene el riesgo de cada activo en pesos</h3>
          <Grafico alto={Math.max(200, enPesos.length * 46)}
            datos={[
              { type: "bar", orientation: "h", name: "el activo",
                y: enPesos.map((x) => x.ticker).reverse(), x: enPesos.map((x) => x.activo_pct).reverse(),
                marker: { color: c.series[2] } },
              { type: "bar", orientation: "h", name: "el dólar",
                y: enPesos.map((x) => x.ticker).reverse(), x: enPesos.map((x) => x.fx_pct).reverse(),
                marker: { color: c.alerta } }]}
            layout={{ barmode: "stack", margin: { l: 82 }, xaxis: { ticksuffix: " %" } }} />
          <div className="pie">{d.nota}</div>
        </div>
      )}
      <div className="panel">
        <h3>Detalle</h3>
        <div className="tabla-wrap"><table>
          <thead><tr><th>Activo</th><th>Moneda</th><th className="n">Valor</th>
            <th className="n">Del activo</th><th className="n">Del dólar</th>
            <th className="n">Correlación con el MEP</th></tr></thead>
          <tbody>{d.por_activo.map((x) => (
            <tr key={x.ticker}><td className="mono">{x.ticker}</td><td>{x.moneda}</td>
              <td className="n">{usd(x.valor_usd)}</td><td className="n">{pct(x.activo_pct, 1)}</td>
              <td className="n">{pct(x.fx_pct, 1)}</td>
              <td className="n">{x.correlacion_con_mep == null ? "—" : num(x.correlacion_con_mep, 2)}</td>
            </tr>))}</tbody>
        </table></div>
      </div>
    </>
  );
}

function RiesgoLimite({ cartera, d }) {
  const [objetivo, setObjetivo] = useState(Math.abs(d.var95_pct * 0.7).toFixed(2));
  const [r, setR] = useState(null);
  const [cargando, setCargando] = useState(false);
  const calcular = async () => {
    setCargando(true);
    setR(await api(`/api/riesgo/${encodeURIComponent(cartera)}/ajustar?var=${objetivo}`));
    setCargando(false);
  };
  return (
    <>
      <div className="panel">
        <h3>¿Cuánto tendría que desarmar para no perder más de…?</h3>
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginTop: 10 }}>
          <span>No quiero perder más de</span>
          <input type="number" step="0.05" min="0.05" value={objetivo}
                 onChange={(e) => setObjetivo(e.target.value)} style={{ width: 90 }} />
          <span>% en un día malo.</span>
          <button className="btn primario" onClick={calcular} disabled={cargando}>
            {cargando ? "Calculando…" : "Calcular"}</button>
          <span className="pie" style={{ marginTop: 0 }}>
            Hoy: {pct(d.var95_pct)} ({usd(d.var95_usd)})</span>
        </div>
      </div>
      {r?.error && <div className="aviso mal">{r.error}</div>}
      {r && !r.error && r.ya_cumple && <div className="aviso ok">{r.mensaje}</div>}
      {r && !r.error && !r.ya_cumple && (
        <>
          <div className="kpis">
            <Kpi etiqueta="Mantener invertido" valor={pct(r.invertido_pct, 1)} />
            <Kpi etiqueta="Pasar a dólares" valor={pct(r.liquidez_pct, 1)} tono="neg"
                 sub={usd(r.a_liquidar_usd)} />
            <Kpi etiqueta="Día malo pasaría a ser" valor={usd(r.var_objetivo_usd)}
                 sub={`desde ${usd(r.var_actual_usd)}`} />
          </div>
          <div className="panel">
            <h3>Qué vender de cada posición</h3>
            <div className="tabla-wrap"><table>
              <thead><tr><th>Activo</th><th className="n">Peso hoy</th><th className="n">Peso nuevo</th>
                <th className="n">Vender</th><th className="n">Unidades</th></tr></thead>
              <tbody>{r.ajustes.map((a) => (
                <tr key={a.ticker}><td className="mono">{a.ticker}</td>
                  <td className="n">{pct(a.peso_actual_pct, 1)}</td>
                  <td className="n">{pct(a.peso_nuevo_pct, 1)}</td>
                  <td className="n neg">{usd(a.vender_usd)}</td>
                  <td className="n">{a.vender_unidades == null ? "—" : num(a.vender_unidades, 2)}</td>
                </tr>))}</tbody>
            </table></div>
            <div className="pie">{r.nota}</div>
          </div>
        </>
      )}
    </>
  );
}

/* ── Markowitz ── */
function Markowitz({ d, cartera, bench }) {
  const c = colores();
  const [bt, setBt] = useState(null);
  const [meses, setMeses] = useState(6);
  const [objetivo, setObjetivo] = useState("max_sharpe");
  const f = d.frontera || [];
  const nube = d.nube || {};
  const datos = [
    { type: "scattergl", mode: "markers", name: "carteras posibles",
      x: nube.vol, y: nube.ret, marker: { size: 3, color: c.texto3, opacity: 0.28 },
      hoverinfo: "skip" },
    { type: "scatter", mode: "lines", name: "frontera eficiente",
      x: f.map((p) => p.vol), y: f.map((p) => p.ret),
      line: { color: c.acento, width: 2.5 } },
    { type: "scatter", mode: "markers+text", name: "tu cartera",
      x: [d.actual.vol_pct], y: [d.actual.ret_pct], text: ["actual"], textposition: "top center",
      marker: { size: 15, color: c.series[2], symbol: "star", line: { width: 1, color: c.panel } } },
    { type: "scatter", mode: "markers+text", name: "máximo Sharpe",
      x: [d.max_sharpe.vol_pct], y: [d.max_sharpe.ret_pct], text: ["óptima"], textposition: "top center",
      marker: { size: 13, color: c.positivo, symbol: "triangle-up" } },
    { type: "scatter", mode: "markers+text", name: "mínima varianza",
      x: [d.min_varianza.vol_pct], y: [d.min_varianza.ret_pct], text: ["mín. riesgo"], textposition: "bottom center",
      marker: { size: 12, color: c.series[1], symbol: "diamond" } },
  ];
  return (
    <>
      <div className="kpis">
        <Kpi etiqueta="Tu Sharpe" valor={num(d.actual.sharpe, 3)} sub={`${pct(d.actual.ret_pct)} / ${pct(d.actual.vol_pct)}`} />
        <Kpi etiqueta="Sharpe óptimo" valor={num(d.max_sharpe.sharpe, 3)} tono="pos"
             sub={`${pct(d.max_sharpe.ret_pct)} / ${pct(d.max_sharpe.vol_pct)}`} />
        <Kpi etiqueta="Mínima varianza" valor={pct(d.min_varianza.vol_pct)}
             sub={`retorno ${pct(d.min_varianza.ret_pct)}`} />
        <Kpi etiqueta="Tasa libre" valor={pct(d.rf * 100)} sub={d.rf_label} />
      </div>
      <div className="fila f2">
        <div className="panel">
          <h3>Frontera eficiente</h3>
          <Grafico datos={datos} alto={380}
                   layout={{ xaxis: { title: "Volatilidad anual", ticksuffix: " %" },
                             yaxis: { title: "Retorno anual", ticksuffix: " %" } }} />
          <div className="pie">
            La nube gris son carteras posibles con tus mismos activos; la línea es lo
            mejor alcanzable para cada nivel de riesgo. Tu cartera nunca puede quedar
            por encima de la línea.
          </div>
        </div>
        <div className="panel">
          <h3>Cómo quedarían los pesos</h3>
          <Grafico alto={Math.max(230, d.tickers.length * 50)}
            datos={[
              { type: "bar", orientation: "h", name: "hoy",
                y: d.tickers.slice().reverse(), x: d.actual.pesos.slice().reverse(),
                marker: { color: c.texto3 } },
              { type: "bar", orientation: "h", name: "máximo Sharpe",
                y: d.tickers.slice().reverse(), x: d.max_sharpe.pesos.slice().reverse(),
                marker: { color: c.positivo } },
              { type: "bar", orientation: "h", name: "mínima varianza",
                y: d.tickers.slice().reverse(), x: d.min_varianza.pesos.slice().reverse(),
                marker: { color: c.series[1] } }]}
            layout={{ barmode: "group", margin: { l: 82 }, xaxis: { ticksuffix: " %" } }} />
          <div className="pie">
            Máximo Sharpe busca el mejor retorno por unidad de riesgo; mínima varianza,
            la cartera más tranquila sin mirar el retorno esperado —que es el dato peor
            estimado del modelo, y por eso suele ser la más robusta—.
          </div>
        </div>
      </div>

      <div className="fila f2">
        <div className="panel">
          <h3>Qué habría que operar
            <select value={objetivo} onChange={(e) => setObjetivo(e.target.value)}
                    style={{ marginLeft: "auto" }}>
              <option value="max_sharpe">para máximo Sharpe</option>
              <option value="min_varianza">para mínima varianza</option>
            </select>
          </h3>
          <div className="tabla-wrap"><table>
            <thead><tr><th>Ticker</th><th className="n">Hoy</th><th className="n">Objetivo</th>
                       <th className="n">Diferencia</th><th>Acción</th></tr></thead>
            <tbody>{((objetivo === "max_sharpe" ? d.acciones_max_sharpe
                                                : d.acciones_min_varianza) || []).map((a) => (
              <tr key={a.ticker}>
                <td className="mono">{a.ticker}</td>
                <td className="n">{pct(a.peso_actual_pct, 1)}</td>
                <td className="n">{pct(a.peso_objetivo_pct, 1)}</td>
                <td className={"n " + signo(a.delta_usd)}>{usd(a.delta_usd)}</td>
                <td><span className={"chip " + (a.accion === "COMPRAR" ? "ok" : a.accion === "VENDER" ? "mal" : "")}>{a.accion}</span></td>
              </tr>))}</tbody>
          </table></div>
          <div className="pie">
            Markowitz optimiza sobre retornos pasados: son el peor insumo del modelo.
            Leelo como una dirección, no como una instrucción — y mirá el backtest.
          </div>
        </div>

        <div className="panel">
          <h3>¿Habría funcionado?
            <span style={{ marginLeft: "auto", display: "flex", gap: 6, alignItems: "center" }}>
              <select value={meses} onChange={(e) => setMeses(+e.target.value)}>
                {[3, 6, 12].map((m) => <option key={m} value={m}>{m} meses</option>)}
              </select>
              <button className="btn" style={{ padding: "4px 11px", fontSize: 12.5 }}
                      onClick={async () => { setBt("cargando");
                        setBt(await api(`/api/markowitz/${encodeURIComponent(cartera)}/backtest?meses=${meses}&benchmark=${bench}`)); }}>
                Probar</button>
            </span>
          </h3>
          {bt === "cargando" ? <div className="cargando">Optimizando con datos viejos y midiendo después…</div>
           : !bt ? <div className="pie" style={{ marginTop: 10 }}>
               Optimiza con los datos ANTERIORES al período de prueba y mide qué pasó
               después. Es la única forma honesta de evaluar Markowitz: optimizar y medir
               sobre el mismo período siempre da un resultado espectacular que no significa nada.
             </div>
           : bt.error ? <div className="aviso mal">{bt.error}</div> : (
            <>
              <Grafico alto={230}
                datos={Object.entries(bt.curvas).map(([n, v], i) => ({
                  type: "scatter", mode: "lines", name: n, x: bt.fechas, y: v,
                  line: { width: n === bt.ganadora ? 2.6 : 1.4,
                          color: c.series[i % c.series.length] } }))}
                layout={{ yaxis: { title: "Base 100", tickprefix: "" }, margin: { t: 6 } }} />
              <div className="tabla-wrap"><table>
                <thead><tr><th>Estrategia</th><th className="n">Retorno</th>
                  <th className="n">Sharpe</th><th className="n">Peor caída</th></tr></thead>
                <tbody>{bt.resultados.map((r) => (
                  <tr key={r.estrategia} style={r.estrategia === bt.ganadora ? { fontWeight: 600 } : null}>
                    <td>{r.estrategia}{r.estrategia === bt.ganadora && " ★"}</td>
                    <td className={"n " + signo(r.retorno_pct)}>{pct(r.retorno_pct)}</td>
                    <td className="n">{num(r.sharpe, 3)}</td>
                    <td className="n neg">{pct(r.max_drawdown_pct)}</td>
                  </tr>))}</tbody>
              </table></div>
              <div className={"aviso " + (bt.ganadora === "Máximo Sharpe" ? "ok" : "ojo")}>
                {bt.veredicto}
              </div>
              <div className="pie">{bt.nota}</div>
            </>)}
        </div>
      </div>
    </>
  );
}

/* ── Monte Carlo ── */
const SUB_MC = [["abanico","Abanico"],["activos","Por activo"],
                ["correlaciones","Correlaciones en el tiempo"],["motores","Motores"]];

function MonteCarlo({ d, cartera }) {
  const [sub, setSub] = useState("abanico");
  const f = d.final || {};
  return (
    <>
      <div className="kpis">
        <Kpi etiqueta="Hoy" valor={usd(d.valor_inicial)} />
        <Kpi etiqueta="Mediana a un año" valor={usd(f.mediana)}
             tono={f.mediana > d.valor_inicial ? "pos" : "neg"} />
        <Kpi etiqueta="Escenario malo (5 %)" valor={usd(f.var95)} tono="neg"
             sub={`perdés ${pct(f.perdida_var95_pct, 1)}`} />
        <Kpi etiqueta="Escenario muy malo (1 %)" valor={usd(f.var99)} tono="neg"
             sub={`perdés ${pct(f.perdida_var99_pct, 1)}`} />
        <Kpi etiqueta="Probabilidad de ganar" valor={pct(f.prob_ganancia, 1)}
             tono={f.prob_ganancia > 50 ? "pos" : "neg"} />
      </div>
      <div className="tabs" style={{ marginTop: 4 }}>
        {SUB_MC.map(([k, t]) => (
          <button key={k} className={"tab" + (sub === k ? " on" : "")}
                  onClick={() => setSub(k)}>{t}</button>))}
      </div>
      {sub === "abanico" && <DistribucionFinal d={d} />}
      {sub === "activos" && <McPorActivo cartera={cartera} horizonte={d.horizonte_ruedas} />}
      {sub === "correlaciones" && <CorrelacionesAnimadas cartera={cartera} />}
      {sub === "motores" && <McMotores d={d} cartera={cartera} />}
    </>
  );
}

function McPorActivo({ cartera, horizonte }) {
  const c = colores();
  const [d, setD] = useState(null);
  useEffect(() => { setD(null);
    api(`/api/montecarlo/${encodeURIComponent(cartera)}/por-activo?horizonte=${horizonte}`).then(setD);
  }, [cartera, horizonte]);
  if (!d) return <div className="cargando">Simulando cada activo por separado…</div>;
  if (d.error) return <div className="aviso mal">{d.error}</div>;

  const todos = [...d.por_activo, d.cartera];
  return (
    <>
      <div className="panel">
        <h3>Rango de resultados de cada activo</h3>
        <Grafico alto={Math.max(260, todos.length * 52)}
          datos={[
            { type: "bar", orientation: "h", name: "escenario malo → mediana",
              y: todos.map((f) => f.ticker).reverse(),
              x: todos.map((f) => f.mediana - f.p5).reverse(),
              base: todos.map((f) => f.p5).reverse(),
              marker: { color: c.negativo, opacity: 0.55 },
              hovertemplate: "%{y}<extra></extra>" },
            { type: "bar", orientation: "h", name: "mediana → escenario bueno",
              y: todos.map((f) => f.ticker).reverse(),
              x: todos.map((f) => f.p95 - f.mediana).reverse(),
              base: todos.map((f) => f.mediana).reverse(),
              marker: { color: c.positivo, opacity: 0.55 },
              hovertemplate: "%{y}<extra></extra>" },
            { type: "scatter", mode: "markers", name: "hoy",
              y: todos.map((f) => f.ticker).reverse(),
              x: todos.map((f) => f.valor_inicial).reverse(),
              marker: { symbol: "line-ns-open", size: 16, color: c.texto,
                        line: { width: 2.5, color: c.texto } },
              hovertemplate: "%{y}: $%{x:,.0f} hoy<extra></extra>" }]}
          layout={{ barmode: "overlay", margin: { l: 82 },
                    xaxis: { title: "Valor a un año", tickprefix: "$" } }} />
        <div className="pie">
          Cada barra va del escenario malo (5 %) al bueno (95 %), con la marca vertical
          en lo que vale hoy. Cuanto más larga, más incierto es ese activo.
        </div>
      </div>

      <div className="panel">
        <h3>Detalle</h3>
        <div className="tabla-wrap"><table>
          <thead><tr><th>Activo</th><th className="n">Peso</th><th className="n">Hoy</th>
            <th className="n">Mediana</th><th className="n">Escenario malo</th>
            <th className="n">Pérdida</th><th className="n">P(ganar)</th>
            <th className="n">Incertidumbre</th></tr></thead>
          <tbody>{todos.map((f) => (
            <tr key={f.ticker} style={f.ticker === "CARTERA"
                  ? { borderTop: "2px solid var(--acento)", fontWeight: 600 } : null}>
              <td className="mono">{f.ticker}</td>
              <td className="n">{pct(f.peso_pct, 1)}</td>
              <td className="n">{usd(f.valor_inicial, 0)}</td>
              <td className="n">{usd(f.mediana, 0)}</td>
              <td className="n">{usd(f.p5, 0)}</td>
              <td className="n neg">{pct(f.perdida_var95_pct, 1)}</td>
              <td className="n">{pct(f.prob_ganancia, 1)}</td>
              <td className="n">{num(f.amplitud, 2)}×</td>
            </tr>))}</tbody>
        </table></div>
        <div className="aviso ok">
          <b>Diversificar vale {usd(d.ahorro_diversificacion_usd)} en el escenario malo.</b>{" "}
          {d.nota}
        </div>
        <div className="pie">
          "Incertidumbre" es el ancho del abanico como múltiplo del valor de hoy: cuántas
          veces su propio valor separa al buen escenario del malo.
        </div>
      </div>
    </>
  );
}

function CorrelacionesAnimadas({ cartera }) {
  const c = colores();
  const [d, setD] = useState(null);
  const [i, setI] = useState(0);
  const [corriendo, setCorriendo] = useState(false);

  useEffect(() => { setD(null); setI(0);
    api(`/api/montecarlo/${encodeURIComponent(cartera)}/correlaciones`).then(setD); }, [cartera]);

  useEffect(() => {
    if (!corriendo || !d?.cuadros) return;
    const id = setTimeout(() => setI((x) => (x + 1) % d.cuadros.length), 260);
    return () => clearTimeout(id);
  }, [corriendo, i, d]);

  if (!d) return <div className="cargando">Calculando cómo se movieron las correlaciones…</div>;
  if (d.error) return <div className="aviso mal">{d.error}</div>;

  const cuadro = d.cuadros[i];
  const cerca = (d.eventos || []).filter((e) =>
    Math.abs(new Date(e.fecha) - new Date(cuadro.fecha)) < 45 * 864e5);

  return (
    <>
      <div className="panel">
        <h3>Las correlaciones no son estables
          <span style={{ marginLeft: "auto", display: "flex", gap: 8, alignItems: "center" }}>
            <button className="btn" style={{ padding: "3px 11px", fontSize: 12.5 }}
                    onClick={() => setCorriendo(!corriendo)}>
              {corriendo ? "⏸ Detener" : "▶ Reproducir"}</button>
            <input type="range" min="0" max={d.cuadros.length - 1} value={i}
                   onChange={(e) => { setCorriendo(false); setI(+e.target.value); }}
                   style={{ width: 190 }} />
            <span className="mono" style={{ fontSize: 12.5 }}>{cuadro.fecha}</span>
          </span>
        </h3>
        <div className="fila f2" style={{ marginBottom: 0, marginTop: 8 }}>
          <Grafico alto={Math.max(280, d.tickers.length * 46)}
            datos={[{ type: "heatmap", z: cuadro.matriz, x: d.tickers, y: d.tickers,
                      zmin: -1, zmax: 1,
                      colorscale: [[0, c.negativo], [0.5, c.panel], [1, c.acento]],
                      text: cuadro.matriz.map((f) => f.map((v) => v.toFixed(2))),
                      texttemplate: "%{text}", textfont: { size: 10 },
                      hovertemplate: "%{y} ↔ %{x}: %{z:.2f}<extra></extra>",
                      colorbar: { thickness: 10, len: 0.8 } }]}
            layout={{ margin: { l: 80, b: 70, t: 6, r: 10 } }} />
          <div>
            <Grafico alto={200}
              datos={[{ type: "scatter", mode: "lines", name: "correlación media",
                        x: d.cuadros.map((q) => q.fecha), y: d.cuadros.map((q) => q.media),
                        line: { color: c.acento, width: 2 } }]}
              layout={{ margin: { t: 6, l: 44, b: 40 },
                        yaxis: { title: "Correlación media" },
                        shapes: [{ type: "line", x0: cuadro.fecha, x1: cuadro.fecha,
                                   yref: "paper", y0: 0, y1: 1,
                                   line: { color: c.alerta, width: 2 } },
                                 ...(d.eventos || []).map((e) => ({
                                   type: "line", x0: e.fecha, x1: e.fecha, yref: "paper",
                                   y0: 0, y1: 1, line: { color: c.texto3, width: 0.8, dash: "dot" } }))] }} />
            <div className="kpis" style={{ gridTemplateColumns: "1fr 1fr", marginTop: 8 }}>
              <Kpi etiqueta="Ahora" valor={num(cuadro.media, 3)}
                   tono={cuadro.media > d.media_global + 0.15 ? "neg"
                        : cuadro.media < d.media_global - 0.15 ? "pos" : ""} />
              <Kpi etiqueta="Promedio del período" valor={num(d.media_global, 3)} />
            </div>
            {cerca.length > 0 && (
              <div className="aviso ojo">
                Por estas fechas: {cerca.map((e) => e.descripcion).join(" · ")}.
              </div>)}
          </div>
        </div>
        <div className="pie">
          {d.nota} El máximo del período fue <b>{d.maximo.media}</b> el {d.maximo.fecha}; el
          mínimo, <b>{d.minimo.media}</b> el {d.minimo.fecha}. Una matriz de correlaciones
          promedio esconde este movimiento, y es el que decide si la diversificación va a
          estar ahí cuando haga falta.
        </div>
      </div>
    </>
  );
}

function McMotores({ d, cartera }) {
  const c = colores();
  const [motores, setMotores] = useState(null);
  const a = d.abanico || {};
  const banda = (lo, hi, color, nombre) => ([
    { type: "scatter", x: a.dias, y: hi, mode: "lines", line: { width: 0 },
      showlegend: false, hoverinfo: "skip" },
    { type: "scatter", x: a.dias, y: lo, mode: "lines", line: { width: 0 },
      fill: "tonexty", fillcolor: color, name: nombre, hoverinfo: "skip" },
  ]);
  const datos = [
    ...banda(a.p5, a.p95, c.acento + "22", "casi seguro · 9 de cada 10 casos"),
    ...banda(a.p25, a.p75, c.acento + "44", "lo más típico · la mitad de los casos"),
    { type: "scatter", x: a.dias, y: a.p50, mode: "lines", name: "mediana",
      line: { color: c.acento, width: 2.5 } },
  ];
  const layout = {
    xaxis: { title: "Ruedas hacia adelante" }, yaxis: { title: "Valor en dólares" },
    shapes: [{ type: "line", x0: a.dias?.[0], x1: a.dias?.[a.dias.length - 1],
               y0: d.valor_inicial, y1: d.valor_inicial,
               line: { color: c.texto3, width: 2, dash: "dot" } }],
  };
  const f = d.final || {};
  return (
    <>
      <div className="kpis">
        <Kpi etiqueta="Hoy" valor={usd(d.valor_inicial)} />
        <Kpi etiqueta="Mediana a un año" valor={usd(f.mediana)}
             tono={f.mediana > d.valor_inicial ? "pos" : "neg"} />
        <Kpi etiqueta="Escenario malo (5 %)" valor={usd(f.var95)} tono="neg"
             sub={`perdés ${pct(f.perdida_var95_pct, 1)}`} />
        <Kpi etiqueta="Escenario muy malo (1 %)" valor={usd(f.var99)} tono="neg"
             sub={`perdés ${pct(f.perdida_var99_pct, 1)}`} />
        <Kpi etiqueta="Probabilidad de ganar" valor={pct(f.prob_ganancia, 1)}
             tono={f.prob_ganancia > 50 ? "pos" : "neg"} />
      </div>
      <div className="panel">
        <h3>Futuros posibles · {d.n_simulaciones.toLocaleString("es-AR")} simulaciones</h3>
        <Grafico datos={datos} layout={layout} alto={380} />
        <div className="pie">
          La línea punteada es lo que vale hoy. La banda oscura contiene la mitad de los
          escenarios; la clara, nueve de cada diez. Motor: <b>{d.motor}</b>.
        </div>
      </div>
      <div className="panel">
        <h3>¿Cambia según el supuesto de distribución?</h3>
        {!motores ? (
          <button className="btn" onClick={async () =>
            setMotores(await api(`/api/montecarlo/${encodeURIComponent(cartera)}/motores?horizonte=${d.horizonte_ruedas}`))}>
            Comparar los tres motores
          </button>
        ) : (
          <>
            <div className="tabla-wrap"><table>
              <thead><tr><th>Motor</th><th className="n">Escenario malo</th>
                         <th className="n">Pérdida</th><th className="n">Muy malo</th>
                         <th className="n">Pérdida</th></tr></thead>
              <tbody>{Object.entries(motores).map(([k, v]) => (
                <tr key={k}><td>{k}</td>
                  <td className="n">{usd(v.var95)}</td><td className="n neg">{pct(v.perdida_var95_pct, 1)}</td>
                  <td className="n">{usd(v.var99)}</td><td className="n neg">{pct(v.perdida_var99_pct, 1)}</td>
                </tr>))}</tbody>
            </table></div>
            <div className="pie">
              Las colas gordas pesan en el riesgo de un día —ahí está el VaR de
              Cornish-Fisher, en la pestaña de Riesgo— pero se diluyen al componer
              muchos días: por eso los tres motores dan parecido a este horizonte.
            </div>
          </>
        )}
      </div>
    </>
  );
}

function DistribucionFinal({ d }) {
  const c = colores();
  const [paso, setPaso] = useState(null);          // null = animación apagada
  const dist = d.distribucion || {};
  const a = d.abanico || {};

  // Animación en bucle sobre el abanico: muestra cómo se va abriendo el rango de
  // resultados rueda a rueda. Se puede parar — una animación que no se detiene
  // molesta más de lo que explica.
  useEffect(() => {
    if (paso === null) return;
    const id = setTimeout(() => setPaso((p) => (p + 1) % (a.dias?.length || 1)), 90);
    return () => clearTimeout(id);
  }, [paso, a.dias]);

  const hasta = paso === null ? (a.dias?.length || 0) : paso + 1;
  const corte = (arr) => (arr || []).slice(0, hasta);

  return (
    <>
      <div className="panel">
        <h3>Cómo se abre el abanico
          <button className="btn" style={{ marginLeft: "auto", padding: "3px 11px", fontSize: 12.5 }}
                  onClick={() => setPaso(paso === null ? 0 : null)}>
            {paso === null ? "▶ Reproducir" : "⏸ Detener"}</button>
        </h3>
        <Grafico alto={320}
          datos={[
            { type: "scatter", x: corte(a.dias), y: corte(a.p95), mode: "lines",
              line: { width: 0 }, showlegend: false, hoverinfo: "skip" },
            { type: "scatter", x: corte(a.dias), y: corte(a.p5), mode: "lines", line: { width: 0 },
              fill: "tonexty", fillcolor: c.acento + "22", name: "9 de cada 10 casos" },
            { type: "scatter", x: corte(a.dias), y: corte(a.p75), mode: "lines",
              line: { width: 0 }, showlegend: false, hoverinfo: "skip" },
            { type: "scatter", x: corte(a.dias), y: corte(a.p25), mode: "lines", line: { width: 0 },
              fill: "tonexty", fillcolor: c.acento + "44", name: "la mitad de los casos" },
            { type: "scatter", x: corte(a.dias), y: corte(a.p50), mode: "lines",
              name: "mediana", line: { color: c.acento, width: 2.5 } },
          ]}
          layout={{ xaxis: { title: "Ruedas hacia adelante",
                             range: [0, a.dias?.[a.dias.length - 1] || 1] },
                    yaxis: { title: "Valor en dólares",
                             range: [Math.min(...(a.p5 || [0])) * 0.95,
                                     Math.max(...(a.p95 || [1])) * 1.05] },
                    shapes: [{ type: "line", xref: "paper", x0: 0, x1: 1,
                               y0: d.valor_inicial, y1: d.valor_inicial,
                               line: { color: c.texto3, width: 2, dash: "dot" } }] }} />
        <div className="pie">
          La incertidumbre no crece de golpe: se abre con la raíz del tiempo. La línea
          punteada es lo que vale hoy.{" "}
          {paso !== null && <b>Rueda {a.dias?.[paso]} de {a.dias?.[a.dias.length - 1]}.</b>}
        </div>
      </div>

      <div className="panel">
        <h3>Dónde puede terminar</h3>
        <Grafico alto={340}
          datos={[
            { type: "bar", x: dist.x, y: dist.y, name: "escenarios simulados",
              marker: { color: c.series[2], opacity: 0.75 },
              hovertemplate: "$%{x:,.0f}: %{y} escenarios<extra></extra>" },
            { type: "scatter", mode: "lines", x: dist.x, y: dist.normal,
              name: "ajuste normal", line: { color: c.alerta, width: 2 } },
            { type: "scatter", mode: "lines", x: dist.x, y: dist.lognormal,
              name: "ajuste lognormal", line: { color: c.positivo, width: 2, dash: "dot" } },
          ]}
          layout={{ bargap: 0.02, xaxis: { title: "Valor final", tickprefix: "$" },
                    yaxis: { title: "Escenarios" },
                    shapes: [d.final.var95, d.final.var99, d.valor_inicial].map((x, i) => ({
                      type: "line", x0: x, x1: x, yref: "paper", y0: 0, y1: 0.9,
                      line: { color: i === 2 ? c.texto3 : c.negativo, width: 1.6, dash: "dash" } })),
                    annotations: [
                      { x: d.final.var95, y: 1, yref: "paper", text: "5 % peor", showarrow: false,
                        font: { size: 10, color: c.negativo }, yanchor: "bottom" },
                      { x: d.valor_inicial, y: 1, yref: "paper", text: "hoy", showarrow: false,
                        font: { size: 10, color: c.texto3 }, yanchor: "bottom" }] }} />
        <div className="pie">
          Las barras son los {d.n_simulaciones.toLocaleString("es-AR")} escenarios simulados.
          El mejor ajuste teórico es <b>{dist.mejor_ajuste}</b> — que sea lognormal y no normal
          es lo esperable: un precio no puede ser negativo, así que la distribución de valores
          finales está sesgada hacia arriba.
        </div>
      </div>
    </>
  );
}

/* ── Benchmark (CAPM) ── */
function Capm({ d: inicial, cartera, bench }) {
  const c = colores();
  const [d, setD] = useState(inicial);
  const [todos, setTodos] = useState(null);
  // El selector global manda: si cambia, se recalcula contra ese índice.
  useEffect(() => {
    if (bench === (d?.benchmark || "SP500")) return;
    setD(null);
    api(`/api/capm/${encodeURIComponent(cartera)}?benchmark=${bench}`).then(setD);
  }, [bench, cartera]);
  if (!d) return <div className="cargando">Comparando contra el índice…</div>;
  if (d.error) return <div className="aviso mal">{d.error}</div>;
  const nivel = d.diagnostico_r2?.nivel;
  const gana = d.retorno_cartera_pct > d.retorno_benchmark_pct;
  const defensiva = d.beta < 0.8, agresiva = d.beta > 1.2;
  const datos = [
    { type: "scattergl", mode: "markers", name: "ruedas",
      x: (d.nube || []).map((p) => p.b), y: (d.nube || []).map((p) => p.p),
      marker: { size: 4, color: c.texto3, opacity: 0.45 },
      hovertemplate: "índice %{x:.2f} % · cartera %{y:.2f} %<extra></extra>" },
    { type: "scatter", mode: "lines", name: `pendiente = beta ${d.beta}`,
      x: (d.recta || []).map((p) => p.b), y: (d.recta || []).map((p) => p.p),
      line: { color: c.acento, width: 2.5 } },
  ];
  return (
    <>
      <div className="kpis">
        <Kpi etiqueta="Beta" valor={num(d.beta, 3)} ayuda={AYUDA.beta} sub={d.benchmark_nombre} />
        <Kpi etiqueta="Alpha anual" valor={pct(d.alpha_anual_pct)} tono={signo(d.alpha_anual_pct)} ayuda={AYUDA.alpha} />
        <Kpi etiqueta="R²" valor={num(d.r2, 3)} ayuda={AYUDA.r2}
             tono={nivel === "alto" ? "pos" : nivel === "bajo" ? "neg" : ""} />
        <Kpi etiqueta="Treynor" valor={num(d.treynor, 3)} />
        <Kpi etiqueta="Information ratio" valor={num(d.information_ratio, 3)} />
        <Kpi etiqueta="Cartera vs índice" valor={pct(d.retorno_cartera_pct)}
             sub={`índice ${pct(d.retorno_benchmark_pct)}`}
             tono={d.retorno_cartera_pct > d.retorno_benchmark_pct ? "pos" : "neg"} />
      </div>

      <div className={"aviso " + (nivel === "alto" ? "ok" : nivel === "bajo" ? "mal" : "ojo")}>
        <b>R² = {d.r2}.</b> {d.diagnostico_r2?.texto}
      </div>

      <div className="panel" style={{ marginBottom: 14 }}>
        <h3>Qué dice todo esto, en una lectura</h3>
        <div style={{ fontSize: 14.5, color: "var(--texto-2)", lineHeight: 1.7, marginTop: 8 }}>
          <p style={{ margin: "0 0 10px" }}>
            Sobre {d.n_ruedas} ruedas, tu cartera rindió <b className={gana ? "pos" : "neg"}>
            {pct(d.retorno_cartera_pct)}</b> anual contra <b>{pct(d.retorno_benchmark_pct)}</b> del{" "}
            {d.benchmark_nombre}.
          </p>
          <p style={{ margin: "0 0 10px" }}>
            Con <b>beta {num(d.beta, 2)}</b>, cuando el índice sube 10 % tu cartera tiende a{" "}
            {d.beta >= 0 ? "subir" : "bajar"} <b>{num(Math.abs(d.beta * 10), 1)} %</b>.{" "}
            {defensiva ? "Se mueve MENOS que el mercado: es defensiva frente a ese índice."
             : agresiva ? "Se mueve MÁS que el mercado: amplifica sus movimientos, para bien y para mal."
             : "Se mueve prácticamente al ritmo del mercado."}
          </p>
          <p style={{ margin: "0 0 10px" }}>
            El <b>alpha de {pct(d.alpha_anual_pct)}</b> es lo que rendiste por encima de lo que
            te correspondía por el riesgo de mercado que asumiste.{" "}
            {d.alpha_anual_pct > 0
              ? "Positivo: la cartera aportó algo que el índice no explica."
              : "Negativo: asumiendo ese riesgo, el índice te habría dado más."}
            {nivel === "bajo" && <> <b>Pero con R² de {d.r2} este número no se sostiene</b>: el
              índice no explica lo que hace tu cartera, así que beta y alpha están midiendo ruido.</>}
          </p>
          <p style={{ margin: 0 }}>
            El <b>tracking error de {pct(d.tracking_error_pct)}</b> es cuánto te despegás del
            índice en un año típico, y el <b>information ratio de {num(d.information_ratio, 2)}</b>{" "}
            dice si ese despegue te pagó: {d.information_ratio > 0.5
              ? "es una diferencia consistente, no un golpe de suerte"
              : d.information_ratio > 0 ? "apenas positivo, poco consistente"
              : "te despegaste del índice para peor"}.
          </p>
        </div>
      </div>

      <div className="fila f2">
        <div className="panel">
          <h3>Recta característica</h3>
          <Grafico datos={datos} alto={340}
                   layout={{ xaxis: { title: `Retorno diario · ${d.benchmark_nombre}`, ticksuffix: " %" },
                             yaxis: { title: "Retorno diario · cartera", ticksuffix: " %" } }} />
          <div className="pie">
            Cada punto es una rueda. La pendiente de la recta <b>es</b> el beta. Si la nube
            está dispersa, esa pendiente no describe gran cosa: eso es lo que dice el R².
          </div>
        </div>
        <div className="panel">
          <h3>¿Cuál es el índice correcto?</h3>
          {!todos ? (
            <button className="btn" onClick={async () =>
              setTodos(await api(`/api/capm/${encodeURIComponent(cartera)}/benchmarks`))}>
              Comparar los tres índices
            </button>
          ) : todos.error ? <div className="aviso mal">{todos.error}</div> : (
            <>
              <div className="tabla-wrap"><table>
                <thead><tr><th>Índice</th><th className="n">R²</th><th className="n">Beta</th><th className="n">Alpha</th></tr></thead>
                <tbody>{Object.entries(todos.benchmarks).sort((a,b)=>b[1].r2-a[1].r2).map(([k, v]) => (
                  <tr key={k}>
                    <td>{v.nombre}{k === todos.recomendado && <span className="chip ok" style={{marginLeft:7}}>correcto</span>}</td>
                    <td className="n">{num(v.r2, 3)}</td><td className="n">{num(v.beta, 3)}</td>
                    <td className="n">{pct(v.alpha_anual_pct)}</td>
                  </tr>))}</tbody>
              </table></div>
              <div className="aviso ojo">
                Fijate que el alpha <b>sube</b> cuanto peor es el índice. Elegir el
                benchmark por el número más lindo es elegir el que menos explica la cartera.
              </div>
            </>
          )}
        </div>
      </div>
    </>
  );
}

/* ── Momentum ── */
function Momentum({ d }) {
  const c = colores();
  const a = d.por_activo || [];
  const color = (s) => s === "FAVORABLE" ? c.positivo : s === "EVITAR" ? c.negativo
                     : s === "ESPERAR" ? c.alerta : c.texto3;
  return (
    <>
      <div className="panel">
        <h3>Momentum a 12 meses, salteando el último</h3>
        <Grafico alto={Math.max(220, a.length * 44)}
          datos={[{ type: "bar", orientation: "h",
                    y: a.map((x) => x.ticker).reverse(),
                    x: a.map((x) => x.mom_12_1_pct).reverse(),
                    marker: { color: a.map((x) => color(x.señal)).reverse() },
                    hovertemplate: "%{y}: %{x:.1f} %<extra></extra>" }]}
          layout={{ margin: { l: 82 }, xaxis: { ticksuffix: " %" } }} />
        <div className="pie">{d.nota_metodo}</div>
      </div>
      <div className="panel">
        <h3>Veredicto por activo</h3>
        <div className="tabla-wrap"><table>
          <thead><tr><th>Ticker</th><th className="n">12−1</th><th className="n">12 meses</th>
                     <th className="n">3 meses</th><th>Señal</th><th>Qué significa</th></tr></thead>
          <tbody>{a.map((x) => (
            <tr key={x.ticker}>
              <td className="mono">{x.ticker}</td>
              <td className={"n " + signo(x.mom_12_1_pct)}>{pct(x.mom_12_1_pct, 1)}</td>
              <td className="n">{pct(x.mom_12m_pct, 1)}</td>
              <td className={"n " + signo(x.mom_3m_pct)}>{pct(x.mom_3m_pct, 1)}</td>
              <td><span className={"chip " + (x.señal === "FAVORABLE" ? "ok" : x.señal === "EVITAR" ? "mal" : x.señal === "ESPERAR" ? "ojo" : "")}>{x.señal}</span></td>
              <td style={{ fontSize: 12.5, color: "var(--texto-2)" }}>{x.veredicto}</td>
            </tr>))}</tbody>
        </table></div>
      </div>
    </>
  );
}

/* ── Objetivos ── */
function Objetivos({ d, bl }) {
  const a = d.por_activo || [];
  return (
    <>
      <div className="kpis">
        <Kpi etiqueta="Upside promedio" valor={pct(d.upside_promedio_pct, 1)}
             tono={signo(d.upside_promedio_pct)} sub="según analistas" />
        <Kpi etiqueta="Con cobertura" valor={`${d.con_cobertura} / ${d.total}`}
             sub="activos con consenso" />
      </div>
      <div className="panel">
        <h3>Precio objetivo y momento de entrada</h3>
        <div className="tabla-wrap"><table>
          <thead><tr><th>Ticker</th><th className="n">Hoy</th><th className="n">Objetivo</th>
                     <th className="n">Upside</th><th>Momentum</th><th>Combinada</th>
                     <th>Qué hacer</th></tr></thead>
          <tbody>{a.map((x) => (
            <tr key={x.ticker}>
              <td className="mono">{x.ticker}{x.reexpresado && <span className="chip" style={{marginLeft:6}} title={`consenso de ${x.origen_consenso}`}>{x.origen_consenso}</span>}</td>
              <td className="n">{usd(x.actual)}</td>
              <td className="n">{x.objetivo_medio ? usd(x.objetivo_medio) : "—"}</td>
              <td className={"n " + signo(x.upside_pct)}>{x.upside_pct == null ? "—" : pct(x.upside_pct, 1)}</td>
              <td style={{ fontSize: 12.5 }}>{x.momentum || "—"}</td>
              <td><span className={"chip " + (x.combinada === "COMPRAR" ? "ok" : x.combinada === "CARO" || x.combinada === "REDUCIR" ? "mal" : x.combinada === "ESPERAR GIRO" ? "ojo" : "")}>{x.combinada}</span></td>
              <td style={{ fontSize: 12.5, color: "var(--texto-2)" }}>{x.combinada_texto}</td>
            </tr>))}</tbody>
        </table></div>
        <div className="pie">
          El precio objetivo dice <b>cuánto</b> puede valer; el momentum, <b>cuándo</b>.
          Un objetivo alto con la acción cayendo no es una compra: es esperar el giro.
        </div>
      </div>

      <h3 style={{ margin: "22px 0 4px", fontSize: 16 }}>
        Y si llevo estos objetivos a la cartera: Black-Litterman</h3>
      <div className="pie" style={{ marginBottom: 12, marginTop: 0 }}>
        Toma los precios objetivo de arriba como opiniones sobre el futuro, les asigna
        confianza según cuántos analistas los sostienen —recortándola donde el momentum va
        en contra— y las combina con lo que el mercado ya tiene implícito en tu cartera.
      </div>
      {!bl ? <div className="cargando">Calculando Black-Litterman…</div>
       : bl.error ? <div className="aviso mal">{bl.error}</div>
       : <BlackLitterman d={bl} />}
    </>
  );
}

/* ── Black-Litterman ── */
function BlackLitterman({ d }) {
  const c = colores();
  const acc = d.acciones || [];
  return (
    <>
      <div className="kpis">
        <Kpi etiqueta="Retorno esperado" valor={pct(d.ret_bl_pct)} />
        <Kpi etiqueta="Volatilidad" valor={pct(d.vol_bl_pct)} />
        <Kpi etiqueta="Sharpe" valor={num(d.sharpe_bl, 3)} />
        <Kpi etiqueta="Aversión al riesgo (δ)" valor={num(d.delta, 2)} sub={d.delta_label} />
        <Kpi etiqueta="Incertidumbre (τ)" valor={num(d.tau, 5)} sub={d.tau_label} />
      </div>
      <div className="aviso">{d.equilibrio_nota}</div>
      {acc.length === 0 ? (
        <div className="aviso ojo">{d.nota || "Sin views: el modelo devuelve el punto de partida."}</div>
      ) : (
        <div className="panel">
          <h3>Pesos sugeridos</h3>
          <Grafico alto={Math.max(230, acc.length * 44)}
            datos={[
              { type: "bar", orientation: "h", name: "hoy",
                y: acc.map((a) => a.ticker).reverse(), x: acc.map((a) => a.peso_actual_pct).reverse(),
                marker: { color: c.texto3 } },
              { type: "bar", orientation: "h", name: "Black-Litterman",
                y: acc.map((a) => a.ticker).reverse(), x: acc.map((a) => a.peso_bl_pct).reverse(),
                marker: { color: c.acento } },
            ]}
            layout={{ barmode: "group", margin: { l: 82 }, xaxis: { ticksuffix: " %" } }} />
        </div>
      )}
    </>
  );
}

/* ── Regímenes ── */
function Regimenes({ d, cartera }) {
  const c = colores();
  const [activos, setActivos] = useState(null);
  const [sel, setSel] = useState("__cartera__");
  useEffect(() => { api(`/api/riesgo/${encodeURIComponent(cartera)}/por-activo`).then(setActivos); }, [cartera]);
  const t = d.linea_tiempo || [];
  const franjas = [];
  let inicio = null;
  t.forEach((p, i) => {
    if (p.regimen === 1 && inicio === null) inicio = p.fecha;
    if ((p.regimen !== 1 || i === t.length - 1) && inicio !== null) {
      franjas.push({ type: "rect", xref: "x", yref: "paper", x0: inicio, x1: p.fecha,
                     y0: 0, y1: 1, fillcolor: c.negativo, opacity: 0.10, line: { width: 0 } });
      inicio = null;
    }
  });
  return (
    <>
      <div className="kpis">
        <Kpi etiqueta="Régimen actual" valor={d.regimen_actual}
             tono={d.regimen_actual === "calma" ? "pos" : "neg"} />
        <Kpi etiqueta="Tiempo en tensión" valor={pct(d.pct_tension, 1)}
             sub={`de ${d.dias_clasificados} ruedas`} />
        <Kpi etiqueta="Cambios de régimen" valor={d.transiciones?.length ?? 0} />
      </div>
      <div className="panel">
        <h3>Volatilidad y miedo del mercado
          <select value={sel} onChange={(e) => setSel(e.target.value)} style={{ marginLeft: "auto" }}>
            <option value="__cartera__">Cartera completa</option>
            {(activos?.por_activo || []).map((x) =>
              <option key={x.ticker} value={x.ticker}>{x.ticker}</option>)}
          </select>
        </h3>
        <Grafico alto={380}
          datos={[
            sel === "__cartera__"
              ? { type: "scatter", mode: "lines", name: "volatilidad de tu cartera",
                  x: t.map((p) => p.fecha), y: t.map((p) => p.vol_cartera),
                  line: { color: c.acento, width: 1.8 } }
              : { type: "scatter", mode: "lines", name: `retorno diario · ${sel}`,
                  x: (activos.series[sel] || []).map((p) => p.fecha),
                  y: (activos.series[sel] || []).map((p) => p.ret),
                  line: { color: c.acento, width: 0.9 } },
            ...(sel === "__cartera__" ? [{ type: "scatter", mode: "lines", name: "umbral de tensión",
              x: t.map((p) => p.fecha), y: t.map((p) => p.umbral),
              line: { color: c.texto3, width: 1, dash: "dot" } }] : []),
            { type: "scatter", mode: "lines", name: "VIX (miedo global)",
              x: t.map((p) => p.fecha), y: t.map((p) => p.vix),
              yaxis: "y2", line: { color: c.series[3], width: 1.2 } },
            { type: "scatter", mode: "markers", name: "eventos",
              x: (d.eventos || []).map((e) => e.fecha),
              y: (d.eventos || []).map(() => 0), yaxis: "y2",
              marker: { symbol: "diamond", size: 9,
                        color: (d.eventos || []).map((e) => e.alcance === "AR" ? c.series[3] : c.series[4]) },
              text: (d.eventos || []).map((e) => e.descripcion),
              hovertemplate: "<b>%{x}</b><br>%{text}<extra></extra>" },
          ]}
          layout={{ shapes: [...franjas, ...(d.eventos || []).map((e) => ({
                      type: "line", x0: e.fecha, x1: e.fecha, yref: "paper", y0: 0, y1: 1,
                      line: { color: e.alcance === "AR" ? c.series[3] : c.series[4],
                              width: 0.9, dash: "dot" } }))],
                    yaxis: { title: sel === "__cartera__" ? "Volatilidad anual" : "Retorno diario",
                             ticksuffix: " %" },
                    yaxis2: { title: "VIX", overlaying: "y", side: "right", showgrid: false } }} />
        <div className="pie">
          {d.metodo} Las líneas verticales son los eventos macro —pasá el mouse por los rombos
          para leerlos—; las franjas rojas, los períodos de tensión.
        </div>
      </div>
      <div className="panel">
        <h3>Qué pasaba alrededor</h3>
        <div className="tabla-wrap"><table>
          <thead><tr><th>Fecha</th><th>Alcance</th><th>Evento</th></tr></thead>
          <tbody>{(d.eventos || []).slice().reverse().map((e, i) => (
            <tr key={i}><td className="mono">{e.fecha}</td>
              <td><span className="chip">{e.alcance}</span></td><td>{e.descripcion}</td></tr>))}</tbody>
        </table></div>
        <div className="pie">{d.nota_eventos}</div>
      </div>
    </>
  );
}

/* ── Stress ── */
function Stress({ d }) {
  return (
    <div className="panel">
      <h3>Qué le habría pasado a esta cartera en cinco crisis reales</h3>
      <div className="tabla-wrap"><table>
        <thead><tr><th>Escenario</th><th>Período</th><th>Qué pasó</th>
                   <th className="n">Impacto</th><th className="n">En dólares</th></tr></thead>
        <tbody>{(d.escenarios || []).map((e, i) => (
          <tr key={i}>
            <td><b>{e.nombre}</b></td>
            <td className="mono" style={{ fontSize: 12 }}>{e.desde} → {e.hasta}</td>
            <td style={{ fontSize: 12.5, color: "var(--texto-2)" }}>{e.descripcion}</td>
            <td className={"n " + signo(e.pnl_pct)}>{e.pnl_pct == null ? "—" : pct(e.pnl_pct)}</td>
            <td className={"n " + signo(e.pnl_usd)}>{e.pnl_usd == null ? e.nota : usd(e.pnl_usd)}</td>
          </tr>))}</tbody>
      </table></div>
      <div className="pie">
        Se aplican los retornos reales de esas ventanas a tu cartera de hoy. Los escenarios
        anteriores a tu historia se informan como tales en vez de dar cero.
      </div>
    </div>
  );
}

/* ═══════════════ Modo 2 · Comparación ═══════════════ */

function Comparacion({ carteras }) {
  const [sel, setSel] = useState([]);
  const [d, setD] = useState(null);
  const [cargando, setCargando] = useState(false);
  const c = colores();

  const alternar = (n) => setSel((s) => s.includes(n) ? s.filter((x) => x !== n) : [...s, n]);

  const comparar = async () => {
    setCargando(true); setD(null);
    setD(await api("/api/comparar", { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ carteras: sel }) }));
    setCargando(false);
  };

  return (
    <>
      <div className="panel" style={{ marginBottom: 14 }}>
        <h3>Elegí dos o más carteras</h3>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginTop: 8 }}>
          {carteras.map((x) => (
            <button key={x.nombre} className={"btn" + (sel.includes(x.nombre) ? " primario" : "")}
                    onClick={() => alternar(x.nombre)}>{x.nombre}</button>
          ))}
          <button className="btn primario" disabled={sel.length < 2 || cargando}
                  onClick={comparar} style={{ marginLeft: "auto" }}>
            {cargando ? "Comparando…" : "Comparar"}
          </button>
        </div>
      </div>

      {cargando && <div className="cargando">Alineando series y corriendo las pruebas…</div>}
      {d?.error && <div className="aviso mal">{d.error}</div>}
      {d && !d.error && <ResultadoComparacion d={d} c={c} />}
      {!d && !cargando && <div className="vacio">
        Elegí al menos dos carteras. Se comparan sobre el período que ambas comparten,
        y se prueba si la diferencia es real o puede ser azar.
      </div>}
    </>
  );
}

function VeredictoComparacion({ d, concluyente }) {
  const lider = d.lider_por_criterios;
  const m = d.metricas[lider];
  const gana = d.criterios_ganados[lider];
  const rivales = d.pruebas_sharpe || [];
  const sostenidas = rivales.filter((r) => r.concluyente).map((r) => r.contra);
  const dudosas = rivales.filter((r) => !r.concluyente).map((r) => r.contra);

  return (
    <div className="panel" style={{ marginBottom: 14,
         borderLeft: `4px solid var(--${concluyente ? "positivo" : "alerta"})` }}>
      <h3 style={{ fontSize: 16 }}>
        {concluyente ? `Gana ${lider}` : `${lider} lidera, pero con reparos`}
        <span className={"chip " + (concluyente ? "ok" : "ojo")} style={{ marginLeft: 8 }}>
          {concluyente ? "diferencia demostrable" : "no concluyente"}</span>
      </h3>

      <div style={{ fontSize: 14.5, color: "var(--texto-2)", lineHeight: 1.7, marginTop: 10 }}>
        <p style={{ margin: "0 0 10px" }}>
          <b>{lider}</b> gana {gana.puntos} de 8 criterios: {gana.cuales.join(", ")}. Rindió{" "}
          <b>{pct(m.retorno_anual_pct)}</b> anual con <b>{pct(m.volatilidad_anual_pct)}</b> de
          volatilidad, o sea <b>{num(m.sharpe, 2)}</b> de Sharpe, y su peor caída fue{" "}
          <b className="neg">{pct(m.max_drawdown_pct)}</b>.
        </p>

        {sostenidas.length > 0 && (
          <p style={{ margin: "0 0 10px" }}>
            <b className="pos">La ventaja se sostiene</b> contra {sostenidas.join(" y ")}: la
            probabilidad de que esa diferencia sea casualidad es menor al 5 %.
          </p>)}

        {dudosas.length > 0 && (
          <p style={{ margin: "0 0 10px" }}>
            <b className="neg">Pero contra {dudosas.join(" y ")} no se puede afirmar nada.</b>{" "}
            {rivales.filter((r) => !r.concluyente).map((r) => (
              <span key={r.contra}>
                Le saca {num(r.diferencia_anual, 2)} de Sharpe, pero las dos se mueven casi
                igual (correlación {num(r.correlacion, 2)}) y con {r.n_ruedas} ruedas esa
                diferencia aparece por azar {pct(r.p_valor * 100, 0)} de las veces.{" "}
              </span>))}
          </p>)}

        <p style={{ margin: 0, color: "var(--texto-3)", fontSize: 13.5 }}>
          {concluyente
            ? "Con estos datos, elegir esa cartera está respaldado por la evidencia."
            : "Cuando dos carteras comparten activos, sus resultados se parecen y hace falta " +
              "mucha más historia para separarlas. Si tenés que elegir igual, mirá la que menos " +
              "cae y la que menos depende de un solo activo — eso se sostiene aunque el Sharpe no."}
        </p>
      </div>
    </div>
  );
}

function ResultadoComparacion({ d, c }) {
  const nombres = d.carteras;
  const p = d.periodo_comun;
  const concluyente = (d.pruebas_sharpe || []).every((x) => x.concluyente);

  const FILAS = [
    ["retorno_anual_pct", "Retorno anual", (v) => pct(v)],
    ["volatilidad_anual_pct", "Volatilidad", (v) => pct(v)],
    ["sharpe", "Sharpe", (v) => num(v, 3)],
    ["sortino", "Sortino", (v) => num(v, 3)],
    ["calmar", "Calmar", (v) => num(v, 3)],
    ["max_drawdown_pct", "Peor caída", (v) => pct(v)],
    ["var95_pct", "Día malo", (v) => pct(v)],
    ["curtosis_exceso", "Curtosis", (v) => num(v, 2)],
  ];

  return (
    <>
      <VeredictoComparacion d={d} concluyente={concluyente} />

      <div className="fila f2">
        <div className="panel">
          <h3>Evolución comparada · base 100</h3>
          <Grafico alto={330}
            datos={nombres.map((n, i) => ({
              type: "scatter", mode: "lines", name: n,
              x: (d.curva_valor || []).map((f) => f.fecha),
              y: (d.curva_valor || []).map((f) => f[n]),
              line: { color: c.series[i % c.series.length], width: 2 },
            }))} />
          <div className="pie">
            Período común: {p.desde} → {p.hasta} ({p.ruedas} ruedas). Comparar sobre
            historias de distinta longitud compara épocas del mercado, no estrategias.
          </div>
        </div>

        <div className="panel">
          <h3>¿La ventaja es real?</h3>
          <div className="tabla-wrap"><table>
            <thead><tr><th>{d.lider_por_criterios} contra</th><th className="n">Δ Sharpe</th>
                       <th className="n">Correlación</th><th className="n">p</th><th>Conclusión</th></tr></thead>
            <tbody>{(d.pruebas_sharpe || []).map((t, i) => (
              <tr key={i}>
                <td>{t.contra}</td>
                <td className="n">{num(t.diferencia_anual, 3)}</td>
                <td className="n">{num(t.correlacion, 2)}</td>
                <td className="n">{t.p_valor == null ? "—" : num(t.p_valor, 3)}</td>
                <td><span className={"chip " + (t.concluyente ? "ok" : "ojo")}>
                  {t.concluyente ? "significativa" : "no concluyente"}</span></td>
              </tr>))}</tbody>
          </table></div>
          <div className="pie">
            Prueba de Jobson-Korkie con corrección de Memmel. Cuando dos carteras
            comparten activos su correlación es alta, y una diferencia que parece grande
            puede no distinguirse del ruido.
          </div>
        </div>
      </div>

      <div className="panel">
        <h3>Tabla comparativa</h3>
        <div className="tabla-wrap"><table>
          <thead><tr><th>Métrica</th>{nombres.map((n) => (
            <th key={n} className="n">{n}{n === d.lider_por_criterios ? " ★" : ""}</th>))}</tr></thead>
          <tbody>
            {FILAS.map(([k, et, f]) => (
              <tr key={k}><td>{et}</td>
                {nombres.map((n) => <td key={n} className="n">{f(d.metricas[n][k])}</td>)}
              </tr>))}
            <tr><td>Criterios ganados</td>
              {nombres.map((n) => <td key={n} className="n">
                {d.criterios_ganados[n].puntos} / 8</td>)}</tr>
          </tbody>
        </table></div>
      </div>

      <div className="fila f2">
        <div className="panel">
          <h3>Con barra de error</h3>
          <div className="tabla-wrap"><table>
            <thead><tr><th>Cartera</th><th className="n">Sharpe</th>
                       <th className="n">Intervalo de confianza 95 %</th></tr></thead>
            <tbody>{nombres.map((n) => {
              const i = d.intervalos_confianza[n]?.sharpe || {};
              return (<tr key={n}><td>{n}</td><td className="n">{num(i.observado, 3)}</td>
                <td className="n">[{num(i.ic95_bajo, 2)} · {num(i.ic95_alto, 2)}]</td></tr>);
            })}</tbody>
          </table></div>
          <div className="pie">
            Si los intervalos de dos carteras se superponen, los datos no alcanzan para
            separarlas. Un Sharpe medido sobre pocos años es mucho menos preciso de lo que
            sugiere su cifra.
          </div>
        </div>

        <div className="panel">
          <h3>¿O es que probaste muchas?</h3>
          <div className="tabla-wrap"><table>
            <thead><tr><th>Cartera</th><th className="n">Sharpe</th>
                       <th className="n">Umbral de azar</th><th className="n">DSR</th></tr></thead>
            <tbody>{nombres.map((n) => {
              const s = d.sharpe_deflactado[n] || {};
              return (<tr key={n}><td>{n}</td>
                <td className="n">{num(s.sharpe_anual, 3)}</td>
                <td className="n">{num(s.umbral_azar_anual, 3)}</td>
                <td className={"n " + (s.dsr >= 0.95 ? "pos" : s.dsr < 0.8 ? "neg" : "")}>{num(s.dsr, 3)}</td>
              </tr>);
            })}</tbody>
          </table></div>
          <div className="pie">
            Sharpe deflactado: probabilidad de que el resultado no sea suerte, considerando
            cuántas variantes se compararon. Debajo de 0,80 conviene desconfiar.
          </div>
        </div>
      </div>
    </>
  );
}

/* ═══════════════ Carteras y Conectores ═══════════════ */

function Carteras({ carteras, recargar }) {
  const [sel, setSel] = useState(null);
  const [filas, setFilas] = useState([]);
  const [msg, setMsg] = useState(null);
  const [destino, setDestino] = useState("");

  const abrir = async (n) => {
    setSel(n); setMsg(null);
    setFilas(await api(`/api/carteras/${encodeURIComponent(n)}`));
  };
  const guardar = async () => {
    const r = await api(`/api/carteras/${encodeURIComponent(sel)}`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ posiciones: filas }) });
    setMsg(r.error ? { mal: r.error } : { ok: `Guardadas ${r.guardadas} posiciones.` });
    recargar();
  };
  const subir = async (archivo, ruta) => {
    const destinoFinal = (destino || sel || "").trim();
    if (!destinoFinal) { setMsg({ mal: "Elegí o escribí una cartera de destino." }); return; }
    const fd = new FormData(); fd.append("file", archivo);
    const r = await api(`/api/carteras/${encodeURIComponent(destinoFinal)}/${ruta}`,
                        { method: "POST", body: fd });
    if (r.error) { setMsg({ mal: r.error }); return; }
    setMsg({ ok: `${r.agregadas} agregadas, ${r.omitidas} ya estaban.` +
                 (r.cerradas_por_venta ? ` ${r.cerradas_por_venta} lotes cerrados por venta fueron al P&L realizado (${usd(r.pnl_realizado_usd)}).` : "") });
    recargar(); abrir(destinoFinal);
  };
  const editar = (i, campo, v) =>
    setFilas((f) => f.map((x, j) => (j === i ? { ...x, [campo]: v } : x)));

  return (
    <>
      <div className="panel" style={{ marginBottom: 14 }}>
        <h3>Carteras</h3>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginTop: 8 }}>
          {carteras.map((x) => (
            <button key={x.nombre} className={"btn" + (sel === x.nombre ? " primario" : "")}
                    onClick={() => abrir(x.nombre)}>{x.nombre} <span style={{opacity:.6}}>({x.posiciones})</span></button>
          ))}
          <button className="btn" onClick={() => {
            const n = prompt("Nombre de la cartera nueva:");
            if (n) { setSel(n.trim()); setFilas([]); setMsg({ ok: "Cartera nueva: agregá activos y guardá." }); }
          }}>+ Nueva</button>
          <a className="btn" href="/api/plantilla" style={{ textDecoration: "none", marginLeft: "auto" }}>
            Descargar plantilla CSV
          </a>
        </div>
      </div>

      <div className="panel" style={{ marginBottom: 14 }}>
        <h3>Importar</h3>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center", marginTop: 8 }}>
          <input type="text" placeholder="cartera de destino" value={destino}
                 onChange={(e) => setDestino(e.target.value)} style={{ minWidth: 170 }} />
          <label className="btn">Formato propio
            <input type="file" accept=".csv" hidden
                   onChange={(e) => e.target.files[0] && subir(e.target.files[0], "importar")} />
          </label>
          <label className="btn">CSV de Yahoo Finance
            <input type="file" accept=".csv" hidden
                   onChange={(e) => e.target.files[0] && subir(e.target.files[0], "importar-yahoo")} />
          </label>
        </div>
        <div className="pie">
          Del CSV de Yahoo solo entra lo que sigue abierto: las ventas netean FIFO contra
          las compras más viejas y lo cerrado va al P&amp;L realizado.
        </div>
      </div>

      {msg && <div className={"aviso " + (msg.mal ? "mal" : "ok")}>{msg.mal || msg.ok}</div>}

      {sel && (
        <div className="panel">
          <h3>{sel}</h3>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", margin: "8px 0 12px" }}>
            <button className="btn primario" onClick={guardar}>Guardar</button>
            <button className="btn" onClick={() => setFilas((f) => [...f, {
              ticker: "", buy_date: "", buy_price: 0, qty: 0, commissions: 0,
              source: "", currency: "", asset_type: "", notes: "" }])}>+ Activo</button>
            <a className="btn" style={{ textDecoration: "none" }}
               href={`/api/carteras/${encodeURIComponent(sel)}/exportar`}>Exportar CSV</a>
            <button className="btn peligro" style={{ marginLeft: "auto" }} onClick={async () => {
              if (!confirm(`¿Eliminar la cartera "${sel}"?`)) return;
              await api(`/api/carteras/${encodeURIComponent(sel)}`, { method: "DELETE" });
              setSel(null); setFilas([]); recargar();
            }}>Eliminar</button>
          </div>
          <div className="tabla-wrap"><table>
            <thead><tr><th>Ticker</th><th>Fecha</th><th className="n">Precio</th>
                       <th className="n">Cantidad</th><th className="n">Comisiones</th>
                       <th>Origen</th><th>Moneda</th><th>Notas</th><th></th></tr></thead>
            <tbody>{filas.map((f, i) => (
              <tr key={i}>
                {[["ticker", 100], ["buy_date", 100]].map(([k, w]) => (
                  <td key={k}><input type="text" value={f[k] || ""} style={{ width: w }}
                        onChange={(e) => editar(i, k, e.target.value)} /></td>))}
                {["buy_price", "qty", "commissions"].map((k) => (
                  <td key={k} className="n"><input type="number" value={f[k] ?? 0} style={{ width: 96 }}
                        onChange={(e) => editar(i, k, +e.target.value)} /></td>))}
                <td><input type="text" value={f.source || ""} placeholder="cocos" style={{ width: 70 }}
                      onChange={(e) => editar(i, "source", e.target.value)} /></td>
                <td><input type="text" value={f.currency || ""} placeholder="auto" style={{ width: 60 }}
                      onChange={(e) => editar(i, "currency", e.target.value)} /></td>
                <td><input type="text" value={f.notes || ""} style={{ width: 110 }}
                      onChange={(e) => editar(i, "notes", e.target.value)} /></td>
                <td><button className="btn peligro" style={{ padding: "3px 8px" }}
                      onClick={() => setFilas((x) => x.filter((_, j) => j !== i))}>✕</button></td>
              </tr>))}</tbody>
          </table></div>
          <div className="pie">
            <b>Origen</b>: poné <code>cocos</code> si es un bono u ON — marca que cotiza cada
            100 nominales. <b>Moneda</b>: solo si la detección automática se equivoca con
            ese ticker.
          </div>
        </div>
      )}
    </>
  );
}

function Conectores() {
  const [d, setD] = useState(null);
  useEffect(() => { api("/api/conectores").then(setD); }, []);
  if (!d) return <div className="cargando">Consultando fuentes…</div>;
  return (
    <>
      <div className="aviso">
        Solo dos fuentes piden credencial, y las dos son <b>opcionales</b>: sin ellas la
        aplicación funciona igual, con menos cobertura.
      </div>
      <div className="fila f2">
        <div className="panel">
          <h3>Públicas · sin credencial</h3>
          <div className="tabla-wrap"><table>
            <thead><tr><th>Fuente</th><th>Aporta</th><th>Estado</th></tr></thead>
            <tbody>{d.publicas.map((f, i) => (
              <tr key={i}><td><b>{f.nombre}</b></td><td>{f.aporta}</td>
                <td><span className="chip ok">{f.estado}</span></td></tr>))}</tbody>
          </table></div>
        </div>
        <div className="panel">
          <h3>Con credencial · opcionales</h3>
          {d.con_credencial.map((f, i) => (
            <div key={i} style={{ marginBottom: 14 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <b>{f.nombre}</b>
                <span className={"chip " + (f.conectado ? "ok" : "ojo")}>
                  {f.conectado ? "conectado" : "no conectado"}</span>
              </div>
              <div style={{ fontSize: 12.5, color: "var(--texto-2)", marginTop: 3 }}>
                Aporta: {f.aporta}. Requiere {f.requiere}.
              </div>
              <div style={{ fontSize: 12.5, color: "var(--texto-3)", marginTop: 2 }}>
                {f.detalle} — <i>{f.sin_ella}</i>
              </div>
            </div>
          ))}
        </div>
      </div>
      <div className="panel">
        <h3>Descartadas</h3>
        <div className="tabla-wrap"><table>
          <thead><tr><th>Fuente</th><th>Por qué no se usa</th></tr></thead>
          <tbody>{d.descartadas.map((f, i) => (
            <tr key={i}><td>{f.nombre}</td><td>{f.motivo}</td></tr>))}</tbody>
        </table></div>
      </div>
    </>
  );
}

/* ═══════════════ Mercado · MEP y noticias ═══════════════ */

function Mercado() {
  const [mep, setMep] = useState(null);
  const [news, setNews] = useState(null);
  const [rango, setRango] = useState("2024-01-01");
  const c = colores();

  useEffect(() => { api(`/api/mep?desde=${rango}`).then(setMep); }, [rango]);
  useEffect(() => { api("/api/noticias?limite=30").then(setNews); }, []);

  const RANGOS = [["2026-01-01", "este año"], ["2024-01-01", "2 años"],
                  ["2020-01-01", "todo"]];

  return (
    <>
      {mep?.error && <div className="aviso mal">{mep.error}</div>}
      {mep && !mep.error && mep.serie && (
        <>
          <div className="kpis">
            <Kpi etiqueta="Dólar MEP hoy" valor={usd(mep.hoy)} sub={mep.fuente} />
            <Kpi etiqueta="Ruedas en la serie" valor={mep.ruedas.toLocaleString("es-AR")} />
          </div>
          <div className="panel">
            <h3>Dólar MEP
              <span style={{ marginLeft: "auto", display: "flex", gap: 4 }}>
                {RANGOS.map(([v, t]) => (
                  <button key={v} className={"btn" + (rango === v ? " primario" : "")}
                          style={{ padding: "3px 10px", fontSize: 12 }}
                          onClick={() => setRango(v)}>{t}</button>))}
              </span>
            </h3>
            <Grafico alto={340}
              datos={[{ type: "scatter", mode: "lines", name: "MEP",
                        x: mep.serie.map((p) => p.fecha), y: mep.serie.map((p) => p.valor),
                        line: { color: c.acento, width: 1.8 },
                        hovertemplate: "%{x}<br>$%{y:,.2f}<extra></extra>" }]}
              layout={{ yaxis: { title: "Pesos por dólar", tickprefix: "$" } }} />
            <div className="pie">
              Esta es la serie con la que se convierte toda la cartera a dólares, usando
              el valor de la fecha de cada operación. Fuentes públicas, sin credencial.
            </div>
          </div>
        </>
      )}

      <div className="panel" style={{ marginTop: 14 }}>
        <h3>Qué está pasando</h3>
        {!news ? <div className="cargando">Buscando titulares…</div>
         : news.error || !news.noticias
         ? <div className="aviso mal">No se pudieron traer titulares. {news.error || ""}</div> : (
          <>
            {news.fuentes_caidas?.length > 0 && (
              <div className="aviso ojo" style={{ marginTop: 4 }}>
                Sin respuesta de: {news.fuentes_caidas.join(", ")}. Se muestran las demás.
              </div>
            )}
            <div className="tabla-wrap"><table>
              <thead><tr><th>Fecha</th><th>Fuente</th><th>Titular</th></tr></thead>
              <tbody>{news.noticias.map((n, i) => (
                <tr key={i}>
                  <td className="mono" style={{ fontSize: 12, whiteSpace: "nowrap" }}>
                    {n.fecha ? n.fecha.slice(0, 16).replace("T", " ") : "—"}</td>
                  <td style={{ fontSize: 12, color: "var(--texto-3)", whiteSpace: "nowrap" }}>{n.fuente}</td>
                  <td>{n.enlace
                    ? <a href={n.enlace} target="_blank" rel="noopener"
                         style={{ color: "var(--texto)", textDecoration: "none" }}>{n.titulo}</a>
                    : n.titulo}</td>
                </tr>))}</tbody>
            </table></div>
            <div className="pie">{news.nota}</div>
          </>
        )}
      </div>
    </>
  );
}

/* ═══════════════ Raíz ═══════════════ */

function App() {
  const [modo, setModo] = useState("analisis");
  const [tema, setTema] = useState(() => localStorage.getItem("tema") || "auto");
  const [carteras, setCarteras] = useState([]);
  const [cartera, setCartera] = useState(null);

  const recargar = useCallback(async () => {
    const c = await api("/api/carteras");
    if (Array.isArray(c)) setCarteras(c);
  }, []);

  useEffect(() => { recargar(); }, [recargar]);

  useEffect(() => {
    // "auto" = no marcar nada y dejar que mande prefers-color-scheme.
    if (tema === "auto") delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = tema;
    localStorage.setItem("tema", tema);
  }, [tema]);

  return (
    <>
      <Barra modo={modo} setModo={setModo} tema={tema} setTema={setTema}
             carteras={carteras} cartera={cartera} setCartera={setCartera} />
      <div className="hoja">
        {modo === "analisis" && <Analisis cartera={cartera} />}
        {modo === "comparacion" && <Comparacion carteras={carteras} />}
        {modo === "carteras" && <Carteras carteras={carteras} recargar={recargar} />}
        {modo === "mercado" && <Mercado />}
        {modo === "conectores" && <Conectores />}
      </div>
      <footer>
        <span>© Leandro R. Bergero · Msc Finance and Banking BSM-UPF ·{" "}
          <a href="https://github.com/leabergero" target="_blank" rel="noopener">github.com/leabergero</a></span>
        <span>Todos los valores en dólares, convertidos con el MEP de la fecha de cada operación.</span>
      </footer>
    </>
  );
}

ReactDOM.createRoot(document.getElementById("raiz")).render(<App />);
