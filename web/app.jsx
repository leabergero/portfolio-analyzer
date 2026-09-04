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
    marcaActual: v("--marca-actual"), marcaOptima: v("--marca-optima"),
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
    // Los tres se mezclan campo a campo: un `margin: {l: 82}` en el llamador
    // reemplazaba el objeto entero y Plotly volvía a SUS defaults (t=100, b=80),
    // así que el área de dibujo quedaba en 50 px dentro de un gráfico de 230 y
    // las barras se amontonaban abajo con medio panel vacío arriba.
    const mezcla = { ...base, ...layout,
      margin: { ...base.margin, ...(layout?.margin || {}) },
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
  realizado: { que: "Ganancia o pérdida ya cerrada",
    como: "Lo que dejaron las posiciones que vendiste, netas de comisiones. Cada pata se convierte a dólares con el MEP de su propia fecha, así el resultado no mezcla el movimiento del tipo de cambio con el del activo.",
    umbral: "Ya está cobrado: no cambia con el precio de mañana." },
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
          ["carteras", "Carteras"], ["mercado", "Dólar MEP"],
          ["conectores", "Conectores"], ["cocos", "Cocos"]].map(([k, t]) => (
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
// correlaciones, distribución de retornos, comparación contra el índice y
// momentum. Riesgo queda solo con lo que profundiza. Menos pestañas, y cada una
// con una pregunta entera adentro.
const PESTANAS = [
  ["posicion", "Posición"], ["riesgo", "Riesgo"],
  ["markowitz", "Optimización"], ["montecarlo", "Monte Carlo"],
  ["regimenes", "Regímenes"],
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
        {/* El índice solo cambia algo en dos pestañas: en Posición manda sobre
            beta, alpha y R², y en Optimización calibra la aversión al riesgo (δ)
            de Black-Litterman. En Riesgo, Monte Carlo y Regímenes lo único que
            movería es la región de la tasa libre de riesgo, que ya va escrita
            debajo de cada KPI que la usa. Mostrarlo ahí invitaba a tocarlo
            esperando un efecto que no existe. */}
        {(tab === "posicion" || tab === "markowitz") && (
          <span style={{ marginLeft: "auto", display: "flex", alignItems: "center",
                         gap: 7, paddingBottom: 6 }}>
            <span style={{ fontSize: 12, color: "var(--texto-3)" }}>Comparar contra</span>
            <select value={bench} onChange={(e) => setBench(e.target.value)}>
              {BENCHMARKS.map(([k, t]) => <option key={k} value={k}>{t}</option>)}
            </select>
          </span>)}
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
                        recargar={recargar} bench={bench}
                        extras={{ composicion: R.composicion, riesgo: R.riesgo,
                                  momentum: R.momentum, capm: R.capm }} />,
    riesgo: <Riesgo d={d} cartera={cartera} extras={{ stress: R.stress }} />,
    markowitz: <Markowitz d={d} cartera={cartera} bench={bench}
                          extras={{ objetivos: R.objetivos, bl: R.blacklitterman,
                                    momentum: R.momentum }} />,
    montecarlo: <MonteCarlo d={d} cartera={cartera} />,
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

function Posicion({ d, cartera, recargar, extras, bench }) {
  const filas = d.posiciones || [];
  const [corr, setCorr] = useState(null);
  const [real, setReal] = useState(null);
  const r = extras?.riesgo;
  useEffect(() => { setCorr(null);
    api(`/api/correlaciones/${encodeURIComponent(cartera)}`).then(setCorr); }, [cartera]);
  // Lo cerrado se venía guardando y neteando sin que se viera en ningún lado.
  const [n, setN] = useState(0);
  useEffect(() => { setReal(null);
    api(`/api/carteras/${encodeURIComponent(cartera)}/realizado`).then(setReal); }, [cartera, n]);
  const cerrado = real?.n ? real.total_usd : null;

  return (
    <>
      {/* 1 · Cómo se comporta la cartera, antes que el detalle de qué tiene */}
      {r && !r.error && <KpisRiesgo d={r} />}

      {/* 2 · Qué tengo */}
      <div className="kpis">
        <Kpi etiqueta="Valor total" valor={usd(d.valor_total)} ayuda={AYUDA.valor}
             sub={d.mep_hoy ? `MEP $${d.mep_hoy}` : null} />
        <Kpi etiqueta="Costo" valor={usd(d.costo_total)} sub="comisiones incluidas" />
        <Kpi etiqueta="Resultado abierto" valor={usd(d.pnl)} tono={signo(d.pnl)} ayuda={AYUDA.pnl}
             sub={pct(d.pnl_pct)} />
        {cerrado != null && (
          <Kpi etiqueta="Resultado realizado" valor={usd(cerrado)} tono={signo(cerrado)}
               sub={`${real.n} operaciones cerradas`} ayuda={AYUDA.realizado} />)}
        {cerrado != null && (
          <Kpi etiqueta="Resultado total" valor={usd(d.pnl + cerrado)}
               tono={signo(d.pnl + cerrado)} sub="abierto + cerrado" />)}
        <Kpi etiqueta="Posiciones" valor={filas.length} sub={`${new Set(filas.map(f=>f.ticker)).size} activos`} />
      </div>
      <AltaRapida cartera={cartera} recargar={recargar} />
      {d.sin_precio?.length > 0 && (
        <div className="aviso ojo">
          <b>{d.sin_precio.length} posiciones sin precio</b> y quedaron fuera del total:{" "}
          {d.sin_precio.join(", ")}. Los bonos y ONs necesitan Cocos conectado.
        </div>
      )}
      {real?.n > 0 && <CalendarioRealizado real={real} />}

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

      {real && <PnlRealizado real={real} cartera={cartera} recargar={() => setN((x) => x + 1)} />}

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

      {/* 6 · Contra qué se compara */}
      <Seccion titulo="¿Y contra el mercado?" />
      {extras?.capm
        ? (extras.capm.error
            ? <div className="aviso mal">{extras.capm.error}</div>
            : <Capm d={extras.capm} cartera={cartera} bench={bench} />)
        : <div className="cargando">Comparando contra el índice…</div>}

      {/* 7 · Es momento de entrar o esperar */}
      <Seccion titulo="¿Viento a favor o en contra?" />
      {extras?.momentum
        ? (extras.momentum.error
            ? <div className="aviso mal">{extras.momentum.error}</div>
            : <Momentum d={extras.momentum} />)
        : <div className="cargando">Midiendo el momentum…</div>}
    </>
  );
}

function CalendarioRealizado({ real }) {
  const c = colores();
  const trades = real.trades || [];
  if (trades.length === 0) return null;

  // Un punto por mes: lo que dejaron las ventas y, apilado encima, los
  // dividendos. `barmode: "relative"` es lo que hace que en un mismo mes lo
  // positivo crezca hacia arriba y lo negativo hacia abajo sin taparse.
  const meses = {};
  for (const t of trades) {
    const m = (t.sell_date || "").slice(0, 7);
    if (!m) continue;
    const x = meses[m] || (meses[m] = { mes: m, ventas: 0, dividendos: 0 });
    if (t.tipo === "dividendo") x.dividendos += t.pnl_usd;
    else x.ventas += t.pnl_usd;
  }
  const filas = Object.values(meses).sort((a, b) => (a.mes < b.mes ? -1 : 1));
  if (filas.length === 0) return null;

  const x = filas.map((f) => f.mes + "-15");        // al medio del mes que representa
  const conDividendos = filas.filter((f) => f.dividendos).length;
  const total = filas.reduce((s, f) => s + f.ventas + f.dividendos, 0);
  const mejor = filas.reduce((a, b) => (a.ventas + a.dividendos > b.ventas + b.dividendos ? a : b));
  const peor = filas.reduce((a, b) => (a.ventas + a.dividendos < b.ventas + b.dividendos ? a : b));
  const nombreMes = (m) => new Date(m + "-15T12:00:00")
    .toLocaleDateString("es-AR", { month: "long", year: "numeric" });
  const mesCorto = (fecha) => new Date(fecha + "T12:00:00")
    .toLocaleDateString("es-AR", { month: "short", year: "2-digit" }).replace(".", "");

  return (
    <div className="panel">
      <h3>Mes a mes</h3>
      <Grafico alto={260}
        datos={[
          { type: "bar", name: "ventas", x, y: filas.map((f) => f.ventas),
            marker: { color: filas.map((f) => (f.ventas >= 0 ? c.positivo : c.negativo)),
                      line: { width: 0 } },
            width: 18 * 86400000, text: filas.map((f) => nombreMes(f.mes)),
            textposition: "none",
            hovertemplate: "%{text}<br>ventas: %{y:$,.2f}<extra></extra>" },
          { type: "bar", name: "dividendos", x, y: filas.map((f) => f.dividendos),
            marker: { color: c.alerta, line: { width: 0 } },
            width: 18 * 86400000, text: filas.map((f) => nombreMes(f.mes)),
            textposition: "none",
            hovertemplate: "%{text}<br>dividendos: %{y:$,.2f}<extra></extra>" },
        ]}
        layout={{ barmode: "relative", bargap: 0.35, margin: { t: 12, l: 62 },
                  legend: { orientation: "h", y: -0.2, x: 0.5, xanchor: "center" },
                  // Plotly rotula los meses en inglés y no trae el locale es en
                  // el bundle: las etiquetas se arman acá, una cada tres meses
                  // para que no se pisen por más años que acumule la cartera.
                  xaxis: { type: "date", showgrid: false,
                           tickvals: x.filter((_, i) => i % 3 === 0),
                           ticktext: x.filter((_, i) => i % 3 === 0).map(mesCorto) },
                  yaxis: { tickprefix: "$", zeroline: true, zerolinewidth: 1.4 } }} />
      <div className="pie">
        Cada barra es un mes: lo que dejaron las ventas y, apilado encima, los dividendos
        cobrados{conDividendos ? ` (${conDividendos} de ${filas.length} meses tuvieron)` : ""}.
        El mejor fue <b>{nombreMes(mejor.mes)}</b> con {usd(mejor.ventas + mejor.dividendos)} y
        el peor <b>{nombreMes(peor.mes)}</b> con {usd(peor.ventas + peor.dividendos)}; los{" "}
        {filas.length} meses suman {usd(total)}.
      </div>
    </div>
  );
}

function AltaDividendo({ cartera, recargar }) {
  const linea = (base) => ({ ticker: base?.ticker || "", fecha: "", importe: "",
                             qty: base?.qty || "", por_accion: base?.por_accion ?? true,
                             moneda: base?.moneda || "" });
  const [filas, setFilas] = useState([linea()]);
  const [msg, setMsg] = useState(null);
  const [abierto, setAbierto] = useState(false);
  const set = (i, k, v) => setFilas((f) => f.map((x, j) => (j === i ? { ...x, [k]: v } : x)));

  // Al escribir el ticker se pregunta en qué moneda cotiza y se propone esa,
  // pero queda editable: un CEDEAR D cotiza en dólares y sin embargo su
  // dividendo suele acreditarse en pesos. Darlo por sentado multiplica el
  // importe por el MEP y nadie se entera.
  const sugerirMoneda = async (i, ticker) => {
    if (!ticker) return;
    const r = await api(`/api/validar/${encodeURIComponent(ticker)}`);
    // De paso avisa si el ticker no existe: siete dividendos de Apple quedaron
    // cargados en APPLD.BA —el papel es AAPLD.BA— y el error solo se ve como
    // una fila de más en la tabla, meses después.
    setFilas((f) => f.map((x, j) => (j !== i ? x : {
      ...x, existe: !!r?.valido, moneda: x.moneda || r?.moneda || "" })));
  };
  // La fila nueva hereda ticker, cantidad y modo de la anterior: seis cobros de
  // un mismo papel se cargan cambiando nada más que la fecha y el importe.
  const sumar = () => setFilas((f) => [...f, linea(f[f.length - 1])]);
  const quitar = (i) => setFilas((f) => (f.length === 1 ? [linea()] : f.filter((_, j) => j !== i)));

  const completas = filas.filter((f) => f.ticker && f.fecha && f.importe);

  const guardar = async () => {
    const r = await api(`/api/carteras/${encodeURIComponent(cartera)}/dividendo`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dividendos: completas }) });
    if (r.error) { setMsg({ mal: r.error }); return; }
    setMsg({ ok: `${r.agregados} ${r.agregados === 1 ? "dividendo registrado" : "dividendos registrados"}` +
                 `, ${num(r.importe_total, 2)} en total.` +
                 (r.agregados < completas.length
                   ? ` ${completas.length - r.agregados} ya estaban cargados.` : "") });
    setFilas([linea(filas[filas.length - 1])]);
    recargar && recargar();
  };

  if (!abierto) return (
    <button className="btn" style={{ marginTop: 10 }} onClick={() => setAbierto(true)}>
      + Registrar dividendos</button>);

  return (
    <div className="panel" style={{ background: "var(--panel-2)", marginTop: 10 }}>
      <h3>Dividendos cobrados
        <button className="btn" style={{ marginLeft: "auto", padding: "3px 10px", fontSize: 12 }}
                onClick={() => setAbierto(false)}>Cerrar</button>
      </h3>
      <div className="tabla-wrap"><table>
        <thead><tr><th>Ticker</th><th>Fecha de cobro</th><th className="n">Importe</th>
          <th>Moneda</th><th>El importe es</th><th className="n">Acciones</th>
          <th className="n">Resultado</th><th></th></tr></thead>
        <tbody>
          {filas.map((f, i) => {
            const qty = parseFloat(f.qty) || 1;
            const imp = parseFloat(f.importe) || 0;
            const total = f.por_accion ? qty * imp : imp;
            return (
              <tr key={i}>
                <td><input type="text" value={f.ticker}
                           style={{ width: 110,
                                    borderColor: f.existe === false ? "var(--negativo)" : "" }}
                           title={f.existe === false ? "No se encontraron precios para ese ticker" : ""}
                           placeholder="METR.BA"
                           onBlur={(e) => sugerirMoneda(i, e.target.value.trim().toUpperCase())}
                           onChange={(e) => set(i, "ticker", e.target.value.toUpperCase())} /></td>
                <td><input type="date" value={f.fecha} style={{ width: 140 }}
                           onChange={(e) => set(i, "fecha", e.target.value)} /></td>
                <td><input type="number" step="0.0001" value={f.importe} style={{ width: 110 }}
                           onChange={(e) => set(i, "importe", e.target.value)} /></td>
                <td>
                  <select value={f.moneda || ""} style={{ width: 90 }}
                          onChange={(e) => set(i, "moneda", e.target.value)}>
                    <option value="">auto</option>
                    <option value="ARS">ARS</option>
                    <option value="USD">USD</option>
                  </select>
                </td>
                <td>
                  <select value={f.por_accion ? "unit" : "total"} style={{ width: 130 }}
                          onChange={(e) => set(i, "por_accion", e.target.value === "unit")}>
                    <option value="unit">por acción</option>
                    <option value="total">el total cobrado</option>
                  </select>
                </td>
                <td><input type="number" value={f.qty} style={{ width: 100 }}
                           disabled={!f.por_accion} placeholder={f.por_accion ? "" : "—"}
                           onChange={(e) => set(i, "qty", e.target.value)} /></td>
                <td className="n mono">{total ? `${num(total, 2)} ${f.moneda || ""}` : "—"}</td>
                <td><button className="btn" style={{ padding: "2px 9px", fontSize: 12 }}
                            onClick={() => quitar(i)}>✕</button></td>
              </tr>);
          })}
        </tbody>
      </table></div>
      <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 10 }}>
        <button className="btn" onClick={sumar}>+ Otra línea</button>
        <button className="btn primario" onClick={guardar} disabled={completas.length === 0}>
          Registrar {completas.length || ""} {completas.length === 1 ? "dividendo" : "dividendos"}
        </button>
        {completas.length > 0 && (
          <span className="mono" style={{ marginLeft: "auto", fontSize: 13.5 }}>
            {num(completas.reduce((s, f) => s + (f.por_accion
              ? (parseFloat(f.qty) || 1) * (parseFloat(f.importe) || 0)
              : parseFloat(f.importe) || 0), 0), 2)} en total
          </span>)}
      </div>
      {msg && <div className={"aviso " + (msg.mal ? "mal" : "ok")}>{msg.mal || msg.ok}</div>}
      {filas.some((f) => f.existe === false) && (
        <div className="aviso ojo">
          <b>{filas.filter((f) => f.existe === false).map((f) => f.ticker).join(", ")}</b>: no se
          encontraron precios para ese ticker. Se puede cargar igual, pero revisá que esté bien
          escrito — un dividendo bajo un ticker que no existe queda suelto, sin sumarse al papel.
        </div>)}
      <div className="pie">
        Un dividendo <b>no toca la posición</b>: no suma papeles ni cambia el costo de nada.
        Entra como resultado del día que se cobró y, si es en pesos, se convierte a dólares con
        el MEP de esa fecha. Cargá todos los cobros juntos —de un papel o de varios— y se
        procesan de una sola vez; cada línea nueva hereda el ticker, las acciones y la moneda
        de la anterior. <b>Mirá la moneda</b>: se propone la del papel, pero un CEDEAR D cotiza
        en dólares y su dividendo suele acreditarse en pesos. Si dice USD y cargaste pesos, el
        importe queda multiplicado por el MEP.
      </div>
    </div>
  );
}

