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
          ["carteras", "Carteras"], ["conectores", "Conectores"]].map(([k, t]) => (
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

const PESTANAS = [
  ["posicion", "Posición"], ["composicion", "Composición"], ["riesgo", "Riesgo"],
  ["markowitz", "Markowitz"], ["montecarlo", "Monte Carlo"], ["capm", "Benchmark"],
  ["momentum", "Momentum"], ["objetivos", "Objetivos"],
  ["blacklitterman", "Black-Litterman"], ["regimenes", "Regímenes"], ["stress", "Stress"],
];

function Analisis({ cartera }) {
  const [run, setRun] = useState(null);
  const [estado, setEstado] = useState(null);
  const [tab, setTab] = useState("posicion");

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
      </div>
      <Panel tab={tab} R={R} M={M} cartera={cartera} />
    </>
  );
}

function Panel({ tab, R, M, cartera }) {
  const d = R[tab];
  if (M[tab]?.estado === "corriendo" || M[tab]?.estado === "en cola")
    return <div className="cargando">Calculando {M[tab]?.nombre}…</div>;
  if (!d) return <div className="cargando">Sin datos.</div>;
  if (d.error) return <div className="aviso mal"><b>No se pudo calcular.</b> {d.error}</div>;

  const vistas = {
    posicion: <Posicion d={d} />, composicion: <Composicion d={d} />,
    riesgo: <Riesgo d={d} />, markowitz: <Markowitz d={d} />,
    montecarlo: <MonteCarlo d={d} cartera={cartera} />, capm: <Capm d={d} cartera={cartera} />,
    momentum: <Momentum d={d} />, objetivos: <Objetivos d={d} />,
    blacklitterman: <BlackLitterman d={d} />, regimenes: <Regimenes d={d} />,
    stress: <Stress d={d} />,
  };
  return vistas[tab] || <div className="cargando">—</div>;
}

/* ── Posición ── */
function Posicion({ d }) {
  const filas = d.posiciones || [];
  return (
    <>
      <div className="kpis">
        <Kpi etiqueta="Valor total" valor={usd(d.valor_total)} ayuda={AYUDA.valor}
             sub={d.mep_hoy ? `MEP $${d.mep_hoy}` : null} />
        <Kpi etiqueta="Costo" valor={usd(d.costo_total)} sub="comisiones incluidas" />
        <Kpi etiqueta="Resultado" valor={usd(d.pnl)} tono={signo(d.pnl)} ayuda={AYUDA.pnl}
             sub={pct(d.pnl_pct)} />
        <Kpi etiqueta="Posiciones" valor={filas.length} sub={`${new Set(filas.map(f=>f.ticker)).size} activos`} />
      </div>
      {d.sin_precio?.length > 0 && (
        <div className="aviso ojo">
          <b>{d.sin_precio.length} posiciones sin precio</b> y quedaron fuera del total:{" "}
          {d.sin_precio.join(", ")}. Los bonos y ONs necesitan Cocos conectado.
        </div>
      )}
      <div className="panel">
        <h3>Tenencias</h3>
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
function Riesgo({ d }) {
  const c = colores();
  const contrib = d.contribucion_riesgo || [];
  const barras = [{
    type: "bar", orientation: "h",
    y: contrib.map((x) => x.ticker).reverse(),
    x: contrib.map((x) => x.riesgo_pct).reverse(),
    marker: { color: c.negativo }, name: "aporte al riesgo",
    hovertemplate: "%{y}: %{x:.1f} % del riesgo<extra></extra>",
  }, {
    type: "bar", orientation: "h",
    y: contrib.map((x) => x.ticker).reverse(),
    x: contrib.map((x) => x.peso_pct).reverse(),
    marker: { color: c.series[2] }, name: "peso en la cartera",
    hovertemplate: "%{y}: %{x:.1f} % de peso<extra></extra>",
  }];
  const desbalance = contrib.filter((x) => x.ratio && x.ratio > 1.5);

  return (
    <>
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

      <div className="fila f2">
        <div className="panel">
          <h3>Quién trae el riesgo</h3>
          <Grafico datos={barras} layout={{ barmode: "group", margin: { l: 82 },
                   xaxis: { ticksuffix: " %" } }} alto={Math.max(220, contrib.length * 46)} />
          <div className="pie">
            Las contribuciones suman exactamente la volatilidad de la cartera
            (identidad de Euler). Un activo cuya barra roja supera a la azul aporta
            más riesgo del que su peso sugiere.
          </div>
        </div>
        <div className="panel">
          <h3>Cuánto esconde suponer normalidad</h3>
          <div className="tabla-wrap"><table>
            <thead><tr><th>Método</th><th className="n">Pérdida en un día malo</th><th className="n">En dólares</th></tr></thead>
            <tbody>
              <tr><td>Histórico (95 %)</td><td className="n">{pct(d.var95_pct)}</td><td className="n neg">{usd(d.var95_usd)}</td></tr>
              <tr><td>Cornish-Fisher (95 %)</td><td className="n">{pct(d.var95_cornish_fisher_pct)}</td><td className="n neg">{usd(d.var95_cornish_fisher_usd)}</td></tr>
              <tr><td>Histórico (99 %)</td><td className="n">{pct(d.var99_pct)}</td><td className="n neg">{usd(d.var99_usd)}</td></tr>
            </tbody>
          </table></div>
          <div className="pie">
            Cornish-Fisher ajusta el cuantil por la asimetría y las colas gordas reales.
            La diferencia con el histórico es cuánto riesgo queda oculto si se supone
            que los retornos se portan como una campana.
          </div>
        </div>
      </div>

      {desbalance.length > 0 && (
        <div className="aviso ojo">
          <b>Riesgo concentrado.</b>{" "}
          {desbalance.map((x) => `${x.ticker} pesa ${x.peso_pct} % y aporta ${x.riesgo_pct} % del riesgo`).join(" · ")}.
        </div>
      )}
    </>
  );
}

/* ── Markowitz ── */
function Markowitz({ d }) {
  const c = colores();
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
          <h3>Para llegar a la cartera de máximo Sharpe</h3>
          <div className="tabla-wrap"><table>
            <thead><tr><th>Ticker</th><th className="n">Hoy</th><th className="n">Objetivo</th>
                       <th className="n">Diferencia</th><th>Acción</th></tr></thead>
            <tbody>{(d.acciones_max_sharpe || []).map((a) => (
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
            Leelo como una dirección, no como una instrucción.
          </div>
        </div>
      </div>
    </>
  );
}

/* ── Monte Carlo ── */
function MonteCarlo({ d, cartera }) {
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

/* ── Benchmark (CAPM) ── */
function Capm({ d, cartera }) {
  const c = colores();
  const [todos, setTodos] = useState(null);
  const nivel = d.diagnostico_r2?.nivel;
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
function Objetivos({ d }) {
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
function Regimenes({ d }) {
  const c = colores();
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
        <h3>Volatilidad de la cartera y miedo del mercado</h3>
        <Grafico alto={340}
          datos={[
            { type: "scatter", mode: "lines", name: "volatilidad de tu cartera",
              x: t.map((p) => p.fecha), y: t.map((p) => p.vol_cartera),
              line: { color: c.acento, width: 1.8 } },
            { type: "scatter", mode: "lines", name: "umbral de tensión",
              x: t.map((p) => p.fecha), y: t.map((p) => p.umbral),
              line: { color: c.texto3, width: 1, dash: "dot" } },
            { type: "scatter", mode: "lines", name: "VIX (miedo global)",
              x: t.map((p) => p.fecha), y: t.map((p) => p.vix),
              yaxis: "y2", line: { color: c.series[3], width: 1.2 } },
          ]}
          layout={{ shapes: franjas, yaxis: { title: "Volatilidad anual", ticksuffix: " %" },
                    yaxis2: { title: "VIX", overlaying: "y", side: "right", showgrid: false } }} />
        <div className="pie">{d.metodo}</div>
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
      <div className={"aviso " + (concluyente ? "ok" : "ojo")}>
        <b>{d.veredicto}</b>
      </div>

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