function PnlRealizado({ real, cartera, recargar }) {
  const [abierto, setAbierto] = useState(false);
  const [detalle, setDetalle] = useState(false);
  const trades = real.trades || [];
  const porTicker = Object.values(trades.reduce((acc, t) => {
    const x = acc[t.ticker] || (acc[t.ticker] = { ticker: t.ticker, n: 0, usd: 0,
                                                  origen: 0, activo: 0, fx: 0,
                                                  moneda: t.moneda });
    x.n += 1; x.usd += t.pnl_usd; x.origen += t.pnl_origen || 0;
    x.activo += t.pnl_activo_usd || 0; x.fx += t.pnl_fx_usd || 0;
    return acc;
  }, {})).sort((a, b) => b.usd - a.usd);
  const ganadores = porTicker.filter((x) => x.usd > 0).length;
  const enPesos = (real.total_origen || {}).ARS;
  const enDolar = (real.total_origen || {}).USD;

  return (
    <div className="panel">
      <h3 style={{ cursor: "pointer" }} onClick={() => setAbierto(!abierto)}>
        <span style={{ display: "flex", alignItems: "center", gap: 9 }}>
          <span style={{ fontSize: 11, color: "var(--texto-3)" }}>{abierto ? "▾" : "▸"}</span>
          Posiciones cerradas
        </span>
        <span style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 14 }}>
          <span style={{ fontSize: 12.5, color: "var(--texto-3)" }}>
            {real.n} operaciones</span>
          <span className={"mono " + signo(real.total_usd)} style={{ fontSize: 16, fontWeight: 700 }}>
            {usd(real.total_usd)}</span>
        </span>
      </h3>

      {!abierto ? (
        <>
          <div className="pie" style={{ marginTop: 4 }}>
            <b className={signo(real.total_activo_usd)}>{usd(real.total_activo_usd)}</b> de
            resultado de inversión {real.total_fx_usd < 0 ? "menos" : "más"}{" "}
            <b className={signo(real.total_fx_usd)}>{usd(Math.abs(real.total_fx_usd))}</b> de
            resultado por tipo de cambio.
            {enPesos != null && <> En moneda de origen: <b>{num(enPesos, 2)} ARS</b>
              {enDolar ? <> y <b>{num(enDolar, 2)} USD</b></> : null} — ese es el número que
              se puede cotejar contra el resumen del broker, que no sabe de MEP.</>}
          </div>
        </>
      ) : (
        <>
          <div style={{ display: "flex", gap: 8, margin: "10px 0 4px" }}>
            <div className="modos">
              {[[false, "Por activo"], [true, `Las ${real.n} operaciones`]].map(([k, txt]) => (
                <button key={String(k)} className={"modo" + (detalle === k ? " on" : "")}
                        onClick={() => setDetalle(k)}>{txt}</button>))}
            </div>
          </div>
          <div className="tabla-wrap"><table>
            {detalle ? (
              <>
                <thead><tr><th>Ticker</th><th>Compra</th><th>Venta</th><th className="n">Cantidad</th>
                  <th className="n">Precio compra</th><th className="n">Precio venta</th>
                  <th className="n">Dólar compra → venta</th>
                  <th className="n">Resultado origen</th>
                  <th className="n">Resultado inversión</th>
                  <th className="n">Resultado tipo de cambio</th>
                  <th className="n">Resultado USD</th></tr></thead>
                <tbody>{[...trades].sort((a, b) => (a.sell_date < b.sell_date ? 1 : -1)).map((t, i) => (
                  <tr key={i}>
                    <td className="mono">{t.ticker}{t.tipo === "dividendo" &&
                      <span className="chip ok" style={{ marginLeft: 6, minWidth: 0 }}>div</span>}</td>
                    <td className="mono">{t.buy_date}</td>
                    <td className="mono">{t.sell_date}</td>
                    <td className="n">{num(t.qty, 2)}</td>
                    <td className="n">{num(t.buy_price, 2)}</td>
                    <td className="n">{num(t.sell_price, 2)}</td>
                    <td className={"n " + signo(t.pnl_fx_usd)}>
                      {t.mep_compra && t.mep_venta
                        ? `${num(t.mep_compra, 2)} → ${num(t.mep_venta, 2)}  ` +
                          `(${t.mep_venta >= t.mep_compra ? "+" : ""}` +
                          `${num((t.mep_venta / t.mep_compra - 1) * 100, 1)}%)`
                        : "—"}</td>
                    <td className={"n " + signo(t.pnl_origen)}>
                      {num(t.pnl_origen, 2)} {t.moneda}</td>
                    <td className={"n " + signo(t.pnl_activo_usd)}>{usd(t.pnl_activo_usd)}</td>
                    <td className={"n " + (t.pnl_fx_usd ? "fx " + signo(t.pnl_fx_usd) : "")}>
                      {t.pnl_fx_usd ? usd(t.pnl_fx_usd) : "—"}</td>
                    <td className={"n " + signo(t.pnl_usd)}>{usd(t.pnl_usd)}</td>
                  </tr>))}</tbody>
              </>
            ) : (
              <>
                <thead><tr><th>Ticker</th><th className="n">Operaciones</th>
                  <th className="n">Resultado en su moneda</th>
                  <th className="n">Resultado inversión</th>
                  <th className="n">Resultado tipo de cambio</th>
                  <th className="n">Resultado en dólares</th></tr></thead>
                <tbody>{porTicker.map((x) => (
                  <tr key={x.ticker}>
                    <td className="mono">{x.ticker}</td>
                    <td className="n">{x.n}</td>
                    <td className={"n " + signo(x.origen)}>{num(x.origen, 2)} {x.moneda}</td>
                    <td className={"n " + signo(x.activo)}>{usd(x.activo)}</td>
                    <td className={"n " + (x.fx ? "fx " + signo(x.fx) : "")}>
                      {x.fx ? usd(x.fx) : "—"}</td>
                    <td className={"n " + signo(x.usd)}>{usd(x.usd)}</td>
                  </tr>))}
                  <tr style={{ fontWeight: 700 }}>
                    <td>NETO</td><td className="n">{real.n}</td>
                    <td className="n">{enPesos != null ? `${num(enPesos, 2)} ARS` : ""}
                      {enDolar != null ? ` · ${num(enDolar, 2)} USD` : ""}</td>
                    <td className={"n " + signo(real.total_activo_usd)}>{usd(real.total_activo_usd)}</td>
                    <td className={"n fx " + signo(real.total_fx_usd)}>{usd(real.total_fx_usd)}</td>
                    <td className={"n " + signo(real.total_usd)}>{usd(real.total_usd)}</td>
                  </tr>
                </tbody>
              </>
            )}
          </table></div>
          <div className="pie">
            <b>En su moneda</b> es lo que muestra el broker, que no sabe de MEP. El resultado
            en dólares se abre en dos: <b>resultado inversión</b> es lo que dejó el activo, y{" "}
            <b>resultado tipo de cambio</b> lo que el MEP le hizo al capital mientras estuvo
            invertido. Suman el neto exacto — la ganancia se convierte al MEP de la venta, que
            es el dólar con el que se cobró. Una operación que ya era en dólares no tiene
            resultado de tipo de cambio: no hubo exposición. Neteo FIFO contra las compras más viejas; los splits se
            prorratean sobre lo que había abierto. {ganadores} de {porTicker.length} tickers
            cerraron en verde.
          </div>
          <AltaDividendo cartera={cartera} recargar={recargar} />
        </>
      )}
    </div>
  );
}

/* Vive acá, junto a Posición, que es donde se muestra. Se perdió una vez al
   reescribir Riesgo y la app quedó rota sin que Babel lo notara: una referencia
   a un componente inexistente es un error de EJECUCIÓN, no de sintaxis. */
function MatrizCorrelaciones({ corr }) {
  const c = colores();
  const [enCaidas, setEnCaidas] = useState(false);
  const m = enCaidas && corr.matriz_caidas ? corr.matriz_caidas : corr.matriz;
  const tono = { defensiva: "ok", mixta: "ojo", agresiva: "mal" }[corr.caracter];
  return (
    <div className="panel">
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
            bargap: 0.02, margin: { t: 28 },
            xaxis: { title: "Retorno de un día", ticksuffix: " %" },
            yaxis: { title: "Cantidad de días" },
            shapes: [linea(d.var95_pct, c.alerta), linea(d.var99_pct, c.negativo),
                     linea(dist.media_pct, c.texto3, 1)],
            // Las tres marcas caen en pocos puntos porcentuales, así que cada
            // una se ancla hacia afuera de su propia línea: centradas se
            // escribían una encima de la otra.
            annotations: [
              { x: d.var99_pct, y: 1, yref: "paper", text: "1 de cada 100", showarrow: false,
                font: { size: 10, color: c.negativo }, yanchor: "bottom", xanchor: "right" },
              { x: d.var95_pct, y: 1, yref: "paper", text: "día malo", showarrow: false,
                font: { size: 10, color: c.alerta }, yanchor: "bottom", xanchor: "left" },
              { x: dist.media_pct, y: 1, yref: "paper", text: "día promedio", showarrow: false,
                font: { size: 10, color: c.texto3 }, yanchor: "bottom", xanchor: "left" }] }} />
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

/* ── Riesgo ──
   Una sola página que se lee de arriba abajo, no sub-pestañas: el riesgo se
   entiende encadenando —cuánto puedo perder, cuándo se disparó, qué activo lo
   trae, cuánto es del dólar, qué pasó en crisis reales, y qué haría para
   bajarlo—. Saltar de pestaña rompía esa lectura. */
function Riesgo({ d, cartera, extras }) {
  return (
    <>
      <KpisRiesgo d={d} />
      <Seccion titulo="¿Cuándo se disparó el riesgo?" />
      <RiesgoEvolucion cartera={cartera} />
      <Seccion titulo="El riesgo de cada activo por separado" />
      <RiesgoActivos cartera={cartera} />
      <Seccion titulo="Quién trae el riesgo de la cartera" />
      <RiesgoResumen d={d} />
      <Seccion titulo="¿Cuánto del riesgo es el dólar?" />
      <RiesgoCambiario cartera={cartera} />
      <Seccion titulo="Qué habría pasado en crisis reales" />
      {extras.stress ? <Stress d={extras.stress} /> : <div className="cargando">Calculando…</div>}
      <Seccion titulo="Ponerle un techo al riesgo" />
      <RiesgoLimite cartera={cartera} d={d} />
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
          <h3>Peso contra aporte al riesgo</h3>
          <Grafico alto={Math.max(230, contrib.length * 40 + 110)}
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
        </div>)}
    </>
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

  const ev = d.eventos || [];
  // Los eventos se dibujan como marcadores sobre la propia serie del VaR, no
  // como líneas punteadas de un píxel: así se ven, se pueden apuntar con el
  // mouse y se lee qué pasó ese día. Antes estaban pero eran invisibles y mudos.
  const porFecha = Object.fromEntries(d.serie.map((p) => [p.fecha, p.var95_pct]));
  const cercano = (f) => porFecha[f] ??
    (d.serie.reduce((mejor, p) =>
      Math.abs(new Date(p.fecha) - new Date(f)) < Math.abs(new Date(mejor.fecha) - new Date(f))
        ? p : mejor, d.serie[0]).var95_pct);

  return (
    <>
      <div className="panel">
        <h3>Pérdida en un día malo, a lo largo del tiempo</h3>
        <Grafico alto={400}
          datos={[
            { type: "scatter", mode: "lines", name: "día malo (VaR 95 %)",
              x: d.serie.map((p) => p.fecha), y: d.serie.map((p) => p.var95_pct),
              line: { color: c.negativo, width: 1.9 },
              hovertemplate: "%{x}<br>%{y:.2f} %<extra></extra>" },
            { type: "scatter", mode: "lines", name: "día muy malo (CVaR 95 %)",
              x: d.serie.map((p) => p.fecha), y: d.serie.map((p) => p.cvar95_pct),
              line: { color: c.alerta, width: 1.2, dash: "dot" },
              hovertemplate: "%{x}<br>%{y:.2f} %<extra></extra>" },
            { type: "scatter", mode: "markers", name: "eventos argentinos",
              x: ev.filter((e) => e.alcance === "AR").map((e) => e.fecha),
              y: ev.filter((e) => e.alcance === "AR").map((e) => cercano(e.fecha)),
              marker: { symbol: "diamond", size: 11, color: c.series[3],
                        line: { width: 1.2, color: c.panel } },
              text: ev.filter((e) => e.alcance === "AR").map((e) => e.descripcion),
              hovertemplate: "<b>%{x}</b><br>%{text}<extra></extra>" },
            { type: "scatter", mode: "markers", name: "eventos mundiales",
              x: ev.filter((e) => e.alcance !== "AR").map((e) => e.fecha),
              y: ev.filter((e) => e.alcance !== "AR").map((e) => cercano(e.fecha)),
              marker: { symbol: "circle", size: 10, color: c.series[4],
                        line: { width: 1.2, color: c.panel } },
              text: ev.filter((e) => e.alcance !== "AR").map((e) => e.descripcion),
              hovertemplate: "<b>%{x}</b><br>%{text}<extra></extra>" },
          ]}
          layout={{
            shapes: ev.map((e) => ({ type: "line", x0: e.fecha, x1: e.fecha, yref: "paper",
              y0: 0, y1: 1, line: { color: e.alcance === "AR" ? c.series[3] : c.series[4],
                                    width: 1, dash: "dot" }, opacity: 0.5 })),
            yaxis: { title: "Pérdida diaria", ticksuffix: " %" } }} />
        <div className="pie">
          VaR 95 % sobre las últimas {d.ventana_ruedas} ruedas en cada punto: cuando la línea
          baja, la cartera se volvió más riesgosa. Los <b>rombos</b> son eventos argentinos y
          los <b>círculos</b>, mundiales — apuntalos con el mouse para leer qué pasó.
          Son contexto, no causa.
        </div>
      </div>
      <div className="panel">
        <h3>Los {ev.length} eventos del período</h3>
        <div className="tabla-wrap"><table>
          <thead><tr><th>Fecha</th><th className="c">Alcance</th><th>Qué pasó</th>
            <th className="n">Día malo por entonces</th></tr></thead>
          <tbody>{ev.slice().reverse().map((e, i) => (
            <tr key={i}><td className="mono">{e.fecha}</td>
              <td><span className="chip">{e.alcance}</span></td><td>{e.descripcion}</td>
              <td className="n neg">{pct(cercano(e.fecha))}</td></tr>))}</tbody>
        </table></div>
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
          <Grafico alto={Math.max(210, enPesos.length * 40 + 110)}
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
  const c = colores();
  const sugerido = Math.abs(d.var95_pct * 0.8).toFixed(2);
  const [objetivo, setObjetivo] = useState(sugerido);
  // `pedido` es el límite que ya se calculó; `objetivo`, el que el usuario está
  // tipeando. Separarlos deja que el panel se arme solo al entrar —con un 20 %
  // menos de riesgo que hoy, que es la pregunta que uno viene a hacerse— sin
  // disparar una optimización por cada tecla.
  const [pedido, setPedido] = useState(sugerido);
  const [r, setR] = useState(null);
  const [cargando, setCargando] = useState(false);

  useEffect(() => {
    let vivo = true;
    setCargando(true); setR(null);
    api(`/api/riesgo/${encodeURIComponent(cartera)}/ajustar?var=${pedido}`)
      .then((x) => { if (!vivo) return; setR(x); setCargando(false); });
    return () => { vivo = false; };
  }, [pedido, cartera]);

  const calcular = () => setPedido(objetivo);

  const ordenes = (r?.ordenes || []).filter((o) => o.accion !== "MANTENER");

  return (
    <>
      <div className="panel">
        <h3>¿Qué tendría que comprar y vender para no pasar de cierto riesgo?</h3>
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginTop: 10 }}>
          <span>No quiero perder más de</span>
          <input type="number" step="0.05" min="0.05" value={objetivo}
                 onChange={(e) => setObjetivo(e.target.value)} style={{ width: 90 }}
                 onKeyDown={(e) => e.key === "Enter" && calcular()} />
          <span>% en un día malo.</span>
          <button className="btn primario" onClick={calcular}
                  disabled={cargando || objetivo === pedido}>
            {cargando ? "Optimizando…" : "Recalcular"}</button>
          <span className="pie" style={{ marginTop: 0 }}>
            Hoy: {pct(d.var95_pct)} ({usd(d.var95_usd)}) · abajo está resuelto
            para {pct(pedido)}, cambiá el número para probar otro techo.</span>
        </div>
        <div className="pie">
          La cartera queda <b>invertida al 100 %</b>: se cambia la mezcla, no el nivel de
          exposición. Se busca el movimiento más chico que cumple el límite, para no deshacer
          decisiones que ya tomaste.
        </div>
      </div>

      {r?.error && <div className="aviso mal">{r.error}</div>}
      {r?.ya_cumple && <div className="aviso ok">{r.mensaje}</div>}
      {r && r.alcanzable === false && (
        <>
          <div className="aviso ojo"><b>Ese límite no se alcanza solo rebalanceando.</b> {r.mensaje}</div>
          <div className="panel">
            <h3>La mezcla de menor riesgo posible con estos activos</h3>
            <div className="tabla-wrap"><table>
              <thead><tr><th>Activo</th><th className="n">Peso</th></tr></thead>
              <tbody>{Object.entries(r.pesos_minimo_riesgo).sort((a, b) => b[1] - a[1]).map(([t, w]) => (
                <tr key={t}><td className="mono">{t}</td><td className="n">{pct(w, 1)}</td></tr>))}</tbody>
            </table></div>
            <div className="pie">
              Llega a {pct(r.var_minimo_posible_pct)} de pérdida en un día malo, contra
              {" "}{pct(r.var_actual_pct)} de tu cartera actual.
            </div>
          </div>
        </>
      )}

      {r && r.alcanzable && !r.ya_cumple && (
        <>
          <div className="fila f2">
            <div className="panel">
              <h3>Antes y después</h3>
              <div className="tabla-wrap"><table>
                <thead><tr><th></th><th className="n">Hoy</th><th className="n">Rebalanceada</th>
                  <th className="n">Cambio</th></tr></thead>
                <tbody>
                  {[["Pérdida en un día malo", "var95_pct", true],
                    ["Volatilidad anual", "volatilidad_pct", true],
                    ["Retorno anual esperado", "retorno_anual_pct", false]].map(([et, k, menosEsMejor]) => {
                    const a = r.antes[k], b = r.despues[k];
                    const mejora = menosEsMejor ? Math.abs(b) < Math.abs(a) : b > a;
                    return (
                      <tr key={k}><td>{et}</td>
                        <td className="n">{pct(a)}</td>
                        <td className="n">{pct(b)}</td>
                        <td className={"n " + (mejora ? "pos" : "neg")}>
                          {(b - a >= 0 ? "+" : "") + num(b - a, 2)} pp</td>
                      </tr>);
                  })}
                </tbody>
              </table></div>
              <div className={"aviso " + (r.despues.retorno_anual_pct < r.antes.retorno_anual_pct ? "ojo" : "ok")}>
                Bajar el riesgo cuesta retorno: pasás de {pct(r.antes.retorno_anual_pct)} a{" "}
                {pct(r.despues.retorno_anual_pct)} anual esperado. Ese es el precio del límite
                que pediste, y conviene verlo antes de operar.
              </div>
              <div className="pie">{r.nota_metodo}</div>
            </div>

            <div className="panel">
              <h3>Cómo se mueven los pesos</h3>
              <Grafico alto={Math.max(240, r.ordenes.length * 40 + 110)}
                datos={[
                  { type: "bar", orientation: "h", name: "hoy",
                    y: r.ordenes.map((o) => o.ticker).reverse(),
                    x: r.ordenes.map((o) => o.peso_actual_pct).reverse(),
                    marker: { color: c.texto3 } },
                  { type: "bar", orientation: "h", name: "rebalanceada",
                    y: r.ordenes.map((o) => o.ticker).reverse(),
                    x: r.ordenes.map((o) => o.peso_nuevo_pct).reverse(),
                    marker: { color: c.acento } }]}
                layout={{ barmode: "group", margin: { l: 82 }, xaxis: { ticksuffix: " %" } }} />
              <div className="pie">
                Rotación {pct(r.rotacion_pct)}: hay que operar {usd(r.a_operar_usd)} entre
                compras y ventas sobre una cartera de {usd(r.valor_total)}.
              </div>
            </div>
          </div>

          <div className="panel">
            <h3>Órdenes</h3>
            <div className="tabla-wrap"><table>
              <thead><tr><th className="c">Acción</th><th>Activo</th><th className="n">Peso hoy</th>
                <th className="n">Peso nuevo</th><th className="n">Monto</th>
                <th className="n">Unidades</th></tr></thead>
              <tbody>{ordenes.map((o) => (
                <tr key={o.ticker}>
                  <td><span className={"chip " + (o.accion === "COMPRAR" ? "ok" : "mal")}>{o.accion}</span></td>
                  <td className="mono">{o.ticker}</td>
                  <td className="n">{pct(o.peso_actual_pct, 1)}</td>
                  <td className="n">{pct(o.peso_nuevo_pct, 1)}</td>
                  <td className={"n " + signo(o.monto_usd)}>{usd(Math.abs(o.monto_usd))}</td>
                  <td className="n">{o.unidades == null ? "—" : num(Math.abs(o.unidades), 2)}</td>
                </tr>))}</tbody>
            </table></div>
            <div className="pie">{r.nota}</div>
          </div>
        </>
      )}
    </>
  );
}

/* ── Optimización ──
   Markowitz, precios objetivo y Black-Litterman en una sola pestaña. Eran tres
   lecturas del mismo problema —cómo debería estar repartida la cartera— y
   tenerlas separadas obligaba a comparar de memoria entre pantallas. */
function Markowitz({ d, cartera, bench, extras }) {
  const c = colores();
  const [objetivo, setObjetivo] = useState("max_sharpe");
  const [bt, setBt] = useState(null);
  const [meses, setMeses] = useState(6);

  // El backtest se dispara solo: hacerlo esperar un clic escondía justamente el
  // dato que relativiza todo lo demás de esta pestaña.
  useEffect(() => {
    let vivo = true;
    setBt(null);
    api(`/api/markowitz/${encodeURIComponent(cartera)}/backtest?meses=${meses}&benchmark=${bench}`)
      .then((r) => vivo && setBt(r));
    return () => { vivo = false; };
  }, [cartera, meses, bench]);

  const acciones = objetivo === "max_sharpe" ? d.acciones_max_sharpe : d.acciones_min_varianza;
  const destino = objetivo === "max_sharpe" ? d.max_sharpe : d.min_varianza;

  const frontera = [
    { type: "scattergl", mode: "markers", name: "carteras posibles",
      x: d.nube?.vol, y: d.nube?.ret, marker: { size: 3, color: c.texto3, opacity: 0.28 },
      hoverinfo: "skip" },
    { type: "scatter", mode: "lines", name: "frontera eficiente",
      x: (d.frontera || []).map((p) => p.vol), y: (d.frontera || []).map((p) => p.ret),
      line: { color: c.acento, width: 2.5 } },
    { type: "scatter", mode: "markers+text", name: "tu cartera",
      x: [d.actual.vol_pct], y: [d.actual.ret_pct], text: ["actual"], textposition: "top center",
      marker: { size: 17, color: c.marcaActual, symbol: "star",
                line: { width: 1, color: c.panel } } },
    { type: "scatter", mode: "markers+text", name: "máximo Sharpe",
      x: [d.max_sharpe.vol_pct], y: [d.max_sharpe.ret_pct], text: ["óptima"], textposition: "top center",
      marker: { size: 14, color: c.marcaOptima, symbol: "triangle-up",
                line: { width: 1, color: c.panel } } },
    { type: "scatter", mode: "markers+text", name: "mínima varianza",
      x: [d.min_varianza.vol_pct], y: [d.min_varianza.ret_pct], text: ["mín. riesgo"],
      textposition: "bottom center", marker: { size: 12, color: c.series[1], symbol: "diamond" } },
  ];

  return (
    <>
      <div className="kpis">
        <Kpi etiqueta="Tu Sharpe" valor={num(d.actual.sharpe, 3)}
             sub={`${pct(d.actual.ret_pct)} / ${pct(d.actual.vol_pct)}`} />
        <Kpi etiqueta="Sharpe óptimo" valor={num(d.max_sharpe.sharpe, 3)} tono="pos"
             sub={`${pct(d.max_sharpe.ret_pct)} / ${pct(d.max_sharpe.vol_pct)}`} />
        <Kpi etiqueta="Mínima varianza" valor={pct(d.min_varianza.vol_pct)}
             sub={`retorno ${pct(d.min_varianza.ret_pct)}`} />
        <Kpi etiqueta="Tasa libre" valor={pct(d.rf * 100)} sub={d.rf_label} />
      </div>

      <div className="fila f2">
        <div className="panel">
          <h3>Frontera eficiente</h3>
          <Grafico datos={frontera} alto={380}
                   layout={{ xaxis: { title: "Volatilidad anual", ticksuffix: " %" },
                             yaxis: { title: "Retorno anual", ticksuffix: " %" } }} />
          <div className="pie">
            La nube gris son carteras posibles con tus mismos activos; la línea es lo mejor
            alcanzable para cada nivel de riesgo. Tu cartera nunca puede quedar por encima.
          </div>
        </div>

        <div className="panel">
          <h3>Cómo quedarían los pesos</h3>
          <Grafico alto={340}
            datos={[
              { type: "bar", name: "hoy", x: d.tickers, y: d.actual.pesos,
                marker: { color: c.texto3 },
                hovertemplate: "%{x}: %{y:.1f} %<extra>hoy</extra>" },
              { type: "bar", name: "máximo Sharpe", x: d.tickers, y: d.max_sharpe.pesos,
                marker: { color: c.positivo },
                hovertemplate: "%{x}: %{y:.1f} %<extra>máx Sharpe</extra>" },
              { type: "bar", name: "mínima varianza", x: d.tickers, y: d.min_varianza.pesos,
                marker: { color: c.series[1] },
                hovertemplate: "%{x}: %{y:.1f} %<extra>mín varianza</extra>" }]}
            layout={{ barmode: "group", yaxis: { title: "Peso en la cartera", ticksuffix: " %" },
                      xaxis: { tickangle: -35 } }} />
          <div className="pie">
            Máximo Sharpe busca el mejor retorno por unidad de riesgo; mínima varianza, la
            cartera más tranquila sin mirar el retorno esperado —que es el dato peor estimado
            del modelo, y por eso suele ser la más robusta—.
          </div>
        </div>
      </div>

      <div className="fila f2">
        <div className="panel">
          <h3>Qué habría que operar
            <span style={{ marginLeft: "auto", display: "flex", gap: 3,
                           background: "var(--panel-2)", padding: 3, borderRadius: 8 }}>
              {[["max_sharpe", "Máximo Sharpe"], ["min_varianza", "Mínima varianza"]].map(([k, t]) => (
                <button key={k} className={"modo" + (objetivo === k ? " on" : "")}
                        onClick={() => setObjetivo(k)}>{t}</button>))}
            </span>
          </h3>
          <div className="pie" style={{ marginTop: 2, marginBottom: 8 }}>
            Destino: {pct(destino.ret_pct)} de retorno con {pct(destino.vol_pct)} de
            volatilidad — Sharpe {num(destino.sharpe, 3)}.
          </div>
          <div className="tabla-wrap"><table>
            <thead><tr><th>Ticker</th><th className="n">Hoy</th><th className="n">Objetivo</th>
                       <th className="n">Diferencia</th><th className="c">Acción</th></tr></thead>
            <tbody>{(acciones || []).map((a) => (
              <tr key={a.ticker}>
                <td className="mono">{a.ticker}</td>
                <td className="n">{pct(a.peso_actual_pct, 1)}</td>
                <td className="n">{pct(a.peso_objetivo_pct, 1)}</td>
                <td className={"n " + signo(a.delta_usd)}>{usd(a.delta_usd)}</td>
                <td><span className={"chip " + (a.accion === "COMPRAR" ? "ok" : a.accion === "VENDER" ? "mal" : "")}>{a.accion}</span></td>
              </tr>))}</tbody>
          </table></div>
        </div>

        <div className="panel">
          <h3>¿Habría funcionado?
            <span style={{ marginLeft: "auto", display: "flex", gap: 3,
                           background: "var(--panel-2)", padding: 3, borderRadius: 8 }}>
              {[3, 6, 12].map((m) => (
                <button key={m} className={"modo" + (meses === m ? " on" : "")}
                        onClick={() => setMeses(m)}>{m} m</button>))}
            </span>
          </h3>
          {!bt ? <div className="cargando">Optimizando con datos viejos y midiendo después…</div>
           : bt.error ? <div className="aviso mal">{bt.error}</div> : (
            <>
              <Grafico alto={210}
                datos={Object.entries(bt.curvas).map(([n, v], i) => ({
                  type: "scatter", mode: "lines", name: n, x: bt.fechas, y: v,
                  line: { width: n === bt.ganadora ? 2.6 : 1.4,
                          color: c.series[i % c.series.length] } }))}
                layout={{ yaxis: { title: "Base 100" }, margin: { t: 6 } }} />
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

      <Seccion titulo="¿Y si además uso los precios objetivo?" />
      <ObjetivosYBL cartera={cartera} extras={extras} d={d} bench={bench} />
    </>
  );
}

/* ── Monte Carlo ── */

function MonteCarlo({ d, cartera }) {
  // Un solo botón para todo: el abanico abriéndose rueda a rueda y las
  // correlaciones moviéndose en el tiempo son la misma película contada dos
  // veces, y tenerlas en pestañas separadas obligaba a arrancar cada una a mano.
  const [corriendo, setCorriendo] = useState(false);
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

      <div className="panel" style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <button className="btn primario" onClick={() => setCorriendo(!corriendo)}>
          {corriendo ? "⏸ Detener la simulación" : "▶ Reproducir la simulación"}
        </button>
        <span style={{ fontSize: 12.5, color: "var(--texto-3)" }}>
          Mueve a la vez el abanico y las correlaciones: cómo se abre el rango de
          resultados rueda a rueda, y cómo se movió lo que los activos tienen en común.
        </span>
      </div>

      <DistribucionFinal d={d} corriendo={corriendo} />
      <McPorActivo cartera={cartera} horizonte={d.horizonte_ruedas} />
      <CorrelacionesAnimadas cartera={cartera} corriendo={corriendo} />
      <McMotores cartera={cartera} horizonte={d.horizonte_ruedas} />
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
        <Grafico alto={Math.max(280, todos.length * 44 + 110)}
          datos={[
            // El corte de color es el valor de HOY, no la mediana: rojo quiere decir
            // literalmente "termino con menos de lo que tengo". Cada mitad se recorta
            // contra el valor inicial, así que un activo cuyo abanico entero quedó de un
            // solo lado no dibuja la mitad que no existe.
            { type: "bar", orientation: "h", name: "termina con menos que hoy",
              y: todos.map((f) => f.ticker).reverse(),
              base: todos.map((f) => f.p5).reverse(),
              x: todos.map((f) => Math.max(0, Math.min(f.p95, f.valor_inicial) - f.p5)).reverse(),
              marker: { color: c.negativo, opacity: 0.55 },
              hovertemplate: "%{y}<extra></extra>" },
            { type: "bar", orientation: "h", name: "termina con más que hoy",
              y: todos.map((f) => f.ticker).reverse(),
              base: todos.map((f) => Math.max(f.p5, f.valor_inicial)).reverse(),
              x: todos.map((f) => Math.max(0, f.p95 - Math.max(f.p5, f.valor_inicial))).reverse(),
              marker: { color: c.positivo, opacity: 0.55 },
              hovertemplate: "%{y}<extra></extra>" },
            { type: "scatter", mode: "markers", name: "mediana",
              y: todos.map((f) => f.ticker).reverse(),
              x: todos.map((f) => f.mediana).reverse(),
              marker: { symbol: "line-ns-open", size: 16, color: c.texto,
                        line: { width: 2.5, color: c.texto } },
              hovertemplate: "%{y}: mediana $%{x:,.0f}<extra></extra>" }]}
          layout={{ barmode: "overlay", margin: { l: 82 },
                    xaxis: { title: "Valor a un año", tickprefix: "$" } }} />
        <div className="pie">
          El color se parte en lo que vale hoy: <b className="neg">rojo</b> es terminar con
          menos de lo que tenés, <b className="pos">verde</b> con más. La marca vertical es
          la mediana. La barra entera va del escenario malo (5 %) al bueno (95 %), o sea que
          cubre <b>el 90 % de los escenarios y no todos</b>: queda un 5 % peor que el extremo
          izquierdo, y de ese lado no hay piso dibujado.
        </div>
      </div>

      <div className="panel">
        <h3>Detalle</h3>
        <div className="tabla-wrap"><table>
          <thead><tr><th>Activo</th><th className="n">Peso</th><th className="n">Hoy</th>
            <th className="n">Mediana</th><th className="n">Escenario malo</th>
            <th className="n">Escenario bueno</th>
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
              <td className="n">{usd(f.p95, 0)}</td>
              <td className="n neg">{pct(f.perdida_var95_pct, 1)}</td>
              <td className="n">{pct(f.prob_ganancia, 1)}</td>
              <td className="n">{num(f.amplitud, 2)}×</td>
            </tr>))}</tbody>
        </table></div>
        <div className="aviso ok">
          <b>Diversificar vale {usd(d.ahorro_diversificacion_usd)} en el escenario malo.</b>{" "}
          {d.nota}
        </div>
        <div className="pie" style={{ lineHeight: 1.65 }}>
          <b>Cómo se lee cada fila.</b> Los cinco números de la simulación parten los
          escenarios en tramos de probabilidad conocida: <b>5 %</b> termina peor que el
          escenario malo, <b>45 %</b> entre el escenario malo y la mediana, <b>45 %</b>
          entre la mediana y el bueno, y <b>5 %</b> mejor que el bueno. Ojo con confundir
          ese corte con el de perder: el borde entre perder y ganar es la columna
          <i> hoy</i>, y <i>P(ganar)</i> es exactamente la probabilidad de terminar a su
          derecha — nominal en dólares, sin descontar inflación ni compararla contra una
          tasa sin riesgo.
          <br /><br />
          <b>Para comparar activos entre sí no sirve el largo de la barra</b>, que está en
          dólares y por lo tanto mezcla riesgo con tamaño de la posición: el que más pesa
          siempre parece el más incierto. Eso se mira en <i>Incertidumbre</i>, que es el
          ancho del abanico como múltiplo del valor de hoy — cuántas veces su propio valor
          separa al buen escenario del malo — y en <i>Pérdida</i>, que es cuánto cae desde
          hoy hasta el escenario malo. Un activo con incertidumbre alta <b>y</b> peso alto
          es el que decide el resultado de la cartera; el resto es ruido alrededor.
          <br /><br />
          <b>La fila CARTERA no es la suma de las de arriba.</b> Se simula la serie de la
          cartera ya ponderada, que arrastra las correlaciones reales entre los papeles, y
          por eso su incertidumbre es menor que la del activo que la domina. Los escenarios
          malos de cada activo tampoco ocurren juntos: cada p5 es el suyo, aislado.
          <br /><br />
          <b>Lo que hay que tomar con pinzas es el centro, no el ancho.</b> Cada activo se
          simula con su propio μ y σ históricos, así que un papel que viene subiendo
          proyecta mediana al alza sólo porque así se movió antes. La forma del abanico es
          mucho más confiable que dónde está parado.
        </div>
      </div>
    </>
  );
}

function CorrelacionesAnimadas({ cartera, corriendo }) {
  const c = colores();
  const [d, setD] = useState(null);
  const [i, setI] = useState(0);

  useEffect(() => { setD(null); setI(0);
    api(`/api/montecarlo/${encodeURIComponent(cartera)}/correlaciones`).then(setD); }, [cartera]);

  useEffect(() => { if (corriendo) setI(0); }, [corriendo]);

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
            <input type="range" min="0" max={d.cuadros.length - 1} value={i}
                   onChange={(e) => setI(+e.target.value)}
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

function McMotores({ cartera, horizonte }) {
  const [motores, setMotores] = useState(null);

  // Antes había que apretar un botón para pedirlos. Ya no: es una tabla de cuatro
  // filas y la pregunta que contesta —¿el resultado depende del supuesto de
  // distribución?— hay que hacérsela siempre, no solo cuando uno se acuerda.
  useEffect(() => { setMotores(null);
    api(`/api/montecarlo/${encodeURIComponent(cartera)}/motores?horizonte=${horizonte}`)
      .then(setMotores);
  }, [cartera, horizonte]);

  return (
    <div className="panel">
      <h3>¿Cambia según el supuesto de distribución?</h3>
      {!motores ? <div className="cargando">Comparando los tres motores…</div>
       : motores.error ? <div className="aviso mal">{motores.error}</div> : (
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
  );
}

function DistribucionFinal({ d, corriendo }) {
  const c = colores();
  const [paso, setPaso] = useState(0);
  const dist = d.distribucion || {};
  const a = d.abanico || {};

  useEffect(() => { if (corriendo) setPaso(0); }, [corriendo]);

  useEffect(() => {
    if (!corriendo) return;
    const id = setTimeout(() => setPaso((x) => (x + 1) % (a.dias?.length || 1)), 90);
    return () => clearTimeout(id);
  }, [corriendo, paso, a.dias]);

  const hasta = corriendo ? paso + 1 : (a.dias?.length || 0);
  const corte = (arr) => (arr || []).slice(0, hasta);

  // El abanico se parte en la línea de hoy: abajo es plata perdida, arriba es
  // plata ganada, y son dos cosas distintas aunque el gráfico las dibuje juntas.
  // Cada mitad se recorta contra el valor inicial —min para la de abajo, max
  // para la de arriba— así que si el abanico entero quedó de un solo lado, la
  // otra mitad se aplana en cero en vez de pintar una franja que no existe.
  const V = d.valor_inicial;
  const bajo = (arr) => corte(arr).map((v) => Math.min(v, V));
  const alto = (arr) => corte(arr).map((v) => Math.max(v, V));
  const banda = (lo, hi, alfa, nombre) => [
    { type: "scatter", x: corte(a.dias), y: bajo(hi), mode: "lines", line: { width: 0 },
      showlegend: false, hoverinfo: "skip" },
    { type: "scatter", x: corte(a.dias), y: bajo(lo), mode: "lines", line: { width: 0 },
      fill: "tonexty", fillcolor: c.negativo + alfa, name: nombre + " · pierde",
      hoverinfo: "skip" },
    { type: "scatter", x: corte(a.dias), y: alto(hi), mode: "lines", line: { width: 0 },
      showlegend: false, hoverinfo: "skip" },
    { type: "scatter", x: corte(a.dias), y: alto(lo), mode: "lines", line: { width: 0 },
      fill: "tonexty", fillcolor: c.acento + alfa, name: nombre + " · gana",
      hoverinfo: "skip" },
  ];

  return (
    <>
      <div className="panel">
        <h3>Cómo se abre el abanico</h3>
        <Grafico alto={320}
          datos={[
            ...banda(a.p5, a.p95, "22", "9 de cada 10 casos"),
            ...banda(a.p25, a.p75, "44", "la mitad de los casos"),
            { type: "scatter", x: corte(a.dias), y: corte(a.p50), mode: "lines",
              name: "mediana", line: { color: c.texto, width: 2.5 } },
          ]}
          layout={{ xaxis: { title: "Ruedas hacia adelante",
                             range: [0, a.dias?.[a.dias.length - 1] || 1] },
                    yaxis: { title: "Valor en dólares",
                             range: [Math.min(...(a.p5 || [0])) * 0.95,
                                     Math.max(...(a.p95 || [1])) * 1.05] },
                    shapes: [{ type: "line", xref: "paper", x0: 0, x1: 1,
                               y0: V, y1: V,
                               line: { color: c.texto3, width: 2, dash: "dot" } }] }} />
        <div className="pie">
          La incertidumbre no crece de golpe: se abre con la raíz del tiempo. La línea
          punteada es lo que vale hoy, y todo lo pintado en rojo abajo es la parte de los
          escenarios en la que terminás con menos de lo que tenés.{" "}
          {corriendo && <b>Rueda {a.dias?.[paso]} de {a.dias?.[a.dias.length - 1]}.</b>}
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
          layout={{ bargap: 0.02, margin: { t: 26 },
                    xaxis: { title: "Valor final", tickprefix: "$" },
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
          El mejor ajuste teórico es <b>{dist.mejor_ajuste}</b>
          {dist.mejor_ajuste === "lognormal"
            ? <> — es lo esperable: un precio no puede ser negativo, así que la distribución
                de valores finales queda sesgada hacia arriba y la campana normal se queda
                corta en los dos extremos.</>
            : <>: en este horizonte la campana normal describe los valores finales tan bien
                como la lognormal.</>}
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

  // Los tres índices se comparan solos. Con un R² bajo, saber cuál de los tres
  // explica la cartera es justamente lo que hay que mirar: dejarlo detrás de un
  // botón era esconder la respuesta a la advertencia que da el panel de arriba.
  useEffect(() => {
    let vivo = true;
    setTodos(null);
    api(`/api/capm/${encodeURIComponent(cartera)}/benchmarks`)
      .then((r) => vivo && setTodos(r));
    return () => { vivo = false; };
  }, [cartera]);
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
          {!todos ? <div className="cargando">Midiendo los tres índices…</div>
           : todos.error ? <div className="aviso mal">{todos.error}</div> : (
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
        <Grafico alto={Math.max(230, a.length * 40 + 110)}
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
                     <th className="n">3 meses</th><th className="c">Señal</th>
                     <th className="n">1 mes</th><th className="c">Entrada</th>
                     <th>Qué significa</th></tr></thead>
          <tbody>{a.map((x) => (
            <tr key={x.ticker}>
              <td className="mono">{x.ticker}</td>
              <td className={"n " + signo(x.mom_12_1_pct)}>{pct(x.mom_12_1_pct, 1)}</td>
              <td className="n">{pct(x.mom_12m_pct, 1)}</td>
              <td className={"n " + signo(x.mom_3m_pct)}>{pct(x.mom_3m_pct, 1)}</td>
              <td><span className={"chip " + (x.señal === "FAVORABLE" ? "ok" : x.señal === "EVITAR" ? "mal" : x.señal === "ESPERAR" ? "ojo" : "")}>{x.señal}</span></td>
              {/* El mes va después de la señal y sin color de signo: acá un
                  número negativo es una buena noticia para el que compra, así
                  que pintarlo de rojo diría lo contrario de lo que significa. */}
              <td className="n">{pct(x.mom_1m_pct, 1)}</td>
              <td title={x.entrada_texto}>
                <span className={"chip " + (x.entrada === "BUEN PRECIO" ? "ok"
                                          : x.entrada === "CARO" ? "ojo" : "")}>{x.entrada}</span>
              </td>
              <td style={{ fontSize: 12.5, color: "var(--texto-2)" }}>
                {x.veredicto}
                {x.entrada !== "—" && x.entrada !== "NORMAL" &&
                  <> <b>{x.entrada_texto}</b></>}
              </td>
            </tr>))}</tbody>
        </table></div>
        <div className="pie">
          Las tres primeras columnas dicen <b>qué</b> tiene viento a favor; el último mes dice
          <b> a qué precio conviene entrar</b>, y se lee al revés: a un mes no hay momentum,
          hay reversión — es el mismo efecto que el 12−1 saltea para no ensuciarse. Un papel
          con tendencia buena que subió 15 % en el mes no deja de ser bueno: está caro hoy.
        </div>
      </div>
    </>
  );
}

/* ── Precios objetivo + Black-Litterman ── */

function ObjetivosYBL({ cartera, extras, d, bench }) {
  const [manuales, setManuales] = useState({});
  const [bl, setBl] = useState(null);
  const [editando, setEditando] = useState(null);
  const obj = extras?.objetivos;

  // BL corre solo, con las views de analistas, y se recalcula cuando el usuario
  // impone una opinión propia. No hay botón: es el modo normal de uso.
  useEffect(() => {
    let vivo = true;
    if (Object.keys(manuales).length === 0) { setBl(extras?.bl || null); return; }
    setBl("cargando");
    api(`/api/blacklitterman/${encodeURIComponent(cartera)}`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ manuales, benchmark: bench }) })
      .then((r) => vivo && setBl(r));
    return () => { vivo = false; };
  }, [manuales, cartera, bench, extras?.bl]);

  if (!obj) return <div className="cargando">Buscando precios objetivo…</div>;
  if (obj.error) return <div className="aviso mal">{obj.error}</div>;

  const guardar = (ticker, cfg) => {
    setManuales((m) => ({ ...m, [ticker]: cfg }));
    setEditando(null);
  };
  const borrar = (ticker) =>
    setManuales((m) => { const n = { ...m }; delete n[ticker]; return n; });

  return (
    <>
      <div className="panel">
        <h3>Precio objetivo y momento de entrada</h3>
        <div className="tabla-wrap"><table>
          <thead><tr><th>Ticker</th><th className="n">Hoy</th><th className="n">Objetivo</th>
            <th className="n">Upside</th><th className="c">Momentum</th><th className="c">Combinada</th>
            <th className="c">Tu opinión</th></tr></thead>
          <tbody>{(obj.por_activo || []).map((x) => {
            const mv = manuales[x.ticker];
            return (
              <tr key={x.ticker}>
                <td className="mono">{x.ticker}</td>
                <td className="n">{usd(x.actual)}</td>
                <td className="n">{x.objetivo_medio ? usd(x.objetivo_medio) : "—"}</td>
                <td className={"n " + signo(x.upside_pct)}>
                  {x.upside_pct == null ? "—" : pct(x.upside_pct, 1)}</td>
                <td><span className={"chip " + (x.momentum === "FAVORABLE" ? "ok"
                      : x.momentum === "EVITAR" ? "mal"
                      : x.momentum === "ESPERAR" ? "ojo" : "")}>{x.momentum || "—"}</span></td>
                <td><span className={"chip " + (x.combinada === "COMPRAR" ? "ok"
                      : x.combinada === "CARO" || x.combinada === "REDUCIR" ? "mal"
                      : x.combinada === "ESPERAR GIRO" ? "ojo" : "")}>{x.combinada}</span></td>
                <td style={{ textAlign: "center" }}>
                  {mv ? (
                    <span style={{ display: "flex", gap: 6, alignItems: "center",
                                   justifyContent: "center" }}>
                      <span className="chip ojo">{mv.modo === "B2" ? `evento ${mv.meses} m` : "propia"}</span>
                      <span className="mono" style={{ fontSize: 11.5 }}>{mv.bajo}–{mv.alto}</span>
                      <button className="btn" style={{ padding: "1px 7px", fontSize: 11 }}
                              onClick={() => borrar(x.ticker)}>✕</button>
                    </span>
                  ) : (
                    <button className="btn" style={{ padding: "2px 9px", fontSize: 12 }}
                            onClick={() => setEditando(x)}>Fijar</button>)}
                </td>
              </tr>);
          })}</tbody>
        </table></div>
        <div className="pie">
          El precio objetivo dice <b>cuánto</b> puede valer; el momentum, <b>cuándo</b>. Un
          objetivo alto con la acción cayendo no es una compra: es esperar el giro. Si tenés una
          opinión propia sobre un papel —o si no hay cobertura de analistas, como pasa con las
          small caps argentinas— fijala vos y pisa al consenso.
        </div>
      </div>

      {editando && <EditorView activo={editando} onGuardar={guardar}
                               onCerrar={() => setEditando(null)} />}

      {bl === "cargando" ? <div className="cargando">Recalculando con tu opinión…</div>
       : !bl ? <div className="cargando">Calculando Black-Litterman…</div>
       : bl.error ? <div className="aviso mal">{bl.error}</div>
       : <BlackLitterman bl={bl} actual={d.actual} />}
    </>
  );
}

function EditorView({ activo, onGuardar, onCerrar }) {
  const [modo, setModo] = useState("B1");
  const [bajo, setBajo] = useState((activo.actual * 0.9).toFixed(2));
  const [alto, setAlto] = useState((activo.actual * 1.2).toFixed(2));
  const [meses, setMeses] = useState(3);

  const medio = (parseFloat(bajo) + parseFloat(alto)) / 2;
  const bruto = activo.actual ? medio / activo.actual - 1 : 0;
  const anualizado = modo === "B2" ? Math.pow(1 + bruto, 12 / Math.max(1, meses)) - 1 : bruto;
  const anchoPct = medio > 0 ? (parseFloat(alto) - parseFloat(bajo)) / medio * 100 : 100;
  const confianza = Math.round(Math.max(10, Math.min(90, 90 - anchoPct)));

  return (
    <div className="panel" style={{ borderLeft: "4px solid var(--acento)" }}>
      <h3>Tu opinión sobre {activo.ticker}
        <button className="btn" style={{ marginLeft: "auto", padding: "3px 10px", fontSize: 12 }}
                onClick={onCerrar}>Cancelar</button>
      </h3>
      <div className="modos" style={{ width: "fit-content", margin: "10px 0" }}>
        {[["B1", "Opinión propia"], ["B2", "Evento corporativo"]].map(([k, t]) => (
          <button key={k} className={"modo" + (modo === k ? " on" : "")}
                  onClick={() => setModo(k)}>{t}</button>))}
      </div>
      <div style={{ display: "flex", gap: 12, alignItems: "flex-end", flexWrap: "wrap" }}>
        <label style={{ fontSize: 11.5, color: "var(--texto-3)" }}>Precio piso<br />
          <input type="number" step="0.01" value={bajo} style={{ width: 110, marginTop: 3 }}
                 onChange={(e) => setBajo(e.target.value)} /></label>
        <label style={{ fontSize: 11.5, color: "var(--texto-3)" }}>Precio techo<br />
          <input type="number" step="0.01" value={alto} style={{ width: 110, marginTop: 3 }}
                 onChange={(e) => setAlto(e.target.value)} /></label>
        {modo === "B2" && (
          <label style={{ fontSize: 11.5, color: "var(--texto-3)" }}>Meses hasta que se resuelve<br />
            <input type="number" min="1" max="60" value={meses} style={{ width: 110, marginTop: 3 }}
                   onChange={(e) => setMeses(+e.target.value)} /></label>)}
        <button className="btn primario"
                onClick={() => onGuardar(activo.ticker, { modo, bajo: +bajo, alto: +alto, meses })}>
          Aplicar</button>
      </div>
      <div className="aviso ok">
        Hoy cotiza {usd(activo.actual)}. Tu rango da un precio medio de {usd(medio)},
        o sea <b>{pct(bruto * 100, 1)}</b>
        {modo === "B2" && <> en {meses} {meses === 1 ? "mes" : "meses"}, que anualizado
          compuesto son <b>{pct(anualizado * 100, 1)}</b></>}.
        {" "}Confianza estimada: <b>{confianza} %</b>.
      </div>
      <div className="pie">
        La confianza sale del <b>ancho del rango</b>, no se pide como número: nadie sabe
        responder "¿qué tan seguro estás del 0 al 100?", pero todos saben entre qué precios
        creen que va a estar. Un rango angosto es una opinión firme. El tope es 90 % aunque
        el rango sea de un centavo — con certeza total el modelo concentra todo en ese activo.
        {modo === "B2" && <> El modo <b>evento corporativo</b> existe para casos como una OPA:
          el plazo real cambia el retorno anualizado y por lo tanto el peso que el modelo le da.</>}
      </div>
    </div>
  );
}

function BlackLitterman({ bl, actual }) {
  const c = colores();
  const acc = bl.acciones || [];
  const manuales = (bl.views_aplicadas || []).filter((v) => v.manual);

  // Comparación contra la cartera de hoy: un retorno esperado suelto no dice
  // nada si no se ve contra qué se compara.
  const delta = (nuevo, viejo) => nuevo == null || viejo == null ? null : nuevo - viejo;
  const dRet = delta(bl.ret_bl_pct, actual?.ret_pct);
  const dVol = delta(bl.vol_bl_pct, actual?.vol_pct);
  const dShr = delta(bl.sharpe_bl, actual?.sharpe);
  // La flecha marca la DIRECCIÓN del cambio; el color dice si eso es bueno o
  // malo. Mezclar las dos cosas en la flecha hacía que una volatilidad que sube
  // se mostrara con ▼ — el dato correcto contando exactamente lo contrario.
  const flecha = (v) => v == null || v === 0 ? "" : (v > 0 ? "▲ " : "▼ ");
  const tono = (v, mejorSiSube = true) => v == null ? "" :
    ((v > 0) === mejorSiSube ? "pos" : v === 0 ? "" : "neg");

  return (
    <>
      <div className="kpis">
        <Kpi etiqueta="Retorno esperado" valor={pct(bl.ret_bl_pct)} tono={tono(dRet)}
             sub={dRet == null ? null : `${flecha(dRet)}${num(Math.abs(dRet), 2)} pp vs tu cartera (${pct(actual?.ret_pct)})`} />
        <Kpi etiqueta="Volatilidad" valor={pct(bl.vol_bl_pct)} tono={tono(dVol, false)}
             sub={dVol == null ? null : `${flecha(dVol)}${num(Math.abs(dVol), 2)} pp vs ${pct(actual?.vol_pct)}`} />
        <Kpi etiqueta="Sharpe" valor={num(bl.sharpe_bl, 3)} tono={tono(dShr)}
             sub={dShr == null ? null : `${flecha(dShr)}${num(Math.abs(dShr), 3)} vs ${num(actual?.sharpe, 3)}`} />
        <Kpi etiqueta="Aversión al riesgo (δ)" valor={num(bl.delta, 2)} sub={bl.delta_label} />
        <Kpi etiqueta="Incertidumbre (τ)" valor={num(bl.tau, 5)} sub={bl.tau_label} />
      </div>

      {manuales.length > 0 && (
        <div className="aviso ok">
          <b>Con tu opinión aplicada:</b>{" "}
          {manuales.map((v) => `${v.ticker} ${v.ret > 0 ? "+" : ""}${v.ret} % anual` +
            (v.modo === "B2" ? ` (evento a ${v.meses} meses)` : "") +
            `, confianza ${v.confidence} %`).join(" · ")}.
        </div>)}

      <div className="aviso">{bl.equilibrio_nota}</div>

      {acc.length === 0 ? (
        <div className="aviso ojo">{bl.nota || "Sin views: el modelo devuelve el punto de partida."}</div>
      ) : (
        <div className="fila f2">
          <div className="panel">
            <h3>De dónde a dónde se mueve cada peso</h3>
            {(() => {
              // Un activo por fila, con la línea que va del peso de hoy al que
              // sugiere el modelo. La versión anterior ponía los dos pesos en un
              // eje vertical compartido y los tickers de pesos parecidos —o dos
              // activos que van los dos a 0 %— se escribían uno encima del otro.
              // Con una fila por activo eso no puede pasar, y la dirección del
              // movimiento se sigue leyendo de un vistazo.
              const orden = [...acc].sort((a, b) => a.peso_actual_pct - b.peso_actual_pct);
              const tick = orden.map((a) => a.ticker);
              const tope = Math.max(...orden.map((a) => Math.max(a.peso_actual_pct, a.peso_bl_pct)));
              const linea = (arr, color) => ({
                type: "scatter", mode: "lines", showlegend: false, hoverinfo: "skip",
                x: arr.flatMap((a) => [a.peso_actual_pct, a.peso_bl_pct, null]),
                y: arr.flatMap((a) => [a.ticker, a.ticker, null]),
                line: { width: 3, color },
              });
              return (
                <Grafico alto={Math.max(280, acc.length * 52 + 90)}
                  datos={[
                    linea(orden.filter((a) => a.peso_bl_pct >= a.peso_actual_pct), c.positivo),
                    linea(orden.filter((a) => a.peso_bl_pct < a.peso_actual_pct), c.negativo),
                    { type: "scatter", mode: "markers", name: "hoy", x: orden.map((a) => a.peso_actual_pct),
                      y: tick, marker: { size: 10, color: c.texto3 },
                      hovertemplate: "%{y}: %{x:.1f} % hoy<extra></extra>" },
                    { type: "scatter", mode: "markers+text", name: "Black-Litterman",
                      x: orden.map((a) => a.peso_bl_pct), y: tick,
                      text: orden.map((a) => `${a.peso_bl_pct.toFixed(1)} %`),
                      textposition: orden.map((a) => a.peso_bl_pct >= a.peso_actual_pct
                                                     ? "middle right" : "middle left"),
                      textfont: { size: 11.5 }, marker: { size: 11, color: c.acento },
                      hovertemplate: "%{y}: %{x:.1f} % sugerido<extra></extra>" },
                  ]}
                  layout={{ legend: { orientation: "h", y: -0.14, x: 0.5, xanchor: "center" },
                            xaxis: { ticksuffix: " %", zeroline: false,
                                     range: [-tope * 0.14, tope * 1.16] },
                            // Sin categoryarray Plotly ordena por orden de
                            // aparición, y como las subidas y las bajadas van en
                            // traces distintos las filas salían mezcladas.
                            yaxis: { automargin: true, showgrid: false,
                                     categoryorder: "array", categoryarray: tick },
                            margin: { l: 10, r: 16, t: 10, b: 30 } }} />
              );
            })()}
            <div className="pie">
              Cada línea es un activo: arranca en su peso de hoy y termina en el que sugiere
              el modelo. En verde lo que sube, en rojo lo que baja.
            </div>
          </div>

          <div className="panel">
            <h3>Qué operar</h3>
            <div className="tabla-wrap"><table>
              <thead><tr><th>Ticker</th><th className="n">Hoy</th><th className="n">Sugerido</th>
                <th className="n">Monto</th><th className="n">Retorno esperado</th>
                <th className="c">Acción</th></tr></thead>
              <tbody>{acc.map((a) => (
                <tr key={a.ticker}>
                  <td className="mono">{a.ticker}</td>
                  <td className="n">{pct(a.peso_actual_pct, 1)}</td>
                  <td className="n">{pct(a.peso_bl_pct, 1)}</td>
                  <td className={"n " + signo(a.delta_usd)}>{usd(a.delta_usd)}</td>
                  <td className={"n " + signo(a.ret_bl_pct)}>{pct(a.ret_bl_pct, 1)}</td>
                  <td><span className={"chip " + (a.accion === "COMPRAR" ? "ok" : a.accion === "VENDER" ? "mal" : "")}>{a.accion}</span></td>
                </tr>))}</tbody>
            </table></div>
            <div className="pie">
              "Retorno esperado" es el posterior del modelo: la mezcla entre lo que estaba
              implícito en tu cartera y lo que dicen las views, pesada por confianza.
            </div>
          </div>
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
          layout={{ // El eje del VIX vive a la derecha y necesita su propio margen:
                    // con el de por defecto los números salían cortados por el borde.
                    margin: { r: 58 },
                    // Veinticinco líneas a todo lo alto tapaban las dos series que
                    // el gráfico existe para mostrar. Quedan como marcas tenues; el
                    // rombo de abajo sigue siendo lo que se lee y se hoverea.
                    shapes: [...franjas, ...(d.eventos || []).map((e) => ({
                      type: "line", x0: e.fecha, x1: e.fecha, yref: "paper", y0: 0, y1: 1,
                      opacity: 0.3,
                      line: { color: e.alcance === "AR" ? c.series[3] : c.series[4],
                              width: 0.7, dash: "dot" } }))],
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
          <thead><tr><th>Fecha</th><th className="c">Alcance</th><th>Evento</th></tr></thead>
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
          <label className="btn yahoo">Importar de <b>yahoo!</b> finance
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

const post = (ruta, cuerpo) => api(ruta, {
  method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify(cuerpo || {}) });

/* Las dos credenciales se cargan desde acá y no desde un archivo a mano: son la
   única configuración que la aplicación pide, y esconderla en el disco obliga a
   documentar un formato que después nadie recuerda. La de Cocos va al vault
   cifrado del proyecto (`data/vault/`), la de FMP a `data/connectors.json`.
   Ninguna de las dos se versiona ni vuelve al navegador una vez guardada. */

function Ficha({ f }) {
  return (
    <>
      <h3 style={{ justifyContent: "space-between" }}>
        <span>{f.nombre}</span>
        <span className={"chip " + (f.conectado ? "ok" : "ojo")}>
          {f.conectado ? "conectado" : "no conectado"}</span>
      </h3>
      <div className="pie" style={{ marginTop: 2, marginBottom: 13 }}>
        Aporta {f.aporta}. <i>{f.sin_ella}</i>
        {f.detalle && <div style={{ marginTop: 2 }}>Estado: {f.detalle}.</div>}
      </div>
    </>
  );
}

function Fmp({ f, recargar }) {
  const [key, setKey] = useState("");
  const [msg, setMsg] = useState(null);
  const [yendo, setYendo] = useState(false);

  const guardar = async () => {
    setYendo(true); setMsg(null);
    const r = await post("/api/conectores/fmp", { api_key: key.trim() });
    setYendo(false);
    if (r.error) { setMsg(["mal", r.error]); return; }
    setKey(""); setMsg(["ok", "Clave guardada."]); recargar();
  };

  return (
    <div className="panel">
      <Ficha f={f} />
      <div style={{ display: "flex", gap: 8 }}>
        <input type="password" value={key} placeholder="API key" style={{ flex: 1 }}
               autoComplete="off" onChange={(e) => setKey(e.target.value)}
               onKeyDown={(e) => { if (e.key === "Enter" && key.trim()) guardar(); }} />
        <button className="btn primario" disabled={!key.trim() || yendo} onClick={guardar}>
          {yendo ? "Guardando…" : f.conectado ? "Reemplazar" : "Guardar"}</button>
      </div>
      <div className="pie">
        Se saca gratis en <a href="https://site.financialmodelingprep.com/developer/docs"
        target="_blank" rel="noreferrer">financialmodelingprep.com</a>. Queda en{" "}
        <span className="mono">data/connectors.json</span> con permisos 600, fuera de git.
      </div>
      {msg && <div className={"aviso " + msg[0]}>{msg[1]}</div>}
    </div>
  );
}

function Cocos({ f, brk, recargar }) {
  const vacias = { email: "", password: "", totp_secret_key: "" };
  const [c, setC] = useState(vacias);
  const [codigo, setCodigo] = useState("");
  const [msg, setMsg] = useState(null);
  const [yendo, setYendo] = useState(false);
  const campo = (k, v) => setC((x) => ({ ...x, [k]: v }));

  const resultado = (r) => setMsg(
    r.conectado ? ["ok", `Conectado — ${r.detalle}.`]
                : ["mal", r.error || r.detalle || "No se pudo conectar."]);

  // Un solo paso: cifra las credenciales, guarda la clave sola y hace el login.
  const ingresar = async () => {
    setYendo(true); setMsg(null);
    const r = await post("/api/broker/vault", c);
    setYendo(false);
    if (r.error) { setMsg(["mal", r.error]); recargar(); return; }
    setC(vacias); resultado(r); recargar();
  };

  // Reconecta con las credenciales ya guardadas, sin volver a tipearlas.
  const reconectar = async (forzar) => {
    setYendo(true); setMsg(null);
    resultado(await post("/api/broker/conectar",
                         { forzar_login: !!forzar, codigo_2fa: codigo.trim() }));
    setYendo(false); setCodigo(""); recargar();
  };

  const salir = async () => { await post("/api/broker/desconectar"); setMsg(null); recargar(); };
  const borrar = async () => {
    if (!confirm("¿Borrar las credenciales de Cocos guardadas?")) return;
    await post("/api/broker/borrar"); setMsg(null); recargar();
  };

  return (
    <div className="panel">
      <Ficha f={f} />

      {!brk?.vault_cargado && (
        <>
          <div style={{ display: "grid", gap: 7 }}>
            <input type="email" placeholder="Email de Cocos" value={c.email}
                   autoComplete="off" onChange={(e) => campo("email", e.target.value)} />
            <input type="password" placeholder="Contraseña" value={c.password}
                   autoComplete="new-password" onChange={(e) => campo("password", e.target.value)} />
            <input type="text" inputMode="numeric" placeholder="Código 2FA de la app (6 dígitos)"
                   value={c.totp_secret_key} autoComplete="off"
                   onChange={(e) => campo("totp_secret_key", e.target.value)} />
            <button className="btn primario" disabled={yendo || !c.email || !c.password}
                    onClick={ingresar}>{yendo ? "Conectando…" : "Ingresar y conectar"}</button>
          </div>
          <div className="pie">
            Abrí tu app de autenticación y poné el <b>código de 6 dígitos</b> del momento: la app
            entra con eso y guarda la sesión, así los próximos arranques no piden nada. Las
            credenciales se cifran con AES-256-GCM en <span className="mono">data/vault/</span>.
            Si en cambio tenés la <b>semilla</b> (el texto largo que se escanea una vez),
            pegala ahí y no vuelve a pedir código nunca.
          </div>
        </>
      )}

      {brk?.vault_cargado && !f.conectado && (
        <>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
            <input type="text" inputMode="numeric" placeholder="Código 2FA (si lo pide)"
                   value={codigo} style={{ width: 170 }} autoComplete="off"
                   onChange={(e) => setCodigo(e.target.value)}
                   onKeyDown={(e) => { if (e.key === "Enter") reconectar(true); }} />
            <button className="btn primario" disabled={yendo}
                    onClick={() => reconectar(false)}>{yendo ? "Conectando…" : "Conectar"}</button>
            <button className="btn peligro" disabled={yendo} onClick={borrar}>Borrar credenciales</button>
          </div>
          <div className="pie">
            Primero intenta con la sesión guardada. Si caducó, poné el código de 6 dígitos de la
            app y tocá Conectar.
          </div>
        </>
      )}

      {f.conectado && (
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <button className="btn peligro" onClick={salir}>Desconectar</button>
          <button className="btn peligro" onClick={borrar}>Borrar credenciales</button>
          <span className="pie" style={{ margin: 0 }}>
            {f.cuenta ? `Cuenta ${f.cuenta}` : "Sesión activa"}. Desconectar deja las
            credenciales; borrarlas las elimina del disco.
          </span>
        </div>
      )}

      {msg && <div className={"aviso " + msg[0]}>{msg[1]}</div>}
    </div>
  );
}

function Conectores() {
  const [d, setD] = useState(null);
  const [brk, setBrk] = useState(null);
  const cargar = () => {
    api("/api/conectores").then(setD);
    api("/api/broker/estado").then(setBrk);
  };
  useEffect(() => { cargar(); }, []);
  if (!d) return <div className="cargando">Consultando fuentes…</div>;
  const fuente = (t) => d.con_credencial.find((f) => f.nombre.includes(t)) || {};

  return (
    <>
      <div className="aviso">
        Solo dos fuentes piden credencial, y las dos son <b>opcionales</b>: sin ellas la
        aplicación funciona igual, con menos cobertura.
      </div>
      <div className="fila f2">
        <Cocos f={fuente("Cocos")} brk={brk} recargar={cargar} />
        <Fmp f={fuente("Financial Modeling")} recargar={cargar} />
      </div>
      <div className="panel" style={{ marginBottom: 14 }}>
        <h3>Públicas · sin credencial</h3>
        <div className="tabla-wrap"><table>
          <thead><tr><th>Fuente</th><th>Aporta</th><th>Estado</th></tr></thead>
          <tbody>{d.publicas.map((f, i) => (
            <tr key={i}><td><b>{f.nombre}</b></td><td>{f.aporta}</td>
              <td><span className="chip ok">{f.estado}</span></td></tr>))}</tbody>
        </table></div>
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

/* ═══════════════ Mi Cocos · la cuenta real del broker ═══════════════ */
// Espejo de lo que Cocos expone hoy por API, todo en pesos y crudo del broker.
// Es el punto de partida para lo que viene: cruzar estas tenencias reales contra
// la cartera cargada a mano y valuar todo en dólares por MEP.

const ars = (n, dec = 2) =>
  n == null ? "—" : "$" + Number(n).toLocaleString("es-AR",
    { minimumFractionDigits: dec, maximumFractionDigits: dec });

function MiCocos() {
  const [d, setD] = useState(null);
  const [err, setErr] = useState(null);
  const [movs, setMovs] = useState([]);
  const [masMovs, setMasMovs] = useState(false);
  const [cargandoMovs, setCargandoMovs] = useState(false);
  const [cat, setCat] = useState(null);           // filtro de categoría
  const [fci, setFci] = useState(null);           // tracking de FCI
  const [tenFci, setTenFci] = useState(null);     // participaciones como lotes
  const [destino, setDestino] = useState("");     // cartera a la que se importan
  const [importando, setImportando] = useState(null);

  const traerMovs = (offset = 0) => {
    setCargandoMovs(true);
    api(`/api/cocos/movimientos?limite=40&offset=${offset}`).then((r) => {
      setCargandoMovs(false);
      if (r.error) return;
      setMovs((prev) => offset ? [...prev, ...r.movimientos] : r.movimientos);
      setMasMovs(r.hay_mas);
    });
  };

  const cargar = () => {
    setErr(null); setD(null); setMovs([]); setCat(null); setFci(null);
    setTenFci(null); setImportando(null);
    api("/api/cocos/resumen").then((r) => {
      if (r.error) { setErr(r.error); return; }
      setD(r);
      if (!r.conectado) return;
      traerMovs(0);
      api("/api/cocos/fci").then(setFci);
      api("/api/cocos/fci/tenencias").then((t) => {
        setTenFci(t);
        if (t.cartera) setDestino(t.cartera);
      });
    });
  };

  const importarFci = () => {
    setImportando({ estado: "yendo" });
    api("/api/cocos/fci/importar", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cartera: destino }),
    }).then((r) => setImportando(r));
  };
  useEffect(() => { cargar(); }, []);

  if (err) return <div className="aviso mal"><b>No se pudo leer Cocos.</b> {err}</div>;
  if (!d) return <div className="cargando">Consultando tu cuenta de Cocos…</div>;
  if (!d.conectado) return (
    <div className="vacio">
      No estás conectado a Cocos. Andá a <b>Conectores</b> y conectá tu cuenta para
      ver acá tus posiciones, saldos y datos.
    </div>
  );

  const errBloque = (x) => x && typeof x === "object" && x.error;
  const pos = Array.isArray(d.posiciones) ? d.posiciones : [];
  const dia = Array.isArray(d.dia) ? d.dia : [];
  const porDia = Object.fromEntries(dia.map((t) => [t.instrument_code, t]));
  const perfil = d.perfil || {};
  const cuenta = perfil.account || {};
  const fondos = d.fondos || {};
  const bancos = Array.isArray(d.bancos) ? d.bancos : [];

  // Totales de las tenencias, en pesos, tal como los da Cocos.
  // Un FCI recién suscripto todavía no tiene cuotaparte del día: se valúa al PPC
  // en vez de contarlo como cero.
  const precio = (p) => p.last ?? p.average_price ?? 0;
  const valor = pos.reduce((s, p) => s + (p.quantity || 0) * precio(p), 0);
  const resultado = pos.reduce((s, p) => s + (p.result || 0), 0);
  const costo = valor - resultado;
  const efectivo = fondos.CI || {};

  return (
    <>
      <div className="aviso ojo">
        Todo lo de esta pantalla sale <b>en vivo de Cocos</b> y está <b>en pesos</b>, tal como
        lo informa el broker. Es de solo lectura. <button className="btn"
        style={{ padding: "1px 9px", fontSize: 12, marginLeft: 4 }}
        onClick={cargar}>Actualizar</button>
      </div>

      {/* ── Cabecera de cuenta ── */}
      <div className="kpis">
        <Kpi etiqueta="Titular" valor={`${perfil.first_name || ""} ${perfil.last_name || ""}`.trim() || "—"}
             sub={perfil.email} />
        <Kpi etiqueta="Cuenta" valor={cuenta.id ? `#${cuenta.id}` : "—"}
             sub={cuenta.tier ? `Tier ${cuenta.tier} · ${cuenta.entityType || ""}` : null} />
        <Kpi etiqueta="Valor tenencias" valor={ars(valor, 0)} sub="cantidad × último" />
        <Kpi etiqueta="Resultado" valor={ars(resultado, 0)} tono={resultado >= 0 ? "pos" : "neg"}
             sub={costo ? pct(resultado / costo * 100) + " sobre el costo" : null} />
        <Kpi etiqueta="Efectivo disponible" valor={ars(efectivo.ars, 0)}
             sub={`US$ ${num(efectivo.usd)} · cable ${num(efectivo.ext)}`} />
      </div>

      {/* ── Posiciones ── */}
      <div className="panel" style={{ marginBottom: 14 }}>
        <h3>Posiciones ({pos.length})</h3>
        {errBloque(d.posiciones)
          ? <div className="aviso mal">{d.posiciones.error}</div>
          : pos.length === 0
          ? <div className="vacio">Sin tenencias en la cuenta.</div>
          : <div className="tabla-wrap"><table>
              <thead><tr>
                <th>Ticker</th><th>Instrumento</th><th>Tipo</th>
                <th className="n">Cantidad</th><th className="n">PPC</th><th className="n">Último</th>
                <th className="n">Día</th><th className="n">Valor</th>
                <th className="n">Resultado</th><th className="n">Rend.</th>
              </tr></thead>
              <tbody>{pos.map((p) => {
                const v = (p.quantity || 0) * precio(p);
                const dd = porDia[p.instrument_code];
                const varDia = dd && dd.previous_price && dd.last_price
                  ? (dd.last_price / dd.previous_price - 1) * 100 : null;
                const rp = p.result_percentage != null ? p.result_percentage * 100 : null;
                return (
                  <tr key={p.instrument_code + p.id_security}>
                    <td className="mono"><b>{p.short_ticker || p.instrument_code}</b></td>
                    <td>{p.instrument_short_name}</td>
                    <td style={{ fontSize: 12, color: "var(--texto-3)" }}>{p.instrument_type}</td>
                    <td className="n">{num(p.quantity, p.quantity % 1 ? 2 : 0)}</td>
                    <td className="n">{ars(p.average_price)}</td>
                    <td className="n">{ars(p.last)}</td>
                    <td className={"n " + signo(varDia)}>{varDia == null ? "—" : pct(varDia)}</td>
                    <td className="n">{ars(v, 0)}</td>
                    <td className={"n " + signo(p.result)}>{ars(p.result, 0)}</td>
                    <td className={"n " + signo(rp)}>{rp == null ? "—" : pct(rp)}</td>
                  </tr>);
              })}</tbody>
            </table></div>}
        <div className="pie">
          PPC = precio promedio de compra. «Día» es la variación de hoy (precio previo vs.
          último). Los bonos y ONs vienen cada 100 nominales; hoy no tenés en cartera.
          Los FCI llegan del broker cada 1000 cuotapartes y en pesos aun los que son en
          dólares: acá ya están por cuotaparte. Si el fondo todavía no publicó la del día,
          «Último» queda vacío y el valor se calcula con el PPC.
        </div>
      </div>

      <div className="fila f2">
        {/* ── Saldos por plazo ── */}
        <div className="panel">
          <h3>Saldos disponibles por liquidación</h3>
          {errBloque(fondos)
            ? <div className="aviso mal">{fondos.error}</div>
            : <div className="tabla-wrap"><table>
                <thead><tr><th>Plazo</th><th className="n">Pesos</th>
                  <th className="n">Dólar MEP</th><th className="n">Cable</th></tr></thead>
                <tbody>{[["CI", "Inmediato"], ["24hs", "24 hs"], ["48hs", "48 hs"]].map(([k, t]) => (
                  <tr key={k}><td>{t}</td>
                    <td className="n">{ars((fondos[k] || {}).ars)}</td>
                    <td className="n">{num((fondos[k] || {}).usd)}</td>
                    <td className="n">{num((fondos[k] || {}).ext)}</td></tr>))}</tbody>
              </table></div>}
          <div className="pie">Lo que podés operar hoy (CI), mañana (24 hs) o pasado (48 hs).</div>
        </div>

        {/* ── Cuentas bancarias ── */}
        <div className="panel">
          <h3>Cuentas bancarias ({bancos.length})</h3>
          {errBloque(d.bancos)
            ? <div className="aviso mal">{d.bancos.error}</div>
            : bancos.length === 0
            ? <div className="vacio">Sin cuentas registradas.</div>
            : <div className="tabla-wrap"><table>
                <thead><tr><th>Entidad</th><th>Moneda</th><th>CBU/CVU</th></tr></thead>
                <tbody>{bancos.map((b) => (
                  <tr key={b.id_bank_account}>
                    <td>{b.entity}</td><td>{b.currency}</td>
                    <td className="mono" style={{ fontSize: 12 }}>{b.cbu_cvu}</td></tr>))}</tbody>
              </table></div>}
          <div className="pie">Las cuentas a las que Cocos puede transferir tus retiros.</div>
        </div>
      </div>

      {/* ── Tracking de FCI ── */}
      <div className="panel" style={{ marginBottom: 14 }}>
        <h3>Fondos comunes (FCI) · suscripciones, rescates y resultado</h3>
        {!fci
          ? <div className="cargando">Reconstruyendo el historial de los fondos…</div>
          : fci.error
          ? <div className="aviso mal">{fci.error}</div>
          : (fci.fci || []).length === 0
          ? <div className="vacio">No hay movimientos de FCI en el historial.</div>
          : <>
              <div className="tabla-wrap"><table>
                <thead><tr>
                  <th>FCI</th><th>Moneda</th>
                  <th className="n">Suscripto</th><th className="n">Rescatado</th>
                  <th className="n">Tenencia hoy</th><th className="n">Resultado</th><th className="n">Rend.</th>
                  <th className="n">Período</th>
                </tr></thead>
                <tbody>{fci.fci.map((f) => {
                  const mon = (n) => f.moneda === "ARS" ? ars(n, 0) : num(n) + " " + (f.moneda || "");
                  return (
                    <tr key={f.ticker}>
                      <td className="mono"><b>{f.ticker}</b></td>
                      <td style={{ fontSize: 12, color: "var(--texto-3)" }}>{f.moneda}</td>
                      <td className="n">{mon(f.suscrito)}<div style={{ fontSize: 10.5, color: "var(--texto-3)" }}>{f.n_susc} aportes</div></td>
                      <td className="n">{mon(f.rescatado)}<div style={{ fontSize: 10.5, color: "var(--texto-3)" }}>{f.n_resc} rescates</div></td>
                      <td className="n">{f.valor_actual ? mon(f.valor_actual) : "—"}</td>
                      <td className={"n " + signo(f.resultado)}>{mon(f.resultado)}</td>
                      <td className={"n " + signo(f.resultado_pct)}>{f.resultado_pct == null ? "—" : pct(f.resultado_pct)}</td>
                      <td className="mono" style={{ fontSize: 11 }}>{f.desde}<br />{f.hasta}</td>
                    </tr>);
                })}</tbody>
              </table></div>
              <div className="pie">
                Resultado = tenencia de hoy + lo rescatado − lo suscripto (lo que sacaste más lo
                que aún tenés, contra lo que pusiste). En los de barrido diario (COCORMA) el capital
                rota muchas veces, así que mirá el <b>resultado en $</b> más que el %.
                {fci.cortado && <> · Historial recortado a los {fci.total_movs} movimientos más recientes.</>}
              </div>
            </>}

        {/* Llevar la participación a una cartera: sólo la posición y el resultado. */}
        {tenFci && !tenFci.error && (tenFci.lotes || []).length > 0 && (
          <div style={{ borderTop: "1px solid var(--borde)", marginTop: 12, paddingTop: 12,
                        display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <span style={{ fontSize: 13 }}>
              Llevar {tenFci.lotes.map((l) => l.ticker).join(" y ")} a la cartera
            </span>
            <select value={destino} onChange={(e) => setDestino(e.target.value)}
                    disabled={!!tenFci.cartera}>
              <option value="">elegí una…</option>
              {(tenFci.carteras || []).map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
            <button className="btn" disabled={!destino || importando?.estado === "yendo"}
                    onClick={importarFci}>
              {importando?.estado === "yendo" ? "Importando…" : "Importar"}
            </button>
            {importando?.ok && <span className="ok" style={{ fontSize: 12 }}>
              Listo: {importando.importadas} en {importando.cartera}
              {importando.reemplazadas ? ` (pisó ${importando.reemplazadas})` : ""}.
            </span>}
            {importando?.error && <span className="mal" style={{ fontSize: 12 }}>{importando.error}</span>}
          </div>)}
        {tenFci && !tenFci.error && (tenFci.lotes || []).length > 0 && (
          <div className="pie">
            Va sólo la tenencia y su resultado. Un FCI no tiene serie de precios, así que
            queda fuera del riesgo y de la optimización. Re-importar pisa la anterior, no
            duplica. La cuenta queda asociada a esa cartera.
          </div>)}
      </div>

      {/* ── Movimientos ── */}
      <div className="panel" style={{ marginBottom: 14 }}>
        <h3>Movimientos {movs.length ? `(${cat ? movs.filter((m) => m.categoria === cat).length + " de " : ""}${movs.length}${masMovs ? "+" : ""})` : ""}</h3>
        {movs.length > 0 && (
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", margin: "2px 0 12px" }}>
            {[null, ...Array.from(new Set(movs.map((m) => m.categoria)))].map((c) => (
              <button key={c || "todas"} onClick={() => setCat(c)}
                      className={"btn" + (cat === c ? " primario" : "")}
                      style={{ padding: "3px 11px", fontSize: 12.5 }}>
                {c || "Todas"}</button>))}
          </div>
        )}
        {movs.length === 0 && cargandoMovs
          ? <div className="cargando">Trayendo movimientos…</div>
          : movs.length === 0
          ? <div className="vacio">Sin movimientos.</div>
          : <>
              <div className="tabla-wrap"><table>
                <thead><tr>
                  <th>Fecha</th><th>Concepto</th><th>Ticker</th>
                  <th className="n">Cantidad</th><th className="n">Precio</th><th className="n">Importe</th>
                </tr></thead>
                <tbody>{(cat ? movs.filter((m) => m.categoria === cat) : movs).map((m, i) => {
                  const q = m.quantity && typeof m.quantity === "object" ? null : m.quantity;
                  return (
                    <tr key={(m.idTicket || m.identifierId || i) + "-" + i}>
                      <td className="mono" style={{ fontSize: 12 }}>{m.fecha}</td>
                      <td>{m.labelConcept || m.identifier}</td>
                      <td className="mono">{m.ticker || ""}</td>
                      <td className="n">{q ? num(q, q % 1 ? 2 : 0) : ""}</td>
                      <td className="n">{m.price ? ars(m.price) : ""}</td>
                      <td className={"n " + signo(m.amount)}>
                        {m.amount == null ? "—"
                          : (m.currency === "ARS" ? ars(m.amount) : num(m.amount) + " " + (m.currency || ""))}</td>
                    </tr>);
                })}</tbody>
              </table></div>
              {masMovs && (
                <button className="btn" style={{ marginTop: 10 }} disabled={cargandoMovs}
                        onClick={() => traerMovs(movs.length)}>
                  {cargandoMovs ? "Cargando…" : "Cargar más"}</button>)}
            </>}
        <div className="pie">
          Pagos con tarjeta, compras y ventas de instrumentos, rescates de FCI, acreditaciones.
          Importe en la moneda de cada movimiento (ARS o USD).
        </div>
      </div>

      {/* ── Qué se puede desarrollar ── */}
      <div className="panel">
        <h3>Qué se puede construir con esto</h3>
        <div className="pie" style={{ fontSize: 13, lineHeight: 1.6 }}>
          <b style={{ color: "var(--texto)" }}>Ya disponible por API:</b> posiciones con precio
          promedio y resultado, variación del día, saldos por plazo, movimientos completos,
          cuentas bancarias, perfil de la cuenta, y —lo que ya usa la app— precios de bonos, ONs
          y letras.<br />
          <b style={{ color: "var(--texto)" }}>Próximo paso natural:</b> cruzar estas tenencias
          reales contra la cartera que cargás a mano (detectar diferencias), y reconstruir el
          costo real desde los movimientos para valuar todo en dólares por el MEP de cada fecha.
        </div>
      </div>
    </>
  );
}

/* ═══════════════ Dólar MEP · serie, hitos y noticias ═══════════════ */

function Mercado({ cartera }) {
  const [mep, setMep] = useState(null);
  const [news, setNews] = useState(null);
  const [real, setReal] = useState(null);
  const [rango, setRango] = useState("2024-01-01");
  const c = colores();

  useEffect(() => { api(`/api/mep?desde=${rango}`).then(setMep); }, [rango]);
  useEffect(() => { api("/api/noticias?limite=30").then(setNews); }, []);
  useEffect(() => {
    if (!cartera) { setReal(null); return; }
    api(`/api/carteras/${encodeURIComponent(cartera)}/realizado`).then(setReal);
  }, [cartera]);

  const RANGOS = [["2026-01-01", "este año"], ["2024-01-01", "2 años"],
                  ["2020-01-01", "todo"]];

  // Los hitos se pintan sobre la curva, en el MEP de esa rueda: una traza por
  // tipo, así la leyenda de Plotly ya sirve de filtro sin escribir un toggle.
  const TIPOS = { crisis: ["Crisis", c.negativo], politica: ["Política", c.series[4]],
                  macro: ["Macro", c.alerta], positivo: ["Positivo", c.positivo],
                  global: ["Global", c.series[2]] };
  // Cada operación cerrada en pesos recorrió un tramo del dólar: de la cotización
  // con la que se compró a la del día que se cobró. Se dibuja sobre la curva y se
  // pinta por el resultado de tipo de cambio, que ya viene calculado con el mismo
  // MEP que valúa la cartera (`pnl_realizado`). Las que ya eran en dólares no
  // tienen tramo: no hubo exposición.
  const tramos = Object.values((real?.trades || [])
    .filter((t) => t.pnl_fx_usd && t.mep_compra && t.mep_venta)
    .reduce((acc, t) => {
      const k = t.buy_date + "·" + t.sell_date;
      const x = acc[k] || (acc[k] = { ...t, tickers: [], fx: 0 });
      if (!x.tickers.includes(t.ticker)) x.tickers.push(t.ticker);
      x.fx += t.pnl_fx_usd;
      return acc;
    }, {}));

  // Una banda por operación, de la compra a la venta, y translúcidas: donde varias
  // se pisan el color se acumula, así que la intensidad muestra cuánto capital
  // estuvo expuesto a la vez. Las verdes se dibujan últimas — o sea, encima de las
  // rojas — porque son las pocas y quedarían tapadas abajo del montón.
  const bandas = [...tramos].sort((a, b) => (a.fx > 0) - (b.fx > 0));

  const hitos = mep?.eventos || [];
  const marcas = Object.entries(TIPOS).map(([tipo, [nombre, color]]) => {
    const del = hitos.filter((h) => h.tipo === tipo);
    return del.length === 0 ? null : {
      type: "scatter", mode: "markers", name: nombre,
      x: del.map((h) => h.fecha),
      // La noticia puede caer en feriado: se ancla en la primera rueda posterior.
      y: del.map((h) => (mep.serie.find((p) => p.fecha >= h.fecha) || {}).valor),
      text: del.map((h) => h.titulo),
      marker: { color, size: del.map((h) => (h.impacto === "alto" ? 11 : 8)),
                symbol: "triangle-down", line: { color: c.panel, width: 1 } },
      hovertemplate: "<b>%{text}</b><br>%{x} · $%{y:,.2f}<extra></extra>",
    };
  }).filter(Boolean);

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
            <Grafico alto={360}
              datos={[{ type: "scatter", mode: "lines", name: "MEP",
                        x: mep.serie.map((p) => p.fecha), y: mep.serie.map((p) => p.valor),
                        line: { color: c.acento, width: 1.8 },
                        hovertemplate: "%{x}<br>$%{y:,.2f}<extra></extra>" },
                      ...marcas]}
              layout={{ yaxis: { title: "Pesos por dólar", tickprefix: "$" },
                        shapes: [
                          ...bandas.map((b) => ({
                            type: "rect", yref: "paper", y0: 0, y1: 1,
                            x0: b.buy_date, x1: b.sell_date, layer: "below",
                            fillcolor: b.fx > 0 ? c.positivo : c.negativo,
                            opacity: 0.07, line: { width: 0 } })),
                          ...hitos.filter((h) => h.impacto === "alto").map((h) => ({
                            type: "line", x0: h.fecha, x1: h.fecha, y0: 0, y1: 1,
                            yref: "paper", layer: "below",
                            line: { color: c.borde, width: 1, dash: "dot" } }))],
                        legend: { orientation: "h", y: -0.18, font: { size: 10 } },
                        margin: { b: 46 } }} />
            <div className="pie">
              Los triángulos son las noticias que movieron al MEP; se apagan tocando su
              color en la leyenda. La lista se edita a mano en <code>data/eventos_mep.json</code>:
              nadie publica "qué noticia movió al dólar", así que marcar saltos automáticamente
              solo pondría una etiqueta genérica sobre cada rueda volátil.{" "}
              {cartera
                ? bandas.length > 0
                  ? <>El fondo pinta una banda por cada una de las {tramos.length} posiciones
                      en pesos que <b>{cartera}</b> abrió y cerró, de la compra a la venta:{" "}
                      <b className="pos">verde</b> si el MEP le sumó dólares,{" "}
                      <b className="neg">rojo</b> si se los llevó. Se superponen, así que cuanto
                      más intenso el color, más operaciones expuestas al mismo tiempo.</>
                  : <><b>{cartera}</b> no tiene operaciones cerradas en pesos, así que no hay
                      tramos que marcar: lo que se compró y se vendió en dólares no tuvo
                      exposición al MEP.</>
                : <>Elegí una cartera arriba y el fondo se pinta con los períodos en que
                     tuviste posiciones en pesos, verde o rojo según lo que te hizo el dólar.</>}
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
        {modo === "mercado" && <Mercado cartera={cartera} />}
        {modo === "conectores" && <Conectores />}
        {modo === "cocos" && <MiCocos />}
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
