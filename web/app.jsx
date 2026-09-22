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

const { useState, useEffect, useRef, useCallback, useMemo } = React;

/* ═══════════════ utilidades ═══════════════ */

/* El sobre firmado de la sesión web. Vive sólo en este navegador: es lo único
   que prueba quién sos ante el servidor, que no guarda credenciales de nadie.
   En modo local no existe y todo esto queda inerte. Los try/catch son porque
   localStorage tira excepción en ventana privada o con las cookies bloqueadas,
   y ahí la app tiene que seguir andando igual, pidiendo login cada vez. */
/* Cuál es "tu" cartera: la que se abre sola al entrar. Vive en este navegador,
   igual que el tema. Con una sola cartera no hay nada que elegir y es esa; con
   varias, manda lo que el usuario haya fijado en Carteras, y si eso ya no
   existe (la borró o la renombró) se cae a la primera en vez de dejar la
   pantalla vacía preguntando. */
const DEFECTO = "pa.cartera";
const carteraDefecto = {
  leer: () => { try { return localStorage.getItem(DEFECTO); } catch { return null; } },
  poner: (n) => { try { n ? localStorage.setItem(DEFECTO, n) : localStorage.removeItem(DEFECTO); }
                  catch { /* sin memoria */ } },
};

const elegirCartera = (carteras) => {
  const nombres = (carteras || []).map((c) => c.nombre);
  if (!nombres.length) return null;
  if (nombres.length === 1) return nombres[0];
  const fijada = carteraDefecto.leer();
  return nombres.includes(fijada) ? fijada : nombres[0];
};

/* La simulación: qué estarías comprando o vendiendo, sin tocar la cartera. Vive
   en este navegador y nada más — el servidor no guarda ninguna, viajan en el
   header `X-Sim` de cada pedido y se aplican en memoria (ver `api/sim.py`).
   Una por cartera: la simulación de una no tiene sentido sobre otra. */
const simul = {
  leer: (c) => { try { return JSON.parse(localStorage.getItem("pa.sim." + c) || "[]"); }
                 catch { return []; } },
  poner: (c, l) => { try { (l || []).length ? localStorage.setItem("pa.sim." + c, JSON.stringify(l))
                                            : localStorage.removeItem("pa.sim." + c); }
                     catch { /* sin memoria */ } },
  cabecera: (l) => (l || []).map((x) => `${x.ticker}:${x.qty}`).join(","),
};

/* ponytail: un solo global, porque la simulación es una sola —la del usuario que
   está mirando la pantalla— y la leen los treinta y pico de fetch repartidos por
   los paneles. Pasarla por props hasta cada uno sería un refactor entero para el
   mismo resultado. Si algún día hay dos vistas simultáneas, esto pasa a props. */
let SIM_ACTIVA = "";

/* Desde qué plaza se mira la cartera. No es un formato de pantalla: manda la
   moneda de medición, la tasa libre de riesgo y el índice con el que abre —el
   detalle está en `core/mercado.py`, acá vive sólo lo que se dibuja. Viaja en el
   header `X-Mercado` de cada pedido.

   `locales` es lo que sólo le sirve a quien invierte DESDE Argentina: el MEP,
   los conectores y Cocos. Un europeo no tiene por qué ver esas tres pestañas.

   ponytail: global como SIM_ACTIVA y por la misma razón — lo leen los treinta y
   pico de fetch repartidos por los paneles y el formateador de importes. */
const MERCADOS = {
  AR: { bandera: "🇦🇷", nombre: "Argentina", nombre_en: "Argentina", simbolo: "$", moneda: "dólares",
        moneda_en: "dollars", bench: "MERVAL", locales: true,
        pie: "Todos los valores en dólares, convertidos con el MEP de la fecha de cada operación.",
        // El MEP es jerga del mercado argentino y no se traduce (ver memoria
        // "Plan de traducción a inglés"): esta plaza sólo la ve quien invierte
        // desde acá, así que el pie queda igual en los dos idiomas.
        pie_en: "Todos los valores en dólares, convertidos con el MEP de la fecha de cada operación." },
  EU: { bandera: "🇪🇺", nombre: "Europa", nombre_en: "Europe", simbolo: "€", moneda: "euros",
        moneda_en: "euros", bench: "STOXX600", locales: false,
        pie: "Todos los valores en euros, convertidos con el EURUSD de cada fecha.",
        pie_en: "All values in euros, converted at the EURUSD rate of each date." },
  US: { bandera: "🇺🇸", nombre: "Estados Unidos", nombre_en: "United States", simbolo: "$",
        moneda: "dólares", moneda_en: "dollars", bench: "SP500", locales: false,
        pie: "Todos los valores en dólares.", pie_en: "All values in dollars." },
};

/* "dólares" o "euros", para los textos que nombran la moneda. */
const MON = () => t(MERCADOS[MERCADO].moneda, MERCADOS[MERCADO].moneda_en);

let MERCADO = "AR";

/* Idioma de la interfaz: "es" o "en". Mismo mecanismo que MERCADO/SIM_ACTIVA
   —un global que se fija en el render de App()— porque lo lee `t()` y los
   formateadores de número desde fuera de todo componente.

   Se elige una sola vez sola: al ingresar por primera vez, con el `locale` de
   la cuenta de Google (ver `core/usuarios.py::canjear`, `store.anotar`). Desde
   que alguien lo cambia a mano en el menú de la cuenta, ese valor manda y un
   ingreso nuevo no lo pisa. Vive en este navegador, igual que el tema —no hay
   nada que sincronizar entre pestañas, y guardarlo en el perfil del server es
   lo que hace que un ingreso nuevo, en otro navegador, ya lo traiga bien. */
let IDIOMA = "es";

const IDIOMA_KEY = "pa.idioma";
const idiomaLocal = {
  leer: () => { try { return localStorage.getItem(IDIOMA_KEY); } catch { return null; } },
  poner: (v) => { try { localStorage.setItem(IDIOMA_KEY, v); } catch { /* sin memoria */ } },
};

/* Traducir sin diccionario aparte: la versión en inglés vive al lado de la
   original, en el mismo `t(es, en)`. Un diccionario centralizado obliga a
   saltar de archivo para ver o corregir una traducción; esto no — y evita el
   problema de una clave que no matchea porque alguien retocó el texto en
   español y se olvidó de tocar la clave. */
const t = (es, en) => (IDIOMA === "en" ? en : es);

const SOBRE = "pa.sesion";
const sesion = {
  leer: () => { try { return localStorage.getItem(SOBRE); } catch { return null; } },
  poner: (s) => { try { localStorage.setItem(SOBRE, s); } catch { /* sin memoria */ } },
  tirar: () => { try { localStorage.removeItem(SOBRE); } catch { /* nada que hacer */ } },
};

// Mismo mecanismo, sobre aparte: el de InvIU es independiente del de Cocos —
// se puede tener uno, el otro, los dos, o ninguno.
const SOBRE_INVIU = "pa.sesion.inviu";
const sesionInviu = {
  leer: () => { try { return localStorage.getItem(SOBRE_INVIU); } catch { return null; } },
  poner: (s) => { try { localStorage.setItem(SOBRE_INVIU, s); } catch { /* sin memoria */ } },
  tirar: () => { try { localStorage.removeItem(SOBRE_INVIU); } catch { /* nada que hacer */ } },
};

const api = async (ruta, opciones) => {
  const o = { ...(opciones || {}) };
  const guardado = sesion.leer();
  if (guardado) o.headers = { ...(o.headers || {}), "X-Sesion": guardado };
  const guardadoInviu = sesionInviu.leer();
  if (guardadoInviu) o.headers = { ...(o.headers || {}), "X-Sesion-Inviu": guardadoInviu };
  if (SIM_ACTIVA) o.headers = { ...(o.headers || {}), "X-Sim": SIM_ACTIVA };
  o.headers = { ...(o.headers || {}), "X-Mercado": MERCADO };

  const r = await fetch(ruta, o);

  // Cocos renovó el token: el servidor devuelve un sobre nuevo y hay que
  // quedárselo, o la próxima request va con el viejo y no entra.
  const renovado = r.headers.get("X-Sesion");
  if (renovado) sesion.poner(renovado);
  const renovadoInviu = r.headers.get("X-Sesion-Inviu");
  if (renovadoInviu) sesionInviu.poner(renovadoInviu);

  // El servidor avisa que el sobre murió (venció, o el broker lo rechazó). Se
  // tira y se avisa a la pantalla, pero NO se sale de la app: el broker es
  // opcional y las carteras se siguen viendo igual.
  if (r.headers.get("X-Sesion-Fin")) {
    sesion.tirar();
    window.dispatchEvent(new CustomEvent("pa:reautenticar"));
  }
  if (r.headers.get("X-Sesion-Inviu-Fin")) {
    sesionInviu.tirar();
    window.dispatchEvent(new CustomEvent("pa:reautenticar-inviu"));
  }

  const d = await r.json().catch(() => ({ error: "Respuesta ilegible del servidor." }));
  if (!r.ok && !d.error) d.error = `Error ${r.status}`;

  // Dos cosas distintas se pueden haber caído, y no se arreglan igual:
  //   ingresar     → la sesión de la app. Volver a entrar con Google.
  //   reautenticar → la de Cocos (24 h, o token revocado). Reconectar el broker,
  //                  sin salir de la app: la cartera se sigue viendo.
  if (r.status === 401 && d.ingresar) {
    window.dispatchEvent(new CustomEvent("pa:ingresar"));
  } else if (r.status === 401 && d.reautenticar) {
    if (ruta.startsWith("/api/inviu/")) {
      sesionInviu.tirar();
      window.dispatchEvent(new CustomEvent("pa:reautenticar-inviu", { detail: d.error }));
    } else {
      sesion.tirar();
      window.dispatchEvent(new CustomEvent("pa:reautenticar", { detail: d.error }));
    }
  }
  return d;
};

const usd = (n, dec = 2) =>
  n == null ? "—" : MERCADOS[MERCADO].simbolo + Number(n).toLocaleString(
    IDIOMA === "en" ? "en-US" : "es-AR",
    { minimumFractionDigits: dec, maximumFractionDigits: dec });
const pct = (n, dec = 2) => (n == null ? "—" : Number(n).toFixed(dec) + " %");
const num = (n, dec = 2) => (n == null ? "—" : Number(n).toFixed(dec));
const signo = (n) => (n == null ? "" : n > 0 ? "pos" : n < 0 ? "neg" : "");
// Las órdenes de comprar/vender/mantener que arma el optimizador son un enum
// fijo del backend, no prosa libre: se pueden mapear acá sin el refactor de
// códigos de error que todavía falta para el resto de los mensajes del server.
const ACCIONES_EN = { COMPRAR: "BUY", VENDER: "SELL", MANTENER: "HOLD" };
const accionLabel = (a) => t(a, ACCIONES_EN[a] || a);
// Señales de momentum/precio objetivo: mismo criterio que ACCIONES_EN — son un
// enum fijo del backend, no prosa, así que se mapean sin esperar el refactor
// de códigos de error para el resto de los mensajes del servidor.
const SENAL_EN = { FAVORABLE: "FAVORABLE", EVITAR: "AVOID", ESPERAR: "WAIT",
                  INCIPIENTE: "EMERGING", NEUTRAL: "NEUTRAL",
                  "BUEN PRECIO": "GOOD PRICE", CARO: "EXPENSIVE", NORMAL: "NORMAL",
                  COMPRAR: "BUY", REDUCIR: "REDUCE", MANTENER: "HOLD",
                  "SIN DATO": "NO DATA", "ESPERAR GIRO": "WAIT FOR TURN" };
const senalLabel = (s) => (s == null ? s : t(s, SENAL_EN[s] || s));
const hace = (s) => (s < 3600 ? `${Math.round(s / 60)} min` : `${(s / 3600).toFixed(1)} h`);

// Frases fijas que arma el backend (momentum, rebalanceo de riesgo, Black-
// Litterman, riesgo cambiario): un catálogo chico y cerrado de sentencias
// completas, no prosa libre por ticker — se puede traducir con un diccionario
// exacto acá, sin el refactor de códigos de error que le falta al resto de
// los mensajes del servidor. Si el backend agrega una frase nueva que no está
// acá, `libre()` la deja pasar tal cual en español antes que romper nada.
const LIBRES_EN = {
  // momentum.py — veredicto por activo
  ["Subió fuerte pero la tendencia se está desacelerando: riesgo de reversión. "
  + "No es momento de sobreponderar."]:
    "It's risen hard but the trend is decelerating: risk of reversal. "
    + "Not the moment to overweight it.",
  "Tendencia positiva y sostenida en 12 y 3 meses. Viento a favor para entrar o mantener.":
    "Positive, sustained trend over 12 and 3 months. Tailwind to enter or hold.",
  "Baja en 12 y 3 meses: el momentum está en contra. Conviene esperar una señal de giro.":
    "Down over 12 and 3 months: momentum is against it. Better to wait for a turning signal.",
  "Posible giro al alza: 3 meses en positivo sobre un año flojo. Vigilar, todavía no confirma.":
    "Possible upward turn: 3 months positive over a weak year. Watch it, not confirmed yet.",
  "Sin tendencia clara. El momentum no aporta señal de timing.":
    "No clear trend. Momentum doesn't offer a timing signal.",
  // momentum.py — entrada
  "La tendencia de fondo no acompaña: el precio de entrada es una discusión para más adelante.":
    "The underlying trend doesn't support it: entry price is a discussion for later.",
  "Viene disparado en el último mes. Con la reversión de corto plazo a favor, conviene esperar el pullback.":
    "It's spiked in the last month. With short-term reversion in its favor, better to wait for the pullback.",
  ["Cayó en el último mes sin que la tendencia de fondo se rompa: es la entrada que el momentum de 12 meses "
  + "sigue avalando."]:
    "It dropped in the last month without breaking the underlying trend: it's the entry the 12-month "
    + "momentum still backs.",
  "El último mes no aporta ni descuento ni sobreprecio.":
    "The last month adds neither a discount nor a premium.",
  // momentum.py — nota_metodo
  ["El momentum principal es 12−1 (doce meses salteando el último) porque el mes más reciente tiende a "
  + "revertir. Ese mismo mes se usa aparte, y con el signo invertido, como señal de entrada."]:
    "The main momentum is 12−1 (twelve months skipping the last one) because the most recent month "
    + "tends to revert. That same month is used separately, with the sign flipped, as an entry signal.",
  // risk.py — rebalancear_a_var
  ["La cartera queda invertida al 100 %: se cambia la mezcla, no el nivel de exposición. Se busca el "
  + "movimiento más chico que cumple el límite, para no deshacer decisiones que ya tomaste."]:
    "The portfolio stays 100 % invested: the mix changes, not the exposure level. It looks for the "
    + "smallest move that satisfies the limit, so it doesn't undo decisions you already made.",
  ["La optimización usa el VaR paramétrico porque es derivable; el histórico del resultado se calcula "
  + "aparte y se muestra al lado, así la diferencia entre ambos queda a la vista."]:
    "The optimization uses parametric VaR because it's differentiable; the historical result is "
    + "calculated separately and shown alongside, so the difference between the two stays visible.",
  // risk.py — riesgo_cambiario
  ["Para un activo que cotiza en pesos, su retorno en dólares mezcla lo que hizo el activo con lo que "
  + "hizo el MEP. La descomposición reparte el término cruzado por igual entre las dos fuentes."]:
    "For an asset quoted in pesos, its dollar return mixes what the asset did with what the MEP rate "
    + "did. The decomposition splits the cross term evenly between the two sources.",
  // blacklitterman.py
  ["El equilibrio se calcula sobre los pesos de esta cartera, no sobre capitalizaciones de mercado: "
  + "mide cuánto te movés respecto de tu propia posición."]:
    "The equilibrium is calculated over this portfolio's own weights, not market capitalizations: "
    + "it measures how much you move relative to your own position.",
  "Sin views, Black-Litterman devuelve el punto de partida.":
    "Without views, Black-Litterman returns the starting point.",
};
const libre = (s) => (s == null ? s : t(s, LIBRES_EN[s] || s));

// EVENTOS (regimenes.py) y ESCENARIOS de stress-test (risk.py): catálogos
// fijos y acotados —28 eventos macro, 8 crisis reales—, no texto generado por
// usuario. Mismo criterio que LIBRES_EN: diccionario exacto, cae a español
// si el backend agrega uno nuevo que todavía no está acá.
const EVENTOS_EN = {
  "Corrida cambiaria: empieza la crisis de 2018": "Currency run: the 2018 crisis begins",
  "Acuerdo stand-by con el FMI": "Stand-by agreement with the IMF",
  "Tasa de política monetaria al 60 %": "Monetary policy rate hits 60 %",
  "PASO: derrota del oficialismo": "Primaries: ruling party defeated",
  "Reperfilamiento de la deuda de corto plazo": "Short-term debt reprofiling",
  "Vuelve el control de cambios": "Currency controls return",
  "Cambio de gobierno": "Change of government",
  "Arranca el desplome por COVID": "The COVID crash begins",
  "La OMS declara la pandemia": "The WHO declares the pandemic",
  "Piso del S&P 500; la Fed anuncia compras ilimitadas": "S&P 500 bottoms; the Fed announces unlimited purchases",
  "Cierra el canje de deuda soberana": "Sovereign debt swap closes",
  "PASO legislativas": "Legislative primaries",
  "Elecciones legislativas": "Legislative elections",
  "Principio de acuerdo con el FMI": "Preliminary agreement with the IMF",
  "Invasión de Ucrania": "Invasion of Ukraine",
  "La Fed empieza a subir tasas": "The Fed starts raising rates",
  "Renuncia de Guzmán; salto del dólar libre": "Guzmán resigns; free-market dollar jumps",
  "Massa asume el ministerio de Economía": "Massa takes over the Economy ministry",
  "Caída de Silicon Valley Bank": "Silicon Valley Bank collapses",
  "Sequía histórica: se derrumban las exportaciones": "Historic drought: exports collapse",
  "PASO y devaluación del 22 %": "Primaries and a 22 % devaluation",
  "Balotaje presidencial": "Presidential runoff",
  "Devaluación del 54 %": "54 % devaluation",
  "DNU de desregulación": "Deregulation decree",
  "Se aprueba la Ley Bases": "The Ley Bases is approved",
  "Fin del dólar blend para exportadores": "End of the blended exchange rate for exporters",
  "Nuevo acuerdo con el FMI; se flexibiliza el cepo": "New IMF agreement; capital controls eased",
  "Aranceles generalizados de EE.UU.": "Sweeping US tariffs",
  "Escalada Irán–Israel; salta el petróleo": "Iran–Israel escalation; oil spikes",
};
const eventoDescripcion = (s) => (s == null ? s : t(s, EVENTOS_EN[s] || s));
const ALCANCE_EN = { AR: "AR", MUNDO: "WORLD" };
const alcanceLabel = (a) => t(a, ALCANCE_EN[a] || a);

const ESCENARIOS_EN = {
  "Crisis subprime": "Subprime crisis", "PASO 2019": "2019 primaries",
  "Crash COVID": "COVID crash", "Reestructuración 2020": "2020 restructuring",
  "Invasión de Ucrania": "Invasion of Ukraine", "Ajuste de la Fed 2022": "2022 Fed tightening",
  "Devaluación diciembre 2023": "December 2023 devaluation", "Tensión en Ormuz": "Strait of Hormuz tension",
  "Cae Lehman: S&P 500 −40 % en diez semanas": "Lehman falls: S&P 500 −40 % in ten weeks",
  "Derrota del oficialismo: acciones −40 %, MEP +30 %": "Ruling party defeated: stocks −40 %, MEP rate +30 %",
  "S&P 500 −34 %, Merval −50 %": "S&P 500 −34 %, Merval −50 %",
  "Bonos en default técnico hasta el canje": "Bonds in technical default until the debt swap",
  "Energía y granos por las nubes; Europa −10 %": "Energy and grains soar; Europe −10 %",
  "Suba agresiva de tasas; caen los bonos emergentes": "Aggressive rate hikes; emerging bonds fall",
  "Devaluación del 54 %; los bonos en dólares suben": "54 % devaluation; dollar bonds rise",
  "Israel ataca Irán y amenaza el estrecho: crudo +20 %": "Israel strikes Iran and threatens the strait: crude +20 %",
};
const escenarioLabel = (s) => (s == null ? s : t(s, ESCENARIOS_EN[s] || s));

/* El resultado de los FCI suma al realizado como cualquier operación cerrada,
   pero no es del mismo tipo: es el saldo de cientos de suscripciones y rescates
   de un fondo, sin serie de precios y sin operación que mirar. Mientras se
   decide si cuenta o no, el toggle deja ver los dos números sin tocar los datos.

   Se recalcula acá y no en el servidor: los registros ya vienen con su resultado
   abierto en activo y tipo de cambio, así que restarlos es una suma —y el número
   cambia en el momento, sin volver a pedir nada. */
const redondo = (n) => Math.round(n * 100) / 100;

function quitarFci(real) {
  const fci = (real.trades || []).filter((t) => t.tipo === "fci");
  if (!fci.length) return real;
  const suma = (campo) => fci.reduce((s, t) => s + (t[campo] || 0), 0);
  const origen = { ...(real.total_origen || {}) };
  for (const t of fci) {
    if (t.pnl_origen != null) {
      origen[t.moneda] = redondo((origen[t.moneda] || 0) - t.pnl_origen);
      if (!origen[t.moneda]) delete origen[t.moneda];
    }
  }
  return { ...real,
    trades: real.trades.filter((t) => t.tipo !== "fci"),
    n: real.n - fci.length,
    total_usd: redondo(real.total_usd - suma("pnl_usd")),
    total_activo_usd: redondo(real.total_activo_usd - suma("pnl_activo_usd")),
    total_fx_usd: redondo(real.total_fx_usd - suma("pnl_fx_usd")),
    total_origen: origen };
}

/* Lo elige el usuario y es de este navegador, no del dato: si el almacenamiento
   no está disponible —una ventana privada— se sigue con los FCI incluidos. */
const FCI_KEY = "pa:fci-en-cerradas";
const leerPref = () => { try { return localStorage.getItem(FCI_KEY) !== "0"; }
                         catch { return true; } };
const guardarPref = (v) => { try { localStorage.setItem(FCI_KEY, v ? "1" : "0"); }
                             catch { /* sin almacenamiento: vale sólo esta sesión */ } };

/* Recuerda si un cuadro quedó abierto o cerrado, por `id`, en este navegador.
   La primera vez no hay nada guardado: se abre solo (`porDefecto`), y desde
   que el usuario lo cierra una vez, se acuerda para la próxima. */
const usarColapsable = (id, porDefecto = true) => {
  const key = "pa.colapsable." + id;
  const [abierto, setAbierto] = useState(() => {
    try {
      const v = localStorage.getItem(key);
      return v === null ? porDefecto : v === "1";
    } catch { return porDefecto; }
  });
  const alternar = () => setAbierto((a) => {
    const n = !a;
    try { localStorage.setItem(key, n ? "1" : "0"); } catch { /* sin memoria */ }
    return n;
  });
  return [abierto, alternar];
};

/* Un panel con título que se pliega y despliega, recordando la elección por
   `id` (ver `usarColapsable`). `extra` es contenido del título que no debe
   disparar el toggle —un botón de descarga, por ejemplo— así que se le corta
   la propagación del clic aparte. */
function Plegable({ id, titulo, extra, porDefecto = true, children }) {
  const [abierto, alternar] = usarColapsable(id, porDefecto);
  return (
    <div className="panel">
      <h3 style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span onClick={alternar} role="button" tabIndex={0}
              style={{ cursor: "pointer", display: "flex", alignItems: "center", gap: 8,
                       userSelect: "none" }}
              onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && alternar()}>
          <span style={{ display: "inline-block", transition: "transform .15s",
                         transform: abierto ? "rotate(90deg)" : "rotate(0deg)" }}>▸</span>
          {titulo}
        </span>
        {extra && <span style={{ marginLeft: "auto" }} onClick={(e) => e.stopPropagation()}>
          {extra}
        </span>}
      </h3>
      {abierto && children}
    </div>
  );
}

/* El mismo color con transparencia. Las bandas de un abanico se pisan entre
   ellas, y el `opacity` de la traza no toca el relleno: tiene que ir en el
   color o la última cartera dibujada tapa a todas las anteriores. */
const rgba = (hex, a) => {
  const h = String(hex || "").replace("#", "").trim();
  const n = parseInt(h.length === 3 ? h.split("").map((x) => x + x).join("") : h, 16);
  return Number.isFinite(n) ? `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`
                            : hex;
};

/* Los campos de importes son type="text" y no type="number", y `dec()` es el
   que interpreta lo que se tipeó. Con el locale en es-AR el navegador espera
   coma decimal en un input numérico y **descarta el punto**: la tecla . del
   teclado numérico no escribía nada y no había forma de cargar un decimal sin
   soltar el numpad. Con texto entran las dos formas y acá se normaliza. */
const dec = (v) => {
  const n = parseFloat(String(v ?? "").trim().replace(",", "."));
  return Number.isFinite(n) ? n : null;
};
/* Deja tipear sólo lo que puede ser un número, con cualquiera de los dos
   separadores. Sin esto, un campo de texto acepta letras. */
const soloNum = (v) => String(v).replace(/[^\d.,-]/g, "");

// Lo que está en evaluación se ve sólo con ?lab=1. Se borra al aprobarse.
const LAB = new URLSearchParams(location.search).has("lab");

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
      xaxis: { showgrid: false, linecolor: c.borde, zerolinecolor: c.borde, automargin: true },
      yaxis: { showgrid: false, linecolor: c.borde, zerolinecolor: c.borde, automargin: true },
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

function diaEtiqueta(iso) {
  if (!iso) return "";
  const hoy = new Date();
  const local = `${hoy.getFullYear()}-${String(hoy.getMonth() + 1).padStart(2, "0")}-${String(hoy.getDate()).padStart(2, "0")}`;
  if (iso === local) return t("hoy", "today");
  return new Date(iso + "T12:00:00").toLocaleDateString(IDIOMA === "en" ? "en" : "es",
                                                          { day: "numeric", month: "short" });
}

function Kpi({ etiqueta, valor, sub, tono, ayuda }) {
  const [abierto, setAbierto] = useState(false);
  return (
    <div className={"kpi " + (tono || "")}
         onMouseLeave={() => setAbierto(false)}>
      <div className="et">
        {etiqueta}
        {ayuda && (
          <button className="ayuda" aria-label={t("Qué significa", "What it means")}
                  onMouseEnter={() => setAbierto(true)}
                  onClick={(e) => { e.stopPropagation(); setAbierto(!abierto); }}>?</button>
        )}
      </div>
      <div className="val mono">{valor}</div>
      {sub && <div className="sub">{sub}</div>}
      {abierto && ayuda && (
        <div className="globo">
          <b>{t(...ayuda.que)}</b>
          {t(...ayuda.como)}
          {ayuda.umbral && <div className="umbral">{t(...ayuda.umbral)}</div>}
        </div>
      )}
    </div>
  );
}

/* Explicaciones. Qué mide · cómo se lee · desde qué valor mirar con atención.
   Cada campo es [es, en]: se resuelve con t() en el render de Kpi, no acá —
   este objeto se arma una sola vez al cargar el módulo, así que si guardara
   el string ya resuelto quedaría congelado en el idioma que hubiera en ese
   momento y un cambio de idioma no lo actualizaría nunca. */
const AYUDA = {
  valor: { que: ["Valor de la cartera", "Portfolio value"],
    como: ["Cuánto valen hoy todas tus posiciones, en dólares, usando el precio de cierre más reciente de cada activo.",
           "What all your positions are worth today, in dollars, using each asset's most recent closing price."] },
  pnl: { que: ["Ganancia o pérdida no realizada", "Unrealized gain or loss"],
    como: ["La diferencia entre lo que valen hoy y lo que te costaron, comisiones incluidas. Cada compra se convirtió a dólares con el MEP del día en que la hiciste, no con el de hoy.",
           "The difference between what they're worth today and what they cost you, commissions included. Each purchase was converted to dollars at that day's exchange rate, not today's."],
    umbral: ["Es lo que ganarías o perderías si vendieras todo ahora.",
             "It's what you'd gain or lose if you sold everything now."] },
  realizado: { que: ["Ganancia o pérdida ya cerrada", "Already realized gain or loss"],
    como: ["Lo que dejaron las posiciones que vendiste, netas de comisiones. Cada pata se convierte a dólares con el MEP de su propia fecha, así el resultado no mezcla el movimiento del tipo de cambio con el del activo.",
           "What the positions you sold left behind, net of commissions. Each leg is converted to dollars at its own date's rate, so the result doesn't mix the exchange rate's movement with the asset's."],
    umbral: ["Ya está cobrado: no cambia con el precio de mañana.",
             "It's already collected: it doesn't change with tomorrow's price."] },
  sharpe: { que: ["Sharpe", "Sharpe"],
    como: ["Cuánto retorno conseguís por cada unidad de riesgo que asumís. Compara tu ganancia contra la de una letra del Tesoro, que no tiene riesgo.",
           "How much return you get for each unit of risk you take on. Compares your gain against a risk-free Treasury bill."],
    umbral: ["Por debajo de 0,5 el riesgo no se está pagando. Arriba de 1 es bueno; arriba de 2, excelente y poco frecuente.",
             "Below 0.5 the risk isn't paying off. Above 1 is good; above 2 is excellent and rare."] },
  sortino: { que: ["Sortino", "Sortino"],
    como: ["Como el Sharpe, pero solo castiga la volatilidad hacia abajo. Que la cartera suba mucho un día no es un problema, y el Sharpe lo trata como si lo fuera.",
           "Like Sharpe, but it only penalizes downside volatility. A portfolio jumping up a lot in one day isn't a problem, and Sharpe treats it as if it were."],
    umbral: ["Suele ser mayor que el Sharpe. Si son parecidos, las caídas pesan tanto como las subas.",
             "Usually higher than Sharpe. If they're similar, drops weigh as much as rallies."] },
  vol: { que: ["Volatilidad anual", "Annual volatility"],
    como: ["Cuánto oscila la cartera. Es la banda dentro de la cual se mueve en un año normal.",
           "How much the portfolio swings. It's the band it moves within during a normal year."],
    umbral: ["Hasta 15 % es conservadora, 15-25 % moderada, más de 25 % agresiva.",
             "Up to 15 % is conservative, 15-25 % moderate, above 25 % aggressive."] },
  var95: { que: ["Pérdida en un día malo", "Loss on a bad day"],
    como: ["De cada veinte ruedas, una es al menos así de mala. No es el peor caso: es el umbral a partir del cual empieza el 5 % peor.",
           "Out of every twenty sessions, one is at least this bad. It's not the worst case: it's the threshold where the worst 5 % begins."],
    umbral: ["Mirá también la pérdida en un día muy malo, que es cuánto se pierde cuando ese día llega.",
             "Also check the loss on a very bad day, which is how much is lost when that day actually arrives."] },
  cvar: { que: ["Pérdida en un día muy malo", "Loss on a very bad day"],
    como: ["El promedio de lo que se pierde en ese 5 % de días peores. Responde qué tan grave es cuando efectivamente sale mal.",
           "The average of what's lost on that worst 5 % of days. It answers how bad it gets when things actually go wrong."] },
  maxdd: { que: ["Peor caída", "Worst drawdown"],
    como: ["La caída más grande desde un máximo hasta el piso siguiente, en toda la historia de la cartera. Es lo que había que aguantar sin vender.",
           "The largest drop from a peak to the following bottom, across the portfolio's whole history. It's what you had to sit through without selling."] },
  calmar: { que: ["Calmar", "Calmar"],
    como: ["Cuánto rinde la cartera por cada punto de su peor caída. Junta rendimiento y sufrimiento en un solo número.",
           "How much the portfolio yields per point of its worst drawdown. It combines return and pain into a single number."],
    umbral: ["Por encima de 1 el retorno anual supera a la peor caída histórica.",
             "Above 1, the annual return exceeds the worst historical drawdown."] },
  curtosis: { que: ["Curtosis en exceso", "Excess kurtosis"],
    como: ["Cuán frecuentes son los movimientos extremos comparado con una campana normal. Está medida en exceso: una distribución normal da 0.",
           "How frequent extreme moves are compared to a normal bell curve. Measured in excess: a normal distribution gives 0."],
    umbral: ["Arriba de 3 hay colas gordas: los días muy malos pasan más seguido de lo que supone cualquier modelo normal.",
             "Above 3 there are fat tails: very bad days happen more often than any normal model assumes."] },
  concentracion: { que: ["Activos efectivos", "Effective assets"],
    como: ["Cuántos activos realmente diversifican. Se calcula como 1 dividido la suma de los pesos al cuadrado.",
           "How many assets are really diversifying. Calculated as 1 divided by the sum of the squared weights."],
    umbral: ["Si tenés nueve posiciones pero este número da 2, la cartera se comporta casi como si tuviera dos.",
             "If you hold nine positions but this number comes out at 2, the portfolio behaves almost as if it had two."] },
  beta: { que: ["Beta", "Beta"],
    como: ["Cuánto amplifica la cartera los movimientos del índice. Con beta 1,2, si el índice sube 10 % la cartera tiende a subir 12 %.",
           "How much the portfolio amplifies the index's moves. With a beta of 1.2, if the index rises 10 % the portfolio tends to rise 12 %."],
    umbral: ["Solo significa algo si el R² es alto: si el índice no explica la cartera, el beta es ruido.",
             "Only means something if R² is high: if the index doesn't explain the portfolio, beta is noise."] },
  alpha: { que: ["Alpha", "Alpha"],
    como: ["El rendimiento que la cartera consiguió por encima de lo que le correspondía por el riesgo de mercado que asumió.",
           "The return the portfolio achieved above what it was owed for the market risk it took on."] },
  r2: { que: ["R²", "R²"],
    como: ["Cuánto de lo que hace la cartera explica ese índice. Va de 0 a 1.",
           "How much of what the portfolio does that index explains. Ranges from 0 to 1."],
    umbral: ["Debajo de 0,2 el índice no es un comparable válido y beta y alpha no se sostienen.",
             "Below 0.2 the index isn't a valid comparable and beta and alpha don't hold up."] },
  tir: { que: ["TIR", "Yield to maturity"],
    como: ["El rendimiento anual que obtenés si comprás el bono a este precio y lo mantenés hasta el vencimiento, cobrando todos sus pagos.",
           "The annual return you get if you buy the bond at this price and hold it to maturity, collecting all its payments."] },
  duracion: { que: ["Duración modificada", "Modified duration"],
    como: ["Cuánto cae el precio del bono si la tasa sube un punto porcentual. Duración 3 significa que sube la tasa 1 % y el precio cae cerca de 3 %.",
           "How much the bond's price drops if the rate rises one percentage point. A duration of 3 means the rate rises 1 % and the price drops around 3 %."] },
  dv01: { que: ["DV01", "DV01"],
    como: ["Cuántos dólares pierde la cartera si toda la curva de tasas sube un punto básico, o sea una centésima de punto porcentual.",
           "How many dollars the portfolio loses if the whole rate curve rises one basis point, i.e. a hundredth of a percentage point."] },
};

/* ═══════════════ Barra superior ═══════════════ */

/* La identidad de Google arriba a la derecha: foto, nombre y, al tocarla, la
   opción de salir. La foto viene en el id_token; si Google no la manda o el
   archivo no carga, queda la inicial del nombre — nunca un hueco roto. */

/* Quién decide si esto es un teléfono: el navegador, que sabe el ancho real y
   se entera cuando rotás. El User-Agent no sabe ninguna de las dos cosas —y en
   iPhone ni siquiera manda Sec-CH-UA-Mobile, que es de Chromium. */
function useMedia(q) {
  const [va, setVa] = useState(() => window.matchMedia(q).matches);
  useEffect(() => {
    const m = window.matchMedia(q);
    const on = () => setVa(m.matches);
    m.addEventListener("change", on);
    setVa(m.matches);
    return () => m.removeEventListener("change", on);
  }, [q]);
  return va;
}

const ES_MOVIL = "(max-width: 640px)";

function Usuario({ yo, compacto, idioma, cambiarIdioma }) {
  const [abierto, setAbierto] = useState(false);
  const [sinFoto, setSinFoto] = useState(false);
  const caja = useRef(null);

  useEffect(() => {
    if (!abierto) return;
    const afuera = (e) => { if (!caja.current?.contains(e.target)) setAbierto(false); };
    const esc = (e) => { if (e.key === "Escape") setAbierto(false); };
    document.addEventListener("mousedown", afuera);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", afuera);
                   document.removeEventListener("keydown", esc); };
  }, [abierto]);

  // Salir tira la cookie de la app Y el sobre de Cocos: son dos sesiones
  // distintas, pero irse es irse de las dos.
  const salir = async () => { await post("/api/salir"); sesion.tirar(); location.reload(); };
  const inicial = (yo.nombre || yo.email || "?").trim()[0].toUpperCase();

  return (
    <div ref={caja} style={{ position: "relative" }}>
      <button className="btn auto" onClick={() => setAbierto((v) => !v)}
              title={yo.email} aria-haspopup="menu" aria-expanded={abierto}
              style={{ display: "flex", alignItems: "center", gap: 7, paddingLeft: 4 }}>
        {yo.foto && !sinFoto ? (
          <img src={yo.foto} alt="" width="22" height="22" referrerPolicy="no-referrer"
               onError={() => setSinFoto(true)}
               style={{ borderRadius: "50%", display: "block" }} />
        ) : (
          <span style={{ width: 22, height: 22, borderRadius: "50%", display: "grid",
                         placeItems: "center", background: "var(--acento)",
                         color: "var(--panel)", fontSize: 11, fontWeight: 700 }}>
            {inicial}</span>
        )}
        {!compacto && (
          <span style={{ maxWidth: 130, overflow: "hidden", textOverflow: "ellipsis",
                         whiteSpace: "nowrap" }}>
            {yo.nombre || yo.email}</span>
        )}
      </button>

      {abierto && (
        <div className="panel" role="menu"
             style={{ position: "absolute", right: 0, top: "calc(100% + 6px)",
                      minWidth: 210, padding: 10, zIndex: 50, marginBottom: 0 }}>
          <div className="pie" style={{ margin: 0, wordBreak: "break-all" }}>{yo.email}</div>
          {cambiarIdioma && (
            <label style={{ display: "block", fontSize: 11.5, color: "var(--texto-3)", marginTop: 8 }}>
              {t("Idioma", "Language")}<br />
              <select value={idioma || "es"} style={{ width: "100%", marginTop: 3 }}
                      onChange={(e) => cambiarIdioma(e.target.value)}>
                <option value="es">Español</option>
                <option value="en">English</option>
              </select>
            </label>
          )}
          <button className="btn peligro" role="menuitem" onClick={salir}
                  style={{ width: "100%", marginTop: 8 }}>{t("Salir", "Sign out")}</button>
        </div>
      )}
    </div>
  );
}

// Las tres últimas sólo existen para quien invierte desde Argentina: el MEP, el
// broker y la cuenta espejo no le dicen nada a un europeo.
const MODOS = [["analisis", "Análisis"], ["comparacion", "Comparación"],
               ["carteras", "Carteras"], ["mercado", "Dólar MEP"],
               ["conectores", "Conectores"], ["cocos", "Cocos"], ["inviu", "InvIU"]];
const MODOS_LOCALES = ["mercado", "conectores", "cocos", "inviu"];
// Las de MODOS_LOCALES son herramientas de Argentina (MEP, Cocos, InvIU): sólo
// las ve quien invierte desde acá, así que quedan en español siempre — la
// jerga ("dólar MEP") no existe en otros mercados y traducirla literal sería
// peor que dejarla como está.
const MODOS_EN = { analisis: "Analysis", comparacion: "Comparison", carteras: "Portfolios" };
const modoLabel = (k, es) => t(es, MODOS_EN[k] || es);

/* La barra de la app no entra en un teléfono: los seis modos miden 517 px de
   ancho y la pantalla tiene 393. Acá van en un panel que se abre, y arriba
   queda sólo lo que hace falta ver siempre: dónde estás, qué cartera mirás y
   quién sos.

   Es un componente aparte y no una versión con media queries del de escritorio
   a propósito: el camino de PC no cambia ni una línea. */
function BarraMovil({ modo, setModo, tema, setTema, carteras, cartera, setCartera, yo, mercado,
                      idioma, cambiarIdioma }) {
  const [abierto, setAbierto] = useState(false);
  const locales = MERCADOS[mercado].locales;
  const visibles = MODOS.filter(([k]) => locales || !MODOS_LOCALES.includes(k));
  const sistemaOscuro = window.matchMedia?.("(prefers-color-scheme: dark)").matches;
  const esOscuro = tema === "dark" || (tema === "auto" && sistemaOscuro);

  // Con el panel abierto, el fondo no se scrollea: si no, el dedo arrastra la
  // página de atrás y se pierde el menú.
  useEffect(() => {
    if (!abierto) return;
    const esc = (e) => { if (e.key === "Escape") setAbierto(false); };
    document.addEventListener("keydown", esc);
    document.body.style.overflow = "hidden";
    return () => { document.removeEventListener("keydown", esc);
                   document.body.style.overflow = ""; };
  }, [abierto]);

  const elegir = (k) => { setModo(k); setAbierto(false); };

  return (
    <>
      <div className="barra-m">
        <button className="barra-m-ham" onClick={() => setAbierto(true)}
                aria-label={t("Menú", "Menu")} aria-expanded={abierto}>
          <span /><span /><span />
        </button>
        <div className="marca">Portfolio <span>Analyzer</span></div>
        {yo?.email && <Usuario yo={yo} compacto idioma={idioma} cambiarIdioma={cambiarIdioma} />}
      </div>

      {/* La cartera se cambia mucho más seguido que el modo: queda a mano. */}
      {modo === "analisis" && (
        <div className="barra-m-cartera">
          <select value={cartera || ""} onChange={(e) => setCartera(e.target.value)}>
            <option value="">{t("— elegí una cartera —", "— choose a portfolio —")}</option>
            {carteras.map((c) => <option key={c.nombre} value={c.nombre}>{c.nombre}</option>)}
          </select>
        </div>
      )}

      {abierto && (
        <div className="menu-m-fondo" onClick={() => setAbierto(false)}>
          <nav className="menu-m" onClick={(e) => e.stopPropagation()}>
            <div className="menu-m-alto">
              <span className="plaza" title={t(`Se mide desde ${MERCADOS[mercado].nombre}`,
                                                `Measured from ${MERCADOS[mercado].nombre_en}`)}>
                {MERCADOS[mercado].bandera} {t(MERCADOS[mercado].nombre, MERCADOS[mercado].nombre_en)}</span>
              <button className="btn" onClick={() => setAbierto(false)}
                      aria-label={t("Cerrar", "Close")}>✕</button>
            </div>
            {visibles.map(([k, etiqueta]) => (
              <button key={k} className={"menu-m-item" + (modo === k ? " on" : "")}
                      onClick={() => elegir(k)}>{modoLabel(k, etiqueta)}</button>
            ))}
            <div className="menu-m-pie">
              <label className="lab-dianoche"
                     title={esOscuro ? t("Pasar a claro", "Switch to light")
                                      : t("Pasar a oscuro", "Switch to dark")}>
                <input type="checkbox" checked={!esOscuro} aria-label={t("Tema claro", "Light theme")}
                       onChange={() => setTema(esOscuro ? "light" : "dark")} />
                <span className="g"><span className="estrellas" /></span>
              </label>
            </div>
          </nav>
        </div>
      )}
    </>
  );
}

function Barra({ modo, setModo, tema, setTema, carteras, cartera, setCartera, yo,
                 mercado, idioma, cambiarIdioma }) {
  // El switch es binario y el tema tiene tres estados: "auto" —mientras no se
  // tocó— se resuelve mirando qué prefiere el sistema.
  const sistemaOscuro = window.matchMedia?.("(prefers-color-scheme: dark)").matches;
  const esOscuro = tema === "dark" || (tema === "auto" && sistemaOscuro);
  const locales = MERCADOS[mercado].locales;
  return (
    <div className="barra">
      <div className="marca">Portfolio <span>Analyzer</span></div>
      <div className="modos">
        {MODOS.filter(([k]) => locales || !MODOS_LOCALES.includes(k)).map(([k, etiqueta]) => (
          <button key={k} className={"modo" + (modo === k ? " on" : "")}
                  onClick={() => setModo(k)}>{modoLabel(k, etiqueta)}</button>
        ))}
      </div>
      {/* La plaza no se elige acá: es de la cartera y se fija en Carteras. Un
          selector suelto en la barra invitaba a cambiarla como si fuera una
          vista, cuando cambia la moneda con la que se mide todo. */}
      <span className="plaza" title={t(`Se mide desde ${MERCADOS[mercado].nombre}`,
                                        `Measured from ${MERCADOS[mercado].nombre_en}`)}>
        {MERCADOS[mercado].bandera} {t(MERCADOS[mercado].nombre, MERCADOS[mercado].nombre_en)}</span>
      {(modo === "analisis") && (
        <select value={cartera || ""} onChange={(e) => setCartera(e.target.value)}>
          <option value="">{t("— elegí una cartera —", "— choose a portfolio —")}</option>
          {carteras.map((c) => <option key={c.nombre} value={c.nombre}>{c.nombre}</option>)}
        </select>
      )}
      <div className="der">
        {yo?.email && <Usuario yo={yo} idioma={idioma} cambiarIdioma={cambiarIdioma} />}
        <label className="lab-dianoche"
               title={esOscuro ? t("Pasar a claro", "Switch to light") : t("Pasar a oscuro", "Switch to dark")}>
          <input type="checkbox" checked={!esOscuro} aria-label={t("Tema claro", "Light theme")}
                 onChange={() => setTema(esOscuro ? "light" : "dark")} />
          <span className="g"><span className="estrellas" /></span>
        </label>
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
const PESTANAS_EN = { posicion: "Position", riesgo: "Risk", markowitz: "Optimization",
                      montecarlo: "Monte Carlo", regimenes: "Regimes" };
const pestanaLabel = (k, es) => t(es, PESTANAS_EN[k] || es);

const BENCHMARKS = [["SP500", "S&P 500"], ["MERVAL", "Merval"], ["STOXX600", "STOXX 600"]];

/* ── Simulación ─────────────────────────────────────────────────────────────
   "¿Y si compro esto?" sin armar una cartera paralela: los activos simulados se
   suman a los que ya tenés y toda la pantalla —composición, riesgo, frontera,
   Monte Carlo, Black-Litterman— se recalcula con ellos adentro.

   Sólo hace falta el ticker y la cantidad: el precio es el de mercado, así que
   la compra entra sin ganancia ni pérdida y lo único que mueve son los pesos,
   que es la pregunta. Vender descuenta de lo que ya tenés, del lote más viejo
   al más nuevo; no realiza resultado, porque no vendiste nada. */
function Simulador({ cartera, sim, setSim, tenencias }) {
  const [f, setF] = useState({ ticker: "", qty: "" });
  const [check, setCheck] = useState(null);
  const [msg, setMsg] = useState(null);
  const [abierto, setAbierto] = useState(false);

  const tk = f.ticker.trim().toUpperCase();
  const tiene = tenencias[tk] || 0;

  const validar = async () => {
    if (!tk) { setCheck(null); return; }
    setCheck({ cargando: true });
    setCheck(await api(`/api/validar/${encodeURIComponent(tk)}`));
  };

  // Un renglón por ticker: comprar y vender el mismo papel es una cantidad neta,
  // no dos órdenes contradictorias viajando juntas.
  const sumar = (signo) => {
    const pedida = dec(f.qty);
    if (!tk || !pedida || pedida <= 0) { setMsg(t("Falta el ticker o la cantidad.", "Ticker or quantity is missing.")); return; }
    if (signo < 0 && !tiene) { setMsg(t(`No tenés ${tk} en la cartera: no hay nada que vender.`,
                                        `You don't hold ${tk} in the portfolio: there's nothing to sell.`)); return; }
    // Vender más de lo que hay no es un descubierto, es un error de tipeo.
    const q = signo < 0 ? -Math.min(pedida, tiene) : pedida;
    const previo = sim.find((x) => x.ticker === tk)?.qty || 0;
    const total = Math.round((previo + q) * 1e6) / 1e6;
    setSim([...sim.filter((x) => x.ticker !== tk), ...(total ? [{ ticker: tk, qty: total }] : [])]);
    setF({ ticker: "", qty: "" }); setCheck(null); setMsg(null);
    // El recorte no se avisa con un mensaje: al cambiar la simulación se rehace
    // la pantalla entera y el aviso se iría antes de que alguien lo lea. Lo dice
    // el chip, que muestra la cantidad que realmente quedó aplicada.
  };

  const quitar = (x) => setSim(sim.filter((s2) => s2.ticker !== x.ticker));

  if (!abierto && !sim.length) return (
    <button className="lab-neon" style={{ marginBottom: 10 }} onClick={() => setAbierto(true)}>
      {t("Simular operación", "Simulate a trade")}</button>);

  return (
    <div className="panel lab-sim" style={{ marginBottom: 12 }}>
      <h3>{t("Simulación sobre", "Simulation on")} {cartera}
        <button className="btn" style={{ marginLeft: "auto", padding: "3px 10px", fontSize: 12 }}
                onClick={() => { setAbierto(false); setMsg(null); }}>{t("Cerrar", "Close")}</button>
      </h3>

      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "flex-end", marginTop: 10 }}>
        <label style={{ fontSize: 11.5, color: "var(--texto-3)" }}>
          Ticker<br />
          <input value={f.ticker} placeholder="AAPL" style={{ width: 130, marginTop: 3 }}
                 onChange={(e) => setF({ ...f, ticker: e.target.value })} onBlur={validar} />
        </label>
        <label style={{ fontSize: 11.5, color: "var(--texto-3)" }}>
          {t("Cantidad", "Quantity")}<br />
          <input type="text" inputMode="decimal" value={f.qty} style={{ width: 110, marginTop: 3 }}
                 onChange={(e) => setF({ ...f, qty: soloNum(e.target.value) })} />
        </label>
        <button className="btn primario" onClick={() => sumar(1)}>{t("Comprar", "Buy")}</button>
        <button className="btn" onClick={() => sumar(-1)} disabled={!tiene}
                title={tiene ? t(`Tenés ${num(tiene, 0)}`, `You hold ${num(tiene, 0)}`)
                             : t("Sólo se puede vender lo que está en la cartera", "You can only sell what's in the portfolio")}>
          {t("Vender", "Sell")}{tiene ? ` (${t("tenés", "you hold")} ${num(tiene, 0)})` : ""}</button>
      </div>

      {check && !check.cargando && (
        <div className={"aviso " + (check.valido && check.alcanza_para_analisis ? "ok"
                                    : check.valido ? "ojo" : "mal")}>
          {check.valido
            ? <>{t("Cotiza en", "Quoted in")} <b>{check.moneda}</b>, {t("último", "last")} <b>{usd(check.ultimo_usd, 4)}</b>
                {dec(f.qty) ? <> · {num(dec(f.qty), 0)} × {usd(check.ultimo_usd, 4)} = {" "}
                  <b>{usd(dec(f.qty) * check.ultimo_usd)}</b></> : null}. {check.detalle}</>
            : <>{check.detalle}</>}
        </div>)}
      {msg && <div className="aviso ojo">{msg}</div>}

      {sim.length > 0 && (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginTop: 12 }}>
          {sim.map((x) => (
            <span key={x.ticker} className={"chip " + (x.qty > 0 ? "ok" : "mal")}
                  style={{ minWidth: 0, gap: 8 }}>
              <b className="mono">{x.ticker}</b> {x.qty > 0 ? "+" : "−"}{num(Math.abs(x.qty), 0)}
              <button className="lab-x" title={t("Sacar de la simulación", "Remove from the simulation")}
                      onClick={() => quitar(x)}>×</button>
            </span>))}
          <button className="btn" style={{ marginLeft: "auto", padding: "3px 10px", fontSize: 12 }}
                  onClick={() => setSim([])}>{t("Volver a mi cartera", "Back to my portfolio")}</button>
        </div>)}

      <div className="pie">
        {IDIOMA === "en" ? (sim.length > 0
          ? <>Everything you see below is <b>{cartera} with the simulation applied</b>, not your
              actual portfolio. None of this is saved: it goes away when you remove it. The buy
              enters at today's price, so it doesn't add or subtract result — what changes are the
              weights, the risk and the optimization. The sale deducts the oldest lots first and
              doesn't realize gains either: you didn't actually sell anything.</>
          : <>Ticker and quantity, nothing else: the market sets the price. The whole portfolio is
              recalculated with the asset inside, and in Comparison you can measure one against
              the other without duplicating the portfolio. You can't sell more of a stock than you
              hold: the chip shows the quantity that was actually applied.</>
        ) : (sim.length > 0
          ? <>Todo lo que ves abajo es <b>{cartera} con la simulación puesta</b>, no tu cartera.
              Nada de esto se guarda: se va cuando la sacás. La compra entra al precio de hoy,
              así que no suma ni resta resultado — lo que cambia son los pesos, el riesgo y la
              optimización. La venta descuenta los lotes más viejos primero y tampoco realiza
              ganancia: no vendiste nada.</>
          : <>Ticker y cantidad, nada más: el precio lo pone el mercado. Se recalcula la cartera
              entera con el activo adentro, y en Comparación podés medir una contra otra sin
              tener que duplicar la cartera. De un papel no se vende más de lo que tenés: el
              chip dice la cantidad que quedó aplicada.</>)}
      </div>
    </div>
  );
}

function Analisis({ cartera, recargar, sim, setSim }) {
  const [run, setRun] = useState(null);
  const [estado, setEstado] = useState(null);
  const [tab, setTab] = useState("posicion");
  const [bench, setBench] = useState(() => MERCADOS[MERCADO].bench);
  // Mientras el usuario no elija índice manda el que mejor explica la cartera:
  // lo dice el CAPM cuando termina de medir los tres. Si lo tocó se respeta —
  // un selector que se mueve solo después de que lo movieron es un bug.
  const [auto, setAuto] = useState(true);
  const eligio = useRef(false);
  useEffect(() => { eligio.current = false; setAuto(true); }, [cartera]);
  useEffect(() => {
    const oir = (e) => {
      if (eligio.current || !e.detail) return;
      setBench(e.detail); setAuto(true);
    };
    window.addEventListener("pa:indice", oir);
    return () => window.removeEventListener("pa:indice", oir);
  }, []);
  // La simulación es parte de qué se está analizando: cambiarla es relanzar.
  const simKey = simul.cabecera(sim);

  const lanzar = useCallback((forzar = false) => {
    if (!cartera) return;
    // Recalcular no vacía la pantalla: los números de antes se quedan a la vista
    // mientras se rehacen, y el botón es el que cuenta que está trabajando.
    setEstado((e) => (forzar && e ? { ...e, estado: "corriendo" } : null));
    setRun(null);
    api(`/api/analisis/${encodeURIComponent(cartera)}`,
        { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ forzar }) })
      .then((d) => d.run_id && setRun(d.run_id))
      .catch(() => setTimeout(lanzar, 2000));
  }, [cartera]);

  useEffect(() => { lanzar(); }, [lanzar, simKey]);

  /* El bucle que va pintando los paneles a medida que terminan.

     Los dos `catch` no son prolijidad: son el bucle. Sin ellos, un `fetch` que
     falla —la pestaña que el navegador suspende en segundo plano, la wifi que
     hipa, un servidor que se reinicia— rechaza la promesa, la cadena de
     `setTimeout` no se vuelve a armar y el polling muere **en silencio**. La
     pantalla queda congelada en "6 de 11 modelos listos" para siempre aunque el
     servidor haya terminado los once hace rato, que fue exactamente lo que pasó
     el 2026-09-09: el navegador abortó tres pedidos a la vez y no preguntó nunca
     más. Un análisis que no avanza tiene que ser un análisis que no avanza, no
     un cliente que dejó de mirar.

     Y si la corrida ya no existe —el servidor se reinició, o pasaron veinte
     corridas y se descartó la vieja— se relanza sola en vez de esperar por un
     run_id que no va a volver. */
  useEffect(() => {
    if (!run || !cartera) return;
    let vivo = true;
    const consultar = async () => {
      let d = null;
      try {
        d = await api(`/api/analisis/${encodeURIComponent(cartera)}/${run}`);
      } catch { /* se reintenta abajo */ }
      if (!vivo) return;
      if (d && /no existe|se descartó/i.test(d.error || "")) { lanzar(); return; }
      if (d) setEstado(d);
      if (!d || d.estado !== "terminado") setTimeout(consultar, 1200);
    };
    consultar();
    return () => { vivo = false; };
  }, [run, cartera, lanzar]);

  if (!cartera) return <div className="vacio">{t("Elegí una cartera arriba para analizarla.",
                                                  "Choose a portfolio above to analyze it.")}</div>;
  if (!estado) return <div className="cargando">{t("Lanzando los modelos…", "Launching the models…")}</div>;

  const R = estado.resultados || {};
  const M = estado.modelos || {};
  const listos = Object.values(M).filter((m) => m.estado === "listo").length;

  return (
    <>
      {estado.estado !== "terminado" && (
        <PasosModelos M={M} listos={listos} />
      )}
      <div className="tabs">
        {PESTANAS.filter(([k]) => k in M).map(([k, etiqueta]) => (
          <button key={k} className={"tab" + (tab === k ? " on" : "")} onClick={() => setTab(k)}>
            {pestanaLabel(k, etiqueta)}<span className={"pin " + (M[k]?.estado === "listo" ? "listo"
                 : M[k]?.estado === "error" ? "error" : "corriendo")} />
          </button>
        ))}
        {/* Con la simulación puesta, todas las pestañas muestran números que no
            son los de tu cartera. El cartel que lo explica vive en Posición, así
            que en el resto queda esta marca — y lleva ahí de un clic. */}
        {sim.length > 0 && (
          <button className="chip ojo lab-marca" onClick={() => setTab("posicion")}
                  title={t("Estás viendo la cartera con activos simulados. Se edita en Posición.",
                           "You're viewing the portfolio with simulated assets. Edit it in Position.")}>
            {t("simulación", "simulation")} · {sim.length}</button>)}
        {/* El índice solo cambia algo en dos pestañas: en Posición manda sobre
            beta, alpha y R², y en Optimización calibra la aversión al riesgo (δ)
            de Black-Litterman. En Riesgo, Monte Carlo y Regímenes lo único que
            movería es la región de la tasa libre de riesgo, que ya va escrita
            debajo de cada KPI que la usa. Mostrarlo ahí invitaba a tocarlo
            esperando un efecto que no existe. */}
        {(tab === "posicion" || tab === "markowitz") && (
          <span style={{ marginLeft: "auto", display: "flex", alignItems: "center",
                         gap: 7, paddingBottom: 6 }}>
            <span style={{ fontSize: 12, color: "var(--texto-3)" }}>{t("Comparar contra", "Compare against")}</span>
            <select value={bench}
                    title={auto ? t("Elegido solo: es el índice que mejor explica esta "
                                  + "cartera, el de R² más alto de los tres.",
                                  "Chosen automatically: it's the index that best explains this "
                                  + "portfolio, the one with the highest R² of the three.") : undefined}
                    onChange={(e) => { eligio.current = true; setAuto(false);
                                       setBench(e.target.value); }}>
              {BENCHMARKS.map(([k, etq]) => <option key={k} value={k}>{etq}</option>)}
            </select>
          </span>)}
      </div>
      {/* De cuándo son estos números. Volver a esta pantalla reusa el análisis
          que ya está hecho —los precios se vuelven a pedir cada dos horas, así
          que recalcular antes da lo mismo con más espera—, y acá está el botón
          para el que quiera pedirlo igual. */}
      {(() => {
        const corriendo = estado.estado !== "terminado";
        const fresco = !corriendo && estado.edad_s < 90;
        return (
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap",
                        margin: "-2px 0 10px", fontSize: 12, color: "var(--texto-3)" }}>
            <span>{corriendo ? t("Rehaciendo los modelos…", "Redoing the models…")
                   : fresco ? t(`Recién calculado · en ${num(estado.duracion, 1)} s`,
                                `Just calculated · in ${num(estado.duracion, 1)} s`)
                   : t(`Calculado hace ${hace(estado.edad_s)} · en ${num(estado.duracion, 1)} s`,
                       `Calculated ${hace(estado.edad_s)} ago · in ${num(estado.duracion, 1)} s`)}</span>
            <button className={"lab-estados" + (corriendo ? " corriendo" : fresco ? " listo" : "")}
                    disabled={corriendo} onClick={() => lanzar(true)}
                    title={t("Vuelve a correr los catorce modelos y a pedir precios frescos.",
                             "Runs all fourteen models again and fetches fresh prices.")}>
              <i className="punto" />
              <span>{corriendo ? t("recalculando", "recalculating") : t("recalcular", "recalculate")}</span>
            </button>
          </div>);
      })()}
      <Panel key={simKey} tab={tab} R={R} M={M} cartera={cartera} bench={bench}
             recargar={recargar} lanzar={lanzar} sim={sim} setSim={setSim} />
    </>
  );
}

function Panel({ tab, R, M, cartera, bench, recargar, lanzar, sim, setSim }) {
  const d = R[tab];
  if (M[tab]?.estado === "corriendo" || M[tab]?.estado === "en cola")
    return <div className="cargando">{t("Calculando", "Calculating")} {M[tab]?.nombre}…</div>;
  if (!d) return <div className="cargando">{t("Sin datos.", "No data.")}</div>;
  if (d.error) return <div className="aviso mal"><b>{t("No se pudo calcular.", "Could not calculate.")}</b> {d.error}</div>;

  const vistas = {
    posicion: <Posicion d={{ ...d, cartera_nombre: cartera }} cartera={cartera}
                        recargar={recargar} lanzar={lanzar} bench={bench} sim={sim} setSim={setSim}
                        extras={{ composicion: R.composicion, riesgo: R.riesgo,
                                  momentum: R.momentum, capm: R.capm,
                                  correlaciones: R.correlaciones,
                                  evolucion: R.evolucion, benchmarks: R.benchmarks }} />,
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
function AltaRapida({ cartera, recargar, lanzar }) {
  const vacio = { ticker: "", fecha: new Date().toISOString().slice(0, 10),
                  precio: "", qty: "", commissions: "0", source: "", currency: "" };
  const [tipo, setTipo] = useState("compra");
  const [f, setF] = useState(vacio);
  const [check, setCheck] = useState(null);
  const [msg, setMsg] = useState(null);
  const [abierto, setAbierto] = useState(false);

  const validar = async () => {
    const tk = f.ticker.trim().toUpperCase();
    if (!tk) return;
    setCheck({ cargando: true });
    setCheck(await api(`/api/validar/${encodeURIComponent(tk)}`));
  };
  const agregar = async () => {
    const t_ = f.ticker.trim().toUpperCase();
    if (!t_ || !f.precio || !f.qty) {
      setMsg({ mal: t("Faltan ticker, precio o cantidad.", "Ticker, price or quantity is missing.") });
      return;
    }
    let r;
    if (tipo === "compra") {
      const actuales = await api(`/api/carteras/${encodeURIComponent(cartera)}`);
      const nuevas = [...actuales, { ticker: t_, buy_date: f.fecha, buy_price: dec(f.precio),
                                     qty: dec(f.qty), commissions: dec(f.commissions) || 0,
                                     source: f.source, currency: f.currency }];
      r = await api(`/api/carteras/${encodeURIComponent(cartera)}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ posiciones: nuevas }) });
    } else {
      r = await api(`/api/carteras/${encodeURIComponent(cartera)}/vender`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticker: t_, sell_date: f.fecha, sell_price: dec(f.precio),
                               qty: dec(f.qty), commissions: dec(f.commissions) || 0,
                               moneda: f.currency }) });
    }
    if (r.error) { setMsg({ mal: r.error }); return; }
    setMsg(tipo === "compra" ? { ok: t(`${t_} agregado. Recalculando los KPIs…`,
                                       `${t_} added. Recalculating KPIs…`) }
                              : { ok: t(`Venta de ${t_} registrada. Recalculando los KPIs…`,
                                       `${t_} sale recorded. Recalculating KPIs…`) });
    setF(vacio); setCheck(null);
    recargar && recargar();
    lanzar && lanzar(true);
  };

  if (!abierto) return (
    <button className="btn" style={{ marginBottom: 14 }}
            onClick={() => setAbierto(true)}>+ {t("Agregar una posición", "Add a position")}</button>);

  return (
    <div className="panel" style={{ marginBottom: 14 }}>
      <h3>{tipo === "compra" ? t("Agregar una posición a", "Add a position to")
                              : t("Vender de", "Sell from")} {cartera}
        <button className="btn" style={{ marginLeft: "auto", padding: "3px 10px", fontSize: 12 }}
                onClick={() => setAbierto(false)}>{t("Cerrar", "Close")}</button>
      </h3>
      <div style={{ display: "flex", gap: 14, marginTop: 10 }}>
        <label style={{ fontSize: 12.5 }}>
          <input type="radio" checked={tipo === "compra"} onChange={() => setTipo("compra")} /> {t("Compra", "Buy")}
        </label>
        <label style={{ fontSize: 12.5 }}>
          <input type="radio" checked={tipo === "venta"} onChange={() => setTipo("venta")} /> {t("Venta", "Sell")}
        </label>
      </div>
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "flex-end", marginTop: 10 }}>
        {[["ticker", "Ticker", "text", 120, "GGAL.BA"],
          ["fecha", tipo === "compra" ? t("Fecha de compra", "Purchase date") : t("Fecha de venta", "Sale date"),
           "text", 120, "2025-09-19"],
          ["precio", tipo === "compra" ? t("Precio pagado", "Price paid") : t("Precio de venta", "Sale price"),
           "decimal", 110, ""],
          ["qty", t("Cantidad", "Quantity"), "decimal", 100, ""],
          ["commissions", t("Comisiones", "Commissions"), "decimal", 100, ""]].map(([k, et, inputTipo, w, ph]) => (
          <label key={k} style={{ fontSize: 11.5, color: "var(--texto-3)" }}>
            {et}<br />
            <input type={inputTipo === "decimal" ? "text" : inputTipo}
                   inputMode={inputTipo === "decimal" ? "decimal" : undefined}
                   value={f[k]} placeholder={ph} style={{ width: w, marginTop: 3 }}
                   onChange={(e) => setF({ ...f, [k]:
                     inputTipo === "decimal" ? soloNum(e.target.value) : e.target.value })}
                   onBlur={k === "ticker" ? validar : undefined} />
          </label>))}
        <label style={{ fontSize: 11.5, color: "var(--texto-3)" }}>
          {t("Moneda", "Currency")}<br />
          <select value={f.currency} style={{ marginTop: 3 }}
                  onChange={(e) => setF({ ...f, currency: e.target.value })}>
            <option value="">{t("automático (según el ticker)", "automatic (based on the ticker)")}</option>
            <option value="ARS">ARS</option>
            <option value="USD">USD</option>
            <option value="EUR">EUR</option>
          </select>
        </label>
        {tipo === "compra" && (
          <label style={{ fontSize: 11.5, color: "var(--texto-3)" }}>
            {t("Origen", "Source")}<br />
            <select value={f.source} style={{ marginTop: 3 }}
                    onChange={(e) => setF({ ...f, source: e.target.value })}>
              <option value="">{t("automático", "automatic")}</option>
              <option value="cocos">cocos ({t("bono / ON", "bond / note")})</option>
            </select>
          </label>)}
        <button className="btn primario" onClick={agregar}>{tipo === "compra" ? t("Agregar", "Add")
                                                                               : t("Vender", "Sell")}</button>
      </div>
      {check && !check.cargando && (
        <div className={"aviso " + (check.valido && !check.convertible ? "ojo"
                                    : check.valido && check.alcanza_para_analisis ? "ok"
                                    : check.valido ? "ojo" : "mal")}>
          {check.valido
            ? <>{t("Cotiza en", "Quoted in")} <b>{check.moneda}</b>{check.subyacente !== check.ticker &&
                <> ({t("subyacente", "underlying")} <b>{check.subyacente}</b>)</>},
               {" "}{t("último", "last")} <b>{usd(check.ultimo_usd, 4)}</b>,
               {" "}{t(`${check.ruedas} ruedas de historia.`, `${check.ruedas} sessions of history.`)} {check.detalle}
               {check.convertible === false &&
                 <> <b>{t("Ojo:", "Heads up:")}</b> {t("la app convierte pesos, dólares y euros. Este precio "
                    + "entra tal cual y la posición va a quedar mal valuada.",
                    "the app converts pesos, dollars and euros. This price "
                    + "goes in as-is and the position will be valued wrong.")}</>}</>
            : <>{check.detalle} {t("Si es un bono u ON, elegí origen", "If it's a bond or note, choose source")}{" "}
                <b>cocos</b>.</>}
        </div>)}
      {msg && <div className={"aviso " + (msg.mal ? "mal" : "ok")}>{msg.mal || msg.ok}</div>}
      <div className="pie">
        {IDIOMA === "en" ? (tipo === "compra"
          ? <>The price goes in the chosen currency (or the ticker's own currency if you leave
             it «automatic»). The ticker is validated when you leave the field, so you don't
             find out there's no history after you've already loaded everything.</>
          : <>It's deducted from the oldest lots of that ticker (FIFO), same as when
             importing operations from a broker. The result enters the realized P&amp;L,
             converted at the exchange rate of each leg.</>
        ) : (tipo === "compra"
          ? <>El precio va en la moneda elegida (o en la del ticker si dejás «automático»).
             Se valida el ticker al salir del campo, para no descubrir que no hay historia
             cuando ya cargaste todo.</>
          : <>Se descuenta de los lotes más viejos de ese ticker (FIFO), igual que al
             importar operaciones desde un broker. El resultado entra al P&amp;L realizado,
             convertido con el tipo de cambio de cada pata.</>)}
      </div>
    </div>
  );
}

const claveLote = (x) => `${x.ticker}|${x.buy_date}|${x.qty}`;

function Posicion({ d, cartera, recargar, lanzar, extras, bench, sim, setSim }) {
  const filas = d.posiciones || [];
  const [crudo, setCrudo] = useState(null);
  const r = extras?.riesgo;
  // Correlaciones y evolución vienen con el lote de modelos, no de un pedido
  // aparte: pedirlos por separado los ponía a competir con los once por el mismo
  // procesador, y en el servidor sumaban veinte segundos a cada apertura.
  const corr = extras?.correlaciones;
  const ev = extras?.evolucion;
  // Cuánto lleva cada lote sin volver a lo que costó. Sale de la evolución, que
  // es la que tiene las series; los lotes sin serie —un FCI— no están y van "—".
  const twu = Object.fromEntries(((ev && !ev.error && ev.bajo_agua) || [])
    .map((x) => [claveLote(x), x]));
  // Lo cerrado se venía guardando y neteando sin que se viera en ningún lado.
  const [n, setN] = useState(0);
  const [conFci, setConFci] = useState(leerPref);
  useEffect(() => { setCrudo(null);
    api(`/api/carteras/${encodeURIComponent(cartera)}/realizado`).then(setCrudo); }, [cartera, n]);
  // Un solo embudo: los KPIs, el calendario y el panel de cerradas cuelgan de
  // `real`, así que el toggle se aplica una vez acá y llega a los tres.
  const fciTrades = (crudo?.trades || []).filter((t) => t.tipo === "fci");
  const hayFci = fciTrades.length > 0;
  const real = crudo && !conFci ? quitarFci(crudo) : crudo;
  // Cauciones ya están adentro de "Resultado realizado" (son cerrados como
  // cualquier otro) — esto es solo para verlas aparte sin ir a buscarlas.
  const caucionTrades = (crudo?.trades || []).filter((t) => t.tipo === "caucion");
  const caucionTotal = caucionTrades.length
    ? caucionTrades.reduce((s, t) => s + t.pnl, 0) : null;
  // La posición de caución es de la cuenta de InvIU entera, no de esta cartera
  // en particular —por eso se pide aparte, no sale de `crudo`—, pero mostrarla
  // sin más se colaba en CUALQUIER cartera del usuario, aunque sea la de otro
  // inversor de la familia que comparte cuenta de Google pero no de broker.
  // `tiene_inviu` (posiciones abiertas) y el lote de los cerrados son la
  // huella de que esta cartera en particular es la que está atada a InvIU.
  const esDeInviu = d.tiene_inviu ||
    (crudo?.trades || []).some((t) => String(t.lote || "").startsWith("inviu-"));
  const [caucionAbierta, setCaucionAbierta] = useState(null);
  useEffect(() => {
    if (!esDeInviu) { setCaucionAbierta(null); return; }
    let vivo = true;
    api("/api/inviu/estado").then((e) => {
      if (!vivo || !e.conectado) return;
      api("/api/inviu/caucion").then((c) => vivo && setCaucionAbierta(c));
    });
    return () => { vivo = false; };
  }, [esDeInviu]);
  const cerrado = real?.n ? real.total_usd : null;
  // Con el mercado cerrado la última rueda no es la de hoy: la columna lo dice.
  const hoy = diaEtiqueta(d.dia_fecha) === t("hoy", "today") ? t("Hoy", "Today") : t("Día", "Day");
  const dia = d.dia_fecha
    ? t(`Resultado de la rueda del ${d.dia_fecha} contra el cierre anterior`,
        `Result of the ${d.dia_fecha} session vs. the previous close`) : undefined;

  return (
    <>
      {/* 1 · Cómo se comporta la cartera, antes que el detalle de qué tiene */}
      {r && !r.error && <KpisRiesgo d={r} />}

      {/* 2 · Qué tengo */}
      <div className="kpis">
        {!(ev && !ev.error) && (
          <Kpi etiqueta={t("Valor total", "Total value")} valor={usd(d.valor_total)} ayuda={AYUDA.valor}
               sub={MERCADOS[MERCADO].locales && d.mep_hoy ? `MEP $${d.mep_hoy}` : null} />)}
        <Kpi etiqueta={t("Costo", "Cost")} valor={usd(d.costo_total)}
             sub={t("comisiones incluidas", "commissions included")} />
        <Kpi etiqueta={t("Resultado abierto", "Open result")} valor={usd(d.pnl)} tono={signo(d.pnl)} ayuda={AYUDA.pnl}
             sub={<>{pct(d.pnl_pct)}{d.pnl_dia != null && <>{" · "}
               <span className={d.pnl_dia >= 0 ? "up" : "down"}
                     title={t(`${pct(d.pnl_dia_pct)} en la rueda del ${d.dia_fecha}, contra el cierre anterior`,
                              `${pct(d.pnl_dia_pct)} on the session of ${d.dia_fecha}, vs. the previous close`)}>
                 {diaEtiqueta(d.dia_fecha)} {usd(d.pnl_dia)}</span></>}</>} />
        {cerrado != null && (
          <Kpi etiqueta={t("Resultado realizado", "Realized result")} valor={usd(cerrado)} tono={signo(cerrado)}
               sub={t(`${real.n} operaciones cerradas`, `${real.n} closed trades`)} ayuda={AYUDA.realizado} />)}
        {cerrado != null && (
          <Kpi etiqueta={t("Resultado total", "Total result")} valor={usd(d.pnl + cerrado)}
               tono={signo(d.pnl + cerrado)} sub={t("abierto + cerrado", "open + realized")} />)}
        {caucionTotal != null && (
          <Kpi etiqueta="Resultado cauciones" valor={usd(caucionTotal)} tono={signo(caucionTotal)}
               sub="carry trade tomadora + colocadora, ya incluido en el realizado" />)}
        <Kpi etiqueta={t("Posiciones", "Positions")} valor={filas.length}
             sub={t(`${new Set(filas.map(f=>f.ticker)).size} activos`,
                    `${new Set(filas.map(f=>f.ticker)).size} assets`)} />
      </div>

      {/* Mismo recuadro que en la pestaña InvIU: solo el lado que sigue
          vigente hoy — una deuda (tomadora) o una inversión (colocadora) que
          no hay que perder de vista aunque se esté mirando otra cartera. */}
      {caucionAbierta && !caucionAbierta.error &&
       (caucionAbierta.tomadora || caucionAbierta.colocadora) && (
        <div className="kpis">
          {caucionAbierta.tomadora && (
            <Kpi etiqueta="Caución tomadora (deuda de corto plazo)"
                 valor={caucionAbierta.tomadora.moneda === "ARS"
                   ? ars(caucionAbierta.tomadora.monto, 0) : usd(caucionAbierta.tomadora.monto, 0)}
                 tono="neg recuadro"
                 sub={`desde ${caucionAbierta.tomadora.desde} · vence ${caucionAbierta.tomadora.vence}` +
                   (caucionAbierta.tomadora.tasa_tna != null
                     ? ` · ${num(caucionAbierta.tomadora.tasa_tna, 1)}% (TNA)` : "")} />
          )}
          {caucionAbierta.colocadora && (
            <Kpi etiqueta="Caución colocadora (plata prestada por vos)"
                 valor={caucionAbierta.colocadora.moneda === "ARS"
                   ? ars(caucionAbierta.colocadora.monto, 0) : usd(caucionAbierta.colocadora.monto, 0)}
                 tono="pos recuadro"
                 sub={`desde ${caucionAbierta.colocadora.desde} · vence ${caucionAbierta.colocadora.vence}` +
                   (caucionAbierta.colocadora.tasa_tna != null
                     ? ` · ${num(caucionAbierta.colocadora.tasa_tna, 1)}% (TNA)` : "")} />
          )}
        </div>
      )}
      {ev && !ev.error && (<>
        <div className="fila f2">
          <ValorCartera ev={ev} mep={d.mep_hoy} />
          <RendimientoTotal ev={ev} />
        </div>
        <TirVentana ev={ev} />
      </>)}
      {d.sin_precio?.length > 0 && (
        <div className="aviso ojo">
          <b>{t(`${d.sin_precio.length} posiciones sin precio`, `${d.sin_precio.length} positions without a price`)}</b>
          {t(" y quedaron fuera del total: ", " and were left out of the total: ")}
          {d.sin_precio.join(", ")}. {t("Los bonos y ONs necesitan Cocos conectado.",
                                        "Bonds and corporate notes need Cocos connected.")}
        </div>
      )}
      {real?.n > 0 && <CalendarioRealizado real={real} />}

      <Plegable id={`tenencias-${cartera}`} titulo={t("Tenencias", "Holdings")} extra={
        <a className="btn" style={{ textDecoration: "none", fontSize: 12.5 }}
           href={`/api/reporte/${encodeURIComponent(d.cartera_nombre || "")}`}>{t("Descargar PDF", "Download PDF")}</a>
      }>
        <div className="tabla-wrap"><table className="tenencias">
          <thead><tr>
            <th>Ticker</th><th>{t("Compra", "Purchase")}</th>
            <th className="n" title={t("Cantidad", "Quantity")}>{t("Cant.", "Qty.")}</th>
            <th className="n">{t("Precio compra", "Buy price")}</th>
            <th className="n">{t("Precio hoy", "Price today")}</th>
            <th className="n">{t("Valor", "Value")}</th>
            <th className="n" title={dia}>{hoy}</th><th className="n" title={dia}>{hoy} %</th>
            <th className="n">{t("Resultado", "Result")}</th><th className="n">%</th>
            <th className="n" title={t("Time under water: días corridos que lleva el lote sin volver a lo que costó.",
                                       "Time under water: running days the lot has gone without recovering its cost.")}>TWU</th>
          </tr></thead>
          <tbody>{filas.map((f, i) => (
            <tr key={i}>
              <td className="mono textochip">{f.ticker}
                {f.es_bono && <span className="chip" style={{marginLeft:6}}>{t("bono", "bond")}</span>}
                {f.sim && <span className="chip ojo" style={{marginLeft:6}}
                                title={t("Simulada: no está en tu cartera", "Simulated: not in your portfolio")}>
                                {t("sim", "sim")}</span>}</td>
              <td className="mono">{f.buy_date}</td>
              <td className="n">{num(f.qty, 0)}</td>
              <td className="n">{usd(f.buy_price_usd, 4)}</td>
              <td className="n">{f.precio_usd == null ? "—" : (
                <>{usd(f.precio_usd, 4)}{f.precio_estimado && (
                  // Cocos no publica la cuotaparte de un fondo que no tenés hoy
                  // en la cuenta conectada. Se muestra el PPC para que la
                  // tenencia no valga cero, con el asterisco que lo aclara.
                  <span title="Cocos no publica la cuotaparte de este fondo. Es el último valor conocido (tu precio promedio de compra), no un precio de mercado."
                        style={{ color: "var(--alerta)", cursor: "help" }}> *</span>)}</>
              )}</td>
              <td className="n">{usd(f.valor_usd)}</td>
              <td className={"n " + signo(f.pnl_dia_usd)}>{usd(f.pnl_dia_usd)}</td>
              <td className={"n " + signo(f.pnl_dia_pct)}>{pct(f.pnl_dia_pct, 1)}</td>
              <td className={"n " + signo(f.pnl_usd)}>{usd(f.pnl_usd)}</td>
              <td className={"n " + signo(f.pnl_pct)}>{pct(f.pnl_pct, 1)}</td>
              <td className="n">{(() => {
                const tw = twu[claveLote(f)];
                if (!tw) return "—";
                if (!tw.dias && !tw.desde) return <span style={{ color: "var(--texto-3)" }}>—</span>;
                // Un lote que cayó hoy lleva cero días corridos, y eso no es
                // "nunca estuvo abajo": se dice "hoy".
                return <span className="neg" title={t(`En pérdida desde el ${tw.desde}`,
                                                       `Underwater since ${tw.desde}`)}>
                  {tw.dias ? `${tw.dias} d` : t("hoy", "today")}</span>;
              })()}</td>
            </tr>))}
          </tbody>
        </table></div>
        <div className="pie">
          {IDIOMA === "en" ? (<>
            Each lot is valued at today's price, and its cost at the exchange rate of the
            day you bought it. Converting an old purchase to today's rate would measure the
            exchange rate, not the asset's return. <b>{hoy}</b> is what the lot gained
            or lost in the last session against the previous close —if you bought it in that
            same session, against what it cost you—; ones without a previous close, like a
            FCI, show «—». <b>TWU</b> —time under water— is
            the running days the lot has gone without recovering its cost: a −8 % from this
            week and one from two years ago aren't the same position, and the percentage
            alone doesn't tell them apart. Measured against your cost, commissions included.
          </>) : (<>
            Cada lote se valuó con el precio de hoy, y su costo con el tipo de cambio del
            día en que lo compraste. Convertir una compra vieja al cambio de hoy mediría el
            tipo de cambio, no el rendimiento del activo. <b>{hoy}</b> es lo que el lote ganó
            o perdió en la última rueda contra el cierre anterior —si lo compraste en esa
            misma rueda, contra lo que te costó—; los que no tienen cierre previo, como un
            FCI, van «—». <b>TWU</b> —time under water— son
            los días corridos que el lote lleva sin volver a lo que te costó: un −8 % de esta
            semana y uno que viene de hace dos años no son la misma posición, y el porcentaje
            solo no los distingue. Se mide contra tu costo, comisiones incluidas.
          </>)}
        </div>
      </Plegable>

      {/* Cargar y simular van juntos y acá: debajo de lo que tenés —que es
          contra lo que se agrega o se simula— y antes de lo que ya cerraste. */}
      <AltaRapida cartera={cartera} recargar={recargar} lanzar={lanzar} />
      <Simulador cartera={cartera} sim={sim} setSim={setSim}
                 tenencias={filas.reduce(
                   (a, f) => ({ ...a, [f.ticker]: (a[f.ticker] || 0) + f.qty }), {})} />

      {real && <PnlRealizado real={real} cartera={cartera} recargar={() => setN((x) => x + 1)}
                             fciTrades={fciTrades} hayFci={hayFci} conFci={conFci}
                             setConFci={(v) => { setConFci(v); guardarPref(v); }} />}

      {ev && <RuedasTicker ev={ev} />}

      {/* 3 · En qué está invertida */}
      <Seccion titulo={t("En qué está invertida", "What it's invested in")} />
      {extras?.composicion
        ? (extras.composicion.error
            ? <div className="aviso mal">{extras.composicion.error}</div>
            : <Composicion d={extras.composicion} cartera={cartera} />)
        : <div className="cargando">{t("Clasificando los activos…", "Classifying the assets…")}</div>}

      {/* 4 · Se mueven juntos o no */}
      <Seccion titulo={t("¿Se mueven juntos?", "Do they move together?")} />
      {corr ? (corr.error ? <div className="aviso mal">{corr.error}</div>
                          : <MatrizCorrelaciones corr={corr} />)
            : <div className="cargando">{t("Calculando correlaciones…", "Calculating correlations…")}</div>}

      {/* 5 · Cómo son los días */}
      <Seccion titulo={t("Cómo son los días de esta cartera", "What this portfolio's days look like")} />
      {r && !r.error ? <Distribucion d={r} /> : <div className="cargando">{t("Calculando…", "Calculating…")}</div>}

      {/* 6 · Contra qué se compara */}
      <Seccion titulo={t("¿Y contra el mercado?", "And against the market?")} />
      {extras?.capm
        ? (extras.capm.error
            ? <div className="aviso mal">{extras.capm.error}</div>
            : <Capm d={extras.capm} cartera={cartera} bench={bench}
                    todos={extras.benchmarks} />)
        : <div className="cargando">{t("Comparando contra el índice…", "Comparing against the index…")}</div>}

      {/* 7 · Es momento de entrar o esperar */}
      <Seccion titulo={t("¿Viento a favor o en contra?", "Tailwind or headwind?")} />
      {extras?.momentum
        ? (extras.momentum.error
            ? <div className="aviso mal">{extras.momentum.error}</div>
            : <Momentum d={extras.momentum} />)
        : <div className="cargando">{t("Midiendo el momentum…", "Measuring momentum…")}</div>}
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
    .toLocaleDateString(IDIOMA === "en" ? "en" : "es-AR", { month: "long", year: "numeric" });
  const mesCorto = (fecha) => new Date(fecha + "T12:00:00")
    .toLocaleDateString(IDIOMA === "en" ? "en" : "es-AR", { month: "short", year: "2-digit" }).replace(".", "");

  return (
    <div className="panel">
      <h3>{t("Mes a mes", "Month by month")}</h3>
      <Grafico alto={260}
        datos={[
          { type: "bar", name: t("ventas", "sales"), x, y: filas.map((f) => f.ventas),
            marker: { color: filas.map((f) => (f.ventas >= 0 ? c.positivo : c.negativo)),
                      line: { width: 0 } },
            width: 18 * 86400000, text: filas.map((f) => nombreMes(f.mes)),
            textposition: "none",
            hovertemplate: t("%{text}<br>ventas: %{y:$,.2f}<extra></extra>",
                             "%{text}<br>sales: %{y:$,.2f}<extra></extra>") },
          { type: "bar", name: t("dividendos", "dividends"), x, y: filas.map((f) => f.dividendos),
            marker: { color: c.alerta, line: { width: 0 } },
            width: 18 * 86400000, text: filas.map((f) => nombreMes(f.mes)),
            textposition: "none",
            hovertemplate: t("%{text}<br>dividendos: %{y:$,.2f}<extra></extra>",
                             "%{text}<br>dividends: %{y:$,.2f}<extra></extra>") },
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
        {t(`Cada barra es un mes: lo que dejaron las ventas y, apilado encima, los dividendos `
          + `cobrados${conDividendos ? ` (${conDividendos} de ${filas.length} meses tuvieron)` : ""}.`,
          `Each bar is a month: what the sales left behind and, stacked on top, dividends `
          + `collected${conDividendos ? ` (${conDividendos} of ${filas.length} months had some)` : ""}.`)}{" "}
        {t("El mejor fue", "The best was")} <b>{nombreMes(mejor.mes)}</b> {t("con", "with")}{" "}
        {usd(mejor.ventas + mejor.dividendos)} {t("y el peor", "and the worst")}{" "}
        <b>{nombreMes(peor.mes)}</b> {t("con", "with")} {usd(peor.ventas + peor.dividendos)};{" "}
        {t(`los ${filas.length} meses suman`, `the ${filas.length} months add up to`)} {usd(total)}.
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
    setMsg({ ok: t(`${r.agregados} ${r.agregados === 1 ? "dividendo registrado" : "dividendos registrados"}`
                 + `, ${num(r.importe_total, 2)} en total.`
                 + (r.agregados < completas.length
                   ? ` ${completas.length - r.agregados} ya estaban cargados.` : ""),
                 `${r.agregados} ${r.agregados === 1 ? "dividend" : "dividends"} recorded`
                 + `, ${num(r.importe_total, 2)} in total.`
                 + (r.agregados < completas.length
                   ? ` ${completas.length - r.agregados} were already loaded.` : "")) });
    setFilas([linea(filas[filas.length - 1])]);
    recargar && recargar();
  };

  if (!abierto) return (
    <button className="btn" style={{ marginTop: 10 }} onClick={() => setAbierto(true)}>
      + {t("Registrar dividendos", "Record dividends")}</button>);

  return (
    <div className="panel" style={{ background: "var(--panel-2)", marginTop: 10 }}>
      <h3>{t("Dividendos cobrados", "Dividends collected")}
        <button className="btn" style={{ marginLeft: "auto", padding: "3px 10px", fontSize: 12 }}
                onClick={() => setAbierto(false)}>{t("Cerrar", "Close")}</button>
      </h3>
      <div className="tabla-wrap"><table>
        <thead><tr><th>Ticker</th><th>{t("Fecha de cobro", "Collection date")}</th>
          <th className="n">{t("Importe", "Amount")}</th>
          <th>{t("Moneda", "Currency")}</th><th>{t("El importe es", "The amount is")}</th>
          <th className="n">{t("Acciones", "Shares")}</th>
          <th className="n">{t("Resultado", "Result")}</th><th></th></tr></thead>
        <tbody>
          {filas.map((f, i) => {
            const qty = dec(f.qty) || 1;
            const imp = dec(f.importe) || 0;
            const total = f.por_accion ? qty * imp : imp;
            return (
              <tr key={i}>
                <td><input type="text" value={f.ticker}
                           style={{ width: 110,
                                    borderColor: f.existe === false ? "var(--negativo)" : "" }}
                           title={f.existe === false ? t("No se encontraron precios para ese ticker",
                                                          "No prices found for that ticker") : ""}
                           placeholder="METR.BA"
                           onBlur={(e) => sugerirMoneda(i, e.target.value.trim().toUpperCase())}
                           onChange={(e) => set(i, "ticker", e.target.value.toUpperCase())} /></td>
                <td><input type="date" value={f.fecha} style={{ width: 140 }}
                           onChange={(e) => set(i, "fecha", e.target.value)} /></td>
                <td><input type="text" inputMode="decimal" value={f.importe} style={{ width: 110 }}
                           onChange={(e) => set(i, "importe", soloNum(e.target.value))} /></td>
                <td>
                  <select value={f.moneda || ""} style={{ width: 90 }}
                          onChange={(e) => set(i, "moneda", e.target.value)}>
                    <option value="">{t("auto", "auto")}</option>
                    <option value="ARS">ARS</option>
                    <option value="USD">USD</option>
                  </select>
                </td>
                <td>
                  <select value={f.por_accion ? "unit" : "total"} style={{ width: 130 }}
                          onChange={(e) => set(i, "por_accion", e.target.value === "unit")}>
                    <option value="unit">{t("por acción", "per share")}</option>
                    <option value="total">{t("el total cobrado", "the total collected")}</option>
                  </select>
                </td>
                <td><input type="text" inputMode="decimal" value={f.qty} style={{ width: 100 }}
                           disabled={!f.por_accion} placeholder={f.por_accion ? "" : "—"}
                           onChange={(e) => set(i, "qty", soloNum(e.target.value))} /></td>
                <td className="n mono">{total ? `${num(total, 2)} ${f.moneda || ""}` : "—"}</td>
                <td><button className="btn" style={{ padding: "2px 9px", fontSize: 12 }}
                            onClick={() => quitar(i)}>✕</button></td>
              </tr>);
          })}
        </tbody>
      </table></div>
      <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 10 }}>
        <button className="btn" onClick={sumar}>+ {t("Otra línea", "Another line")}</button>
        <button className="btn primario" onClick={guardar} disabled={completas.length === 0}>
          {t("Registrar", "Record")} {completas.length || ""} {t(completas.length === 1 ? "dividendo" : "dividendos",
                                                                  completas.length === 1 ? "dividend" : "dividends")}
        </button>
        {completas.length > 0 && (
          <span className="mono" style={{ marginLeft: "auto", fontSize: 13.5 }}>
            {num(completas.reduce((s, f) => s + (f.por_accion
              ? (dec(f.qty) || 1) * (dec(f.importe) || 0)
              : dec(f.importe) || 0), 0), 2)} {t("en total", "in total")}
          </span>)}
      </div>
      {msg && <div className={"aviso " + (msg.mal ? "mal" : "ok")}>{msg.mal || msg.ok}</div>}
      {filas.some((f) => f.existe === false) && (
        <div className="aviso ojo">
          <b>{filas.filter((f) => f.existe === false).map((f) => f.ticker).join(", ")}</b>:{" "}
          {t("no se encontraron precios para ese ticker. Se puede cargar igual, pero revisá que esté bien "
            + "escrito — un dividendo bajo un ticker que no existe queda suelto, sin sumarse al papel.",
            "no prices were found for that ticker. It can still be loaded, but check that it's spelled "
            + "right — a dividend under a ticker that doesn't exist stays loose, without adding to the stock.")}
        </div>)}
      <div className="pie">
        {IDIOMA === "en" ? (<>
          A dividend <b>doesn't touch the position</b>: it doesn't add shares or change any cost.
          It enters as a result on the day it was collected and, if in pesos, converts to dollars
          at that date's MEP rate. Load all the collections together —for one stock or several— and
          they're processed at once; each new line inherits the ticker, shares and currency from
          the previous one. <b>Check the currency</b>: it proposes the stock's own, but a CEDEAR D
          quotes in dollars and its dividend is usually credited in pesos. If it says USD and you
          loaded pesos, the amount ends up multiplied by the MEP rate.
        </>) : (<>
          Un dividendo <b>no toca la posición</b>: no suma papeles ni cambia el costo de nada.
          Entra como resultado del día que se cobró y, si es en pesos, se convierte a dólares con
          el MEP de esa fecha. Cargá todos los cobros juntos —de un papel o de varios— y se
          procesan de una sola vez; cada línea nueva hereda el ticker, las acciones y la moneda
          de la anterior. <b>Mirá la moneda</b>: se propone la del papel, pero un CEDEAR D cotiza
          en dólares y su dividendo suele acreditarse en pesos. Si dice USD y cargaste pesos, el
          importe queda multiplicado por el MEP.
        </>)}
      </div>
    </div>
  );
}

function PnlRealizado({ real, cartera, recargar, fciTrades, hayFci, conFci, setConFci }) {
  // Borrar de a una, con la confirmación en el mismo botón: lo importado se
  // puede volver a traer, pero lo cargado a mano no, así que un clic no alcanza.
  const [porBorrar, setPorBorrar] = useState(null);
  // Filtro por papel para el detalle. Con 45 operaciones, buscar las de un
  // ticker a ojo es el trabajo que la tabla debería estar haciendo.
  const [soloTicker, setSoloTicker] = useState("");
  // `tr` (trade) y no `t`: `t()` es el traductor global, y esta función entera
  // recorre trades. Nombrarlo `t` acá los haría chocar apenas se necesitara
  // traducir algo dentro de un .map/.filter/.reduce de trades.
  const claveTrade = (tr) => JSON.stringify({ ticker: tr.ticker, buy_date: tr.buy_date,
                                             sell_date: tr.sell_date, qty: tr.qty });
  const borrar = (tr) => {
    if (porBorrar !== claveTrade(tr)) { setPorBorrar(claveTrade(tr)); return; }
    setPorBorrar(null);
    api(`/api/carteras/${encodeURIComponent(cartera)}/realizado`, {
      method: "DELETE", headers: { "Content-Type": "application/json" },
      body: claveTrade(tr),
    }).then(() => recargar());
  };
  const [abierto, setAbierto] = useState(false);
  const [detalle, setDetalle] = useState(false);
  // Dividendo en edición: su clave y el importe neto que se está escribiendo.
  const [editando, setEditando] = useState(null);
  const [yahoo, setYahoo] = useState(null);
  const guardarImporte = async (tr) => {
    const r = await api(`/api/carteras/${encodeURIComponent(cartera)}/realizado`, {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filtro: JSON.parse(claveTrade(tr)), importe: dec(editando.valor) }) });
    if (r.error) { alert(r.error); return; }
    setEditando(null); recargar();
  };
  const traerYahoo = async () => {
    setYahoo({ yendo: true });
    const r = await api(`/api/carteras/${encodeURIComponent(cartera)}/dividendos/yahoo`,
                        { method: "POST" });
    setYahoo(r);
    if (r.agregados) recargar();
  };
  const trades = real.trades || [];
  // Un FCI viaja con la marca de su lote: es un resultado ya cerrado como
  // cualquier otro —suma al neto de arriba— pero se mira aparte, porque no es
  // una operación sino el saldo de cientos de suscripciones y rescates.
  const esFci = (tr) => tr.tipo === "fci";
  const fci = fciTrades || [];
  const fciUsd = fci.reduce((s, tr) => s + tr.pnl_usd, 0);
  // Las cauciones ya están en `trades` como dos cerrados más —el neto de cada
  // lado, no uno por rollover— así que no hacen falta pasarlas aparte como a
  // los FCI: se filtran acá mismo por su `tipo`.
  const esCaucion = (tr) => tr.tipo === "caucion";
  const caucion = trades.filter(esCaucion);
  const caucionUsd = caucion.reduce((s, tr) => s + tr.pnl_usd, 0);
  const porTicker = Object.values(trades.reduce((acc, tr) => {
    const x = acc[tr.ticker] || (acc[tr.ticker] = { ticker: tr.ticker, n: 0, usd: 0,
                                                  origen: 0, activo: 0, fx: 0,
                                                  moneda: tr.moneda, fci: esFci(tr),
                                                  caucion: esCaucion(tr) });
    x.n += 1; x.usd += tr.pnl_usd; x.origen += tr.pnl_origen || 0;
    x.activo += tr.pnl_activo_usd || 0; x.fx += tr.pnl_fx_usd || 0;
    return acc;
  }, {})).sort((a, b) => b.usd - a.usd);
  const ganadores = porTicker.filter((x) => x.usd > 0).length;
  const detalladas = soloTicker ? trades.filter((tr) => tr.ticker === soloTicker) : trades;
  const sumaDetalle = detalladas.reduce((s, tr) => s + (tr.pnl_usd || 0), 0);
  const enPesos = (real.total_origen || {}).ARS;
  const enDolar = (real.total_origen || {}).USD;

  return (
    <div className="panel">
      <h3 style={{ cursor: "pointer" }} onClick={() => setAbierto(!abierto)}>
        <span style={{ display: "flex", alignItems: "center", gap: 9 }}>
          <span style={{ fontSize: 11, color: "var(--texto-3)" }}>{abierto ? "▾" : "▸"}</span>
          {t("Posiciones cerradas", "Closed positions")}
        </span>
        <span style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 14 }}>
          {hayFci && (
            <label className="lab-interruptor" onClick={(e) => e.stopPropagation()}
                   title={t("Los FCI no son operaciones: son el saldo de cientos de suscripciones y rescates. "
                           + "Mirá el número con y sin.",
                           "FCI funds aren't trades: they're the balance of hundreds of subscriptions and "
                           + "redemptions. Check the number with and without.")}>
              <input type="checkbox" checked={conFci}
                     onChange={(e) => setConFci(e.target.checked)} />
              <span className="via"><span className="bola" /></span>
              <span>{t("con FCI", "with FCI")}</span>
            </label>)}
          <span style={{ fontSize: 12.5, color: "var(--texto-3)" }}>
            {real.n} {t("operaciones", "trades")}</span>
          <span className={"mono " + signo(real.total_usd)} style={{ fontSize: 16, fontWeight: 700 }}>
            {usd(real.total_usd)}</span>
        </span>
      </h3>

      {!abierto ? (
        <>
          <div className="pie" style={{ marginTop: 4 }}>
            <b className={signo(real.total_activo_usd)}>{usd(real.total_activo_usd)}</b>{" "}
            {t("de resultado de inversión", "of investment result")}{" "}
            {t(real.total_fx_usd < 0 ? "menos" : "más", real.total_fx_usd < 0 ? "minus" : "plus")}{" "}
            <b className={signo(real.total_fx_usd)}>{usd(Math.abs(real.total_fx_usd))}</b>{" "}
            {t("de resultado por tipo de cambio.", "of exchange-rate result.")}
            {enPesos != null && <> {t("En moneda de origen:", "In original currency:")} <b>{num(enPesos, 2)} ARS</b>
              {enDolar ? <> {t("y", "and")} <b>{num(enDolar, 2)} USD</b></> : null} —{" "}
              {t("ese es el número que se puede cotejar contra el resumen del broker, que no sabe de MEP.",
                 "that's the number you can check against the broker's statement, which knows nothing about the MEP rate.")}</>}
          </div>
        </>
      ) : (
        <>
          <div style={{ display: "flex", gap: 8, margin: "10px 0 4px" }}>
            <div className="modos">
              {[[false, t("Por activo", "By asset")], [true, t(`Las ${real.n} operaciones`, `All ${real.n} trades`)],
                ...(fci.length ? [["fci", `FCI (${fci.length})`]] : []),
                ...(caucion.length ? [["caucion", t(`Cauciones (${caucion.length})`, `Repos (${caucion.length})`)]] : [])
              ].map(([k, txt]) => (
                <button key={String(k)} className={"modo" + (detalle === k ? " on" : "")}
                        onClick={() => setDetalle(k)}>{txt}</button>))}
            </div>
            {detalle === true && (
              <span style={{ display: "flex", alignItems: "center", gap: 7,
                             fontSize: 12, color: "var(--texto-3)" }}>
                <select value={soloTicker} onChange={(e) => setSoloTicker(e.target.value)}>
                  <option value="">{t("todos los papeles", "all stocks")}</option>
                  {porTicker.map((x) => <option key={x.ticker} value={x.ticker}>{x.ticker}</option>)}
                </select>
                {soloTicker && <>{detalladas.length}{" "}
                  {t(detalladas.length === 1 ? "operación" : "operaciones", detalladas.length === 1 ? "trade" : "trades")} ·{" "}
                  <b className={signo(sumaDetalle)}>{usd(sumaDetalle)}</b>
                  {" "}<button className="chip" onClick={() => setSoloTicker("")}>{t("ver todas", "view all")}</button></>}
              </span>)}
          </div>
          <div className="tabla-wrap"><table>
            {detalle === "fci" ? (
              <>
                <thead><tr><th>{t("Fondo", "Fund")}</th><th>{t("Desde", "From")}</th><th>{t("Hasta", "To")}</th>
                  <th className="n">{t("Suscripto", "Subscribed")}</th><th className="n">{t("Rescatado", "Redeemed")}</th>
                  <th className="n">{t("Rescates", "Redemptions")}</th>
                  <th className="n">{t("Resultado en dólares", "Result in dollars")}</th></tr></thead>
                <tbody>{[...fci].sort((a, b) => b.pnl_usd - a.pnl_usd).map((tr, i) => (
                  <tr key={i}>
                    <td className="mono"><b>{tr.ticker}</b></td>
                    <td className="mono">{tr.buy_date}</td>
                    <td className="mono">{tr.sell_date}</td>
                    <td className="n">{usd(tr.buy_price)}</td>
                    <td className="n">{usd(tr.sell_price)}</td>
                    <td className="n">{tr.n_ops || "—"}</td>
                    <td className={"n " + signo(tr.pnl_usd)}>{usd(tr.pnl_usd)}</td>
                  </tr>))}
                  <tr style={{ fontWeight: 700 }}>
                    <td>{t("SUBTOTAL FCI", "FCI SUBTOTAL")}</td><td colSpan={4} />
                    <td className="n">{fci.reduce((s, tr) => s + (tr.n_ops || 0), 0)}</td>
                    <td className={"n " + signo(fciUsd)}>{usd(fciUsd)}</td>
                  </tr>
                </tbody>
              </>
            ) : detalle === "caucion" ? (
              <>
                <thead><tr><th>{t("Lado", "Side")}</th><th>{t("Desde", "From")}</th><th>{t("Hasta", "To")}</th>
                  <th className="n">{t("Resultado en dólares", "Result in dollars")}</th></tr></thead>
                <tbody>{[...caucion].sort((a, b) => b.pnl_usd - a.pnl_usd).map((tr, i) => (
                  <tr key={i}>
                    <td className="mono"><b>{tr.ticker === "CAUCIONT" ? "Tomadora" : "Colocadora"}</b></td>
                    <td className="mono">{tr.buy_date}</td>
                    <td className="mono">{tr.sell_date}</td>
                    <td className={"n " + signo(tr.pnl_usd)}>{usd(tr.pnl_usd)}</td>
                  </tr>))}
                  <tr style={{ fontWeight: 700 }}>
                    <td>{t("SUBTOTAL CAUCIONES", "REPOS SUBTOTAL")}</td><td colSpan={2} />
                    <td className={"n " + signo(caucionUsd)}>{usd(caucionUsd)}</td>
                  </tr>
                </tbody>
              </>
            ) : detalle ? (
              <>
                <thead><tr><th>Ticker</th><th>{t("Compra", "Buy")}</th><th>{t("Venta", "Sell")}</th>
                  <th className="n">{t("Cantidad", "Quantity")}</th>
                  <th className="n">{t("Precio compra", "Buy price")}</th><th className="n">{t("Precio venta", "Sell price")}</th>
                  <th className="n">{t("Dólar compra → venta", "Rate buy → sell")}</th>
                  <th className="n">{t("Resultado origen", "Result, original currency")}</th>
                  <th className="n">{t("Resultado inversión", "Investment result")}</th>
                  <th className="n">{t("Resultado tipo cambio", "Exchange-rate result")}</th>
                  <th className="n">{t("Resultado USD", "Result USD")}</th></tr></thead>
                <tbody>{[...detalladas].sort((a, b) => (a.sell_date < b.sell_date ? 1 : -1)).map((tr, i) => (
                  <tr key={i}>
                    <td className="mono">{tr.ticker}{tr.tipo === "dividendo" && (LAB && tr.estimado
                      ? <span className="chip ojo" style={{ marginLeft: 6, minWidth: 0, whiteSpace: "nowrap" }}
                              title={t(`${tr.notes}. Corregí el importe con lo que cobraste.`,
                                       `${tr.notes}. Correct the amount with what you actually collected.`)}>
                                {t("div est.", "div est.")}</span>
                      : <span className="chip ok" style={{ marginLeft: 6, minWidth: 0 }}>{t("div", "div")}</span>)}
                      <button className={"eliminar" + (porBorrar === claveTrade(tr) ? " arm" : "")}
                              onMouseLeave={() => porBorrar === claveTrade(tr) && setPorBorrar(null)}
                              onClick={() => borrar(tr)}
                              title={porBorrar === claveTrade(tr)
                                     ? t("Clic de nuevo para borrarla", "Click again to delete it")
                                     : t(`Borrar esta operación de ${cartera}`, `Delete this trade from ${cartera}`)}>✕</button></td>
                    <td className="mono">{tr.buy_date}</td>
                    <td className="mono">{tr.sell_date}</td>
                    <td className="n">{num(tr.qty, 2)}</td>
                    <td className="n">{num(tr.buy_price, 2)}</td>
                    <td className="n">{num(tr.sell_price, 2)}</td>
                    {/* Los dos MEP arriba y la variación debajo: en una sola línea esta
                        celda medía 223 px —el doble que cualquier otra— y era la que
                        empujaba la tabla hasta necesitar scroll horizontal. */}
                    <td className={"n " + signo(tr.pnl_fx_usd)}>
                      {tr.mep_compra && tr.mep_venta ? <>
                        {num(tr.mep_compra, 2)} → {num(tr.mep_venta, 2)}
                        <div style={{ fontSize: 10.5, color: "var(--texto-3)" }}>
                          {tr.mep_venta >= tr.mep_compra ? "+" : ""}
                          {num((tr.mep_venta / tr.mep_compra - 1) * 100, 1)} %
                        </div></> : "—"}</td>
                    <td className={"n " + signo(tr.pnl_origen)}>
                      {LAB && tr.tipo === "dividendo" && editando?.clave === claveTrade(tr) ? (
                        <input type="text" inputMode="decimal" autoFocus value={editando.valor}
                               style={{ width: 90, textAlign: "right" }} aria-label={t("Importe neto cobrado", "Net amount collected")}
                               onChange={(e) => setEditando({ ...editando, valor: soloNum(e.target.value) })}
                               onKeyDown={(e) => { if (e.key === "Enter") guardarImporte(tr);
                                                   if (e.key === "Escape") setEditando(null); }}
                               onBlur={() => setEditando(null)} />
                      ) : <>{num(tr.pnl_origen, 2)} {tr.moneda}</>}
                      {LAB && tr.tipo === "dividendo" && editando?.clave !== claveTrade(tr) && (
                        <button className="eliminar editar" title={t("Corregir el importe neto cobrado", "Correct the net amount collected")}
                                onClick={() => setEditando({ clave: claveTrade(tr),
                                                             valor: String(tr.pnl_origen ?? "") })}>✎</button>)}</td>
                    <td className={"n " + signo(tr.pnl_activo_usd)}>{usd(tr.pnl_activo_usd)}</td>
                    <td className={"n " + (tr.pnl_fx_usd ? "fx " + signo(tr.pnl_fx_usd) : "")}>
                      {tr.pnl_fx_usd ? usd(tr.pnl_fx_usd) : "—"}</td>
                    <td className={"n " + signo(tr.pnl_usd)}>{usd(tr.pnl_usd)}</td>
                  </tr>))}</tbody>
              </>
            ) : (
              <>
                <thead><tr><th>Ticker</th><th className="n">{t("Operaciones", "Trades")}</th>
                  <th className="n">{t("Resultado en su moneda", "Result in its own currency")}</th>
                  <th className="n">{t("Resultado inversión", "Investment result")}</th>
                  <th className="n">{t("Resultado tipo cambio", "Exchange-rate result")}</th>
                  <th className="n">{t("Resultado en dólares", "Result in dollars")}</th></tr></thead>
                <tbody>{porTicker.map((x) => (
                  <tr key={x.ticker}>
                    <td className="mono">{x.ticker}{x.fci &&
                      <span className="chip" style={{ marginLeft: 6, minWidth: 0 }}>fci</span>}
                      {x.caucion &&
                      <span className="chip" style={{ marginLeft: 6, minWidth: 0 }}>caución</span>}</td>
                    <td className="n">{x.n}</td>
                    <td className={"n " + signo(x.origen)}>{num(x.origen, 2)} {x.moneda}</td>
                    <td className={"n " + signo(x.activo)}>{usd(x.activo)}</td>
                    <td className={"n " + (x.fx ? "fx " + signo(x.fx) : "")}>
                      {x.fx ? usd(x.fx) : "—"}</td>
                    <td className={"n " + signo(x.usd)}>{usd(x.usd)}</td>
                  </tr>))}
                  <tr style={{ fontWeight: 700 }}>
                    <td>{t("NETO", "NET")}</td><td className="n">{real.n}</td>
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
          {detalle === "fci" ? (
            <div className="pie">
              {t(`Esto no son operaciones: es el saldo de todas tus suscripciones y rescates, `
                + `uno por fondo. Entra sólo lo que`,
                `These aren't trades: it's the balance of all your subscriptions and redemptions, `
                + `one per fund. Only what`)} <b>{t("ya rescataste", "you already redeemed")}</b>{" "}
              {t(`—apareado FIFO contra lo que costó—, y cada movimiento se pasó a dólares con el MEP de`,
                 `enters —matched FIFO against its cost—, and each movement was converted to dollars at the MEP rate of`)}{" "}
              <b>{t("su", "its own")}</b>{" "}
              {t(`fecha, no con el de hoy. Por eso un fondo puede ganar en pesos y perder en dólares. `
                + `Lo que todavía tenés no está acá: eso es tenencia y vive en la posición.`,
                `date, not today's. That's why a fund can gain in pesos and lose in dollars. `
                + `What you still hold isn't here: that's a holding and lives in the position.`)}
              {conFci
                ? <> {t("El", "The")} <b>{usd(fciUsd)}</b> {t("de subtotal", "subtotal")}{" "}
                    <b>{t("está sumado", "is included")}</b> {t("en el neto de arriba.", "in the net above.")}</>
                : <> {t("El", "The")} <b>{usd(fciUsd)}</b> {t("de subtotal", "subtotal")} <b>{t("no", "isn't")}</b>{" "}
                   {t("está contando en el neto de arriba: lo apagaste con el interruptor «con FCI». "
                     + "Acá se sigue viendo igual.",
                     "counted in the net above: you turned it off with the «with FCI» toggle. "
                     + "It still shows here the same way.")}</>}
            </div>
          ) : detalle === "caucion" ? (
            <div className="pie">
              {t(`Interés cobrado (colocadora) contra interés pagado (tomadora), en todo el `
                + `historial de InvIU — no es una operación por rollover, son cientos, así que cada `
                + `lado entra como un único cerrado agregado. Convertido a dólares con el MEP de`,
                `Interest collected (colocadora) against interest paid (tomadora), across the whole `
                + `InvIU history — it's not one trade per rollover, there are hundreds, so each `
                + `side enters as a single aggregated closed trade. Converted to dollars at the MEP rate of`)}{" "}
              <b>{t("cada fecha", "each date")}</b>. {t("El", "The")} <b>{usd(caucionUsd)}</b>{" "}
              {t("de subtotal ya está sumado en el neto de arriba, como cualquier otro cerrado.",
                 "subtotal is already included in the net above, like any other closed trade.")}
            </div>
          ) : (
          <div className="pie">
            <b>{t("En su moneda", "In its own currency")}</b> {t("es lo que muestra el broker, que no sabe de MEP. "
              + "El resultado en dólares se abre en dos:", "is what the broker shows, which knows nothing about "
              + "the MEP rate. The result in dollars splits into two:")} <b>{t("resultado inversión", "investment result")}</b>{" "}
            {t("es lo que dejó el activo, y", "is what the asset left behind, and")}{" "}
            <b>{t("resultado tipo de cambio", "exchange-rate result")}</b>{" "}
            {t(`lo que el MEP le hizo al capital mientras estuvo `
              + `invertido. Suman el neto exacto — la ganancia se convierte al MEP de la venta, que `
              + `es el dólar con el que se cobró. Una operación que ya era en dólares no tiene `
              + `resultado de tipo de cambio: no hubo exposición. Neteo FIFO contra las compras más viejas; los splits se `
              + `prorratean sobre lo que había abierto.`,
              `what the exchange rate did to the capital while it was `
              + `invested. They add up to the exact net — the gain is converted at the sale's rate, which `
              + `is the rate it was collected at. A trade already in dollars has no `
              + `exchange-rate result: there was no exposure. FIFO netting against the oldest purchases; splits are `
              + `prorated over what was open.`)} {ganadores} {t("de", "out of")} {porTicker.length}{" "}
            {t("tickers cerraron en verde.", "tickers closed in the green.")}
          </div>)}
          {detalle !== "fci" && LAB && (
            <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginTop: 10 }}>
              <button className="btn" onClick={traerYahoo} disabled={yahoo?.yendo}>
                {yahoo?.yendo ? t("Buscando dividendos…", "Looking up dividends…")
                              : t("Traer dividendos de Yahoo", "Fetch dividends from Yahoo")}</button>
              {yahoo && !yahoo.yendo && (
                <span className="pie" style={{ margin: 0 }}>
                  {yahoo.error ? yahoo.error
                    : yahoo.agregados
                    ? <>{yahoo.agregados} {t(yahoo.agregados === 1 ? "dividendo nuevo" : "dividendos nuevos",
                                             yahoo.agregados === 1 ? "new dividend" : "new dividends")}:{" "}
                        {Object.entries(yahoo.por_moneda).map(([m, v]) => `${num(v, 2)} ${m}`).join(" · ")}{" "}
                        {t("netos.", "net.")}</>
                    : t("No hay dividendos nuevos: los que tocaban ya están cargados.",
                        "No new dividends: the ones that were due are already loaded.")}
                </span>)}
            </div>)}
          {detalle !== "fci" && LAB && (
            <div className="pie">
              {IDIOMA === "en" ? (<>
                Yahoo gives the <b>gross</b> dividend per stock and its ex-dividend date; it's
                collected by every lot you held that day —bought before, sold that day or later—.
                The withholding you configured in <b>Portfolios</b> for stocks or CEDEARs is
                deducted, and it stays marked <b>est.</b> until you correct it with ✎ with what
                you actually got credited. What's already loaded isn't repeated: a collection of
                the same stock within the month following the ex-dividend date is taken as the
                same payment. Bonds aren't included: Yahoo doesn't have their income.
              </>) : (<>
                Yahoo da el dividendo <b>bruto</b> por papel y su fecha ex-dividendo; lo cobra cada
                lote que tenías ese día —comprado antes, vendido ese día o después—. Se descuenta la
                retención que configuraste en <b>Carteras</b> para acciones o CEDEARs, y queda
                marcado <b>est.</b> hasta que lo corrijas con ✎ por lo que de verdad te acreditaron.
                No se repite lo que ya está cargado: un cobro del mismo papel dentro del mes
                siguiente al ex-dividendo se toma como el mismo pago. Los bonos no están: Yahoo no
                tiene su renta.
              </>)}
            </div>)}
          {detalle !== "fci" && <AltaDividendo cartera={cartera} recargar={recargar} />}
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
  const CARACTER_EN = { defensiva: "defensive", mixta: "mixed", agresiva: "aggressive" };
  return (
    <div className="panel">
      <h3>{t("¿Defensiva o agresiva?", "Defensive or aggressive?")}
        <span className={"chip " + tono} style={{ marginLeft: 8 }}>{t(corr.caracter, CARACTER_EN[corr.caracter] || corr.caracter)}</span>
        {corr.matriz_caidas && (
          <button className="btn" style={{ marginLeft: "auto", padding: "3px 10px", fontSize: 12 }}
                  onClick={() => setEnCaidas(!enCaidas)}>
            {enCaidas ? t("Ver días normales", "View normal days") : t("Ver solo días de caída", "View only down days")}</button>)}
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
            <Kpi etiqueta={t("Correlación media", "Average correlation")} valor={num(corr.correlacion_media, 3)}
                 ayuda={{ que: [t("Correlación media entre pares", "Average pairwise correlation"),
                               t("Correlación media entre pares", "Average pairwise correlation")],
                          como: [t("Cuánto se mueven juntos tus activos, en promedio. Va de −1 a 1.",
                                   "How much your assets move together, on average. Ranges from −1 to 1."),
                                 t("Cuánto se mueven juntos tus activos, en promedio. Va de −1 a 1.",
                                   "How much your assets move together, on average. Ranges from −1 to 1.")],
                          umbral: [t("Debajo de 0,3 la cartera es defensiva; arriba de 0,6, agresiva: casi todo se mueve junto.",
                                     "Below 0.3 the portfolio is defensive; above 0.6, aggressive: almost everything moves together."),
                                   t("Debajo de 0,3 la cartera es defensiva; arriba de 0,6, agresiva: casi todo se mueve junto.",
                                     "Below 0.3 the portfolio is defensive; above 0.6, aggressive: almost everything moves together.")] }} />
            <Kpi etiqueta={t("En días de caída", "On down days")} valor={num(corr.correlacion_media_en_caidas, 3)}
                 tono={corr.aviso_caidas ? "neg" : ""} sub={t("el 10 % de días peores", "the worst 10 % of days")} />
          </div>
          <div className={"aviso " + tono}>{corr.lectura}</div>
          {corr.aviso_caidas && <div className="aviso mal">{corr.aviso_caidas}</div>}
          {corr.par_mas_correlacionado && (
            <div className="pie">
              {t("El par que más se mueve junto:", "The pair that moves together the most:")}{" "}
              <b>{corr.par_mas_correlacionado.a} ↔ {corr.par_mas_correlacionado.b}</b> ({corr.par_mas_correlacionado.corr}).{" "}
              {t("El que menos:", "The least:")}{" "}
              <b>{corr.par_menos_correlacionado.a} ↔ {corr.par_menos_correlacionado.b}</b> ({corr.par_menos_correlacionado.corr}).
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
  if (!dist || !dist.x) return <div className="aviso ojo">{t("Sin datos suficientes para la distribución.",
                                                              "Not enough data for the distribution.")}</div>;

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
        <h3>{t("Distribución de los retornos diarios", "Distribution of daily returns")}
          <span className={"chip " + (ganaT ? "ojo" : "ok")} style={{ marginLeft: 8 }}>
            {t(`se ajusta mejor a ${dist.mejor_ajuste}`, `best fits ${dist.mejor_ajuste}`)}</span>
        </h3>
        <Grafico alto={400}
          datos={[
            { type: "bar", x: dist.x, y: dist.y, name: t("días que pasaron", "days that happened"),
              marker: { color: dist.zonas.map((z) => colorZona[z]), opacity: 0.85 },
              hovertemplate: t("%{x:.2f} %: %{y} días<extra></extra>", "%{x:.2f} %: %{y} days<extra></extra>") },
            { type: "scatter", mode: "lines", x: dist.x, y: dist.normal,
              name: t("si fuera una campana normal", "if it were a normal bell curve"),
              line: { color: c.texto3, width: 2, dash: "dot" } },
            ...(dist.grados_libertad ? [{ type: "scatter", mode: "lines", x: dist.x,
              y: dist.tstudent, name: t(`t de Student (ν = ${dist.grados_libertad})`,
                                        `Student's t (ν = ${dist.grados_libertad})`),
              line: { color: c.acento, width: 2.4 } }] : []),
          ]}
          layout={{
            bargap: 0.02, margin: { t: 28 },
            xaxis: { title: t("Retorno de un día", "One-day return"), ticksuffix: " %" },
            yaxis: { title: t("Cantidad de días", "Number of days") },
            shapes: [linea(d.var95_pct, c.alerta), linea(d.var99_pct, c.negativo),
                     linea(dist.media_pct, c.texto3, 1)],
            // Las tres marcas caen en pocos puntos porcentuales, así que cada
            // una se ancla hacia afuera de su propia línea: centradas se
            // escribían una encima de la otra.
            annotations: [
              { x: d.var99_pct, y: 1, yref: "paper", text: t("1 de cada 100", "1 in 100"), showarrow: false,
                font: { size: 10, color: c.negativo }, yanchor: "bottom", xanchor: "right" },
              { x: d.var95_pct, y: 1, yref: "paper", text: t("día malo", "bad day"), showarrow: false,
                font: { size: 10, color: c.alerta }, yanchor: "bottom", xanchor: "left" },
              { x: dist.media_pct, y: 1, yref: "paper", text: t("día promedio", "average day"), showarrow: false,
                font: { size: 10, color: c.texto3 }, yanchor: "bottom", xanchor: "left" }] }} />
        <div className="pie">
          {t(`Cada barra es la cantidad de ruedas que terminaron con ese retorno, sobre `,
             `Each bar is the number of sessions that ended with that return, out of `)}
          {dist.n_dias} {t("días.", "days.")} {t("En", "In")} <span style={{ color: c.negativo }}>
            {t("rojo", "red")}</span> {t("las pérdidas graves, en", "severe losses, in")}{" "}
          <span style={{ color: c.alerta }}>{t("ámbar", "amber")}</span> {t("los días malos, en", "bad days, in")}{" "}
          <span style={{ color: c.series[1] }}>{t("dorado", "gold")}</span> {t("lo que se aparta más de dos "
          + "desvíos, y en", "what's more than two standard deviations off, and in")}{" "}
          <span style={{ color: c.series[2] }}>{t("azul", "blue")}</span> {t("el comportamiento "
          + "habitual.", "usual behavior.")} {t("Día promedio", "Average day")} {pct(dist.media_pct, 3)},
          {" "}{t("desvío", "std. dev.")} {pct(dist.sigma_pct)}.
        </div>
      </div>

      <div className="fila f2">
        <div className="panel">
          <h3>{t("Los días extremos pasan más seguido de lo que un modelo normal supone",
                 "Extreme days happen more often than a normal model assumes")}</h3>
          <div className="tabla-wrap"><table>
            <thead><tr><th>{t("Días peores que", "Days worse than")}</th>
              <th className="n">{t("Umbral", "Threshold")}</th>
              <th className="n">{t("Pasaron", "Happened")}</th>
              <th className="n">{t("Si fuera normal", "If it were normal")}</th>
              <th className="n">{t("Exceso", "Excess")}</th></tr></thead>
            <tbody>{(dist.extremos || []).map((e) => (
              <tr key={e.sigmas}>
                <td>−{e.sigmas} {t("desvíos", "std. dev.")}</td>
                <td className="n neg">{pct(e.umbral_pct)}</td>
                <td className="n">{e.observados}</td>
                <td className="n">{e.si_fuera_normal}</td>
                <td className={"n " + (e.veces > 1.5 ? "neg" : "")}>
                  {e.veces == null ? "—" : `${e.veces}×`}</td>
              </tr>))}</tbody>
          </table></div>
          <div className="pie">
            {t("A dos desvíos la campana acierta. Es", "At two standard deviations the bell curve gets it right. It's")}{" "}
            <b>{t("más allá", "beyond that")}</b> {t("donde se rompe:", "where it breaks down:")}
            {peor && peor.veces > 1 && <> {t(`los días peores que −${peor.sigmas} desvíos pasaron`,
              `days worse than −${peor.sigmas} standard deviations happened`)}{" "}
              <b>{t(`${peor.veces} veces más seguido`, `${peor.veces} times more often`)}</b>{" "}
              {t("de lo que predice.", "than it predicts.")}</>}{" "}
            {t("Por eso el VaR calculado con la campana subestima el escenario grave, y por eso "
              + "se muestra también el de Cornish-Fisher.",
              "That's why the VaR calculated with the bell curve underestimates the severe scenario, and why "
              + "the Cornish-Fisher one is also shown.")}
          </div>
        </div>

        <div className="panel">
          <h3>{t("La forma de la distribución", "The shape of the distribution")}</h3>
          <div className="kpis" style={{ gridTemplateColumns: "1fr 1fr" }}>
            <Kpi etiqueta={t("Asimetría", "Skewness")} valor={num(d.asimetria, 3)}
                 tono={d.asimetria < -0.3 ? "neg" : d.asimetria > 0.3 ? "pos" : ""}
                 ayuda={{ que: [t("Asimetría", "Skewness"), t("Asimetría", "Skewness")],
                          como: [t("Hacia qué lado se estira la distribución. Negativa: las caídas grandes son más frecuentes que las subas grandes.",
                                   "Which side the distribution stretches toward. Negative: large drops are more frequent than large rallies."),
                                 t("Hacia qué lado se estira la distribución. Negativa: las caídas grandes son más frecuentes que las subas grandes.",
                                   "Which side the distribution stretches toward. Negative: large drops are more frequent than large rallies.")],
                          umbral: [t("Cerca de 0 es simétrica. Por debajo de −0,5 hay sesgo claro a pérdidas.",
                                     "Close to 0 is symmetric. Below −0.5 there's a clear skew toward losses."),
                                   t("Cerca de 0 es simétrica. Por debajo de −0,5 hay sesgo claro a pérdidas.",
                                     "Close to 0 is symmetric. Below −0.5 there's a clear skew toward losses.")] }} />
            <Kpi etiqueta={t("Curtosis", "Kurtosis")} valor={num(d.curtosis_exceso, 2)} sub={t("en exceso", "excess")}
                 tono={d.curtosis_exceso > 3 ? "neg" : ""} ayuda={AYUDA.curtosis} />
          </div>
          <div className={"aviso " + (d.asimetria < -0.3 ? "ojo" : "")}>
            {d.asimetria < -0.3
              ? t("La cola izquierda es más larga: cuando esta cartera se mueve fuerte, tiende a ser para abajo.",
                  "The left tail is longer: when this portfolio moves hard, it tends to be downward.")
              : d.asimetria > 0.3
              ? t("La cola derecha es más larga: los movimientos fuertes tienden a ser al alza.",
                  "The right tail is longer: strong moves tend to be upward.")
              : t("La distribución es bastante simétrica: subidas y bajadas grandes son igual de frecuentes.",
                  "The distribution is fairly symmetric: large rallies and drops are equally frequent.")}
          </div>
          <div className={"aviso " + (d.curtosis_exceso > 3 ? "mal" : "ok")}>
            {d.curtosis_exceso > 3
              ? t(`Curtosis en exceso de ${num(d.curtosis_exceso, 1)}: hay colas gordas. Los días
                 excepcionales —buenos y malos— pasan mucho más seguido de lo que supone
                 cualquier modelo basado en la campana normal.`,
                 `Excess kurtosis of ${num(d.curtosis_exceso, 1)}: there are fat tails. Exceptional
                 days —good and bad— happen much more often than any model based on the
                 normal bell curve assumes.`)
              : t("Curtosis moderada: los movimientos extremos no son más frecuentes de lo esperable.",
                  "Moderate kurtosis: extreme moves aren't more frequent than expected.")}
          </div>
          {ganaT && (
            <div className="pie">
              {t(`El test de Kolmogórov-Smirnov elige la `, `The Kolmogorov-Smirnov test picks `)}
              <b>{t(`t de Student con ${dist.grados_libertad} grados de libertad`,
                    `Student's t with ${dist.grados_libertad} degrees of freedom`)}</b>{" "}
              {t("por sobre la normal. Menos grados de libertad = colas más gordas; "
                + "por debajo de 5 la diferencia con la campana ya es grande.",
                "over the normal one. Fewer degrees of freedom = fatter tails; "
                + "below 5 the difference from the bell curve is already large.")}
            </div>)}
        </div>
      </div>
    </>
  );
}

/* ═══════════════ Componentes de la librería UX-UI ═══════════════

   DAT-03 heatmap, DAT-15 radar, DAT-16 bullet, DAT-17 treemap, DAT-21 frontera,
   PNL-05 métrica, PNL-16 card con gráfico, PRG-07 stepper, PRG-16 zonas de
   riesgo, TGL-02 día/noche, BTN-02 trazo y el spinner de FDB-05. Traducidos a
   los tokens de esta app: ningún color literal, como el resto del archivo.

   Se desarrollaron detrás de `?lab=1` y se aprobaron uno por uno; de ahí el
   prefijo `lab-` de sus clases, que quedó como marca de origen. */

/* Umbrales de riesgo. No salen de ningún cálculo: son la tolerancia que uno
   decide de antemano, y por eso están acá y no en el backend. */
const ZONAS = { prudente: 1.5, moderado: 2.5, limite: 3.0, escala: 4.0 };

/* PRG-16 · una pérdida contra las zonas de tolerancia y el límite.
   La escala se estira si la cartera se pasa: con tope fijo, una cartera
   volátil clava la aguja en el borde y 4,4 % se ve igual que 6,4 %. */
function BarraRiesgo({ etiqueta, detalle, pct_, usd_, escala, nota }) {
  const c = colores();
  const v = Math.abs(pct_ || 0);
  const en = (x) => (x / escala) * 100 + "%";
  const [tono, texto] =
    v > ZONAS.limite ? ["mal", t("excedido", "exceeded")]
    : v > ZONAS.moderado ? ["ojo", t("agresivo", "aggressive")]
    : v > ZONAS.prudente ? ["ojo", t("moderado", "moderate")] : ["ok", t("prudente", "conservative")];
  return (
    <div className="lab-zona">
      <div className="et">{etiqueta}<s>{detalle}</s></div>
      <div className="lab-barra" style={{ "--pct": en(Math.min(v, escala)), "--lim": en(ZONAS.limite) }}>
        <div className="via" style={{ background: `linear-gradient(90deg,${c.positivo} 0 ${en(ZONAS.prudente)},`
          + `${c.alerta} ${en(ZONAS.prudente)} ${en(ZONAS.moderado)},${c.negativo} ${en(ZONAS.moderado)})` }}>
          <span className="tope"><s>{t("límite", "limit")} {pct(ZONAS.limite, 1)}</s></span></div>
        <span className="aguja" />
        <div className="pies">
          <span style={{ left: en(ZONAS.prudente / 2) }}>{t("prudente", "conservative")}</span>
          <span style={{ left: en((ZONAS.prudente + ZONAS.moderado) / 2) }}>{t("moderado", "moderate")}</span>
          <span style={{ left: en((ZONAS.moderado + escala) / 2) }}>{t("agresivo", "aggressive")}</span>
          <span style={{ left: "100%" }}>{pct(escala, 1)}</span></div>
      </div>
      <div className="val">
        <b className="neg">{pct(-v)}</b>
        <s>{usd_ != null ? usd(usd_) + " · " : ""}{t("usa el", "uses")}{" "}
          {Math.round((v / ZONAS.limite) * 100)} % {t("del límite", "of the limit")}</s>
        <span className={"chip " + tono} style={{ marginTop: 6, display: "inline-block" }}>{texto}</span>
        {nota && <s>{nota}</s>}
      </div>
    </div>
  );
}

function ZonasRiesgo({ d }) {
  // Una sola escala para las dos barras: si cada una se ajusta a lo suyo, el
  // CVaR parece menos grave que el VaR justo cuando es peor.
  const escala = Math.max(ZONAS.escala,
    Math.ceil(Math.max(Math.abs(d.var95_pct || 0), Math.abs(d.cvar95_pct || 0)) * 1.15));
  return (
    <div className="panel">
      <h3>{t("¿Cuánto margen queda antes del límite?", "How much room is left before the limit?")}</h3>
      <BarraRiesgo etiqueta={t("Día malo", "Bad day")}
                   detalle={t("VaR 95 % · 1 rueda de cada 20", "VaR 95 % · 1 session out of 20")}
                   escala={escala} pct_={d.var95_pct} usd_={d.var95_usd} />
      <BarraRiesgo etiqueta={t("Día muy malo", "Very bad day")}
                   detalle={t("CVaR 95 % · promedio de ese 5 % peor", "CVaR 95 % · average of that worst 5 %")}
                   escala={escala} pct_={d.cvar95_pct} usd_={d.cvar95_usd} />
      <div className="pie">
        {t(`Las zonas y el límite de ${pct(ZONAS.limite, 1)} son una política, no un cálculo: `
          + `es cuánto estás dispuesto a perder en un día, decidido antes de que pase. El VaR dice `
          + `el piso de ese 5 % de días; el CVaR, lo que se pierde en promedio cuando se cruza `
          + `—siempre peor, y es el número que importa cuando el día malo llega—.`,
          `The zones and the ${pct(ZONAS.limite, 1)} limit are a policy, not a calculation: `
          + `it's how much you're willing to lose in a day, decided before it happens. VaR says `
          + `the floor of that worst 5 % of days; CVaR, what's lost on average when it's crossed `
          + `—always worse, and it's the number that matters when the bad day arrives—.`)}
      </div>
    </div>
  );
}

/* DAT-17 · treemap por sector: alto de banda = sector, ancho = ticker. Dice de
   una lo que la dona no: qué papel concreto trae cada sector. */
function TreemapSectores({ detalle, campo = "sector", alto = 300 }) {
  const c = colores();
  const sectores = {};
  (detalle || []).forEach((x) => {
    if (!x.valor_usd) return;
    const k = x[campo] || t("Sin dato", "No data");
    (sectores[k] = sectores[k] || { valor: 0, items: [] });
    sectores[k].valor += x.valor_usd;
    sectores[k].items.push(x);
  });
  const orden = Object.entries(sectores).sort((a, b) => b[1].valor - a[1].valor);
  const suma = orden.reduce((a, [, s]) => a + s.valor, 0) || 1;
  if (!orden.length) return <div className="cargando">{t("Sin sectores clasificados.", "No classified sectors.")}</div>;

  return (
    <div className="lab-tree" style={{ height: alto }}>
      {orden.map(([nombre, s], i) => (
        <div className="sec" key={nombre} style={{ flex: s.valor }}>
          <span className="rot" title={`${nombre} · ${usd(s.valor)}`}>
            <u style={{ background: c.series[i % c.series.length] }} />
            <b>{nombre}</b><i>{pct((s.valor / suma) * 100, 1)}</i>
          </span>
          <div className={"cajas" + (s.valor / suma < 0.09 ? " bajo" : "")}>
            {s.items.sort((a, b) => b.valor_usd - a.valor_usd).map((x) => {
              const w = (x.valor_usd / suma) * 100;
              return (
                <i key={x.ticker} className={w < 5 ? "chico" : ""}
                   style={{ flex: x.valor_usd, background: c.series[i % c.series.length] }}
                   title={`${x.ticker} · ${nombre} · ${usd(x.valor_usd)}`}>
                  {x.ticker}<s>{pct(w, 1)}</s>
                </i>);
            })}
          </div>
        </div>))}
    </div>
  );
}

/* DAT-16 · bullet: peso de hoy contra el objetivo, con el monto a operar. */
function BulletPesos({ filas, nota }) {
  const c = colores();
  const tope = Math.max(...filas.flatMap((f) => [f.hoy, f.objetivo]), 1) * 1.12;
  return (
    <>
      {filas.map((f) => {
        const compra = f.monto > 0;
        const mueve = Math.abs(f.hoy - f.objetivo) > 0.05;
        return (
          <div className="lab-bullet" key={f.nombre}>
            <span className="mono">{f.nombre}</span>
            <div className="via">
              <span className="hoy" style={{ width: (f.hoy / tope) * 100 + "%",
                background: mueve ? (compra ? c.positivo : c.negativo) : c.texto3 }} />
              <span className="obj" style={{ left: (f.objetivo / tope) * 100 + "%" }} />
            </div>
            <span className="objpct">{pct(f.objetivo, 1)}</span>
            <span className={"monto " + (mueve ? signo(f.monto) : "")}>
              {mueve ? (compra ? t("comprar ", "buy ") : t("vender ", "sell ")) + usd(Math.abs(f.monto)) : "—"}
            </span>
          </div>);
      })}
      <div className="pie">
        {t("Barra = peso de hoy, línea blanca = peso objetivo, y al lado su número. Verde si hay "
          + "que comprar, rojo si hay que vender.",
          "Bar = today's weight, white line = target weight, with its number next to it. Green means "
          + "buy, red means sell.")} {nota}
      </div>
    </>
  );
}

/* PNL-05 · rendimiento del año, con su curva y el menú de acciones. */
function RendimientoTotal({ ev }) {
  const [abierto, setAbierto] = useState(false);
  const c = colores();
  useEffect(() => {
    if (!abierto) return;
    const cerrar = () => setAbierto(false);
    document.addEventListener("click", cerrar);
    return () => document.removeEventListener("click", cerrar);
  }, [abierto]);
  if (!ev || ev.error) return null;

  const delta = ev.resultado_usd - ev.resultado_mes_anterior_usd;
  const serie = ev.resultado_serie || [];
  const mn = Math.min(...serie, 0), mx = Math.max(...serie, 0), rango = mx - mn || 1;
  const y = (v) => 34 - 4 - ((v - mn) / rango) * 26;
  const linea = serie.map((v, i) => (i ? "L" : "M") +
    ((i / (serie.length - 1)) * 300).toFixed(1) + "," + y(v).toFixed(1)).join(" ");
  const marcas = marcasTiempo(ev.fechas, 6);


  return (
    <div className="panel" style={{ position: "relative" }}>
      <h3>{t("Rendimiento total", "Total return")}
        <button className="btn" style={{ marginLeft: "auto", padding: "2px 9px" }}
                onClick={(e) => { e.stopPropagation(); setAbierto((x) => !x); }}>⋯</button>
      </h3>
      {abierto && (
        <div style={{ position: "absolute", right: 16, top: 46, background: "var(--panel)",
                      border: "1px solid var(--borde)", borderRadius: 8, padding: 4,
                      boxShadow: "var(--sombra)", zIndex: 9 }}>
          {[t("Ver detalle por posición", "View detail by position"),
            t("Comparar con el benchmark", "Compare against the benchmark"),
            t("Exportar CSV", "Export CSV")].map((opc) => (
            <div key={opc} className="pie" style={{ margin: 0, padding: "7px 11px", cursor: "pointer" }}>{opc}</div>))}
        </div>)}
      <div style={{ fontSize: 30, fontWeight: 700, marginTop: 6 }}
           className={signo(ev.resultado_usd)}>{pct(ev.rendimiento_pct)}</div>
      <div style={{ fontSize: 15, marginTop: 2 }} className={signo(ev.resultado_usd)}>
        {t(`${usd(ev.resultado_usd)} sobre ${usd(ev.puesto_neto_usd)} puestos de tu bolsillo`,
           `${usd(ev.resultado_usd)} on ${usd(ev.puesto_neto_usd)} out of your own pocket`)}</div>
      <div className="pie" style={{ marginTop: 8 }}>
        <span className={signo(delta)}>{delta >= 0 ? "▲" : "▼"} {usd(Math.abs(delta))}</span>
        {" "}{t(`desde el cierre del mes pasado · arranca el ${ev.desde}, con la primera compra`,
                `since last month's close · starts on ${ev.desde}, with the first purchase`)}
        {ev.cerradas > 0 && t(` · incluye ${ev.cerradas} posiciones ya cerradas`,
                              ` · includes ${ev.cerradas} already closed positions`)}
        {ev.dividendos_usd > 0 && t(` · ${usd(ev.dividendos_usd)} de dividendos cobrados`,
                                    ` · ${usd(ev.dividendos_usd)} in dividends collected`)}
      </div>
      {ev.sin_serie?.length > 0 && (
        <div className="pie" style={{ marginTop: 6 }}>
          {t("Sin serie de precios y fuera de la cuenta:", "No price series, and out of the account:")}{" "}
          <b>{ev.sin_serie.join(", ")}</b>.
        </div>)}
      <svg viewBox="0 0 300 34" preserveAspectRatio="none"
           style={{ width: "100%", height: 40, marginTop: 12, display: "block" }}>
        <defs>
          {/* El corte va exactamente en el cero, así que un degradé vertical con
              los dos stops pegados alcanza: verde arriba, rojo abajo. */}
          <linearGradient id="labrt" x1="0" y1="0" x2="0" y2="34" gradientUnits="userSpaceOnUse">
            <stop offset={Math.max(0, Math.min(1, y(0) / 34))} stopColor={c.positivo} />
            <stop offset={Math.max(0, Math.min(1, y(0) / 34))} stopColor={c.negativo} />
          </linearGradient>
        </defs>
        <g className="ejeT">
          {marcas.map((m) => (
            <line key={m.et} x1={m.pos * 300} y1="0" x2={m.pos * 300} y2="34" />))}
        </g>
        <line x1="0" y1={y(0)} x2="300" y2={y(0)} stroke={c.borde} strokeWidth="1"
              strokeDasharray="3 3" />
        <path d={linea} fill="none" stroke="url(#labrt)" strokeWidth="1.8"
              strokeLinejoin="round" />
      </svg>
      <div className="lab-ejeT" style={{ position: "relative", height: 15, marginTop: 2 }}>
        {marcas.map((m) => (
          <span key={m.et} style={{ left: `${(m.pos * 100).toFixed(2)}%` }}>{m.et}</span>))}
      </div>
      <div className="pie">
        {t(`La curva es el resultado acumulado en ${MON()}, rueda por rueda, contando las `
          + `posiciones que ya cerraste y los dividendos cobrados. En plata y no en porcentaje `
          + `porque un porcentaje sobre capital variable cae de golpe el día que ponés plata `
          + `nueva, sin que haya pasado nada en el mercado. La línea punteada es el cero.`,
          `The curve is the accumulated result in ${MON()}, session by session, counting `
          + `positions you already closed and dividends collected. In money and not in percentage `
          + `because a percentage over variable capital drops suddenly the day you put in fresh `
          + `money, without anything having happened in the market. The dashed line is zero.`)}
      </div>
    </div>
  );
}

/* DAT-21 · la frontera, con la CAL, la rama ineficiente, cada activo suelto y
   la nube de carteras posibles de fondo. El crosshair dice, para el punto que
   estás mirando, si esa combinación de riesgo y retorno existe: a la izquierda
   de la bala no hay cartera que la alcance, a la derecha hay otra que da lo
   mismo con menos riesgo. */
function FronteraEficiente({ d }) {
  const c = colores();
  const [cursor, setCursor] = useState(null);
  const eff = d.frontera || [];
  const ine = d.frontera_ineficiente || [];
  const activos = d.activos || [];
  const rf = (d.rf || 0) * 100;
  const P = [
    [t("Tu cartera", "Your portfolio"), d.actual, c.marcaActual, false],
    [t("Mínima varianza", "Minimum variance"), d.min_varianza, c.series[2], false],
    [t("Máximo Sharpe", "Maximum Sharpe"), d.max_sharpe, c.marcaOptima, true],
  ];

  const nube = d.nube || {};
  const xs = [...eff, ...ine].map((p) => p.vol)
    .concat(activos.map((a) => a.vol_pct), P.map(([, p]) => p.vol_pct));
  const ys = [...eff, ...ine].map((p) => p.ret)
    .concat(activos.map((a) => a.ret_pct), P.map(([, p]) => p.ret_pct), [rf]);
  const xMax = Math.max(...xs) * 1.08;
  const yMin = Math.min(...ys, 0), yMax = Math.max(...ys) * 1.06;

  const L = 58, R = 606, T = 20, B = 338, W = 620, H = 380;
  const x = (v) => L + (v / xMax) * (R - L);
  const y = (v) => B - ((v - yMin) / (yMax - yMin)) * (B - T);
  const aVol = (px) => ((px - L) / (R - L)) * xMax;
  const aRet = (py) => yMin + ((B - py) / (B - T)) * (yMax - yMin);

  // Marcas redondas: 10, 20, 25, 50… según el rango, para no escribir "17,3 %".
  const marcas = (mn, mx, n) => {
    const bruto = (mx - mn) / n;
    const base = Math.pow(10, Math.floor(Math.log10(bruto)));
    const paso = [1, 2, 2.5, 5, 10].map((k) => k * base).find((k) => (mx - mn) / k <= n) || base * 10;
    const out = [];
    for (let v = Math.ceil(mn / paso) * paso; v <= mx + 1e-9; v += paso) out.push(+v.toFixed(6));
    return out;
  };
  const mx = marcas(0, xMax, 5), my = marcas(yMin, yMax, 5);
  const linea = (pts) => pts.map((p, i) => (i ? "L" : "M") +
    x(p.vol).toFixed(1) + "," + y(p.ret).toFixed(1)).join(" ");

  // La bala entera, ordenada por retorno: con ella se responde, para cualquier
  // retorno, cuál es la menor volatilidad que lo consigue.
  const bala = [...ine, ...eff].sort((a, b) => a.ret - b.ret);
  const volMinima = (ret) => {
    if (!bala.length || ret < bala[0].ret || ret > bala[bala.length - 1].ret) return null;
    const i = bala.findIndex((p) => p.ret >= ret);
    if (i <= 0) return bala[0].vol;
    const a = bala[i - 1], b = bala[i];
    const t = b.ret === a.ret ? 0 : (ret - a.ret) / (b.ret - a.ret);
    return a.vol + t * (b.vol - a.vol);
  };

  // 2.000 puntos en un solo path: un <circle> por cartera hace un DOM que se
  // arrastra al mover el mouse, y a este tamaño un punto es un trazo de 0,7 px.
  const puntos = (nube.vol || []).map((v, i) =>
    `M${x(v).toFixed(1)},${y(nube.ret[i]).toFixed(1)}h.7`).join("");

  const tg = d.max_sharpe;
  const pend = tg.vol_pct > 0 ? (tg.ret_pct - rf) / tg.vol_pct : 0;
  const calFin = Math.min(xMax, yMax > rf && pend > 0 ? (yMax - rf) / pend : xMax);

  // Tooltip a la izquierda del punto cuando está sobre la mitad derecha, para
  // que no se salga del gráfico.
  const globo = (px, py, titulo, detalle) => {
    const flip = px > (L + R) / 2;
    const tx = flip ? px - 12 : px + 12;
    return (
      <g className="tip">
        <rect x={flip ? tx - 104 : tx - 4} y={py - 34} width="108" height="30" rx="5" />
        <text className="t1" x={tx} y={py - 22} textAnchor={flip ? "end" : "start"}>{titulo}</text>
        <text className="t2" x={tx} y={py - 10} textAnchor={flip ? "end" : "start"}>{detalle}</text>
      </g>);
  };

  const mover = (e) => {
    const r = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - r.left) / r.width) * W, py = ((e.clientY - r.top) / r.height) * H;
    setCursor(px < L || px > R || py < T || py > B ? null : { px, py });
  };

  let veredicto = null;
  if (cursor) {
    const vm = volMinima(aRet(cursor.py)), v = aVol(cursor.px);
    if (vm != null) veredicto = v < vm - 0.05 ? ["no", t("inalcanzable", "unreachable")]
      : v > vm + 0.2 ? ["tibio", t("ineficiente", "inefficient")] : ["ok", t("en la frontera", "on the frontier")];
  }

  return (
    <div className="panel">
      <h3>{t("Frontera eficiente", "Efficient frontier")}</h3>
      <div className="lab-fhd">
        <span>{t("riesgo / retorno anual", "risk / annual return")}</span>
        <span>{t("Sharpe tangente", "Tangent Sharpe")} <b>{num(tg.sharpe, 3)}</b></span>
        <span>{t("tasa libre", "risk-free rate")} <b>{pct(rf, 2)}</b></span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="lab-front"
           onPointerMove={mover} onPointerLeave={() => setCursor(null)}>
        <g className="malla">
          {mx.map((v) => <line key={"x" + v} x1={x(v)} y1={T} x2={x(v)} y2={B} />)}
          {my.map((v) => <line key={"y" + v} x1={L} y1={y(v)} x2={R} y2={y(v)} />)}
        </g>
        {puntos && <path className="nube" d={puntos} />}
        {yMin < 0 && <line className="cero" x1={L} y1={y(0)} x2={R} y2={y(0)} />}
        <path className="cal" d={`M${x(0)},${y(rf)} L${x(calFin)},${y(rf + pend * calFin)}`} />
        {ine.length > 0 && <path className="ineficiente" d={linea(ine)} />}
        <path className="eficiente" d={linea(eff)} />

        {cursor && (
          <g className="cruz">
            <line x1={cursor.px} y1={T} x2={cursor.px} y2={B} />
            <line x1={L} y1={cursor.py} x2={R} y2={cursor.py} />
            <g className="et">
              <rect x={cursor.px - 24} y={B + 4} width="48" height="15" rx="3" />
              <text x={cursor.px} y={B + 14.5} textAnchor="middle">σ {pct(aVol(cursor.px), 1)}</text>
            </g>
            <g className="et">
              <rect x={L + 4} y={cursor.py - 7.5} width="48" height="15" rx="3" />
              <text x={L + 8} y={cursor.py + 3.5} textAnchor="start">μ {pct(aRet(cursor.py), 1)}</text>
            </g>
            {veredicto && (
              <text className={"zona " + veredicto[0]}
                    x={cursor.px + (cursor.px > (L + R) / 2 ? -9 : 9)} y={cursor.py - 9}
                    textAnchor={cursor.px > (L + R) / 2 ? "end" : "start"}>{veredicto[1]}</text>)}
          </g>)}

        {[...activos].sort((a, b) => a.vol_pct - b.vol_pct).map((a, i, arr) => {
          const px = x(a.vol_pct), py = y(a.ret_pct);
          const pegado = i > 0 && Math.abs(px - x(arr[i - 1].vol_pct)) < 46
                               && Math.abs(py - y(arr[i - 1].ret_pct)) < 26;
          return (
            <g className="activo" key={a.ticker} tabIndex={0}>
              <circle cx={px} cy={py} r="4.5" />
              <circle className="hit" cx={px} cy={py} r="13" />
              <text x={px} y={py + (pegado ? 16 : -10)} textAnchor="middle">{a.ticker}</text>
              {globo(px, py, a.ticker, `${pct(a.ret_pct, 1)} · σ ${pct(a.vol_pct, 1)}`)}
            </g>);
        })}
        {P.map(([nombre, p, color, tangente]) => {
          const px = x(p.vol_pct), py = y(p.ret_pct);
          return (
            <g className={"marca" + (tangente ? " tan" : "")} key={nombre} tabIndex={0}>
              <circle cx={px} cy={py} r="6.5" style={{ fill: color }} />
              <circle className="hit" cx={px} cy={py} r="14" />
              {globo(px, py, nombre, `${pct(p.ret_pct, 1)} · σ ${pct(p.vol_pct, 1)}`
                                     + ` · S ${num(p.sharpe, 2)}`)}
            </g>);
        })}
        <g className="ejes">
          {mx.map((v) => <text key={"tx" + v} x={x(v)} y={B + 18} textAnchor="middle">{pct(v, 0)}</text>)}
          {my.map((v) => <text key={"ty" + v} x={L - 8} y={y(v) + 3.5} textAnchor="end">{pct(v, 0)}</text>)}
          <text className="ttl" x={(L + R) / 2} y={B + 38} textAnchor="middle">
            {t("VOLATILIDAD ANUAL σ", "ANNUAL VOLATILITY σ")}</text>
          <text className="ttl" x="14" y={(T + B) / 2} textAnchor="middle"
                transform={`rotate(-90 14 ${(T + B) / 2})`}>{t("RETORNO ESPERADO μ", "EXPECTED RETURN μ")}</text>
        </g>
      </svg>
      <div className="lab-flg">
        <span><u className="ueff" />{t("frontera eficiente", "efficient frontier")}</span>
        <span><u className="uine" />{t("rama ineficiente", "inefficient branch")}</span>
        <span><u className="ucal" />CAL</span>
        {P.map(([nombre, , color]) => (
          <span key={nombre}><u style={{ background: color, borderRadius: "50%" }} />{nombre}</span>))}
        <span><u className="uact" />{t("activo suelto", "individual asset")}</span>
        <span><u className="unube" />{t("carteras posibles", "possible portfolios")}</span>
      </div>
    </div>
  );
}

/* DAT-15 · radar comparativo. Cada eje va normalizado entre la mejor y la peor
   de las series, porque el radar compara y no mide en absoluto: con escalas
   crudas un Sharpe de 1,4 desaparece al lado de un retorno de 33 %. Los valores
   reales viven en el tooltip de cada vértice y en la tabla de al lado. */
function Radar({ ejes, series, alto = 250 }) {
  const W = 330, H = alto;
  const cx = W / 2, cy = H / 2 - 7, R = Math.min(W, H) / 2 - 42;
  const punto = (i, v) => {
    const a = (i / ejes.length) * 2 * Math.PI - Math.PI / 2;
    return [cx + Math.cos(a) * R * v, cy + Math.sin(a) * R * v];
  };
  // Piso de 0,18 para que la peor de todas siga dibujando un polígono legible.
  const escalados = ejes.map((eje, i) => {
    const vals = series.map((s) => s.vals[i]);
    const mn = Math.min(...vals), mx = Math.max(...vals), r = mx - mn;
    return vals.map((v) => {
      const t = r === 0 ? 1 : (v - mn) / r;
      return 0.18 + 0.82 * (eje.mas ? t : 1 - t);
    });
  });

  return (
    <>
      <svg viewBox={`0 0 ${W} ${H}`} className="lab-radar">
        <g className="malla">
          {[0.25, 0.5, 0.75, 1].map((k) => (
            <polygon key={k} points={ejes.map((_, i) => punto(i, k).join(",")).join(" ")} />))}
          {ejes.map((_, i) => (
            <line key={i} x1={cx} y1={cy} x2={punto(i, 1)[0]} y2={punto(i, 1)[1]} />))}
        </g>
        {series.map((serie, j) => (
          <polygon key={serie.nombre} className="forma"
                   style={{ stroke: serie.color, fill: serie.color }}
                   points={escalados.map((e, i) => punto(i, e[j]).join(",")).join(" ")} />))}
        {ejes.map((eje, i) => {
          const [x, y] = punto(i, 1.28);
          return (
            <g key={eje.et}>
              <text className="eje" x={x} y={y} textAnchor="middle"
                    dominantBaseline="middle">{eje.et}</text>
              <circle cx={punto(i, 1)[0]} cy={punto(i, 1)[1]} r="22" fill="transparent">
                <title>{`${eje.et}\n` + series.map((s) => `${s.nombre}: ${eje.fmt(s.vals[i])}`).join("\n")}</title>
              </circle>
            </g>);
        })}
      </svg>
      <div className="lab-radar-lg">
        {series.map((s) => (
          <span key={s.nombre}><u style={{ background: s.color }} />{s.nombre}</span>))}
      </div>
    </>
  );
}

/* Las carteras del optimizador, sobre los ejes que las distinguen. Black-
   Litterman es opcional: sin `bl` (o con error) se dibujan igual las otras
   tres — antes, al armar las 4 series siempre, un valor `undefined` de BL
   entraba al Math.min/max compartido de cada eje, daba NaN, y esa NaN
   contaminaba las CUATRO series (el radar entero quedaba en blanco, no solo
   la cuarta). */
function RadarCarteras({ mk, bl }) {
  const c = colores();
  const T = mk.tickers || [];
  const hhi = (w) => w.reduce((a, x) => a + (x / 100) ** 2, 0);
  const rota = (w) => w.reduce((a, x, i) => a + Math.abs(x - mk.actual.pesos[i]), 0) / 200;

  const C = [
    [t("Actual", "Current"), c.marcaActual, mk.actual.ret_pct, mk.actual.vol_pct, mk.actual.sharpe, mk.actual.pesos],
    [t("Mín. varianza", "Min. variance"), c.series[2], mk.min_varianza.ret_pct, mk.min_varianza.vol_pct,
     mk.min_varianza.sharpe, mk.min_varianza.pesos],
    [t("Máx. Sharpe", "Max. Sharpe"), c.marcaOptima, mk.max_sharpe.ret_pct, mk.max_sharpe.vol_pct,
     mk.max_sharpe.sharpe, mk.max_sharpe.pesos],
  ];
  if (bl && bl.ret_bl_pct != null) {
    const pesosBl = T.map((tk) => bl.pesos_bl_pct?.[tk] ?? 0);
    C.push(["Black-Litterman", c.series[4], bl.ret_bl_pct, bl.vol_bl_pct, bl.sharpe_bl, pesosBl]);
  }
  const ejes = [
    { et: t("Retorno", "Return"), mas: true, fmt: (v) => pct(v, 1) },
    { et: t("Estabilidad", "Stability"), mas: false, fmt: (v) => pct(v, 1) + t(" de volatilidad", " volatility") },
    { et: "Sharpe", mas: true, fmt: (v) => num(v, 2) },
    { et: t("Diversificación", "Diversification"), mas: true, fmt: (v) => num(v, 2) + " (1 − HHI)" },
    { et: t("Sin mover", "Unmoved"), mas: false, fmt: (v) => pct(v * 100, 0) + t(" de rotación", " turnover") },
  ];
  const series = C.map(([nombre, color, ret, vol, sh, w]) => ({
    nombre, color, vals: [ret, vol, sh, 1 - hhi(w), rota(w)] }));

  return (
    <div className="fila f2">
      <div className="panel">
        <h3>{t("Cómo se comparan", "How they compare")}</h3>
        <Radar ejes={ejes} series={series} />
        <div className="pie">
          {t(`Cada eje va de la peor a la mejor de las cuatro, no en escala absoluta: sirve para `
            + `ver quién gana en qué, no cuánto vale cada número. "Sin mover" es cuánto de la `
            + `cartera queda quieta — la actual siempre llega al borde, y ahí está su ventaja.`,
            `Each axis runs from the worst to the best of the four, not on an absolute scale: it's `
            + `for seeing who wins at what, not how much each number is worth. "Unmoved" is how much `
            + `of the portfolio stays put — the current one always reaches the edge, and that's its edge.`)}
        </div>
      </div>
      <div className="panel">
        <h3>{t("Los números detrás", "The numbers behind it")}</h3>
        <div className="tabla-wrap"><table>
          <thead><tr><th>{t("Cartera", "Portfolio")}</th><th className="n">{t("Retorno", "Return")}</th>
            <th className="n">{t("Volatilidad", "Volatility")}</th>
            <th className="n">Sharpe</th><th className="n">{t("Diversif.", "Diversif.")}</th>
            <th className="n">{t("Rotación", "Turnover")}</th></tr></thead>
          <tbody>{C.map(([nombre, color, ret, vol, sh, w]) => (
            <tr key={nombre}>
              <td><span style={{ display: "inline-block", width: 9, height: 9, borderRadius: 2,
                                 background: color, marginRight: 7 }} />{nombre}</td>
              <td className={"n " + signo(ret)}>{pct(ret, 1)}</td>
              <td className="n">{pct(vol, 1)}</td>
              <td className="n">{num(sh, 3)}</td>
              <td className="n">{num(1 - hhi(w), 2)}</td>
              <td className="n">{pct(rota(w) * 100, 0)}</td>
            </tr>))}</tbody>
        </table></div>
        <div className="pie">
          {t(`Diversificación es 1 − HHI: 0 sería todo en un solo papel. Rotación es cuánto de la `
            + `cartera hay que dar vuelta para llegar a esa mezcla, y es el precio de entrada de `
            + `cada una de las tres alternativas.`,
            `Diversification is 1 − HHI: 0 would mean everything in a single stock. Turnover is how much `
            + `of the portfolio you have to flip to reach that mix, and it's the entry price of `
            + `each of the three alternatives.`)}
        </div>
      </div>
    </div>
  );
}

const MESES_CORTOS = ["ene", "feb", "mar", "abr", "may", "jun",
                      "jul", "ago", "sep", "oct", "nov", "dic"];

/* Marcas de tiempo para las curvas: la posición relativa de cada inicio de
   trimestre, semestre o año que haya en la serie. Van fuera del SVG porque los
   tres gráficos se estiran con preserveAspectRatio="none" y el texto adentro
   saldría deformado; adentro solo van las líneas, con vector-effect para que el
   trazo no engorde con la escala. */
function marcasTiempo(fechas, cada = 3, tope = 11) {
  if (!fechas?.length) return [];
  const armar = (paso) => {
    const out = [];
    let previa = null;
    fechas.forEach((f, i) => {
      const d = new Date(f + "T00:00:00");
      if (d.getMonth() % paso !== 0) return;
      const clave = `${d.getFullYear()}-${d.getMonth()}`;
      if (clave === previa) return;
      previa = clave;
      out.push({ pos: i / Math.max(1, fechas.length - 1),
                 et: paso >= 12 ? String(d.getFullYear())
                                : `${MESES_CORTOS[d.getMonth()]} ${String(d.getFullYear()).slice(2)}` });
    });
    return out;
  };
  // Si el período es largo, el paso se agranda solo antes que amontonar rótulos.
  for (const paso of [cada, cada * 2, 12]) {
    const m = armar(paso);
    if (m.length <= tope) return m;
  }
  return armar(12);
}

/* PNL-16 · el valor de la cartera con su curva, en lugar del KPI suelto. */
function ValorCartera({ ev, mep }) {
  const c = colores();
  const v = ev.valor_usd || [];
  const puesto = ev.puesto_serie || [];
  const W = 300, H = 74;
  // La escala abraza las dos series: si el capital se sale del cuadro, el cruce
  // se dibuja donde no está.
  const todos = puesto.length === v.length ? v.concat(puesto) : v;
  const mn = Math.min(...todos), mx = Math.max(...todos), rango = mx - mn || 1;
  const y = (x) => H - 8 - ((x - mn) / rango) * (H - 22);
  const px = (i) => (i / Math.max(1, v.length - 1)) * W;
  const camino = (arr) => arr.map((x, i) => (i ? "L" : "M") +
    px(i).toFixed(1) + "," + y(x).toFixed(1)).join(" ");
  const d = camino(v);
  const dCap = puesto.length === v.length ? camino(puesto) : null;
  const mesAtras = v[Math.max(0, v.length - 22)];
  const cambio = mesAtras ? (v[v.length - 1] / mesAtras - 1) * 100 : 0;
  const bajoAgua = dCap && v[v.length - 1] < puesto[puesto.length - 1];
  const marcas = marcasTiempo(ev.fechas, 3);

  return (
    <div className="panel lab-valor">
      <h3>{t("Valor de cartera", "Portfolio value")}</h3>
      <div className="cifra">{usd(ev.valor_hoy_usd)}</div>
      <div className="pie" style={{ marginTop: 6 }}>
        <span className={signo(cambio)}>{cambio >= 0 ? "▲" : "▼"} {pct(Math.abs(cambio), 1)}</span>
        {" "}{t("en el último mes", "over the last month")}{MERCADOS[MERCADO].locales && mep ? ` · MEP $${mep}` : ""}
        {dCap && <> · {t(bajoAgua ? "por debajo de" : "por encima de", bajoAgua ? "below" : "above")} {t("los", "the")}{" "}
          {usd(ev.puesto_neto_usd)} {t("puestos", "put in")}</>}
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
        <defs>
          <linearGradient id="labvg" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor={c.acento} stopOpacity=".30" />
            <stop offset="1" stopColor={c.acento} stopOpacity="0" /></linearGradient>
          {dCap && (<>
            {/* Recortes contra la línea del capital: un umbral que se mueve no
                se puede resolver con un degradé horizontal. */}
            <clipPath id="labSobre"><path d={`${dCap} L${W},0 L0,0 Z`} /></clipPath>
            <clipPath id="labBajo"><path d={`${dCap} L${W},${H} L0,${H} Z`} /></clipPath>
            <linearGradient id="labvr" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor={c.negativo} stopOpacity=".34" />
              <stop offset="1" stopColor={c.negativo} stopOpacity=".05" /></linearGradient>
          </>)}
        </defs>
        <g className="ejeT">
          {marcas.map((m) => (
            <line key={m.et} x1={m.pos * W} y1="0" x2={m.pos * W} y2={H} />))}
        </g>
        {dCap ? (<>
          <path d={`${d} L${W},${H} L0,${H} Z`} fill="url(#labvg)" clipPath="url(#labSobre)" />
          <path d={`${d} L${W},0 L0,0 Z`} fill="url(#labvr)" clipPath="url(#labBajo)" />
          <path className="cap" d={dCap} />
          <path d={d} fill="none" stroke={c.acento} strokeWidth="2" strokeLinejoin="round"
                clipPath="url(#labSobre)" />
          <path d={d} fill="none" stroke={c.negativo} strokeWidth="2" strokeLinejoin="round"
                clipPath="url(#labBajo)" />
        </>) : (<>
          <path d={`${d} L${W},${H} L0,${H} Z`} fill="url(#labvg)" />
          <path d={d} fill="none" stroke={c.acento} strokeWidth="2" strokeLinejoin="round" />
        </>)}
      </svg>
      <div className="lab-ejeT">
        {marcas.map((m) => (
          <span key={m.et} style={{ left: `${(m.pos * 100).toFixed(2)}%` }}>{m.et}</span>))}
      </div>
    </div>
  );
}

/* PRG-07 · un nodo por modelo, encendido cuando ese modelo terminó. Con once
   pasos no entran once etiquetas: el nombre va en el nodo, al pasar el mouse, y
   abajo queda el que está corriendo, que es lo único que uno mira mientras espera. */
function PasosModelos({ M, listos }) {
  // Corren en paralelo, no en fila: si los nodos quedaran en su orden fijo, la
  // línea de avance marcaría 6 y habría encendidos más allá. Ordenados por
  // estado, lo lleno y lo vacío coinciden con la cuenta.
  const orden = { listo: 0, error: 1, corriendo: 2 };
  const claves = Object.keys(M).sort((a, b) =>
    (orden[M[a].estado] ?? 3) - (orden[M[b].estado] ?? 3));
  const corriendo = claves.filter((k) => M[k].estado === "corriendo").map((k) => M[k].nombre);
  const fallados = claves.filter((k) => M[k].estado === "error").length;
  return (
    <div className="lab-pasos">
      <div className="via">
        <div className="hecho" style={{ width: (listos / claves.length) * 100 + "%" }} />
        <div className="nodos">
          {claves.map((k) => (
            <span key={k} className={"n " + (M[k].estado === "listo" ? "on"
              : M[k].estado === "error" ? "mal" : "")} title={`${M[k].nombre} · ${M[k].estado}`} />))}
        </div>
      </div>
      <div className="pies">
        <span><b>{listos}</b> {t("de", "of")} {claves.length} {t("modelos listos", "models ready")}
          {fallados > 0 && ` · ${fallados} ${t("con error", "with an error")}`}</span>
        <span>{corriendo.length ? t("Calculando ", "Calculating ") + corriendo.join(", ") + "…"
                                : t("Cada panel aparece apenas termina.", "Each panel appears as soon as it's done.")}</span>
      </div>
    </div>
  );
}

/* PNL-05 · la tasa anual de los últimos doce meses y cómo llegó hasta ahí.
   Va en su propia tarjeta: mezclada con el resultado acumulado eran dos curvas
   en distinta unidad compitiendo por la misma mirada. */
function TirVentana({ ev }) {
  const c = colores();
  const v = ev.ultimos_12m;
  if (!v || v.tir_pct == null) return null;
  const serie = (v.serie || []).map((p) => p.tir_pct);
  const W = 600, H = 86, pad = 10;
  const mn = Math.min(...serie, 0), mx = Math.max(...serie, 0), rango = (mx - mn) || 1;
  const y = (t) => H - pad - ((t - mn) / rango) * (H - pad * 2);
  const px_ = (i) => (i / Math.max(1, serie.length - 1)) * W;
  const linea = serie.map((t, i) => (i ? "L" : "M") + px_(i).toFixed(1) + "," + y(t).toFixed(1)).join(" ");
  const color = v.tir_pct >= 0 ? c.positivo : c.negativo;
  const marcas = marcasTiempo((v.serie || []).map((p) => p.fecha), 3);

  return (
    <div className="panel">
      <h3>{t("Rendimiento anual · TIR", "Annual return · IRR")}
        <span className="pie" style={{ margin: 0, marginLeft: "auto" }}>
          {v.completa ? t(`toda la historia entra en la ventana, desde el ${v.desde}`,
                          `the whole history fits in the window, since ${v.desde}`)
                      : t(`ventana móvil de 12 meses, desde el ${v.desde}`,
                          `12-month rolling window, since ${v.desde}`)}</span>
      </h3>
      <div className="lab-tirgrande">
        <b className={signo(v.tir_pct)}>{pct(v.tir_pct)}</b>
        <span>{t("anual, comparable contra un plazo fijo o una letra", "annual, comparable against a term deposit or a T-bill")}</span>
      </div>
      <div className="pie" style={{ marginTop: 6 }}>
        {t(`Arrancó valiendo ${usd(v.valor_inicial_usd)}`, `Started worth ${usd(v.valor_inicial_usd)}`)}
        {v.aportado_usd > 0 && t(` · pusiste ${usd(v.aportado_usd)}`, ` · you added ${usd(v.aportado_usd)}`)}
        {v.retirado_usd > 0 && t(` · sacaste ${usd(v.retirado_usd)}`, ` · you withdrew ${usd(v.retirado_usd)}`)}
        {v.dividendos_usd > 0 && t(` · cobraste ${usd(v.dividendos_usd)} de dividendos`, ` · you collected ${usd(v.dividendos_usd)} in dividends`)}
        {t(" · hoy vale ", " · today it's worth ")}{usd(ev.valor_hoy_usd)}
      </div>
      {serie.length > 1 && (
        <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="lab-tirserie">
          <g className="ejeT">
            {marcas.map((m) => (
              <line key={m.et} x1={m.pos * W} y1="0" x2={m.pos * W} y2={H} />))}
          </g>
          <line x1="0" y1={y(0)} x2={W} y2={y(0)} />
          <path d={linea} style={{ stroke: color }} />
        </svg>)}
      {serie.length > 1 && (<>
        <div className="lab-ejeT" style={{ position: "relative", height: 15, marginTop: 3 }}>
          {marcas.map((m) => (
            <span key={m.et} style={{ left: `${(m.pos * 100).toFixed(2)}%` }}>{m.et}</span>))}
        </div>
        <div className="lab-tirejes">
          <span>{t("arranca en", "starts at")} {pct(serie[0], 1)}</span>
          <span>{t("máx", "max")} {pct(mx, 1)} · {t("mín", "min")} {pct(mn, 1)}</span>
          <span>{t("hoy", "today")} · {pct(v.tir_pct, 1)}</span>
        </div></>)}
      {ev.tir_anual_pct != null && !v.completa && (
        <div className="pie">
          {t(`Desde la primera compra, ${num(ev.anos, 1)} años atrás, la misma cuenta da`,
             `Since the first purchase, ${num(ev.anos, 1)} years ago, the same math gives`)}{" "}
          <b className={signo(ev.tir_anual_pct)}>{pct(ev.tir_anual_pct)} {t("anual", "annual")}</b>.
        </div>)}
      <div className="pie">
        {t(`Toma lo que la cartera valía hace doce meses como punto de partida, suma lo que `
          + `entró, resta lo que salió y cierra con lo que vale hoy: las posiciones abiertas a `
          + `precio de mercado, lo que dejaron las que cerraste dentro del período y los `
          + `dividendos cobrados. Se mueve todos los días — si mañana sube un papel pesado, el no `
          + `realizado cambia y la tasa con él. La curva es esa misma tasa calculada parada en `
          + `cada semana del último año, así que dice si venís mejorando o desmejorando.`,
          `It takes what the portfolio was worth twelve months ago as a starting point, adds what `
          + `came in, subtracts what went out and closes with what it's worth today: open positions at `
          + `market price, what the ones you closed within the period left behind, and `
          + `dividends collected. It moves every day — if a heavy stock rises tomorrow, the unrealized `
          + `part changes and the rate with it. The curve is that same rate calculated as of `
          + `each week of the last year, so it tells you if you've been improving or not.`)}
      </div>
    </div>
  );
}

/* DAT-03 · una fila por ticker, una columna por rueda. */
function RuedasTicker({ ev }) {
  const [abierto, setAbierto] = useState(true);
  const c = colores();
  if (!ev || ev.error || !ev.ruedas?.tickers?.length) return null;
  const { fechas, tickers } = ev.ruedas;
  const cols = { gridTemplateColumns: `repeat(${fechas.length},1fr)` };
  // Satura en ±3 %: más allá, todos los días extremos se ven igual y el mapa
  // deja de distinguir un día feo de uno histórico.
  const tono = (v) => {
    if (Math.abs(v) < 0.05) return "var(--panel-2)";
    const m = 18 + Math.min(1, Math.abs(v) / 3) * 82;
    return `color-mix(in srgb, ${v > 0 ? c.positivo : c.negativo} ${m.toFixed(0)}%, var(--panel-2))`;
  };
  return (
    <div className="panel">
      <h3>{t(`Las últimas ${fechas.length} ruedas, ticker por ticker`,
             `The last ${fechas.length} sessions, ticker by ticker`)}
        <button className="btn" style={{ marginLeft: "auto" }}
                onClick={() => setAbierto((x) => !x)}>
          {abierto ? t("Ocultar", "Hide") : t("Mostrar", "Show")}</button>
      </h3>
      {abierto && (<>
        <div className="lab-ruedas">
          {tickers.map((t) => (
            <React.Fragment key={t.ticker}>
              <span className="tk mono">{t.ticker}</span>
              <div className="dias" style={cols}>
                {t.var_pct.map((v, i) => (
                  <i key={i} style={{ background: tono(v) }}
                     title={`${t.ticker} · ${fechas[i]} · ${pct(v)}`} />))}
              </div>
              <span className={"acum mono " + signo(t.acum_pct)}>{pct(t.acum_pct, 1)}</span>
            </React.Fragment>))}
          <span />
          <div className="eje" style={cols}>
            {fechas.map((f, i) => (
              <span key={f}>{i % 5 === 0 ? f.slice(8) + "/" + f.slice(5, 7) : ""}</span>))}
          </div>
          <span />
        </div>
        <div className="lab-escala">−3 %
          <i style={{ background: tono(-3) }} /><i style={{ background: tono(-1.2) }} />
          <i style={{ background: "var(--panel-2)" }} />
          <i style={{ background: tono(1.2) }} /><i style={{ background: tono(3) }} />
          +3 %
          <span style={{ marginLeft: "auto" }}>
            {t(`Última columna: acumulado de las ${fechas.length} ruedas.`,
               `Last column: cumulative over the last ${fechas.length} sessions.`)}
          </span>
        </div>
      </>)}
    </div>
  );
}

/* ── Composición ── */
function Composicion({ d, cartera }) {
  const c = colores();
  // La TIR es propia de renta fija, no del resto de los cortes de arriba —
  // por eso se pide aparte. `/api/tir` ya combina el catálogo propio
  // (exacto, calcado del flujo de fondos real) con bonistas.com como
  // respaldo para lo que ese catálogo no tiene.
  const [tirs, setTirs] = useState(null);
  useEffect(() => {
    setTirs(null);
    api(`/api/tir/${encodeURIComponent(cartera)}`).then((r) => { if (!r.error) setTirs(r); });
  }, [cartera]);
  const dona = (items, titulo) => ({
    datos: [{ type: "pie", hole: 0.5, labels: items.map((x) => x.etiqueta),
              values: items.map((x) => x.pct), textinfo: "label+percent",
              textposition: "outside", automargin: true, textfont: { size: 10 },
              marker: { colors: c.series },
              hovertemplate: "%{label}: %{value:.1f} %<extra></extra>" }],
    layout: { showlegend: false, margin: { t: 8, r: 8, b: 8, l: 8 } }, titulo,
  });
  const cortes = [["por_tipo", t("Por tipo de activo", "By asset type")], ["por_sector", t("Por sector", "By sector")],
                  ["por_industria", t("Por industria", "By industry")]];

  // El alto no puede ser fijo: cada industria es una fila de 30 px como mínimo,
  // y una cartera con doce se salía del panel y se escribía encima del pie.
  // Manda el corte más largo —la industria— y los tres paneles lo siguen, así
  // la fila queda pareja en vez de tres cuadros de alturas distintas.
  const industrias = new Set((d.detalle || []).filter((x) => x.valor_usd)
    .map((x) => x.industria || t("Sin dato", "No data"))).size;
  const alto = Math.max(300, 34 * industrias);
  return (
    <>
      <div className="fila f3">
        {cortes.map(([k, titulo]) => {
          // El corte por sector pasa a treemap: la dona dice cuánto pesa cada
          // sector, pero no qué papel lo trae.
          // La industria es el corte con más categorías: en dona son seis
          // porciones finitas con las etiquetas peleándose el borde.
          if (k === "por_industria") return (
            <div className="panel" key={k}>
              <h3>{titulo}</h3>
              <TreemapSectores detalle={d.detalle} campo="industria" alto={alto} />
            </div>);
          const g = dona(d[k] || [], titulo);
          return (
            <div className="panel" key={k}>
              <h3>{titulo}</h3>
              <Grafico datos={g.datos} layout={g.layout} alto={alto} />
            </div>
          );
        })}
      </div>
      <Plegable id={`detalle-activo-${cartera}`} titulo={t("Detalle por activo", "Detail by asset")}>
        <div className="tabla-wrap"><table>
          <thead><tr><th>Ticker</th><th>{t("Nombre", "Name")}</th><th>{t("Tipo", "Type")}</th>
                     <th>{t("Sector", "Sector")}</th>
                     <th>{t("Industria", "Industry")}</th><th className="n">TIR</th>
                     <th className="n">{t("Valor", "Value")}</th></tr></thead>
          <tbody>{(d.detalle || []).map((x) => (
            <tr key={x.ticker}>
              <td className="mono">{x.ticker}</td><td>{x.nombre || "—"}</td>
              <td>{x.tipo}</td><td>{x.sector}</td><td>{x.industria}</td>
              <td className="n">{tirs?.[x.ticker] != null ? pct(tirs[x.ticker], 1) : "—"}</td>
              <td className="n">{usd(x.valor_usd)}</td>
            </tr>))}</tbody>
        </table></div>
        <div className="pie">
          {t(`Un ETF no tiene sector: es una canasta, no una empresa. En esos casos se muestra `
            + `la categoría del fondo, que es el dato equivalente. La`,
            `An ETF has no sector: it's a basket, not a company. In those cases the fund's `
            + `category is shown, which is the equivalent data point. The`)} <b>TIR</b>{" "}
          {t(`solo sale para renta fija — el resto de los activos queda en «—». Sale del flujo de `
            + `fondos propio cuando el bono está en el catálogo interno, y de bonistas.com (24hs) `
            + `cuando no — las dos son tasas de mercado, nominales.`,
            `only comes out for fixed income — the rest of the assets show «—». It comes from the `
            + `app's own cash-flow model when the bond is in the internal catalog, and from `
            + `bonistas.com (24hs) when it isn't — both are nominal market rates.`)}
        </div>
      </Plegable>
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
      <ZonasRiesgo d={d} />
      <Seccion titulo={t("¿Cuándo se disparó el riesgo?", "When did risk spike?")} />
      <RiesgoEvolucion cartera={cartera} />
      <Seccion titulo={t("El riesgo de cada activo por separado", "The risk of each asset, separately")} />
      <RiesgoActivos cartera={cartera} />
      <Seccion titulo={t("Quién trae el riesgo de la cartera", "Who brings the portfolio's risk")} />
      <RiesgoResumen d={d} />
      <Seccion titulo={t("¿Cuánto del riesgo es el dólar?", "How much of the risk is the exchange rate?")} />
      <RiesgoCambiario cartera={cartera} />
      <Seccion titulo={t("Qué habría pasado en crisis reales", "What would have happened in real crises")} />
      {extras.stress ? <Stress d={extras.stress} /> : <div className="cargando">{t("Calculando…", "Calculating…")}</div>}
      <Seccion titulo={t("Ponerle un techo al riesgo", "Putting a ceiling on risk")} />
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
      <Kpi etiqueta={t("Volatilidad", "Volatility")} valor={pct(d.volatilidad_anual_pct)} ayuda={AYUDA.vol} />
      <Kpi etiqueta={t("Día malo", "Bad day")} valor={usd(d.var95_usd)} tono="neg" ayuda={AYUDA.var95}
           sub={pct(d.var95_pct) + t(" · 1 de cada 20", " · 1 in 20")} />
      <Kpi etiqueta={t("Día muy malo", "Very bad day")} valor={usd(d.cvar95_usd)} tono="neg" ayuda={AYUDA.cvar}
           sub={pct(d.cvar95_pct)} />
      <Kpi etiqueta={t("Peor caída", "Worst drawdown")} valor={pct(d.max_drawdown_pct)} tono="neg" ayuda={AYUDA.maxdd} />
      <Kpi etiqueta={t("Curtosis", "Kurtosis")} valor={num(d.curtosis_exceso)} ayuda={AYUDA.curtosis}
           tono={d.curtosis_exceso > 3 ? "neg" : ""} sub={t("en exceso", "excess")} />
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
          <h3>{t("Peso contra aporte al riesgo", "Weight against risk contribution")}</h3>
          <Grafico alto={Math.max(230, contrib.length * 40 + 110)}
            datos={[
              { type: "bar", orientation: "h", name: t("aporte al riesgo", "risk contribution"),
                y: contrib.map((x) => x.ticker).reverse(),
                x: contrib.map((x) => x.riesgo_pct).reverse(), marker: { color: c.negativo },
                hovertemplate: t("%{y}: %{x:.1f} % del riesgo<extra></extra>", "%{y}: %{x:.1f} % of risk<extra></extra>") },
              { type: "bar", orientation: "h", name: t("peso en la cartera", "weight in the portfolio"),
                y: contrib.map((x) => x.ticker).reverse(),
                x: contrib.map((x) => x.peso_pct).reverse(), marker: { color: c.series[2] },
                hovertemplate: t("%{y}: %{x:.1f} % de peso<extra></extra>", "%{y}: %{x:.1f} % of weight<extra></extra>") }]}
            layout={{ barmode: "group", margin: { l: 82 }, xaxis: { ticksuffix: " %" } }} />
          <div className="pie">
            {t("Las contribuciones suman exactamente la volatilidad de la cartera (identidad "
              + "de Euler). Barra roja mayor que la azul = aporta más riesgo del que su peso sugiere.",
              "The contributions add up to exactly the portfolio's volatility (Euler's identity). "
              + "Red bar bigger than the blue one = contributes more risk than its weight suggests.")}
          </div>
        </div>
        <div className="panel">
          <h3>{t("Cuánto esconde suponer normalidad", "How much assuming normality hides")}</h3>
          <div className="tabla-wrap"><table>
            <thead><tr><th>{t("Método", "Method")}</th><th className="n">{t("Un día malo", "A bad day")}</th>
              <th className="n">{t("En dólares", "In dollars")}</th></tr></thead>
            <tbody>
              <tr><td>{t("Histórico (95 %)", "Historical (95 %)")}</td><td className="n">{pct(d.var95_pct)}</td><td className="n neg">{usd(d.var95_usd)}</td></tr>
              <tr><td>Cornish-Fisher (95 %)</td><td className="n">{pct(d.var95_cornish_fisher_pct)}</td><td className="n neg">{usd(d.var95_cornish_fisher_usd)}</td></tr>
              <tr><td>{t("Histórico (99 %)", "Historical (99 %)")}</td><td className="n">{pct(d.var99_pct)}</td><td className="n neg">{usd(d.var99_usd)}</td></tr>
            </tbody>
          </table></div>
          <div className="pie">
            {t("Cornish-Fisher ajusta el cuantil por la asimetría y las colas gordas reales. "
              + "La diferencia con el histórico es cuánto riesgo queda oculto.",
              "Cornish-Fisher adjusts the quantile for real skewness and fat tails. "
              + "The difference from the historical figure is how much risk stays hidden.")}
          </div>
        </div>
      </div>
      {desbalance.length > 0 && (
        <div className="aviso ojo"><b>{t("Riesgo concentrado.", "Concentrated risk.")}</b>{" "}
          {desbalance.map((x) => t(`${x.ticker} pesa ${x.peso_pct} % y aporta ${x.riesgo_pct} % del riesgo`,
                                   `${x.ticker} weighs ${x.peso_pct} % and contributes ${x.riesgo_pct} % of the risk`)).join(" · ")}.
        </div>)}
    </>
  );
}

function RiesgoActivos({ cartera }) {
  const c = colores();
  const [d, setD] = useState(null);
  const [sel, setSel] = useState("__todos__");
  useEffect(() => { setD(null); api(`/api/riesgo/${encodeURIComponent(cartera)}/por-activo`).then(setD); }, [cartera]);
  if (!d) return <div className="cargando">{t("Midiendo el riesgo de cada activo…", "Measuring each asset's risk…")}</div>;
  if (d.error) return <div className="aviso mal">{d.error}</div>;

  const todos = [...d.por_activo, d.cartera];
  const serie = sel === "__todos__" ? d.serie_cartera : (d.series[sel] || []);
  const foco = sel === "__todos__" ? d.cartera : d.por_activo.find((x) => x.ticker === sel);

  return (
    <>
      <div className="panel" style={{ marginBottom: 14 }}>
        <h3>{t("Riesgo de cada activo por separado", "The risk of each asset, separately")}</h3>
        <div className="tabla-wrap"><table>
          <thead><tr><th>{t("Activo", "Asset")}</th><th className="n">{t("Peso", "Weight")}</th>
            <th className="n">{t("Retorno anual", "Annual return")}</th>
            <th className="n">{t("Volatilidad", "Volatility")}</th>
            <th className="n">{t("Día malo", "Bad day")}</th><th className="n">{t("Día muy malo", "Very bad day")}</th>
            <th className="n">{t("1 de 100", "1 in 100")}</th><th className="n">{t("Peor caída", "Worst drawdown")}</th>
            <th className="n">Sharpe</th></tr></thead>
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
          <b>{t(`Diversificar ahorra ${pct(d.beneficio_diversificacion_pct, 1)} de volatilidad.`,
                `Diversifying saves ${pct(d.beneficio_diversificacion_pct, 1)} of volatility.`)}</b>{" "}
          {t(`El activo más riesgoso cae hasta ${pct(d.por_activo[0]?.max_drawdown_pct, 1)} por su cuenta, `
            + `pero la cartera entera solo ${pct(d.cartera.max_drawdown_pct, 1)}: eso es lo que aporta `
            + `combinarlos. Ventana común: ${d.ventana.desde} → ${d.ventana.hasta}.`,
            `The riskiest asset drops as much as ${pct(d.por_activo[0]?.max_drawdown_pct, 1)} on its own, `
            + `but the whole portfolio only ${pct(d.cartera.max_drawdown_pct, 1)}: that's what combining `
            + `them contributes. Common window: ${d.ventana.desde} → ${d.ventana.hasta}.`)}
        </div>
      </div>

      <div className="panel">
        <h3>{t("Cómo se comportan los días", "How days behave")}
          <select value={sel} onChange={(e) => setSel(e.target.value)} style={{ marginLeft: "auto" }}>
            <option value="__todos__">{t("Cartera completa", "Whole portfolio")}</option>
            {d.por_activo.map((x) => <option key={x.ticker} value={x.ticker}>{x.ticker}</option>)}
          </select>
        </h3>
        <Grafico alto={300}
          datos={[{ type: "bar", x: serie.map((p) => p.fecha), y: serie.map((p) => p.ret),
                    marker: { color: serie.map((p) => p.ret >= 0 ? c.positivo : c.negativo) },
                    hovertemplate: "%{x}: %{y:.2f} %<extra></extra>" }]}
          layout={{ yaxis: { title: t("Retorno diario", "Daily return"), ticksuffix: " %" },
                    shapes: foco ? [{ type: "line", xref: "paper", x0: 0, x1: 1,
                      y0: foco.var95_pct, y1: foco.var95_pct,
                      line: { color: c.alerta, width: 1.5, dash: "dash" } }] : [] }} />
        <div className="pie">
          {t(`Cada barra es una rueda, acotado a la ventana de la cartera. La línea punteada es `
            + `el umbral del día malo (${pct(foco?.var95_pct)}): todo lo que la cruza es ese 5 % peor.`,
            `Each bar is a session, bounded to the portfolio's window. The dashed line is `
            + `the bad-day threshold (${pct(foco?.var95_pct)}): anything crossing it is that worst 5 %.`)}
        </div>
      </div>
    </>
  );
}

function RiesgoEvolucion({ cartera }) {
  const c = colores();
  const [d, setD] = useState(null);
  useEffect(() => { setD(null); api(`/api/riesgo/${encodeURIComponent(cartera)}/rolling`).then(setD); }, [cartera]);
  if (!d) return <div className="cargando">{t("Calculando la ventana móvil…", "Calculating the rolling window…")}</div>;
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
        <h3>{t("Pérdida en un día malo, a lo largo del tiempo", "Loss on a bad day, over time")}</h3>
        <Grafico alto={400}
          datos={[
            { type: "scatter", mode: "lines", name: t("día malo (VaR 95 %)", "bad day (VaR 95 %)"),
              x: d.serie.map((p) => p.fecha), y: d.serie.map((p) => p.var95_pct),
              line: { color: c.negativo, width: 1.9 },
              hovertemplate: "%{x}<br>%{y:.2f} %<extra></extra>" },
            { type: "scatter", mode: "lines", name: t("día muy malo (CVaR 95 %)", "very bad day (CVaR 95 %)"),
              x: d.serie.map((p) => p.fecha), y: d.serie.map((p) => p.cvar95_pct),
              line: { color: c.alerta, width: 1.2, dash: "dot" },
              hovertemplate: "%{x}<br>%{y:.2f} %<extra></extra>" },
            { type: "scatter", mode: "markers", name: t("eventos argentinos", "Argentine events"),
              x: ev.filter((e) => e.alcance === "AR").map((e) => e.fecha),
              y: ev.filter((e) => e.alcance === "AR").map((e) => cercano(e.fecha)),
              marker: { symbol: "diamond", size: 11, color: c.series[3],
                        line: { width: 1.2, color: c.panel } },
              text: ev.filter((e) => e.alcance === "AR").map((e) => eventoDescripcion(e.descripcion)),
              hovertemplate: "<b>%{x}</b><br>%{text}<extra></extra>" },
            { type: "scatter", mode: "markers", name: t("eventos mundiales", "global events"),
              x: ev.filter((e) => e.alcance !== "AR").map((e) => e.fecha),
              y: ev.filter((e) => e.alcance !== "AR").map((e) => cercano(e.fecha)),
              marker: { symbol: "circle", size: 10, color: c.series[4],
                        line: { width: 1.2, color: c.panel } },
              text: ev.filter((e) => e.alcance !== "AR").map((e) => eventoDescripcion(e.descripcion)),
              hovertemplate: "<b>%{x}</b><br>%{text}<extra></extra>" },
          ]}
          layout={{
            shapes: ev.map((e) => ({ type: "line", x0: e.fecha, x1: e.fecha, yref: "paper",
              y0: 0, y1: 1, line: { color: e.alcance === "AR" ? c.series[3] : c.series[4],
                                    width: 1, dash: "dot" }, opacity: 0.5 })),
            yaxis: { title: t("Pérdida diaria", "Daily loss"), ticksuffix: " %" } }} />
        <div className="pie">
          {t(`VaR 95 % sobre las últimas ${d.ventana_ruedas} ruedas en cada punto: cuando la línea `
            + `baja, la cartera se volvió más riesgosa. Los`,
            `VaR 95 % over the last ${d.ventana_ruedas} sessions at each point: when the line `
            + `drops, the portfolio became riskier. The`)} <b>{t("rombos", "diamonds")}</b>{" "}
          {t("son eventos argentinos y los", "are Argentine events and the")} <b>{t("círculos", "circles")}</b>,
          {" "}{t("mundiales — apuntalos con el mouse para leer qué pasó. Son contexto, no causa.",
                 "global — hover them with the mouse to read what happened. They're context, not cause.")}
        </div>
      </div>
      <div className="panel">
        <h3>{t(`Los ${ev.length} eventos del período`, `The ${ev.length} events in the period`)}</h3>
        <div className="tabla-wrap"><table>
          <thead><tr><th>{t("Fecha", "Date")}</th><th className="c">{t("Alcance", "Scope")}</th>
            <th>{t("Qué pasó", "What happened")}</th>
            <th className="n">{t("Día malo por entonces", "Bad day back then")}</th></tr></thead>
          <tbody>{ev.slice().reverse().map((e, i) => (
            <tr key={i}><td className="mono">{e.fecha}</td>
              <td><span className="chip">{alcanceLabel(e.alcance)}</span></td><td>{eventoDescripcion(e.descripcion)}</td>
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
  if (!d) return <div className="cargando">{t("Separando el riesgo del activo del riesgo del dólar…",
                                              "Splitting asset risk from exchange-rate risk…")}</div>;
  if (d.error) return <div className="aviso mal">{d.error}</div>;
  const enPesos = d.por_activo.filter((x) => x.moneda === "ARS");
  return (
    <>
      <div className="kpis">
        <Kpi etiqueta={t("Riesgo del tipo de cambio", "Exchange-rate risk")} valor={pct(d.fx_pct, 1)}
             tono={d.fx_pct > 50 ? "neg" : ""}
             ayuda={{ que: [t("Riesgo cambiario", "Exchange-rate risk"), t("Riesgo cambiario", "Exchange-rate risk")],
                      como: [t("De todo lo que hace oscilar tu cartera medida en dólares, cuánto viene del movimiento del MEP y no de los activos.",
                               "Of everything that makes your portfolio swing measured in dollars, how much comes from the MEP rate's movement and not from the assets."),
                             t("De todo lo que hace oscilar tu cartera medida en dólares, cuánto viene del movimiento del MEP y no de los activos.",
                               "Of everything that makes your portfolio swing measured in dollars, how much comes from the MEP rate's movement and not from the assets.")],
                      umbral: [t("Arriba del 50 % estás apostando más al dólar que a las empresas.",
                                 "Above 50 % you're betting more on the exchange rate than on the companies."),
                               t("Arriba del 50 % estás apostando más al dólar que a las empresas.",
                                 "Above 50 % you're betting more on the exchange rate than on the companies.")] }} />
        <Kpi etiqueta={t("Riesgo de los activos", "Asset risk")} valor={pct(d.activo_pct, 1)} />
        <Kpi etiqueta={t("Expuesto al peso", "Exposed to the peso")} valor={pct(d.pct_expuesto_al_peso, 1)}
             sub={`${usd(d.valor_en_pesos)} ${t("de", "of")} ${usd(d.valor_en_pesos + d.valor_en_dolares)}`} />
      </div>
      {enPesos.length > 0 && (
        <div className="panel">
          <h3>{t("De dónde viene el riesgo de cada activo en pesos", "Where each peso-denominated asset's risk comes from")}</h3>
          <Grafico alto={Math.max(210, enPesos.length * 40 + 110)}
            datos={[
              { type: "bar", orientation: "h", name: t("el activo", "the asset"),
                y: enPesos.map((x) => x.ticker).reverse(), x: enPesos.map((x) => x.activo_pct).reverse(),
                marker: { color: c.series[2] } },
              { type: "bar", orientation: "h", name: t("el dólar", "the exchange rate"),
                y: enPesos.map((x) => x.ticker).reverse(), x: enPesos.map((x) => x.fx_pct).reverse(),
                marker: { color: c.alerta } }]}
            layout={{ barmode: "stack", margin: { l: 82 }, xaxis: { ticksuffix: " %" } }} />
          <div className="pie">{libre(d.nota)}</div>
        </div>
      )}
      <div className="panel">
        <h3>{t("Detalle", "Detail")}</h3>
        <div className="tabla-wrap"><table>
          <thead><tr><th>{t("Activo", "Asset")}</th><th>{t("Moneda", "Currency")}</th>
            <th className="n">{t("Valor", "Value")}</th>
            <th className="n">{t("Del activo", "From the asset")}</th>
            <th className="n">{t("Del dólar", "From the exchange rate")}</th>
            <th className="n">{t("Correlación con el MEP", "Correlation with the MEP rate")}</th></tr></thead>
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

  // dec(): `pedido` viaja en la URL y el servidor espera un número con punto.
  const calcular = () => { const v = dec(objetivo); if (v) setPedido(v); };

  const ordenes = (r?.ordenes || []).filter((o) => o.accion !== "MANTENER");

  return (
    <>
      <div className="panel">
        <h3>{t("¿Qué tendría que comprar y vender para no pasar de cierto riesgo?",
               "What would need to be bought and sold to not exceed a certain risk?")}</h3>
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginTop: 10 }}>
          <span>{t("No quiero perder más de", "I don't want to lose more than")}</span>
          <input type="text" inputMode="decimal" value={objetivo}
                 onChange={(e) => setObjetivo(soloNum(e.target.value))} style={{ width: 90 }}
                 onKeyDown={(e) => e.key === "Enter" && calcular()} />
          <span>{t("% en un día malo.", "% on a bad day.")}</span>
          <button className="btn primario" onClick={calcular}
                  disabled={cargando || dec(objetivo) === pedido || !dec(objetivo)}>
            {cargando ? t("Optimizando…", "Optimizing…") : t("Recalcular", "Recalculate")}</button>
          <span className="pie" style={{ marginTop: 0 }}>
            {t(`Hoy: ${pct(d.var95_pct)} (${usd(d.var95_usd)}) · abajo está resuelto `
              + `para ${pct(pedido)}, cambiá el número para probar otro techo.`,
              `Today: ${pct(d.var95_pct)} (${usd(d.var95_usd)}) · below it's solved `
              + `for ${pct(pedido)}, change the number to try another ceiling.`)}</span>
        </div>
        <div className="pie">
          {t("La cartera queda", "The portfolio stays")} <b>{t("invertida al 100 %", "100 % invested")}</b>:{" "}
          {t("se cambia la mezcla, no el nivel de exposición. Se busca el movimiento más chico "
            + "que cumple el límite, para no deshacer decisiones que ya tomaste.",
            "the mix changes, not the exposure level. It looks for the smallest move "
            + "that satisfies the limit, so it doesn't undo decisions you already made.")}
        </div>
      </div>

      {r?.error && <div className="aviso mal">{r.error}</div>}
      {r?.ya_cumple && <div className="aviso ok">{r.mensaje}</div>}
      {r && r.alcanzable === false && (
        <>
          <div className="aviso ojo"><b>{t("Ese límite no se alcanza solo rebalanceando.",
                                          "That limit can't be reached by rebalancing alone.")}</b> {r.mensaje}</div>
          <div className="panel">
            <h3>{t("La mezcla de menor riesgo posible con estos activos", "The lowest-risk mix possible with these assets")}</h3>
            <div className="tabla-wrap"><table>
              <thead><tr><th>{t("Activo", "Asset")}</th><th className="n">{t("Peso", "Weight")}</th></tr></thead>
              <tbody>{Object.entries(r.pesos_minimo_riesgo).sort((a, b) => b[1] - a[1]).map(([tk, w]) => (
                <tr key={tk}><td className="mono">{tk}</td><td className="n">{pct(w, 1)}</td></tr>))}</tbody>
            </table></div>
            <div className="pie">
              {t(`Llega a ${pct(r.var_minimo_posible_pct)} de pérdida en un día malo, contra `
                + `${pct(r.var_actual_pct)} de tu cartera actual.`,
                `It reaches ${pct(r.var_minimo_posible_pct)} of loss on a bad day, against `
                + `${pct(r.var_actual_pct)} for your current portfolio.`)}
            </div>
          </div>
        </>
      )}

      {r && r.alcanzable && !r.ya_cumple && (
        <>
          <div className="fila f2">
            <div className="panel">
              <h3>{t("Antes y después", "Before and after")}</h3>
              <div className="tabla-wrap"><table>
                <thead><tr><th></th><th className="n">{t("Hoy", "Today")}</th>
                  <th className="n">{t("Rebalanceada", "Rebalanced")}</th>
                  <th className="n">{t("Cambio", "Change")}</th></tr></thead>
                <tbody>
                  {[[t("Pérdida en un día malo", "Loss on a bad day"), "var95_pct", true],
                    [t("Volatilidad anual", "Annual volatility"), "volatilidad_pct", true],
                    [t("Retorno anual esperado", "Expected annual return"), "retorno_anual_pct", false]].map(([et, k, menosEsMejor]) => {
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
                {t(`Bajar el riesgo cuesta retorno: pasás de ${pct(r.antes.retorno_anual_pct)} a `
                  + `${pct(r.despues.retorno_anual_pct)} anual esperado. Ese es el precio del límite `
                  + `que pediste, y conviene verlo antes de operar.`,
                  `Lowering risk costs return: you go from ${pct(r.antes.retorno_anual_pct)} to `
                  + `${pct(r.despues.retorno_anual_pct)} expected annual. That's the price of the limit `
                  + `you asked for, and it's worth seeing before trading.`)}
              </div>
              <div className="pie">{libre(r.nota_metodo)}</div>
            </div>

            <div className="panel">
              <h3>{t("Cómo se mueven los pesos", "How the weights move")}</h3>
              <Grafico alto={Math.max(240, r.ordenes.length * 40 + 110)}
                datos={[
                  { type: "bar", orientation: "h", name: t("hoy", "today"),
                    y: r.ordenes.map((o) => o.ticker).reverse(),
                    x: r.ordenes.map((o) => o.peso_actual_pct).reverse(),
                    marker: { color: c.texto3 } },
                  { type: "bar", orientation: "h", name: t("rebalanceada", "rebalanced"),
                    y: r.ordenes.map((o) => o.ticker).reverse(),
                    x: r.ordenes.map((o) => o.peso_nuevo_pct).reverse(),
                    marker: { color: c.acento } }]}
                layout={{ barmode: "group", margin: { l: 82 }, xaxis: { ticksuffix: " %" } }} />
              <div className="pie">
                {t(`Rotación ${pct(r.rotacion_pct)}: hay que operar ${usd(r.a_operar_usd)} entre `
                  + `compras y ventas sobre una cartera de ${usd(r.valor_total)}.`,
                  `Turnover ${pct(r.rotacion_pct)}: you need to trade ${usd(r.a_operar_usd)} between `
                  + `buys and sells on a portfolio worth ${usd(r.valor_total)}.`)}
              </div>
            </div>
          </div>

          {(
            <div className="panel">
              <h3>{t("Cuánto se corre cada peso", "How much each weight moves")}</h3>
              <BulletPesos nota={t("El objetivo es el peso que cumple el límite pedido.",
                                   "The target is the weight that satisfies the requested limit.")}
                filas={r.ordenes.map((o) => ({ nombre: o.ticker, hoy: o.peso_actual_pct,
                                               objetivo: o.peso_nuevo_pct, monto: o.monto_usd }))} />
            </div>)}

          <div className="panel">
            <h3>{t("Órdenes", "Orders")}</h3>
            <div className="tabla-wrap"><table>
              <thead><tr><th className="c">{t("Acción", "Action")}</th><th>{t("Activo", "Asset")}</th>
                <th className="n">{t("Peso hoy", "Weight today")}</th>
                <th className="n">{t("Peso nuevo", "New weight")}</th><th className="n">{t("Monto", "Amount")}</th>
                <th className="n">{t("Unidades", "Units")}</th></tr></thead>
              <tbody>{ordenes.map((o) => (
                <tr key={o.ticker}>
                  <td><span className={"chip " + (o.accion === "COMPRAR" ? "ok" : "mal")}>{accionLabel(o.accion)}</span></td>
                  <td className="mono">{o.ticker}</td>
                  <td className="n">{pct(o.peso_actual_pct, 1)}</td>
                  <td className="n">{pct(o.peso_nuevo_pct, 1)}</td>
                  <td className={"n " + signo(o.monto_usd)}>{usd(Math.abs(o.monto_usd))}</td>
                  <td className="n">{o.unidades == null ? "—" : num(Math.abs(o.unidades), 2)}</td>
                </tr>))}</tbody>
            </table></div>
            <div className="pie">{libre(r.nota)}</div>
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

  return (
    <>
      <div className="kpis">
        <Kpi etiqueta={t("Tu Sharpe", "Your Sharpe")} valor={num(d.actual.sharpe, 3)}
             sub={`${pct(d.actual.ret_pct)} / ${pct(d.actual.vol_pct)}`} />
        <Kpi etiqueta={t("Sharpe óptimo", "Optimal Sharpe")} valor={num(d.max_sharpe.sharpe, 3)} tono="pos"
             sub={`${pct(d.max_sharpe.ret_pct)} / ${pct(d.max_sharpe.vol_pct)}`} />
        <Kpi etiqueta={t("Mínima varianza", "Minimum variance")} valor={pct(d.min_varianza.vol_pct)}
             sub={t(`retorno ${pct(d.min_varianza.ret_pct)}`, `return ${pct(d.min_varianza.ret_pct)}`)} />
        <Kpi etiqueta={t("Tasa libre", "Risk-free rate")} valor={pct(d.rf * 100)} sub={d.rf_label} />
      </div>

      <div className="fila f2">
        <FronteraEficiente d={d} />

        <div className="panel">
          <h3>{t("Cómo quedarían los pesos", "How the weights would look")}</h3>
          <Grafico alto={340}
            datos={[
              { type: "bar", name: t("hoy", "today"), x: d.tickers, y: d.actual.pesos,
                marker: { color: c.texto3 },
                hovertemplate: t("%{x}: %{y:.1f} %<extra>hoy</extra>", "%{x}: %{y:.1f} %<extra>today</extra>") },
              { type: "bar", name: t("máximo Sharpe", "maximum Sharpe"), x: d.tickers, y: d.max_sharpe.pesos,
                marker: { color: c.positivo },
                hovertemplate: t("%{x}: %{y:.1f} %<extra>máx Sharpe</extra>", "%{x}: %{y:.1f} %<extra>max Sharpe</extra>") },
              { type: "bar", name: t("mínima varianza", "minimum variance"), x: d.tickers, y: d.min_varianza.pesos,
                marker: { color: c.series[1] },
                hovertemplate: t("%{x}: %{y:.1f} %<extra>mín varianza</extra>", "%{x}: %{y:.1f} %<extra>min variance</extra>") }]}
            layout={{ barmode: "group", yaxis: { title: t("Peso en la cartera", "Weight in the portfolio"), ticksuffix: " %" },
                      xaxis: { tickangle: -35 } }} />
          <div className="pie">
            {t("Máximo Sharpe busca el mejor retorno por unidad de riesgo; mínima varianza, la "
              + "cartera más tranquila sin mirar el retorno esperado —que es el dato peor estimado "
              + "del modelo, y por eso suele ser la más robusta—.",
              "Maximum Sharpe seeks the best return per unit of risk; minimum variance, the "
              + "calmest portfolio without looking at expected return —which is the model's worst-estimated "
              + "input, and that's why it tends to be the most robust—.")}
          </div>
        </div>
      </div>

      <div className="fila f2">
        <div className="panel">
          <h3>{t("Qué habría que operar", "What would need to be traded")}
            <span style={{ marginLeft: "auto", display: "flex", gap: 3,
                           background: "var(--panel-2)", padding: 3, borderRadius: 8 }}>
              {[["max_sharpe", t("Máximo Sharpe", "Maximum Sharpe")], ["min_varianza", t("Mínima varianza", "Minimum variance")]].map(([k, etq]) => (
                <button key={k} className={"modo" + (objetivo === k ? " on" : "")}
                        onClick={() => setObjetivo(k)}>{etq}</button>))}
            </span>
          </h3>
          <div className="pie" style={{ marginTop: 2, marginBottom: 8 }}>
            {t(`Destino: ${pct(destino.ret_pct)} de retorno con ${pct(destino.vol_pct)} de `
              + `volatilidad — Sharpe ${num(destino.sharpe, 3)}.`,
              `Target: ${pct(destino.ret_pct)} of return with ${pct(destino.vol_pct)} of `
              + `volatility — Sharpe ${num(destino.sharpe, 3)}.`)}
          </div>
          {(acciones || []).length > 0 && (
            <BulletPesos nota={t("El objetivo es la cartera óptima del modelo elegido arriba.",
                                 "The target is the optimal portfolio of the model chosen above.")}
              filas={acciones.map((a) => ({ nombre: a.ticker, hoy: a.peso_actual_pct,
                                            objetivo: a.peso_objetivo_pct, monto: a.delta_usd }))} />)}
        </div>

        <div className="panel">
          <h3>{t("¿Habría funcionado?", "Would it have worked?")}
            <span style={{ marginLeft: "auto", display: "flex", gap: 3,
                           background: "var(--panel-2)", padding: 3, borderRadius: 8 }}>
              {[3, 6, 12].map((m) => (
                <button key={m} className={"modo" + (meses === m ? " on" : "")}
                        onClick={() => setMeses(m)}>{m} m</button>))}
            </span>
          </h3>
          {!bt ? <div className="cargando">{t("Optimizando con datos viejos y midiendo después…",
                                              "Optimizing with old data and measuring afterward…")}</div>
           : bt.error ? <div className="aviso mal">{bt.error}</div> : (
            <>
              <Grafico alto={210}
                datos={Object.entries(bt.curvas).map(([n, v], i) => ({
                  type: "scatter", mode: "lines", name: n, x: bt.fechas, y: v,
                  line: { width: n === bt.ganadora ? 2.6 : 1.4,
                          color: c.series[i % c.series.length] } }))}
                layout={{ yaxis: { title: t("Base 100", "Base 100") }, margin: { t: 6 } }} />
              <div className="tabla-wrap"><table>
                <thead><tr><th>{t("Estrategia", "Strategy")}</th><th className="n">{t("Retorno", "Return")}</th>
                  <th className="n">Sharpe</th><th className="n">{t("Peor caída", "Worst drawdown")}</th></tr></thead>
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

      <Seccion titulo={t("Black-Litterman · ¿Y si además uso los precios objetivo?",
                         "Black-Litterman · What if I also use target prices?")} />
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
        <Kpi etiqueta={t("Hoy", "Today")} valor={usd(d.valor_inicial)} />
        <Kpi etiqueta={t("Mediana a un año", "Median in a year")} valor={usd(f.mediana)}
             tono={f.mediana > d.valor_inicial ? "pos" : "neg"} />
        <Kpi etiqueta={t("Escenario malo (5 %)", "Bad scenario (5 %)")} valor={usd(f.var95)} tono="neg"
             sub={t(`perdés ${pct(f.perdida_var95_pct, 1)}`, `you lose ${pct(f.perdida_var95_pct, 1)}`)} />
        <Kpi etiqueta={t("Escenario muy malo (1 %)", "Very bad scenario (1 %)")} valor={usd(f.var99)} tono="neg"
             sub={t(`perdés ${pct(f.perdida_var99_pct, 1)}`, `you lose ${pct(f.perdida_var99_pct, 1)}`)} />
        <Kpi etiqueta={t("Probabilidad de ganar", "Probability of winning")} valor={pct(f.prob_ganancia, 1)}
             tono={f.prob_ganancia > 50 ? "pos" : "neg"} />
      </div>

      <div className="panel" style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <button className="btn primario" onClick={() => setCorriendo(!corriendo)}>
          {corriendo ? t("⏸ Detener la simulación", "⏸ Stop the simulation") : t("▶ Reproducir la simulación", "▶ Play the simulation")}
        </button>
        <span style={{ fontSize: 12.5, color: "var(--texto-3)" }}>
          {t("Mueve a la vez el abanico y las correlaciones: cómo se abre el rango de "
            + "resultados rueda a rueda, y cómo se movió lo que los activos tienen en común.",
            "Moves the fan and the correlations at once: how the range of outcomes "
            + "opens up session by session, and how what the assets have in common moved.")}
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
  if (!d) return <div className="cargando">{t("Simulando cada activo por separado…", "Simulating each asset separately…")}</div>;
  if (d.error) return <div className="aviso mal">{d.error}</div>;

  const todos = [...d.por_activo, d.cartera];
  return (
    <>
      <div className="panel">
        <h3>{t("Rango de resultados de cada activo", "Range of outcomes for each asset")}</h3>
        <Grafico alto={Math.max(280, todos.length * 44 + 110)}
          datos={[
            // El corte de color es el valor de HOY, no la mediana: rojo quiere decir
            // literalmente "termino con menos de lo que tengo". Cada mitad se recorta
            // contra el valor inicial, así que un activo cuyo abanico entero quedó de un
            // solo lado no dibuja la mitad que no existe.
            { type: "bar", orientation: "h", name: t("termina con menos que hoy", "ends with less than today"),
              y: todos.map((f) => f.ticker).reverse(),
              base: todos.map((f) => f.p5).reverse(),
              x: todos.map((f) => Math.max(0, Math.min(f.p95, f.valor_inicial) - f.p5)).reverse(),
              marker: { color: c.negativo, opacity: 0.55 },
              hovertemplate: "%{y}<extra></extra>" },
            { type: "bar", orientation: "h", name: t("termina con más que hoy", "ends with more than today"),
              y: todos.map((f) => f.ticker).reverse(),
              base: todos.map((f) => Math.max(f.p5, f.valor_inicial)).reverse(),
              x: todos.map((f) => Math.max(0, f.p95 - Math.max(f.p5, f.valor_inicial))).reverse(),
              marker: { color: c.positivo, opacity: 0.55 },
              hovertemplate: "%{y}<extra></extra>" },
            { type: "scatter", mode: "markers", name: t("mediana", "median"),
              y: todos.map((f) => f.ticker).reverse(),
              x: todos.map((f) => f.mediana).reverse(),
              marker: { symbol: "line-ns-open", size: 16, color: c.texto,
                        line: { width: 2.5, color: c.texto } },
              hovertemplate: t("%{y}: mediana $%{x:,.0f}<extra></extra>", "%{y}: median $%{x:,.0f}<extra></extra>") }]}
          layout={{ barmode: "overlay", margin: { l: 82 },
                    xaxis: { title: t("Valor a un año", "Value in a year"), tickprefix: "$" } }} />
        <div className="pie">
          {t("El color se parte en lo que vale hoy:", "The color splits at what it's worth today:")}{" "}
          <b className="neg">{t("rojo", "red")}</b> {t("es terminar con menos de lo que tenés,", "means ending with less than you have,")}{" "}
          <b className="pos">{t("verde", "green")}</b> {t("con más. La marca vertical es la mediana. "
            + "La barra entera va del escenario malo (5 %) al bueno (95 %), o sea que cubre",
            "means with more. The vertical mark is the median. The whole bar runs from the bad "
            + "scenario (5 %) to the good one (95 %), i.e. it covers")} <b>{t("el 90 % de los escenarios y no todos",
            "90 % of the scenarios and not all of them")}</b>:{" "}
          {t("queda un 5 % peor que el extremo izquierdo, y de ese lado no hay piso dibujado.",
             "there's still a 5 % worse than the left edge, and no floor is drawn on that side.")}
        </div>
      </div>

      <div className="panel">
        <h3>{t("Detalle", "Detail")}</h3>
        <div className="tabla-wrap"><table>
          <thead><tr><th>{t("Activo", "Asset")}</th><th className="n">{t("Peso", "Weight")}</th><th className="n">{t("Hoy", "Today")}</th>
            <th className="n">{t("Mediana", "Median")}</th><th className="n">{t("Escenario malo", "Bad scenario")}</th>
            <th className="n">{t("Escenario bueno", "Good scenario")}</th>
            <th className="n">{t("Pérdida", "Loss")}</th><th className="n">P({t("ganar", "win")})</th>
            <th className="n">{t("Incertidumbre", "Uncertainty")}</th></tr></thead>
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
          <b>{t(`Diversificar vale ${usd(d.ahorro_diversificacion_usd)} en el escenario malo.`,
                `Diversifying is worth ${usd(d.ahorro_diversificacion_usd)} in the bad scenario.`)}</b>{" "}
          {d.nota}
        </div>
        <div className="pie" style={{ lineHeight: 1.65 }}>
          {IDIOMA === "en" ? (<>
            <b>How to read each row.</b> The simulation's five numbers split the
            scenarios into tranches of known probability: <b>5 %</b> ends worse than the
            bad scenario, <b>45 %</b> between the bad scenario and the median, <b>45 %</b>
            between the median and the good one, and <b>5 %</b> better than the good one.
            Careful not to confuse that split with the one for losing: the line between
            losing and winning is the <i>today</i> column, and <i>P(win)</i> is exactly the
            probability of ending to its right — nominal in dollars, without discounting
            inflation or comparing it against a risk-free rate.
            <br /><br />
            <b>The bar's length isn't useful for comparing assets to each other</b>, since
            it's in dollars and therefore mixes risk with position size: whatever weighs
            most always looks the most uncertain. That's what <i>Uncertainty</i> is for,
            which is the fan's width as a multiple of today's value — how many times its
            own value separates the good scenario from the bad one — and <i>Loss</i>, which
            is how much it drops from today to the bad scenario. An asset with high
            uncertainty <b>and</b> high weight is the one that decides the portfolio's
            outcome; the rest is noise around it.
            <br /><br />
            <b>The PORTFOLIO row isn't the sum of the ones above.</b> The already-weighted
            portfolio series is simulated, which carries the real correlations between the
            stocks, and that's why its uncertainty is lower than the asset that dominates
            it. Each asset's bad scenarios don't happen together either: each p5 is its
            own, isolated.
            <br /><br />
            <b>What to take with a grain of salt is the center, not the width.</b> Each
            asset is simulated with its own historical μ and σ, so a stock that's been
            rising projects a median skewed up just because that's how it moved before.
            The fan's shape is much more reliable than where it's centered.
          </>) : (<>
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
          </>)}
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

  if (!d) return <div className="cargando">{t("Calculando cómo se movieron las correlaciones…", "Calculating how the correlations moved…")}</div>;
  if (d.error) return <div className="aviso mal">{d.error}</div>;

  const cuadro = d.cuadros[i];
  const cerca = (d.eventos || []).filter((e) =>
    Math.abs(new Date(e.fecha) - new Date(cuadro.fecha)) < 45 * 864e5);

  return (
    <>
      <div className="panel">
        <h3>{t("Las correlaciones no son estables", "Correlations aren't stable")}
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
              datos={[{ type: "scatter", mode: "lines", name: t("correlación media", "average correlation"),
                        x: d.cuadros.map((q) => q.fecha), y: d.cuadros.map((q) => q.media),
                        line: { color: c.acento, width: 2 } }]}
              layout={{ margin: { t: 6, l: 44, b: 40 },
                        yaxis: { title: t("Correlación media", "Average correlation") },
                        shapes: [{ type: "line", x0: cuadro.fecha, x1: cuadro.fecha,
                                   yref: "paper", y0: 0, y1: 1,
                                   line: { color: c.alerta, width: 2 } },
                                 ...(d.eventos || []).map((e) => ({
                                   type: "line", x0: e.fecha, x1: e.fecha, yref: "paper",
                                   y0: 0, y1: 1, line: { color: c.texto3, width: 0.8, dash: "dot" } }))] }} />
            <div className="kpis" style={{ gridTemplateColumns: "1fr 1fr", marginTop: 8 }}>
              <Kpi etiqueta={t("Ahora", "Now")} valor={num(cuadro.media, 3)}
                   tono={cuadro.media > d.media_global + 0.15 ? "neg"
                        : cuadro.media < d.media_global - 0.15 ? "pos" : ""} />
              <Kpi etiqueta={t("Promedio del período", "Period average")} valor={num(d.media_global, 3)} />
            </div>
            {cerca.length > 0 && (
              <div className="aviso ojo">
                {t("Por estas fechas:", "Around these dates:")} {cerca.map((e) => eventoDescripcion(e.descripcion)).join(" · ")}.
              </div>)}
          </div>
        </div>
        <div className="pie">
          {d.nota} {t(`El máximo del período fue`, `The period's maximum was`)} <b>{d.maximo.media}</b>{" "}
          {t("el", "on")} {d.maximo.fecha}; {t("el mínimo,", "the minimum,")} <b>{d.minimo.media}</b>{" "}
          {t("el", "on")} {d.minimo.fecha}.{" "}
          {t("Una matriz de correlaciones promedio esconde este movimiento, y es el que decide si "
            + "la diversificación va a estar ahí cuando haga falta.",
            "An average correlation matrix hides this movement, and it's what decides whether "
            + "diversification will be there when it's needed.")}
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
      <h3>{t("¿Cambia según el supuesto de distribución?", "Does it change with the distribution assumption?")}</h3>
      {!motores ? <div className="cargando">{t("Comparando los tres motores…", "Comparing the three engines…")}</div>
       : motores.error ? <div className="aviso mal">{motores.error}</div> : (
        <>
          <div className="tabla-wrap"><table>
            <thead><tr><th>{t("Motor", "Engine")}</th><th className="n">{t("Escenario malo", "Bad scenario")}</th>
                       <th className="n">{t("Pérdida", "Loss")}</th><th className="n">{t("Muy malo", "Very bad")}</th>
                       <th className="n">{t("Pérdida", "Loss")}</th></tr></thead>
            <tbody>{Object.entries(motores).map(([k, v]) => (
              <tr key={k}><td>{k}</td>
                <td className="n">{usd(v.var95)}</td><td className="n neg">{pct(v.perdida_var95_pct, 1)}</td>
                <td className="n">{usd(v.var99)}</td><td className="n neg">{pct(v.perdida_var99_pct, 1)}</td>
              </tr>))}</tbody>
          </table></div>
          <div className="pie">
            {t("Las colas gordas pesan en el riesgo de un día —ahí está el VaR de "
              + "Cornish-Fisher, en la pestaña de Riesgo— pero se diluyen al componer "
              + "muchos días: por eso los tres motores dan parecido a este horizonte.",
              "Fat tails matter for one-day risk —that's what the Cornish-Fisher VaR, in the "
              + "Risk tab, is for— but they dilute when compounding "
              + "many days: that's why the three engines give similar results at this horizon.")}
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
        <h3>{t("Cómo se abre el abanico", "How the fan opens up")}</h3>
        <Grafico alto={320}
          datos={[
            ...banda(a.p5, a.p95, "22", t("9 de cada 10 casos", "9 out of 10 cases")),
            ...banda(a.p25, a.p75, "44", t("la mitad de los casos", "half the cases")),
            { type: "scatter", x: corte(a.dias), y: corte(a.p50), mode: "lines",
              name: t("mediana", "median"), line: { color: c.texto, width: 2.5 } },
          ]}
          layout={{ xaxis: { title: t("Ruedas hacia adelante", "Sessions ahead"),
                             range: [0, a.dias?.[a.dias.length - 1] || 1] },
                    yaxis: { title: t("Valor en dólares", "Value in dollars"),
                             range: [Math.min(...(a.p5 || [0])) * 0.95,
                                     Math.max(...(a.p95 || [1])) * 1.05] },
                    shapes: [{ type: "line", xref: "paper", x0: 0, x1: 1,
                               y0: V, y1: V,
                               line: { color: c.texto3, width: 2, dash: "dot" } }] }} />
        <div className="pie">
          {t("La incertidumbre no crece de golpe: se abre con la raíz del tiempo. La línea "
            + "punteada es lo que vale hoy, y todo lo pintado en rojo abajo es la parte de los "
            + "escenarios en la que terminás con menos de lo que tenés.",
            "Uncertainty doesn't grow all at once: it opens up with the square root of time. The "
            + "dashed line is what it's worth today, and everything painted red below is the part "
            + "of the scenarios where you end up with less than you have.")}{" "}
          {corriendo && <b>{t(`Rueda ${a.dias?.[paso]} de ${a.dias?.[a.dias.length - 1]}.`,
                              `Session ${a.dias?.[paso]} of ${a.dias?.[a.dias.length - 1]}.`)}</b>}
        </div>
      </div>

      <div className="panel">
        <h3>{t("Dónde puede terminar", "Where it could end up")}</h3>
        <Grafico alto={340}
          datos={[
            { type: "bar", x: dist.x, y: dist.y, name: t("escenarios simulados", "simulated scenarios"),
              marker: { color: c.series[2], opacity: 0.75 },
              hovertemplate: t("$%{x:,.0f}: %{y} escenarios<extra></extra>", "$%{x:,.0f}: %{y} scenarios<extra></extra>") },
            { type: "scatter", mode: "lines", x: dist.x, y: dist.normal,
              name: t("ajuste normal", "normal fit"), line: { color: c.alerta, width: 2 } },
            { type: "scatter", mode: "lines", x: dist.x, y: dist.lognormal,
              name: t("ajuste lognormal", "lognormal fit"), line: { color: c.positivo, width: 2, dash: "dot" } },
          ]}
          layout={{ bargap: 0.02, margin: { t: 26 },
                    xaxis: { title: t("Valor final", "Final value"), tickprefix: "$" },
                    yaxis: { title: t("Escenarios", "Scenarios") },
                    shapes: [d.final.var95, d.final.var99, d.valor_inicial].map((x, i) => ({
                      type: "line", x0: x, x1: x, yref: "paper", y0: 0, y1: 0.9,
                      line: { color: i === 2 ? c.texto3 : c.negativo, width: 1.6, dash: "dash" } })),
                    annotations: [
                      { x: d.final.var95, y: 1, yref: "paper", text: t("5 % peor", "worst 5 %"), showarrow: false,
                        font: { size: 10, color: c.negativo }, yanchor: "bottom" },
                      { x: d.valor_inicial, y: 1, yref: "paper", text: t("hoy", "today"), showarrow: false,
                        font: { size: 10, color: c.texto3 }, yanchor: "bottom" }] }} />
        <div className="pie">
          {t(`Las barras son los ${d.n_simulaciones.toLocaleString(IDIOMA === "en" ? "en-US" : "es-AR")} `
            + `escenarios simulados.`,
            `The bars are the ${d.n_simulaciones.toLocaleString(IDIOMA === "en" ? "en-US" : "es-AR")} `
            + `simulated scenarios.`)}{" "}
          {t("El mejor ajuste teórico es", "The best theoretical fit is")} <b>{dist.mejor_ajuste}</b>
          {dist.mejor_ajuste === "lognormal"
            ? <> — {t("es lo esperable: un precio no puede ser negativo, así que la distribución "
                + "de valores finales queda sesgada hacia arriba y la campana normal se queda "
                + "corta en los dos extremos.",
                "that's expected: a price can't be negative, so the distribution "
                + "of final values ends up skewed upward and the normal bell curve falls "
                + "short at both ends.")}</>
            : <>: {t("en este horizonte la campana normal describe los valores finales tan bien "
                + "como la lognormal.",
                "at this horizon the normal bell curve describes the final values just as well "
                + "as the lognormal one.")}</>}
        </div>
      </div>
    </>
  );
}

/* ── Benchmark (CAPM) ── */
function Capm({ d: inicial, cartera, bench, todos }) {
  const c = colores();
  const [d, setD] = useState(inicial);
  // El selector global manda: si cambia, se recalcula contra ese índice.
  useEffect(() => {
    if (bench === (d?.benchmark || MERCADOS[MERCADO].bench)) return;
    setD(null);
    api(`/api/capm/${encodeURIComponent(cartera)}?benchmark=${bench}`).then(setD);
  }, [bench, cartera]);

  // Los tres índices se comparan solos, y vienen con el lote de modelos: pedirlos
  // aparte repetía el CAPM que el lote ya había corrido —son tres índices y uno
  // de ellos es el mismo— y competía con él por el procesador. Con un R² bajo,
  // saber cuál de los tres explica la cartera es justamente lo que hay que
  // mirar: dejarlo detrás de un botón era esconder la respuesta a la advertencia
  // que da el panel de arriba.
  //
  // El índice recomendado no sirve de nada si el resto de la pantalla se sigue
  // midiendo contra otro. Se avisa por evento y no por props: el selector vive
  // tres componentes más arriba, y es el mismo canal que la app ya usa para
  // hablar de abajo hacia arriba.
  useEffect(() => {
    if (todos?.recomendado) {
      window.dispatchEvent(new CustomEvent("pa:indice", { detail: todos.recomendado }));
    }
  }, [todos]);
  if (!d) return <div className="cargando">{t("Comparando contra el índice…", "Comparing against the index…")}</div>;
  if (d.error) return <div className="aviso mal">{d.error}</div>;
  const nivel = d.diagnostico_r2?.nivel;
  const gana = d.retorno_cartera_pct > d.retorno_benchmark_pct;
  const defensiva = d.beta < 0.8, agresiva = d.beta > 1.2;
  const datos = [
    // SVG y no `scattergl`: el WebGL no está disponible en todos los equipos ni
    // en todos los navegadores, y donde falta el panel entero queda en "WebGL not
    // supported". Son ~1.200 puntos, que el SVG dibuja sin despeinarse.
    { type: "scatter", mode: "markers", name: t("ruedas", "sessions"),
      x: (d.nube || []).map((p) => p.b), y: (d.nube || []).map((p) => p.p),
      marker: { size: 4, color: c.texto3, opacity: 0.45 },
      hovertemplate: t("índice %{x:.2f} % · cartera %{y:.2f} %<extra></extra>",
                       "index %{x:.2f} % · portfolio %{y:.2f} %<extra></extra>") },
    { type: "scatter", mode: "lines", name: t(`pendiente = beta ${d.beta}`, `slope = beta ${d.beta}`),
      x: (d.recta || []).map((p) => p.b), y: (d.recta || []).map((p) => p.p),
      line: { color: c.acento, width: 2.5 } },
  ];
  return (
    <>
      <div className="kpis">
        <Kpi etiqueta="Beta" valor={num(d.beta, 3)} ayuda={AYUDA.beta} sub={d.benchmark_nombre} />
        <Kpi etiqueta={t("Alpha anual", "Annual alpha")} valor={pct(d.alpha_anual_pct)} tono={signo(d.alpha_anual_pct)} ayuda={AYUDA.alpha} />
        <Kpi etiqueta="R²" valor={num(d.r2, 3)} ayuda={AYUDA.r2}
             tono={nivel === "alto" ? "pos" : nivel === "bajo" ? "neg" : ""} />
        <Kpi etiqueta="Treynor" valor={num(d.treynor, 3)} />
        <Kpi etiqueta="Information ratio" valor={num(d.information_ratio, 3)} />
        <Kpi etiqueta={t("Cartera vs índice", "Portfolio vs index")} valor={pct(d.retorno_cartera_pct)}
             sub={t(`índice ${pct(d.retorno_benchmark_pct)}`, `index ${pct(d.retorno_benchmark_pct)}`)}
             tono={d.retorno_cartera_pct > d.retorno_benchmark_pct ? "pos" : "neg"} />
      </div>

      <div className={"aviso " + (nivel === "alto" ? "ok" : nivel === "bajo" ? "mal" : "ojo")}>
        <b>R² = {d.r2}.</b> {d.diagnostico_r2?.texto}
      </div>

      <div className="panel" style={{ marginBottom: 14 }}>
        <h3>{t("Qué dice todo esto, en una lectura", "What all this says, in one read")}</h3>
        <div style={{ fontSize: 14.5, color: "var(--texto-2)", lineHeight: 1.7, marginTop: 8 }}>
          <p style={{ margin: "0 0 10px" }}>
            {t(`Sobre ${d.n_ruedas} ruedas, tu cartera rindió`, `Over ${d.n_ruedas} sessions, your portfolio returned`)}{" "}
            <b className={gana ? "pos" : "neg"}>
            {pct(d.retorno_cartera_pct)}</b> {t("anual contra", "annual against")} <b>{pct(d.retorno_benchmark_pct)}</b>{" "}
            {t("del", "for the")} {d.benchmark_nombre}.
          </p>
          <p style={{ margin: "0 0 10px" }}>
            {t("Con", "With")} <b>{t("beta", "a beta of")} {num(d.beta, 2)}</b>,{" "}
            {t("cuando el índice sube 10 % tu cartera tiende a", "when the index rises 10 % your portfolio tends to")}{" "}
            {t(d.beta >= 0 ? "subir" : "bajar", d.beta >= 0 ? "rise" : "fall")} <b>{num(Math.abs(d.beta * 10), 1)} %</b>.{" "}
            {defensiva ? t("Se mueve MENOS que el mercado: es defensiva frente a ese índice.",
                           "It moves LESS than the market: it's defensive against that index.")
             : agresiva ? t("Se mueve MÁS que el mercado: amplifica sus movimientos, para bien y para mal.",
                            "It moves MORE than the market: it amplifies its moves, for better and worse.")
             : t("Se mueve prácticamente al ritmo del mercado.", "It moves practically in step with the market.")}
          </p>
          <p style={{ margin: "0 0 10px" }}>
            {t("El", "The")} <b>{t(`alpha de ${pct(d.alpha_anual_pct)}`, `alpha of ${pct(d.alpha_anual_pct)}`)}</b>{" "}
            {t("es lo que rendiste por encima de lo que te correspondía por el riesgo de mercado que asumiste.",
               "is what you returned above what you were owed for the market risk you took on.")}{" "}
            {d.alpha_anual_pct > 0
              ? t("Positivo: la cartera aportó algo que el índice no explica.",
                  "Positive: the portfolio contributed something the index doesn't explain.")
              : t("Negativo: asumiendo ese riesgo, el índice te habría dado más.",
                  "Negative: taking on that risk, the index would have given you more.")}
            {nivel === "bajo" && <> <b>{t(`Pero con R² de ${d.r2} este número no se sostiene`,
                                          `But with an R² of ${d.r2} this number doesn't hold up`)}</b>:{" "}
              {t("el índice no explica lo que hace tu cartera, así que beta y alpha están midiendo ruido.",
                 "the index doesn't explain what your portfolio does, so beta and alpha are measuring noise.")}</>}
          </p>
          <p style={{ margin: 0 }}>
            {t("El", "The")} <b>{t(`tracking error de ${pct(d.tracking_error_pct)}`, `tracking error of ${pct(d.tracking_error_pct)}`)}</b>{" "}
            {t("es cuánto te despegás del índice en un año típico, y el", "is how much you drift from the index in a typical year, and the")}{" "}
            <b>{t(`information ratio de ${num(d.information_ratio, 2)}`, `information ratio of ${num(d.information_ratio, 2)}`)}</b>{" "}
            {t("dice si ese despegue te pagó:", "says whether that drift paid off:")} {d.information_ratio > 0.5
              ? t("es una diferencia consistente, no un golpe de suerte", "it's a consistent difference, not a lucky break")
              : d.information_ratio > 0 ? t("apenas positivo, poco consistente", "barely positive, not very consistent")
              : t("te despegaste del índice para peor", "you drifted from the index for the worse")}.
          </p>
        </div>
      </div>

      <div className="fila f2">
        <div className="panel">
          <h3>{t("Recta característica", "Characteristic line")}</h3>
          <Grafico datos={datos} alto={340}
                   layout={{ xaxis: { title: t(`Retorno diario · ${d.benchmark_nombre}`, `Daily return · ${d.benchmark_nombre}`), ticksuffix: " %" },
                             yaxis: { title: t("Retorno diario · cartera", "Daily return · portfolio"), ticksuffix: " %" } }} />
          <div className="pie">
            {t("Cada punto es una rueda. La pendiente de la recta", "Each point is a session. The line's slope")} <b>{t("es", "is")}</b>{" "}
            {t("el beta. Si la nube está dispersa, esa pendiente no describe gran cosa: eso es lo que dice el R².",
               "the beta. If the cloud is scattered, that slope doesn't describe much: that's what R² says.")}
          </div>
        </div>
        <div className="panel">
          <h3>{t("¿Cuál es el índice correcto?", "Which is the right index?")}</h3>
          {!todos ? <div className="cargando">{t("Midiendo los tres índices…", "Measuring the three indices…")}</div>
           : todos.error ? <div className="aviso mal">{todos.error}</div> : (
            <>
              <div className="tabla-wrap"><table>
                <thead><tr><th>{t("Índice", "Index")}</th><th className="n">R²</th><th className="n">Beta</th>
                  <th className="n">Alpha</th></tr></thead>
                <tbody>{Object.entries(todos.benchmarks).sort((a,b)=>b[1].r2-a[1].r2).map(([k, v]) => (
                  <tr key={k}>
                    <td className="textochip">{v.nombre}
                      {k === todos.recomendado &&
                        <span className="chip ok" style={{ marginLeft: 7 }}>{t("correcto", "correct")}</span>}</td>
                    <td className="n">{num(v.r2, 3)}</td><td className="n">{num(v.beta, 3)}</td>
                    <td className="n">{pct(v.alpha_anual_pct)}</td>
                  </tr>))}</tbody>
              </table></div>
              <div className="aviso ojo">
                {t("Fijate que el alpha", "Notice that the alpha")} <b>{t("sube", "rises")}</b>{" "}
                {t("cuanto peor es el índice. Elegir el benchmark por el número más lindo es elegir el "
                  + "que menos explica la cartera.",
                  "the worse the index is. Choosing the benchmark for the nicest-looking number means choosing "
                  + "the one that explains the portfolio the least.")}
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
        <h3>{t("Momentum a 12 meses, salteando el último", "12-month momentum, skipping the last one")}</h3>
        <Grafico alto={Math.max(230, a.length * 40 + 110)}
          datos={[{ type: "bar", orientation: "h",
                    y: a.map((x) => x.ticker).reverse(),
                    x: a.map((x) => x.mom_12_1_pct).reverse(),
                    marker: { color: a.map((x) => color(x.señal)).reverse() },
                    hovertemplate: "%{y}: %{x:.1f} %<extra></extra>" }]}
          layout={{ margin: { l: 82 }, xaxis: { ticksuffix: " %" } }} />
        <div className="pie">{libre(d.nota_metodo)}</div>
      </div>
      <div className="panel">
        <h3>{t("Veredicto por activo", "Verdict by asset")}</h3>
        <div className="tabla-wrap"><table>
          <thead><tr><th>Ticker</th><th className="n">12−1</th><th className="n">{t("12 meses", "12 months")}</th>
                     <th className="n">{t("3 meses", "3 months")}</th><th className="c">{t("Señal", "Signal")}</th>
                     <th className="n">{t("1 mes", "1 month")}</th><th className="c">{t("Entrada", "Entry")}</th>
                     <th>{t("Qué significa", "What it means")}</th></tr></thead>
          <tbody>{a.map((x) => (
            <tr key={x.ticker}>
              <td className="mono">{x.ticker}</td>
              <td className={"n " + signo(x.mom_12_1_pct)}>{pct(x.mom_12_1_pct, 1)}</td>
              <td className="n">{pct(x.mom_12m_pct, 1)}</td>
              <td className={"n " + signo(x.mom_3m_pct)}>{pct(x.mom_3m_pct, 1)}</td>
              <td><span className={"chip " + (x.señal === "FAVORABLE" ? "ok" : x.señal === "EVITAR" ? "mal" : x.señal === "ESPERAR" ? "ojo" : "")}>{senalLabel(x.señal)}</span></td>
              {/* El mes va después de la señal y sin color de signo: acá un
                  número negativo es una buena noticia para el que compra, así
                  que pintarlo de rojo diría lo contrario de lo que significa. */}
              <td className="n">{pct(x.mom_1m_pct, 1)}</td>
              <td title={libre(x.entrada_texto)}>
                <span className={"chip " + (x.entrada === "BUEN PRECIO" ? "ok"
                                          : x.entrada === "CARO" ? "ojo" : "")}>{senalLabel(x.entrada)}</span>
              </td>
              <td style={{ fontSize: 12.5, color: "var(--texto-2)" }}>
                {libre(x.veredicto)}
                {x.entrada !== "—" && x.entrada !== "NORMAL" &&
                  <> <b>{libre(x.entrada_texto)}</b></>}
              </td>
            </tr>))}</tbody>
        </table></div>
        <div className="pie">
          {t("Las tres primeras columnas dicen", "The first three columns say")} <b>{t("qué", "what")}</b>{" "}
          {t("tiene viento a favor; el último mes dice", "has a tailwind; the last month says")}
          <b>{t(" a qué precio conviene entrar", " at what price it's worth entering")}</b>,{" "}
          {t("y se lee al revés: a un mes no hay momentum, hay reversión — es el mismo efecto que "
            + "el 12−1 saltea para no ensuciarse. Un papel con tendencia buena que subió 15 % en el "
            + "mes no deja de ser bueno: está caro hoy.",
            "and it reads backwards: at one month there's no momentum, there's reversion — it's the "
            + "same effect the 12−1 skips to avoid muddying the signal. A stock with a good trend "
            + "that rose 15 % in the month doesn't stop being good: it's just expensive today.")}
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

  if (!obj) return <div className="cargando">{t("Buscando precios objetivo…", "Looking up target prices…")}</div>;
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
        <h3>{t("Precio objetivo y momento de entrada", "Target price and entry timing")}</h3>
        <div className="tabla-wrap"><table>
          <thead><tr><th>Ticker</th><th className="n">{t("Hoy", "Today")}</th><th className="n">{t("Objetivo", "Target")}</th>
            <th className="n">Upside</th><th className="c">Momentum</th><th className="c">{t("Combinada", "Combined")}</th>
            <th className="c">{t("Tu opinión", "Your view")}</th></tr></thead>
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
                      : x.momentum === "ESPERAR" ? "ojo" : "")}>{x.momentum ? senalLabel(x.momentum) : "—"}</span></td>
                <td><span className={"chip " + (x.combinada === "COMPRAR" ? "ok"
                      : x.combinada === "CARO" || x.combinada === "REDUCIR" ? "mal"
                      : x.combinada === "ESPERAR GIRO" ? "ojo" : "")}>{senalLabel(x.combinada)}</span></td>
                <td style={{ textAlign: "center" }}>
                  {mv ? (
                    <span style={{ display: "flex", gap: 6, alignItems: "center",
                                   justifyContent: "center" }}>
                      <span className="chip ojo">{mv.modo === "B2" ? t(`evento ${mv.meses} m`, `event ${mv.meses} m`) : t("propia", "own")}</span>
                      <span className="mono" style={{ fontSize: 11.5 }}>{mv.bajo}–{mv.alto}</span>
                      <button className="btn" style={{ padding: "1px 7px", fontSize: 11 }}
                              onClick={() => borrar(x.ticker)}>✕</button>
                    </span>
                  ) : (
                    <button className="btn" style={{ padding: "2px 9px", fontSize: 12 }}
                            onClick={() => setEditando(x)}>{t("Fijar", "Set")}</button>)}
                </td>
              </tr>);
          })}</tbody>
        </table></div>
        <div className="pie">
          {t("El precio objetivo dice", "The target price says")} <b>{t("cuánto", "how much")}</b>{" "}
          {t("puede valer; el momentum,", "it could be worth; momentum,")} <b>{t("cuándo", "when")}</b>.{" "}
          {t("Un objetivo alto con la acción cayendo no es una compra: es esperar el giro. Si tenés una "
            + "opinión propia sobre un papel —o si no hay cobertura de analistas, como pasa con las "
            + "small caps argentinas— fijala vos y pisa al consenso.",
            "A high target with the stock falling isn't a buy: it's waiting for the turn. If you have your "
            + "own view on a stock —or if there's no analyst coverage, as happens with Argentine "
            + "small caps— set it yourself and it overrides the consensus.")}
        </div>
      </div>

      {editando && <EditorView activo={editando} onGuardar={guardar}
                               onCerrar={() => setEditando(null)} />}

      {bl === "cargando" ? <div className="cargando">{t("Recalculando con tu opinión…", "Recalculating with your view…")}</div>
       : !bl ? <div className="cargando">{t("Calculando Black-Litterman…", "Calculating Black-Litterman…")}</div>
       : bl.error ? <div className="aviso mal">{bl.error}</div>
       : <BlackLitterman bl={bl} actual={d.actual} />}

      {d && !d.error && (() => {
        const blOk = bl && bl !== "cargando" && !bl.error && bl.ret_bl_pct != null ? bl : null;
        return (
          <>
            <Seccion titulo={blOk ? t("Las cuatro carteras, lado a lado", "The four portfolios, side by side")
                                   : t("Las tres carteras, lado a lado", "The three portfolios, side by side")} />
            <RadarCarteras mk={d} bl={blOk} />
          </>
        );
      })()}
    </>
  );
}

function EditorView({ activo, onGuardar, onCerrar }) {
  const [modo, setModo] = useState("B1");
  const [bajo, setBajo] = useState((activo.actual * 0.9).toFixed(2));
  const [alto, setAlto] = useState((activo.actual * 1.2).toFixed(2));
  const [meses, setMeses] = useState(3);

  const medio = (dec(bajo) + dec(alto)) / 2;
  const bruto = activo.actual ? medio / activo.actual - 1 : 0;
  const anualizado = modo === "B2" ? Math.pow(1 + bruto, 12 / Math.max(1, meses)) - 1 : bruto;
  const anchoPct = medio > 0 ? (dec(alto) - dec(bajo)) / medio * 100 : 100;
  const confianza = Math.round(Math.max(10, Math.min(90, 90 - anchoPct)));

  return (
    <div className="panel" style={{ borderLeft: "4px solid var(--acento)" }}>
      <h3>{t("Tu opinión sobre", "Your view on")} {activo.ticker}
        <button className="btn" style={{ marginLeft: "auto", padding: "3px 10px", fontSize: 12 }}
                onClick={onCerrar}>{t("Cancelar", "Cancel")}</button>
      </h3>
      <div className="modos" style={{ width: "fit-content", margin: "10px 0" }}>
        {[["B1", t("Opinión propia", "Own view")], ["B2", t("Evento corporativo", "Corporate event")]].map(([k, etq]) => (
          <button key={k} className={"modo" + (modo === k ? " on" : "")}
                  onClick={() => setModo(k)}>{etq}</button>))}
      </div>
      <div style={{ display: "flex", gap: 12, alignItems: "flex-end", flexWrap: "wrap" }}>
        <label style={{ fontSize: 11.5, color: "var(--texto-3)" }}>{t("Precio piso", "Floor price")}<br />
          <input type="text" inputMode="decimal" value={bajo} style={{ width: 110, marginTop: 3 }}
                 onChange={(e) => setBajo(soloNum(e.target.value))} /></label>
        <label style={{ fontSize: 11.5, color: "var(--texto-3)" }}>{t("Precio techo", "Ceiling price")}<br />
          <input type="text" inputMode="decimal" value={alto} style={{ width: 110, marginTop: 3 }}
                 onChange={(e) => setAlto(soloNum(e.target.value))} /></label>
        {modo === "B2" && (
          <label style={{ fontSize: 11.5, color: "var(--texto-3)" }}>{t("Meses hasta que se resuelve", "Months until it resolves")}<br />
            <input type="number" min="1" max="60" value={meses} style={{ width: 110, marginTop: 3 }}
                   onChange={(e) => setMeses(+e.target.value)} /></label>)}
        <button className="btn primario"
                onClick={() => onGuardar(activo.ticker, { modo, bajo: dec(bajo), alto: dec(alto), meses })}>
          {t("Aplicar", "Apply")}</button>
      </div>
      <div className="aviso ok">
        {t(`Hoy cotiza ${usd(activo.actual)}. Tu rango da un precio medio de ${usd(medio)}, o sea`,
           `Today it trades at ${usd(activo.actual)}. Your range gives an average price of ${usd(medio)}, i.e.`)}{" "}
        <b>{pct(bruto * 100, 1)}</b>
        {modo === "B2" && <> {t(`en ${meses} ${meses === 1 ? "mes" : "meses"}, que anualizado compuesto son`,
                                `in ${meses} ${meses === 1 ? "month" : "months"}, which compounded annually is`)}{" "}
          <b>{pct(anualizado * 100, 1)}</b></>}.
        {" "}{t("Confianza estimada:", "Estimated confidence:")} <b>{confianza} %</b>.
      </div>
      <div className="pie">
        {t("La confianza sale del", "The confidence comes from the")} <b>{t("ancho del rango", "range's width")}</b>,{" "}
        {t(`no se pide como número: nadie sabe responder "¿qué tan seguro estás del 0 al 100?", pero `
          + `todos saben entre qué precios creen que va a estar. Un rango angosto es una opinión firme. `
          + `El tope es 90 % aunque el rango sea de un centavo — con certeza total el modelo concentra `
          + `todo en ese activo.`,
          `it's not asked for as a number: nobody knows how to answer "how sure are you from 0 to 100?", `
          + `but everyone knows between which prices they think it'll land. A narrow range is a firm `
          + `opinion. The cap is 90 % even if the range is a single cent wide — with total certainty the `
          + `model would put everything into that asset.`)}
        {modo === "B2" && <> {t("El modo", "The")} <b>{t("evento corporativo", "corporate event")}</b>{" "}
          {t("existe para casos como una OPA: el plazo real cambia el retorno anualizado y por lo tanto "
            + "el peso que el modelo le da.",
            "mode exists for cases like a tender offer: the actual timeline changes the annualized return "
            + "and therefore the weight the model gives it.")}</>}
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
        <Kpi etiqueta={t("Retorno esperado", "Expected return")} valor={pct(bl.ret_bl_pct)} tono={tono(dRet)}
             sub={dRet == null ? null : t(`${flecha(dRet)}${num(Math.abs(dRet), 2)} pp vs tu cartera (${pct(actual?.ret_pct)})`,
                                          `${flecha(dRet)}${num(Math.abs(dRet), 2)} pp vs your portfolio (${pct(actual?.ret_pct)})`)} />
        <Kpi etiqueta={t("Volatilidad", "Volatility")} valor={pct(bl.vol_bl_pct)} tono={tono(dVol, false)}
             sub={dVol == null ? null : `${flecha(dVol)}${num(Math.abs(dVol), 2)} pp vs ${pct(actual?.vol_pct)}`} />
        <Kpi etiqueta="Sharpe" valor={num(bl.sharpe_bl, 3)} tono={tono(dShr)}
             sub={dShr == null ? null : `${flecha(dShr)}${num(Math.abs(dShr), 3)} vs ${num(actual?.sharpe, 3)}`} />
        <Kpi etiqueta={t("Aversión al riesgo (δ)", "Risk aversion (δ)")} valor={num(bl.delta, 2)} sub={bl.delta_label} />
        <Kpi etiqueta={t("Incertidumbre (τ)", "Uncertainty (τ)")} valor={num(bl.tau, 5)} sub={bl.tau_label} />
      </div>

      {manuales.length > 0 && (
        <div className="aviso ok">
          <b>{t("Con tu opinión aplicada:", "With your view applied:")}</b>{" "}
          {manuales.map((v) => t(`${v.ticker} ${v.ret > 0 ? "+" : ""}${v.ret} % anual`
            + (v.modo === "B2" ? ` (evento a ${v.meses} meses)` : "")
            + `, confianza ${v.confidence} %`,
            `${v.ticker} ${v.ret > 0 ? "+" : ""}${v.ret} % annual`
            + (v.modo === "B2" ? ` (event in ${v.meses} months)` : "")
            + `, confidence ${v.confidence} %`)).join(" · ")}.
        </div>)}

      <div className="aviso">{libre(bl.equilibrio_nota)}</div>

      {acc.length === 0 ? (
        <div className="aviso ojo">{libre(bl.nota) || t("Sin views: el modelo devuelve el punto de partida.",
                                                  "No views: the model returns the starting point.")}</div>
      ) : (
        <>
          <div className="panel">
            <h3>{t("Qué operar según Black-Litterman", "What to trade according to Black-Litterman")}</h3>
            {acc.length > 0 && (
              <BulletPesos nota={t("El objetivo es el peso posterior, ya con tus views incorporadas.",
                                   "The target is the posterior weight, already with your views incorporated.")}
                filas={acc.map((a) => ({ nombre: a.ticker, hoy: a.peso_actual_pct,
                                         objetivo: a.peso_bl_pct, monto: a.delta_usd }))} />)}
            <div className="tabla-wrap"><table>
              <thead><tr><th>Ticker</th><th className="n">{t("Hoy", "Today")}</th><th className="n">{t("Sugerido", "Suggested")}</th>
                <th className="n">{t("Monto", "Amount")}</th><th className="n">{t("Retorno esperado", "Expected return")}</th>
                <th className="c">{t("Acción", "Action")}</th></tr></thead>
              <tbody>{acc.map((a) => (
                <tr key={a.ticker}>
                  <td className="mono">{a.ticker}</td>
                  <td className="n">{pct(a.peso_actual_pct, 1)}</td>
                  <td className="n">{pct(a.peso_bl_pct, 1)}</td>
                  <td className={"n " + signo(a.delta_usd)}>{usd(a.delta_usd)}</td>
                  <td className={"n " + signo(a.ret_bl_pct)}>{pct(a.ret_bl_pct, 1)}</td>
                  <td><span className={"chip " + (a.accion === "COMPRAR" ? "ok" : a.accion === "VENDER" ? "mal" : "")}>{accionLabel(a.accion)}</span></td>
                </tr>))}</tbody>
            </table></div>
            <div className="pie">
              {t(`"Retorno esperado" es el posterior del modelo: la mezcla entre lo que estaba `
                + `implícito en tu cartera y lo que dicen las views, pesada por confianza.`,
                `"Expected return" is the model's posterior: the blend between what was `
                + `implicit in your portfolio and what the views say, weighted by confidence.`)}
            </div>
          </div>
        </>
      )}
    </>
  );
}

/* ── Regímenes ── */
function Regimenes({ d, cartera }) {
  const c = colores();
  const [activos, setActivos] = useState(null);
  const [posiciones, setPosiciones] = useState(null);
  const [sel, setSel] = useState("__cartera__");
  useEffect(() => { api(`/api/riesgo/${encodeURIComponent(cartera)}/por-activo`).then(setActivos); }, [cartera]);
  useEffect(() => { api(`/api/posicion/${encodeURIComponent(cartera)}`).then((r) => setPosiciones(r.posiciones || [])); }, [cartera]);
  const tl = d.linea_tiempo || [];
  const franjas = [];
  let inicio = null;
  tl.forEach((p, i) => {
    if (p.regimen === 1 && inicio === null) inicio = p.fecha;
    if ((p.regimen !== 1 || i === tl.length - 1) && inicio !== null) {
      franjas.push({ type: "rect", xref: "x", yref: "paper", x0: inicio, x1: p.fecha,
                     y0: 0, y1: 1, fillcolor: c.negativo, opacity: 0.10, line: { width: 0 } });
      inicio = null;
    }
  });
  const aperturas = sel === "__cartera__" ? [] :
    (posiciones || []).filter((p) => p.ticker === sel).map((p) => p.buy_date);
  return (
    <>
      <div className="kpis">
        <Kpi etiqueta={t("Régimen actual", "Current regime")} valor={t(d.regimen_actual, d.regimen_actual === "calma" ? "calm" : "tension")}
             tono={d.regimen_actual === "calma" ? "pos" : "neg"} />
        <Kpi etiqueta={t("Tiempo en tensión", "Time in tension")} valor={pct(d.pct_tension, 1)}
             sub={t(`de ${d.dias_clasificados} ruedas`, `of ${d.dias_clasificados} sessions`)} />
        <Kpi etiqueta={t("Cambios de régimen", "Regime changes")} valor={d.transiciones?.length ?? 0} />
      </div>
      <div className="panel">
        <h3>{t("Volatilidad y miedo del mercado", "Market volatility and fear")}
          <select value={sel} onChange={(e) => setSel(e.target.value)} style={{ marginLeft: "auto" }}>
            <option value="__cartera__">{t("Cartera completa", "Whole portfolio")}</option>
            {(activos?.por_activo || []).map((x) =>
              <option key={x.ticker} value={x.ticker}>{x.ticker}</option>)}
          </select>
        </h3>
        <Grafico alto={380}
          datos={[
            sel === "__cartera__"
              ? { type: "scatter", mode: "lines", name: t("volatilidad de tu cartera", "your portfolio's volatility"),
                  x: tl.map((p) => p.fecha), y: tl.map((p) => p.vol_cartera),
                  line: { color: c.acento, width: 1.8 } }
              : { type: "scatter", mode: "lines", name: t(`retorno diario · ${sel}`, `daily return · ${sel}`),
                  x: (activos.series[sel] || []).map((p) => p.fecha),
                  y: (activos.series[sel] || []).map((p) => p.ret),
                  line: { color: c.acento, width: 0.9 } },
            ...(sel === "__cartera__" ? [{ type: "scatter", mode: "lines", name: t("umbral de tensión", "tension threshold"),
              x: tl.map((p) => p.fecha), y: tl.map((p) => p.umbral),
              line: { color: c.texto3, width: 1, dash: "dot" } }] : []),
            { type: "scatter", mode: "lines", name: t("VIX (miedo global)", "VIX (global fear)"),
              x: tl.map((p) => p.fecha), y: tl.map((p) => p.vix),
              yaxis: "y2", line: { color: c.series[3], width: 1.2 } },
            { type: "scatter", mode: "markers", name: t("eventos", "events"),
              x: (d.eventos || []).map((e) => e.fecha),
              y: (d.eventos || []).map(() => 0), yaxis: "y2",
              marker: { symbol: "diamond", size: 9,
                        color: (d.eventos || []).map((e) => e.alcance === "AR" ? c.series[3] : c.series[4]) },
              text: (d.eventos || []).map((e) => eventoDescripcion(e.descripcion)),
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
                              width: 0.7, dash: "dot" } })),
                      ...aperturas.map((f) => ({
                        type: "line", x0: f, x1: f, yref: "paper", y0: 0, y1: 1,
                        opacity: 0.6, line: { color: "#f59e0b", width: 1.5 } }))],
                    yaxis: { title: t(sel === "__cartera__" ? "Volatilidad anual" : "Retorno diario",
                                      sel === "__cartera__" ? "Annual volatility" : "Daily return"),
                             ticksuffix: " %" },
                    yaxis2: { title: "VIX", overlaying: "y", side: "right", showgrid: false } }} />
        <div className="pie">
          {d.metodo} {t("Las líneas verticales son los eventos macro —pasá el mouse por los rombos "
            + "para leerlos—; las franjas rojas, los períodos de tensión.",
            "The vertical lines are macro events —hover the diamonds with the mouse to read "
            + "them—; the red bands are the periods of tension.")}
        </div>
      </div>
      <div className="panel">
        <h3>{t("Qué pasaba alrededor", "What was happening around it")}</h3>
        <div className="tabla-wrap"><table>
          <thead><tr><th>{t("Fecha", "Date")}</th><th className="c">{t("Alcance", "Scope")}</th>
            <th>{t("Evento", "Event")}</th></tr></thead>
          <tbody>{(d.eventos || []).slice().reverse().map((e, i) => (
            <tr key={i}><td className="mono">{e.fecha}</td>
              <td><span className="chip">{alcanceLabel(e.alcance)}</span></td><td>{eventoDescripcion(e.descripcion)}</td></tr>))}</tbody>
        </table></div>
        <div className="pie">{d.nota_eventos}</div>
      </div>
    </>
  );
}

/* ── Stress ── */
function Stress({ d }) {
  const filas = d.escenarios || [];
  const conProxy = filas.some((e) => e.proxies?.length);
  const parcial = filas.some((e) => e.cobertura_pct != null && e.cobertura_pct < 99.5
                                    && e.pnl_pct != null);
  return (
    <div className="panel">
      <h3>{t(`Qué le habría pasado a esta cartera en ${filas.length} crisis reales`,
             `What would have happened to this portfolio in ${filas.length} real crises`)}</h3>
      <div className="tabla-wrap"><table>
        <thead><tr><th>{t("Escenario", "Scenario")}</th><th>{t("Período", "Period")}</th>
                   <th>{t("Qué pasó", "What happened")}</th>
                   <th className="n">{t("Impacto", "Impact")}</th><th className="n">{t("En dólares", "In dollars")}</th>
                   <th className="n">{t("Cartera cubierta", "Portfolio covered")}</th></tr></thead>
        <tbody>{filas.map((e, i) => (
          <tr key={i}>
            <td><b>{escenarioLabel(e.nombre)}</b></td>
            <td className="mono" style={{ fontSize: 12 }}>{e.desde} → {e.hasta}</td>
            <td style={{ fontSize: 12.5, color: "var(--texto-2)" }}>
              {escenarioLabel(e.descripcion)}
              {e.proxies?.length > 0 && (
                <s style={{ display: "block", textDecoration: "none", color: "var(--texto-3)",
                            fontSize: 11.5, marginTop: 3 }}>
                  {t(`con la historia de ${e.proxies.join(", ")}, que en esa fecha todavía no `
                    + `tenían CEDEAR acá`,
                    `using the history of ${e.proxies.join(", ")}, which didn't have a CEDEAR `
                    + `here yet at that date`)}</s>)}
            </td>
            <td className={"n " + signo(e.pnl_pct)}>{e.pnl_pct == null ? "—" : pct(e.pnl_pct)}</td>
            <td className={"n " + signo(e.pnl_usd)}>{e.pnl_usd == null ? "—" : usd(e.pnl_usd)}</td>
            <td className="n">
              {e.pnl_pct == null ? <span style={{ color: "var(--texto-3)", fontSize: 12 }}>{e.nota}</span>
               : e.cobertura_pct >= 99.5 ? pct(100, 0)
               : <span className="chip ojo">{pct(e.cobertura_pct, 0)}</span>}
            </td>
          </tr>))}</tbody>
      </table></div>
      <div className="pie">
        {t("Se aplican los retornos reales de esas ventanas a tu cartera de hoy.",
           "The actual returns of those windows are applied to your current portfolio.")}
        {conProxy && (
          <> {t(`Cuando un CEDEAR todavía no listaba acá se usa la historia del papel que `
            + `representa: el ratio de conversión es constante y se cancela en el retorno, así que `
            + `lo que se pierde es el spread local de esos días. En una crisis global iban para el `
            + `mismo lado; en una crisis argentina —las PASO, una devaluación— el papel de afuera `
            + `no la sintió igual, y ese escenario conviene leerlo con reservas.`,
            `When a CEDEAR wasn't listed here yet, the history of the stock it represents is `
            + `used: the conversion ratio is constant and cancels out in the return, so what's `
            + `lost is the local spread of those days. In a global crisis they moved the same `
            + `way; in an Argentine crisis —the PASO primaries, a devaluation— the foreign stock `
            + `didn't feel it the same way, and that scenario is worth reading with caution.`)}</>)}
        {parcial && (
          <> {t(`Cuando falta la historia de algún activo, el escenario corre con los que sí `
            + `estaban y los pesos se reparten entre ellos: la columna dice qué porción de la `
            + `cartera quedó representada, y el monto en dólares corresponde solo a esa porción.`,
            `When some asset's history is missing, the scenario runs with the ones that were `
            + `there and the weights are redistributed among them: the column says what portion of `
            + `the portfolio was represented, and the dollar amount corresponds only to that portion.`)}</>)}
      </div>
    </div>
  );
}

/* ═══════════════ Modo 2 · Comparación ═══════════════ */

function Comparacion({ carteras, cartera, sim }) {
  const [sel, setSel] = useState([]);
  const [d, setD] = useState(null);
  const [cargando, setCargando] = useState(false);
  const [conSim, setConSim] = useState(false);
  const c = colores();
  // Con una simulación puesta, la cartera simulada es un competidor más. No
  // existe en ningún lado: la arma el servidor en memoria para esta comparación.
  const simulada = cartera && sim?.length ? `${cartera} + simulación` : null;
  const cuantas = sel.length + (conSim && simulada ? 1 : 0);

  const alternar = (n) => setSel((s) => s.includes(n) ? s.filter((x) => x !== n) : [...s, n]);

  const comparar = async () => {
    setCargando(true); setD(null);
    setD(await api("/api/comparar", { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ carteras: sel,
                             sim_sobre: conSim && simulada ? cartera : null }) }));
    setCargando(false);
  };

  return (
    <>
      <div className="panel" style={{ marginBottom: 14 }}>
        <h3>{t("Elegí dos o más carteras", "Choose two or more portfolios")}</h3>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginTop: 8 }}>
          {carteras.map((x) => (
            <button key={x.nombre} className={"btn" + (sel.includes(x.nombre) ? " primario" : "")}
                    onClick={() => alternar(x.nombre)}>{x.nombre}</button>
          ))}
          {simulada && (
            <button className={"btn" + (conSim ? " primario" : "")}
                    title={t("Tu cartera con los activos que estás simulando", "Your portfolio with the assets you're simulating")}
                    onClick={() => setConSim((v) => !v)}>{simulada}</button>)}
          <button className="lab-trazo" disabled={cuantas < 2 || cargando}
                  onClick={comparar} style={{ marginLeft: "auto" }}>
            <svg><rect x="1" y="1" width="98%" height="90%" rx="6" pathLength="100" /></svg>
            {cargando ? t("Comparando…", "Comparing…") : t("Comparar", "Compare")}
          </button>
        </div>
      </div>

      {cargando && <div className="cargando">{t("Alineando series y corriendo las pruebas…", "Aligning series and running the tests…")}</div>}
      {d?.error && <div className="aviso mal">{d.error}</div>}
      {d && !d.error && <ResultadoComparacion d={d} c={c} />}
      {!d && !cargando && <div className="vacio">
        {t("Elegí al menos dos carteras. Se comparan sobre el período que ambas comparten, "
          + "y se prueba si la diferencia es real o puede ser azar.",
          "Choose at least two portfolios. They're compared over the period they share, "
          + "and it's tested whether the difference is real or could be chance.")}
        {simulada && <><br />{t("Con la simulación puesta podés medir", "With the simulation applied you can measure")}{" "}
          <b>{cartera}</b> {t("contra", "against")}{" "}
          <b>{simulada}</b> {t("sin duplicar nada.", "without duplicating anything.")}</>}
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
        {concluyente ? t(`Gana ${lider}`, `${lider} wins`) : t(`${lider} lidera, pero con reparos`, `${lider} leads, but with caveats`)}
        <span className={"chip " + (concluyente ? "ok" : "ojo")} style={{ marginLeft: 8 }}>
          {concluyente ? t("diferencia demostrable", "provable difference") : t("no concluyente", "inconclusive")}</span>
      </h3>

      <div style={{ fontSize: 14.5, color: "var(--texto-2)", lineHeight: 1.7, marginTop: 10 }}>
        <p style={{ margin: "0 0 10px" }}>
          <b>{lider}</b> {t(`gana ${gana.puntos} de 8 criterios: ${gana.cuales.join(", ")}. Rindió`,
                            `wins ${gana.puntos} out of 8 criteria: ${gana.cuales.join(", ")}. It returned`)}{" "}
          <b>{pct(m.retorno_anual_pct)}</b> {t("anual con", "annual with")} <b>{pct(m.volatilidad_anual_pct)}</b>{" "}
          {t("de volatilidad, o sea", "of volatility, i.e.")} <b>{num(m.sharpe, 2)}</b>{" "}
          {t("de Sharpe, y su peor caída fue", "Sharpe, and its worst drawdown was")}{" "}
          <b className="neg">{pct(m.max_drawdown_pct)}</b>.
        </p>

        {sostenidas.length > 0 && (
          <p style={{ margin: "0 0 10px" }}>
            <b className="pos">{t("La ventaja se sostiene", "The edge holds up")}</b>{" "}
            {t("contra", "against")} {sostenidas.join(" y ")}: {t("la probabilidad de que esa diferencia "
              + "sea casualidad es menor al 5 %.", "the probability that this difference is chance is below 5 %.")}
          </p>)}

        {dudosas.length > 0 && (
          <p style={{ margin: "0 0 10px" }}>
            <b className="neg">{t(`Pero contra ${dudosas.join(" y ")} no se puede afirmar nada.`,
                                  `But against ${dudosas.join(" and ")} nothing can be said.`)}</b>{" "}
            {rivales.filter((r) => !r.concluyente).map((r) => (
              <span key={r.contra}>
                {t(`Le saca ${num(r.diferencia_anual, 2)} de Sharpe, pero las dos se mueven casi `
                  + `igual (correlación ${num(r.correlacion, 2)}) y con ${r.n_ruedas} ruedas esa `
                  + `diferencia aparece por azar ${pct(r.p_valor * 100, 0)} de las veces.`,
                  `It beats it by ${num(r.diferencia_anual, 2)} of Sharpe, but the two move almost `
                  + `the same (correlation ${num(r.correlacion, 2)}) and with ${r.n_ruedas} sessions that `
                  + `difference shows up by chance ${pct(r.p_valor * 100, 0)} of the time.`)}{" "}
              </span>))}
          </p>)}

        <p style={{ margin: 0, color: "var(--texto-3)", fontSize: 13.5 }}>
          {concluyente
            ? t("Con estos datos, elegir esa cartera está respaldado por la evidencia.",
                "With this data, choosing that portfolio is backed by the evidence.")
            : t("Cuando dos carteras comparten activos, sus resultados se parecen y hace falta "
              + "mucha más historia para separarlas. Si tenés que elegir igual, mirá la que menos "
              + "cae y la que menos depende de un solo activo — eso se sostiene aunque el Sharpe no.",
              "When two portfolios share assets, their results look similar and it takes much "
              + "more history to tell them apart. If you have to choose anyway, look at the one that "
              + "drops the least and depends the least on a single asset — that holds up even when Sharpe doesn't.")}
        </p>
      </div>
    </div>
  );
}

/* ── Comparación · las tres preguntas que la tabla de métricas no contesta ──
   Los tres paneles:
   hacia dónde puede ir cada cartera, cuánto se pierde en los días feos, y si lo
   que estás por comprar diversifica o es más de lo mismo. */

function MonteCarloComparado({ mc, nombres, c }) {
  const carteras = nombres.filter((n) => mc?.carteras?.[n]);
  if (carteras.length < 2) return null;

  // Primero todas las bandas y después todas las medianas: Plotly dibuja en
  // orden, y una banda posterior taparía la línea de la cartera anterior.
  const base = mc.base || 100;
  const sobre = (a) => a.map((v) => Math.max(v, base));
  const bajo = (a) => a.map((v) => Math.min(v, base));
  const muda = (y) => ({ type: "scatter", mode: "lines", x: [], y, line: { width: 0 },
                         showlegend: false, hoverinfo: "skip" });

  const bandas = [], lineas = [];
  carteras.forEach((n, i) => {
    const s = mc.carteras[n], col = c.series[i % c.series.length];
    const banda = (alto, bajo_, color) => {
      bandas.push({ ...muda(alto), x: s.dias });
      bandas.push({ ...muda(bajo_), x: s.dias, fill: "tonexty", fillcolor: color });
    };
    // La banda se parte en la base: arriba es el color de la cartera, abajo es
    // rojo. Es plata perdida, y en toda la app lo que cae bajo el umbral se
    // pinta rojo — que el abanico no lo hiciera lo volvía un dibujo bonito.
    banda(sobre(s.p95), sobre(s.p5), rgba(col, 0.16));
    banda(bajo(s.p95), bajo(s.p5), rgba(c.negativo, 0.17));
    lineas.push({ type: "scatter", mode: "lines", name: n, x: s.dias, y: s.mediana,
                  line: { color: col, width: 2.2 },
                  hovertemplate: `${n} · ${t("rueda", "session")} %{x} · %{y:.1f}<extra></extra>` });
  });
  const datos = [...bandas, ...lineas];

  return (
    <div className="panel">
      <h3>{t(`Adónde puede ir cada una · ${mc.horizonte} ruedas`, `Where each one could go · ${mc.horizonte} sessions`)}</h3>
      <Grafico alto={340} datos={datos}
        layout={{ yaxis: { title: t(`base ${base}`, `base ${base}`) }, xaxis: { title: t("ruedas", "sessions") },
                  shapes: [{ type: "line", xref: "paper", x0: 0, x1: 1, y0: base, y1: base,
                             line: { color: c.negativo, width: 1, dash: "dot" } }] }} />
      <div className="tabla-wrap"><table>
        <thead><tr><th>{t("Cartera", "Portfolio")}</th>
          <th className="n">{t("Mal año (p5)", "Bad year (p5)")}</th><th className="n">{t("Mediana", "Median")}</th>
          <th className="n">{t("Buen año (p95)", "Good year (p95)")}</th><th className="n">{t("Peor 1 %", "Worst 1 %")}</th>
          <th className="n">{t("Termina perdiendo", "Ends up losing")}</th></tr></thead>
        <tbody>{carteras.map((n, i) => {
          const f = mc.carteras[n].final;
          return (
            <tr key={n}>
              <td><span style={{ display: "inline-block", width: 9, height: 9, borderRadius: 2,
                                 background: c.series[i % c.series.length], marginRight: 7 }} />{n}</td>
              <td className={"n " + (f.p5 < 100 ? "neg" : "pos")}>{num(f.p5, 1)}</td>
              <td className={"n " + (f.mediana < 100 ? "neg" : "pos")}>{num(f.mediana, 1)}</td>
              <td className="n pos">{num(f.p95, 1)}</td>
              <td className="n neg">{num(f.peor_1_pct, 1)}</td>
              <td className="n">{pct(f.prob_perdida_pct, 1)}</td>
            </tr>);
        })}</tbody>
      </table></div>
      <div className="pie">
        {mc.simulaciones.toLocaleString(IDIOMA === "en" ? "en-US" : "es-AR")}{" "}
        {t(`trayectorias por cartera, motor ${mc.motor}`, `paths per portfolio, ${mc.motor} engine`)}
        {" "}{t("(colas gordas),", "(fat tails),")} <b>{t("la misma semilla y el mismo período para todas",
          "the same seed and the same period for all of them")}</b>:{" "}
        {t(`lo que separa a los abanicos es la cartera, no la suerte del sorteo. Va en base 100 y no en `
          + `dólares porque las carteras tienen tamaños distintos — en plata compararías cuánto `
          + `tenés, no cómo se comporta lo que tenés. La banda es el 90 % central: uno de cada `
          + `veinte años termina por encima, y uno de cada veinte por debajo. Lo que cae bajo la `
          + `base va en rojo: ahí abajo estás perdiendo plata, y cuánta banda queda de ese lado `
          + `es la comparación que importa.`,
          `what separates the fans is the portfolio, not the luck of the draw. It's in base 100 and not `
          + `dollars because the portfolios have different sizes — in money you'd be comparing how much `
          + `you have, not how what you have behaves. The band is the central 90 %: one year out of `
          + `twenty ends above it, and one out of twenty below. What falls below the base is shown in `
          + `red: down there you're losing money, and how much band is left on that side `
          + `is the comparison that matters.`)}
      </div>
    </div>
  );
}

function RiesgoComparado({ M, nombres }) {
  const carteras = nombres.filter((n) => M[n]);
  if (carteras.length < 2) return null;

  // Es la misma barra de Riesgo, con las mismas zonas y el mismo límite de
  // política: la comparación se lee en dónde queda la aguja de cada cartera.
  // Una sola escala para todas —como entre VaR y CVaR en Análisis—, porque si
  // cada barra se ajusta a lo suyo, dos agujas en el mismo lugar dejan de
  // significar lo mismo y la comparación miente.
  const escala = Math.max(ZONAS.escala, Math.ceil(1.15 * Math.max(
    ...carteras.flatMap((n) => [Math.abs(M[n].var95_pct || 0),
                                Math.abs(M[n].cvar95_pct || 0)]))));

  return (
    <div className="panel">
      <h3>{t("Los días feos, lado a lado", "The ugly days, side by side")}</h3>
      {[["var95_pct", t("Día malo", "Bad day"), t("VaR 95 % · 1 rueda de cada 20", "VaR 95 % · 1 session out of 20")],
        ["cvar95_pct", t("Día muy malo", "Very bad day"), t("CVaR 95 % · el promedio de ese 5 % peor", "CVaR 95 % · the average of that worst 5 %")]]
        .map(([k, titulo, detalle]) => (
          <div key={k}>
            <Seccion titulo={`${titulo} · ${detalle}`} />
            {carteras.map((n) => (
              <BarraRiesgo key={n} etiqueta={n} escala={escala} pct_={M[n][k]} />))}
          </div>))}
      <div className="pie">
        {t(`Las mismas zonas y el mismo límite de ${pct(ZONAS.limite, 1)} que en Riesgo: es una `
          + `política —cuánto estás dispuesto a perder en un día, decidido antes de que pase—, `
          + `no un cálculo. Acá va en porcentaje y no en dólares, así dos carteras de tamaños `
          + `distintos se comparan igual, y sobre el período común. El VaR dice el piso de ese `
          + `5 % de días; el CVaR, lo que se pierde en promedio cuando se cruza — siempre peor, `
          + `y es el número que importa cuando el día malo llega.`,
          `The same zones and the same ${pct(ZONAS.limite, 1)} limit as in Risk: it's a `
          + `policy —how much you're willing to lose in a day, decided before it happens—, `
          + `not a calculation. Here it's in percentage and not dollars, so two portfolios of `
          + `different sizes compare evenly, and over the shared period. VaR says the floor of that `
          + `worst 5 % of days; CVaR, what's lost on average when it's crossed — always worse, `
          + `and it's the number that matters when the bad day arrives.`)}
      </div>
    </div>
  );
}

function CorrelacionComparada({ corr, nombres }) {
  if (!corr) return null;
  const conSim = nombres.filter((n) => corr[n]?.simulados?.length);
  const filas = nombres.filter((n) => corr[n]);
  if (!filas.length) return null;
  const caracterEn = (v) => v < 0.3 ? "defensive" : v < 0.6 ? "mixed" : "aggressive";
  const caracterEs = (v) => v < 0.3 ? "defensiva" : v < 0.6 ? "mixta" : "agresiva";

  return (
    <div className="panel">
      <h3>{t("¿Lo que sumás diversifica, o es más de lo mismo?", "Does what you're adding diversify, or is it more of the same?")}</h3>
      <div className="tabla-wrap"><table>
        <thead><tr><th>{t("Cartera", "Portfolio")}</th><th className="n">{t("Activos", "Assets")}</th>
          <th className="n">{t("Correlación media", "Average correlation")}</th><th>{t("Cómo se mueve", "How it moves")}</th></tr></thead>
        <tbody>{filas.map((n) => {
          const x = corr[n];
          return (
            <tr key={n}>
              <td>{n}</td>
              <td className="n">{x.activos}</td>
              <td className="n">{num(x.media_pares, 3)}
                {x.delta != null && (
                  <span className={x.delta < 0 ? " pos" : x.delta > 0 ? " neg" : ""}>
                    {" "}({x.delta > 0 ? "+" : ""}{num(x.delta, 3)})</span>)}</td>
              <td><span className={"chip " + (x.media_pares < 0.3 ? "ok"
                                              : x.media_pares < 0.6 ? "ojo" : "mal")}>
                {t(caracterEs(x.media_pares), caracterEn(x.media_pares))}
              </span></td>
            </tr>);
        })}</tbody>
      </table></div>

      {conSim.map((n) => (
        <div key={n} style={{ marginTop: 14 }}>
          <div className="aviso ojo">{corr[n].lectura}</div>
          <div className="tabla-wrap"><table>
            <thead><tr><th>{t("Activo simulado", "Simulated asset")}</th><th className="n">{t("Peso", "Weight")}</th>
              <th className="n">{t("Correlación con el resto", "Correlation with the rest")}</th>
              <th>{t("Qué aporta", "What it contributes")}</th></tr></thead>
            <tbody>{corr[n].simulados.map((a) => (
              <tr key={a.ticker}>
                <td className="mono">{a.ticker}</td>
                <td className="n">{pct(a.peso_pct, 1)}</td>
                <td className="n">{num(a.correlacion, 3)}</td>
                <td><span className={"chip " + (a.efecto === "diversifica" ? "ok"
                                                : a.efecto === "acompaña" ? "ojo" : "mal")}>
                  {a.efecto === "diversifica" ? t("diversifica", "diversifies")
                   : a.efecto === "acompaña" ? t("acompaña", "tags along") : t("repite riesgo", "repeats risk")}</span></td>
              </tr>))}</tbody>
          </table></div>
        </div>))}

      <div className="pie">
        {t(`La correlación media entre pares dice si la cartera se comporta como una sola cosa: `
          + `por debajo de 0,3 los activos se mueven bastante por su cuenta y la diversificación `
          + `es real; por encima de 0,6 en una caída no hay dónde refugiarse. La segunda tabla `
          + `mide cada activo simulado contra`,
          `The average pairwise correlation says whether the portfolio behaves as a single thing: `
          + `below 0.3 the assets move fairly independently and the diversification is real; `
          + `above 0.6, in a drop there's nowhere to hide. The second table `
          + `measures each simulated asset against`)} <b>{t("el resto de la cartera", "the rest of the portfolio")}</b>,{" "}
        {t(`que es lo que decide si vale la pena: por debajo de 0,3 aporta algo distinto, por `
          + `encima de 0,7 estás comprando dos veces el mismo riesgo. Ojo con leer sólo el promedio `
          + `— un papel que diversifica puede casi no moverlo si la cartera ya estaba diversificada.`,
          `which is what decides if it's worth it: below 0.3 it adds something different, above `
          + `0.7 you're buying the same risk twice. Careful reading only the average `
          + `— a stock that diversifies may barely move it if the portfolio was already diversified.`)}
      </div>
    </div>
  );
}

function ResultadoComparacion({ d, c }) {
  const nombres = d.carteras;
  const p = d.periodo_comun;
  const concluyente = (d.pruebas_sharpe || []).every((x) => x.concluyente);

  // El cuarto valor dice hacia dónde está lo bueno: +1 más alto gana, −1 más
  // bajo gana. En peor caída y día malo los números son negativos, así que el
  // mayor —el menos negativo— es el mejor.
  const FILAS = [
    ["retorno_anual_pct", t("Retorno anual", "Annual return"), (v) => pct(v), 1],
    ["volatilidad_anual_pct", t("Volatilidad", "Volatility"), (v) => pct(v), -1],
    ["sharpe", "Sharpe", (v) => num(v, 3), 1],
    ["sortino", "Sortino", (v) => num(v, 3), 1],
    ["calmar", "Calmar", (v) => num(v, 3), 1],
    ["max_drawdown_pct", t("Peor caída", "Worst drawdown"), (v) => pct(v), 1],
    ["var95_pct", t("Día malo", "Bad day"), (v) => pct(v), 1],
    ["curtosis_exceso", t("Curtosis", "Kurtosis"), (v) => num(v, 2), -1],
  ];

  const M = d.metricas || {};
  // Cada eje se llama por la virtud y los de riesgo van dados vuelta, así que
  // el polígono más grande es la mejor cartera. La tabla de al lado los repite
  // en crudo, con su signo, para el que quiera el número y no la comparación.
  const ejesRadar = [
    { et: t("Retorno", "Return"), col: t("Retorno anual", "Annual return"), mas: true, fmt: (v) => pct(v, 1), k: "retorno_anual_pct" },
    { et: "Sharpe", col: "Sharpe", mas: true, fmt: (v) => num(v, 3), k: "sharpe" },
    { et: t("Estabilidad", "Stability"), col: t("Volatilidad", "Volatility"), mas: false,
      fmt: (v) => pct(v, 1) + t(" anual", " annual"), k: "volatilidad_anual_pct" },
    { et: t("Aguante", "Resilience"), col: t("Peor caída", "Worst drawdown"), mas: false, fmt: (v) => pct(v, 1),
      k: "max_drawdown_pct" },
    { et: t("Día malo", "Bad day"), col: t("Día malo", "Bad day"), mas: false, fmt: (v) => pct(v, 2), k: "var95_pct" },
  ];
  // Peor caída y día malo llegan en negativo: sin el valor absoluto, "menos es
  // mejor" premiaría justo a la que más cae.
  const valores = (n) => ejesRadar.map((e) => e.k.startsWith("max_") || e.k.startsWith("var")
                                              ? Math.abs(M[n][e.k]) : M[n][e.k]);
  const seriesRadar = nombres.filter((n) => M[n]).map((n, i) => ({
    nombre: n, color: c.series[i % c.series.length], vals: valores(n) }));

  return (
    <>
      <VeredictoComparacion d={d} concluyente={concluyente} />

      {seriesRadar.length > 1 && (
        <div className="panel">
          <h3>{t("Quién gana en qué", "Who wins at what")}</h3>
          <div className="lab-radarfila">
            <div><Radar ejes={ejesRadar} series={seriesRadar} alto={270} /></div>
            <div className="tabla-wrap"><table>
              <thead><tr><th>{t("Cartera", "Portfolio")}</th>
                {ejesRadar.map((e) => <th key={e.et} className="n">{e.col}</th>)}</tr></thead>
              <tbody>{seriesRadar.map((s) => (
                <tr key={s.nombre}>
                  <td><span style={{ display: "inline-block", width: 9, height: 9, borderRadius: 2,
                                     background: s.color, marginRight: 7 }} />{s.nombre}</td>
                  {ejesRadar.map((e) => {
                    const crudo = M[s.nombre][e.k];
                    return (
                      <td key={e.et} className={"n " + (e.k === "retorno_anual_pct" ? signo(crudo)
                                                       : crudo < 0 ? "neg" : "")}>
                        {e.k.endsWith("_pct") ? pct(crudo, e.k === "var95_pct" ? 2 : 1)
                                              : num(crudo, 3)}
                      </td>);
                  })}
                </tr>))}</tbody>
            </table></div>
          </div>
          <div className="pie">
            {t(`Cada eje va de la peor a la mejor de las carteras elegidas, no en escala absoluta: `
              + `sirve para ver quién gana en qué, no cuánto vale cada número. Los tres ejes de `
              + `riesgo van dados vuelta —estabilidad es poca volatilidad, aguante es poca caída, `
              + `día malo es poca pérdida—, así que en los cinco vale lo mismo:`,
              `Each axis runs from the worst to the best of the chosen portfolios, not on an `
              + `absolute scale: it's for seeing who wins at what, not how much each number is worth. `
              + `The three risk axes are flipped —stability is low volatility, resilience is a small `
              + `drawdown, bad day is a small loss—, so all five mean the same thing:`)}
            <b>{t(" más lejos del centro es mejor", " farther from the center is better")}</b>.{" "}
            {t("La tabla los muestra como se los cita, con su signo.",
               "The table shows them as they're usually quoted, with their sign.")}
          </div>
        </div>)}

      <div className="fila f2">
        <div className="panel">
          <h3>{t("Evolución comparada · base 100", "Compared evolution · base 100")}</h3>
          <Grafico alto={330}
            datos={nombres.map((n, i) => ({
              type: "scatter", mode: "lines", name: n,
              x: (d.curva_valor || []).map((f) => f.fecha),
              y: (d.curva_valor || []).map((f) => f[n]),
              line: { color: c.series[i % c.series.length], width: 2 },
            }))} />
          <div className="pie">
            {t(`Período común: ${p.desde} → ${p.hasta} (${p.ruedas} ruedas). Comparar sobre `
              + `historias de distinta longitud compara épocas del mercado, no estrategias.`,
              `Shared period: ${p.desde} → ${p.hasta} (${p.ruedas} sessions). Comparing over `
              + `histories of different length compares market eras, not strategies.`)}
          </div>
        </div>

        <div className="panel">
          <h3>{t("¿La ventaja es real?", "Is the edge real?")}</h3>
          <div className="tabla-wrap"><table>
            <thead><tr><th>{t(`${d.lider_por_criterios} contra`, `${d.lider_por_criterios} against`)}</th>
              <th className="n">Δ Sharpe</th>
                       <th className="n">{t("Correlación", "Correlation")}</th><th className="n">p</th>
                       <th>{t("Conclusión", "Conclusion")}</th></tr></thead>
            <tbody>{(d.pruebas_sharpe || []).map((pr, i) => (
              <tr key={i}>
                <td>{pr.contra}</td>
                <td className="n">{num(pr.diferencia_anual, 3)}</td>
                <td className="n">{num(pr.correlacion, 2)}</td>
                <td className="n">{pr.p_valor == null ? "—" : num(pr.p_valor, 3)}</td>
                <td><span className={"chip " + (pr.concluyente ? "ok" : "ojo")}>
                  {pr.concluyente ? t("significativa", "significant") : t("no concluyente", "inconclusive")}</span></td>
              </tr>))}</tbody>
          </table></div>
          <div className="pie">
            {t("Prueba de Jobson-Korkie con corrección de Memmel. Cuando dos carteras "
              + "comparten activos su correlación es alta, y una diferencia que parece grande "
              + "puede no distinguirse del ruido.",
              "Jobson-Korkie test with Memmel's correction. When two portfolios "
              + "share assets their correlation is high, and a difference that looks large "
              + "may not be distinguishable from noise.")}
          </div>
        </div>
      </div>

      <MonteCarloComparado mc={d.montecarlo} nombres={nombres} c={c} />
      <RiesgoComparado M={M} nombres={nombres} />
      <CorrelacionComparada corr={d.correlacion} nombres={nombres} />

      <div className="panel">
        <h3>{t("Tabla comparativa", "Comparison table")}</h3>
        <div className="tabla-wrap"><table>
          <thead><tr><th>{t("Métrica", "Metric")}</th>{nombres.map((n) => (
            <th key={n} className="n">{n}{n === d.lider_por_criterios ? " ★" : ""}</th>))}</tr></thead>
          <tbody>
            {FILAS.map(([k, et, f, dir]) => {
              const vals = nombres.map((n) => d.metricas[n][k]);
              const mejor = dir > 0 ? Math.max(...vals) : Math.min(...vals);
              return (
                <tr key={k}><td>{et}</td>
                  {nombres.map((n) => {
                    const gana = d.metricas[n][k] === mejor;
                    return (
                      <td key={n} className={"n" + (gana ? " lab-gana" : "")}
                          title={gana ? t("mejor de las comparadas", "best of those compared") : undefined}>
                        {f(d.metricas[n][k])}</td>);
                  })}
                </tr>);
            })}
            <tr><td>{t("Criterios ganados", "Criteria won")}</td>
              {(() => {
                const tope = Math.max(...nombres.map((n) => d.criterios_ganados[n].puntos));
                return nombres.map((n) => (
                  <td key={n} className={"n" + (d.criterios_ganados[n].puntos === tope ? " lab-gana" : "")}>
                    {d.criterios_ganados[n].puntos} / 8</td>));
              })()}</tr>
          </tbody>
        </table></div>
      </div>

      <div className="fila f2">
        <div className="panel">
          <h3>{t("Cuánto se puede confiar en cada Sharpe", "How much each Sharpe can be trusted")}</h3>
          <div className="tabla-wrap"><table>
            <thead><tr><th>{t("Cartera", "Portfolio")}</th><th className="n">{t("Sharpe medido", "Measured Sharpe")}</th>
                       <th className="n">{t("Podría estar entre", "Could be between")}</th>
                       <th className="n">{t("Ancho", "Width")}</th></tr></thead>
            <tbody>{nombres.map((n) => {
              const i = d.intervalos_confianza[n]?.sharpe || {};
              const ancho = i.ic95_alto != null ? i.ic95_alto - i.ic95_bajo : null;
              return (<tr key={n}><td>{n}</td><td className="n">{num(i.observado, 3)}</td>
                <td className="n">{num(i.ic95_bajo, 2)} {t("a", "to")} {num(i.ic95_alto, 2)}</td>
                <td className="n">{ancho == null ? "—" : num(ancho, 2)}</td></tr>);
            })}</tbody>
          </table></div>
          <div className="pie">
            {t(`El Sharpe que ves no es un dato exacto: es una`, `The Sharpe you see isn't an exact figure: it's an`)}{" "}
            <b>{t("estimación", "estimate")}</b>{" "}
            {t(`hecha con las ruedas que hubo. Con otras ruedas —el mismo mercado, otro tramo— habría dado `
              + `distinto. La columna del medio es el`,
              `made with the sessions there were. With other sessions —same market, different stretch— it `
              + `would have come out different. The middle column is the`)} <b>{t("intervalo al 95 %", "95 % interval")}</b>:{" "}
            {t(`remuestreando las ruedas reales mil veces, en 95 de cada 100 reconstrucciones el Sharpe cae adentro `
              + `de ese rango. Cuanto más ancho, menos historia hay detrás — un ancho de más de `
              + `1 punto de Sharpe quiere decir que el número todavía no está para decidir nada.`,
              `resampling the actual sessions a thousand times, in 95 out of 100 reconstructions the Sharpe falls inside `
              + `that range. The wider it is, the less history is behind it — a width of more than `
              + `1 point of Sharpe means the number still isn't ready to decide anything.`)}
            {(() => {
              const pares = [];
              for (let a = 0; a < nombres.length; a++)
                for (let b = a + 1; b < nombres.length; b++) {
                  const A = d.intervalos_confianza[nombres[a]]?.sharpe;
                  const B = d.intervalos_confianza[nombres[b]]?.sharpe;
                  if (A?.ic95_alto == null || B?.ic95_alto == null) continue;
                  if (A.ic95_bajo <= B.ic95_alto && B.ic95_bajo <= A.ic95_alto)
                    pares.push(`${nombres[a]} y ${nombres[b]}`);
                }
              return pares.length
                ? <> {t("Acá se superponen los intervalos de", "Here the intervals of")} <b>{pares.join(", ")}</b>:{" "}
                    {t("con esta historia no alcanza para decir cuál es mejor, por más que sus Sharpe "
                      + "difieran en el papel.", "overlap: with this much history it's not enough to say which "
                      + "is better, however much their Sharpe ratios differ on paper.")}</>
                : <> {t("Ningún par se superpone, así que el orden entre estas carteras se sostiene con los "
                      + "datos que hay.", "No pair overlaps, so the ranking between these portfolios holds up "
                      + "with the data there is.")}</>;
            })()}
          </div>
        </div>

        <div className="panel">
          <h3>{t("Descontando que comparaste varias", "Accounting for comparing several")}</h3>
          <div className="tabla-wrap"><table>
            <thead><tr><th>{t("Cartera", "Portfolio")}</th><th className="n">Sharpe</th>
                       <th className="n">{t("Le alcanzaba con", "It would have needed")}</th>
                       <th className="n">{t("Probabilidad de ser real", "Probability of being real")}</th></tr></thead>
            <tbody>{nombres.map((n) => {
              const s = d.sharpe_deflactado[n] || {};
              return (<tr key={n}><td>{n}</td>
                <td className="n">{num(s.sharpe_anual, 3)}</td>
                <td className="n">{num(s.umbral_azar_anual, 3)}</td>
                <td className={"n " + (s.dsr >= 0.95 ? "pos" : s.dsr < 0.8 ? "neg" : "")}>
                  {s.dsr == null ? "—" : pct(s.dsr * 100, 1)}</td>
              </tr>);
            })}</tbody>
          </table></div>
          <div className="pie">
            {t(`Comparar varias carteras y quedarse con la mejor infla el resultado: entre más `
              + `candidatas, más chance de que una destaque`, `Comparing several portfolios and keeping the `
              + `best one inflates the result: the more candidates, the more chance one stands out`)}{" "}
            <b>{t("por casualidad", "by chance")}</b>.{" "}
            {t(`La columna del medio es el Sharpe que habría sacado la mejor de `
              + `${d.sharpe_deflactado?.[nombres[0]]?.n_pruebas || nombres.length} carteras hechas de puro `
              + `ruido — todo lo que no supere ese umbral no prueba nada. `
              + `La última es el`,
              `The middle column is the Sharpe the best of `
              + `${d.sharpe_deflactado?.[nombres[0]]?.n_pruebas || nombres.length} portfolios made of pure `
              + `noise would have gotten — anything that doesn't beat that threshold proves nothing. `
              + `The last one is the`)} <b>{t("Sharpe deflactado", "deflated Sharpe")}</b> (Bailey y López de Prado):{" "}
            {t("la probabilidad de que la habilidad sea real y no el premio a haber probado mucho. "
              + "Los tres tramos, que son los que pintan la columna:",
              "the probability that the skill is real and not the prize for having tried a lot. "
              + "The three tiers, which is what colors the column:")}
            <b>{t(" 95 % o más", " 95 % or more")}</b>{" "}
            {t("el resultado se sostiene solo;", "the result holds up on its own;")}
            <b>{t(" entre 80 % y 95 %", " between 80 % and 95 %")}</b>{" "}
            {t("probablemente real, pero convendría más historia;", "probably real, but more history would help;")}
            <b>{t(" menos de 80 %", " less than 80 %")}</b>{" "}
            {t("no alcanza para descartar la casualidad.", "isn't enough to rule out chance.")}
            {(() => {
              const flojas = nombres.filter((n) => (d.sharpe_deflactado[n]?.dsr ?? 1) < 0.8);
              return flojas.length
                ? <> {t(`Acá no llega${flojas.length > 1 ? "n" : ""}`,
                        `${flojas.length > 1 ? "These don't" : "This one doesn't"} make it:`)}{" "}
                    <b>{flojas.join(", ")}</b>.</>
                : null;
            })()}
          </div>
        </div>
      </div>
    </>
  );
}

/* ═══════════════ Carteras y Conectores ═══════════════ */

function Carteras({ carteras, recargar, cartera, setCartera }) {
  const [sel, setSel] = useState(null);
  const [defecto, setDefecto] = useState(() => carteraDefecto.leer() || "");
  const [filas, setFilas] = useState([]);
  const [msg, setMsg] = useState(null);
  const [destino, setDestino] = useState("");

  // "" = la plaza se deduce sola de los activos. Con valor, el usuario dijo otra
  // cosa y eso manda: es el único dato de la cartera que sus posiciones no
  // pueden contar.
  const [plazaFija, setPlazaFija] = useState("");
  const [ret, setRet] = useState({});
  const [registro, setRegistro] = useState(null);
  const meta = carteras.find((x) => x.nombre === sel);
  const plazaActiva = plazaFija || meta?.mercado || "AR";

  const abrir = async (n) => {
    setSel(n); setMsg(null);
    const m = carteras.find((x) => x.nombre === n);
    setPlazaFija(m?.mercado_fijado ? m.mercado : "");
    setRet(LAB ? await api(`/api/carteras/${encodeURIComponent(n)}/retenciones`) : {});
    setRegistro(null);
    setFilas(await api(`/api/carteras/${encodeURIComponent(n)}`));
  };
  const guardar = async () => {
    const r = await api(`/api/carteras/${encodeURIComponent(sel)}`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ posiciones: filas }) });
    if (r.error) { setMsg({ mal: r.error }); recargar(); return; }
    const p = await api(`/api/carteras/${encodeURIComponent(sel)}/mercado`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mercado: plazaFija || null }) });
    if (LAB) {
      const rr = await api(`/api/carteras/${encodeURIComponent(sel)}/retenciones`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(ret) });
      if (rr.error) { setMsg({ mal: rr.error }); return; }
    }
    setMsg({ ok: t(`Guardadas ${r.guardadas} posiciones · se mide desde `
                 + `${MERCADOS[p.mercado || plazaActiva].nombre}`
                 + `${p.mercado_fijado ? "" : " (deducido de los activos)"}.`,
                 `Saved ${r.guardadas} positions · measured from `
                 + `${MERCADOS[p.mercado || plazaActiva].nombre_en}`
                 + `${p.mercado_fijado ? "" : " (inferred from the assets)"}.`) });
    recargar();
  };
  const subir = async (archivo, ruta) => {
    const destinoFinal = (destino || sel || "").trim();
    if (!destinoFinal) { setMsg({ mal: t("Elegí o escribí una cartera de destino.", "Choose or type a destination portfolio.") }); return; }
    const fd = new FormData(); fd.append("file", archivo);
    const r = await api(`/api/carteras/${encodeURIComponent(destinoFinal)}/${ruta}`,
                        { method: "POST", body: fd });
    if (r.error) { setMsg({ mal: r.error }); return; }
    setMsg({ ok: t(`${r.agregadas} agregadas, ${r.omitidas} ya estaban.`
                 + (r.cerradas_por_venta ? ` ${r.cerradas_por_venta} lotes cerrados por venta fueron al P&L realizado (${usd(r.pnl_realizado_usd)}).` : ""),
                 `${r.agregadas} added, ${r.omitidas} were already there.`
                 + (r.cerradas_por_venta ? ` ${r.cerradas_por_venta} lots closed by sale went to the realized P&L (${usd(r.pnl_realizado_usd)}).` : "")) });
    recargar(); abrir(destinoFinal);
  };
  const editar = (i, campo, v) =>
    setFilas((f) => f.map((x, j) => (j === i ? { ...x, [campo]: v } : x)));

  const fijarDefecto = (n) => {
    setDefecto(n);
    carteraDefecto.poner(n);
    if (n) setCartera(n);           // se aplica ya, sin recargar la página
  };

  return (
    <>
      <div className="panel" style={{ marginBottom: 14 }}>
        <h3>{t("Carteras", "Portfolios")}</h3>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginTop: 8 }}>
          {carteras.map((x) => (
            <button key={x.nombre} className={"btn" + (sel === x.nombre ? " primario" : "")}
                    title={x.mercado ? t(`Se abre en ${MERCADOS[x.mercado].nombre}`, `Opens in ${MERCADOS[x.mercado].nombre_en}`) : undefined}
                    onClick={() => abrir(x.nombre)}>
              {x.mercado && MERCADOS[x.mercado].bandera + " "}{x.nombre}{" "}
              <span style={{opacity:.6}}>({x.posiciones})</span></button>
          ))}
          <button className="btn" onClick={() => {
            const n = prompt(t("Nombre de la cartera nueva:", "Name of the new portfolio:"));
            if (n) { setSel(n.trim()); setFilas([]); setMsg({ ok: t("Cartera nueva: agregá activos y guardá.",
                                                                    "New portfolio: add assets and save.") }); }
          }}>+ {t("Nueva", "New")}</button>
          <a className="btn" href="/api/plantilla" style={{ textDecoration: "none", marginLeft: "auto" }}>
            {t("Descargar plantilla CSV", "Download CSV template")}
          </a>
        </div>
        {carteras.length > 1 && (
          <div style={{ display: "flex", gap: 8, alignItems: "center",
                        flexWrap: "wrap", marginTop: 12 }}>
            <span className="pie" style={{ margin: 0 }}>{t("Cartera por defecto", "Default portfolio")}</span>
            <select value={defecto} onChange={(e) => fijarDefecto(e.target.value)}>
              <option value="">{t("— la primera —", "— the first one —")}</option>
              {carteras.map((x) => (
                <option key={x.nombre} value={x.nombre}>{x.nombre}</option>))}
            </select>
            <span className="pie" style={{ margin: 0 }}>
              {t("Es la que se abre sola al entrar. Con una sola cartera no hace falta: "
                + "esa es. Queda guardada en este navegador.",
                "It's the one that opens automatically when you enter. With a single portfolio "
                + "it's not needed: that one is it. It's saved in this browser.")}
            </span>
          </div>
        )}
      </div>

      <div className="panel" style={{ marginBottom: 14 }}>
        <h3>{t("Importar", "Import")}</h3>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center", marginTop: 8 }}>
          <input type="text" placeholder={t("cartera de destino", "destination portfolio")} value={destino}
                 onChange={(e) => setDestino(e.target.value)} style={{ minWidth: 170 }} />
          <label className="lab-barrido">{t("Formato propio", "Native format")}
            <input type="file" accept=".csv" hidden
                   onChange={(e) => e.target.files[0] && subir(e.target.files[0], "importar")} />
          </label>
          <label className="btn yahoo">{t("Importar de", "Import from")} <b>yahoo!</b> finance
            <input type="file" accept=".csv" hidden
                   onChange={(e) => e.target.files[0] && subir(e.target.files[0], "importar-yahoo")} />
          </label>
        </div>
        <div className="pie">
          {t("Del CSV de Yahoo solo entra lo que sigue abierto: las ventas netean FIFO contra "
            + "las compras más viejas y lo cerrado va al P&amp;L realizado.",
            "From Yahoo's CSV only what's still open comes in: sales are netted FIFO against "
            + "the oldest purchases and what's closed goes to the realized P&amp;L.")}
        </div>
      </div>

      {msg && <div className={"aviso " + (msg.mal ? "mal" : "ok")}>{msg.mal || msg.ok}</div>}

      {sel && (
        <div className="panel">
          <h3>{sel}</h3>
          {/* Desde dónde se mira esta cartera. Normalmente lo dicen los activos
              —.BA es Argentina, ASML.AS es Europa— y no hay nada que elegir; el
              chip está para lo que ninguna posición puede decir: un europeo con
              acciones de EE.UU. las mide igual en euros. */}
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center",
                        margin: "10px 0 2px" }}>
            <span className="pie" style={{ margin: 0 }}>{t("Se mide desde", "Measured from")}</span>
            {Object.entries(MERCADOS).map(([k, m]) => (
              <button key={k} className={"chip-plaza" + (plazaActiva === k ? " on" : "")}
                      onClick={() => setPlazaFija(k)}>{m.bandera} {t(m.nombre, m.nombre_en)}</button>
            ))}
            {plazaFija && (
              <button className="btn" onClick={() => setPlazaFija("")}
                      title={t("Volver a deducirla de los activos", "Go back to inferring it from the assets")}>
                        {t("automática", "automatic")}</button>)}
          </div>
          <div className="pie" style={{ marginBottom: 12 }}>
            {plazaFija ? t("Elegida a mano: se guarda con la cartera.", "Chosen by hand: it's saved with the portfolio.")
                       : t("Deducida de dónde cotizan los activos.", "Inferred from where the assets trade.")}
            {" "}{t("Manda la moneda de todos los números, la tasa libre de riesgo y el "
              + "índice con el que abre.",
              "It sets the currency for every number, the risk-free rate and the "
              + "index it opens with.")}
          </div>
          {LAB && (<>
            <div className="tabla-wrap" style={{ maxWidth: 520, margin: "10px 0 2px" }}><table>
              <thead><tr><th>{t("Retención", "Withholding")}</th><th className="n">{t("Acciones", "Stocks")}</th>
                <th className="n">CEDEARs</th><th className="n">{t("Bonos", "Bonds")}</th></tr></thead>
              <tbody>{[["dividendos", t("Dividendos y renta", "Dividends and income")],
                       ["ventas", t("Resultado de venta", "Sale result")]].map(([c, etq]) => (
                <tr key={c}><td>{etq}</td>
                  {["acciones", "cedears", "bonos"].map((k) => (
                    <td key={k} className="n">
                      <input type="text" inputMode="decimal" placeholder="0" aria-label={`${etq} · ${k}`}
                             value={ret[c]?.[k] ?? ""} style={{ width: 56, textAlign: "right" }}
                             onChange={(e) => setRet({ ...ret, [c]: { ...ret[c], [k]: soloNum(e.target.value) } })} />
                      {" "}%</td>))}
                </tr>))}</tbody>
            </table></div>
            <div className="pie" style={{ marginBottom: 12 }}>
              {t("Lo que te descuentan sobre lo que cobrás y sobre lo que ganás al vender, según "
                + "el tipo de papel. En blanco es cero. Depende del país de la empresa y de dónde "
                + "vivís —un CEDEAR de EE.UU. no retiene lo mismo que uno de Brasil—, así que no "
                + "trae valores sugeridos: poné los de tu resumen. Se guarda con la cartera.",
                "What's withheld from what you collect and from what you gain when you sell, by "
                + "the type of stock. Blank is zero. It depends on the company's country and where "
                + "you live —a US CEDEAR doesn't withhold the same as a Brazilian one—, so it "
                + "doesn't come with suggested values: enter the ones from your statement. It's saved with the portfolio.")}
            </div>
            {/* Control: lo que de verdad se retuvo en cada cobro. Se pide al abrirlo,
                porque los cargados a mano buscan su bruto en Yahoo. */}
            <details style={{ marginBottom: 12 }}
                     onToggle={(e) => e.currentTarget.open && !registro &&
                       api(`/api/carteras/${encodeURIComponent(sel)}/retenciones/registro`).then(setRegistro)}>
              <summary style={{ cursor: "pointer", fontSize: 13 }}>{t("Registro de retenciones", "Withholding record")}</summary>
              {!registro ? <div className="cargando">{t("Buscando los brutos…", "Looking up gross amounts…")}</div>
                : registro.error ? <div className="aviso mal">{registro.error}</div>
                : registro.length === 0 ? <div className="vacio">{t("Esta cartera no tiene dividendos cobrados.",
                                                                     "This portfolio has no dividends collected.")}</div>
                : <div className="tabla-wrap" style={{ maxWidth: 620 }}><table>
                    <thead><tr><th>{t("Fecha", "Date")}</th><th>Ticker</th><th className="n">{t("Bruto", "Gross")}</th>
                      <th className="n">{t("Retención aplicada", "Withholding applied")}</th><th className="n">%</th></tr></thead>
                    {[["acciones", t("Acciones", "Stocks")], ["cedears", "CEDEARs"], ["bonos", t("Bonos", "Bonds")]].map(([k, etq]) => {
                      const filas = registro.filter((f) => f.clase === k);
                      return filas.length > 0 && (
                        <tbody key={k}>
                          <tr><td colSpan={5} style={{ fontWeight: 600, background: "var(--panel-2)" }}>
                            {etq} <span style={{ color: "var(--texto-3)", fontWeight: 400 }}>({filas.length})</span></td></tr>
                          {filas.map((f, i) => (
                            <tr key={i}>
                              <td className="mono">{f.fecha}</td><td className="mono">{f.ticker}</td>
                              <td className="n">{f.bruto == null ? "—" : `${num(f.bruto, 2)} ${f.moneda}`}</td>
                              <td className="n">{f.retencion == null ? "—" : `${num(Math.abs(f.retencion) < 0.005 ? 0 : f.retencion, 2)} ${f.moneda}`}</td>
                              <td className="n">{f.retencion_pct == null ? "—" : pct(Math.abs(f.retencion_pct) < 0.05 ? 0 : f.retencion_pct, 1)}</td>
                            </tr>))}
                        </tbody>);
                    })}
                  </table></div>}
              <div className="pie">
                {t("Bruto según Yahoo por la cantidad del cobro; retención es lo que falta hasta lo "
                  + "registrado como cobrado.", "Gross according to Yahoo for the amount collected; withholding is "
                  + "what's missing up to what's recorded as collected.")} <b>0 %</b>{" "}
                {t("quiere decir que ese dividendo está anotado al bruto: corregilo en Posiciones "
                  + "cerradas con ✎.", "means that dividend is recorded at gross: fix it in Closed positions with ✎.")}
              </div>
            </details>
          </>)}
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", margin: "8px 0 12px" }}>
            <button className="btn primario" onClick={guardar}>{t("Guardar", "Save")}</button>
            <button className="btn" onClick={() => setFilas((f) => [...f, {
              ticker: "", buy_date: "", buy_price: 0, qty: 0, commissions: 0,
              source: "", currency: "", asset_type: "", notes: "" }])}>+ {t("Activo", "Asset")}</button>
            <a className="lab-barrido"
               href={`/api/carteras/${encodeURIComponent(sel)}/exportar`}>{t("Exportar CSV", "Export CSV")}</a>
            <button className="btn peligro" style={{ marginLeft: "auto" }} onClick={async () => {
              if (!confirm(t(`¿Eliminar la cartera "${sel}"?`, `Delete the portfolio "${sel}"?`))) return;
              await api(`/api/carteras/${encodeURIComponent(sel)}`, { method: "DELETE" });
              setSel(null); setFilas([]); recargar();
            }}>{t("Eliminar", "Delete")}</button>
          </div>
          <div className="tabla-wrap"><table>
            <thead><tr><th>Ticker</th><th>{t("Fecha", "Date")}</th><th className="n">{t("Precio", "Price")}</th>
                       <th className="n">{t("Cantidad", "Quantity")}</th><th className="n">{t("Comisiones", "Commissions")}</th>
                       <th>{t("Origen", "Source")}</th><th>{t("Moneda", "Currency")}</th>
                       <th>{t("Notas", "Notes")}</th><th></th></tr></thead>
            <tbody>{filas.map((f, i) => (
              <tr key={i}>
                {[["ticker", 100], ["buy_date", 100]].map(([k, w]) => (
                  <td key={k}><input type="text" value={f[k] || ""} style={{ width: w }}
                        onChange={(e) => editar(i, k, e.target.value)} /></td>))}
                {["buy_price", "qty", "commissions"].map((k) => (
                  <td key={k} className="n"><input type="text" inputMode="decimal" value={f[k] ?? 0} style={{ width: 96 }}
                        onChange={(e) => editar(i, k, soloNum(e.target.value))} /></td>))}
                <td><input type="text" value={f.source || ""} placeholder="cocos" style={{ width: 70 }}
                      onChange={(e) => editar(i, "source", e.target.value)} /></td>
                <td><input type="text" value={f.currency || ""} placeholder={t("auto", "auto")} style={{ width: 60 }}
                      onChange={(e) => editar(i, "currency", e.target.value)} /></td>
                <td><input type="text" value={f.notes || ""} style={{ width: 110 }}
                      onChange={(e) => editar(i, "notes", e.target.value)} /></td>
                <td><button className="btn peligro" style={{ padding: "3px 8px" }}
                      onClick={() => setFilas((x) => x.filter((_, j) => j !== i))}>✕</button></td>
              </tr>))}</tbody>
          </table></div>
          <div className="pie">
            <b>{t("Origen", "Source")}</b>: {t("poné", "put")} <code>cocos</code>{" "}
            {t("si es un bono u ON — marca que cotiza cada 100 nominales.",
               "if it's a bond or note — marks that it trades per 100 nominal units.")}{" "}
            <b>{t("Moneda", "Currency")}</b>: {t("solo si la detección automática se equivoca con ese ticker.",
                                                 "only if the automatic detection gets that ticker wrong.")}
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

function Fmp({ f, brk, recargar }) {
  const [key, setKey] = useState("");
  const [msg, setMsg] = useState(null);
  const [yendo, setYendo] = useState(false);

  // En la web la clave de FMP la ponemos nosotros y es la misma para todos: el
  // usuario no tiene nada que cargar ni que saber. Sólo ve que está andando.
  if (brk?.modo === "web") return (
    <div className="panel">
      <Ficha f={f} />
      <div className="pie">
        La clave la provee la aplicación: no tenés que sacar ninguna ni configurar
        nada. {f.conectado
          ? "Está activa y los precios objetivo de analistas se muestran solos."
          : "Ahora mismo no responde; los objetivos salen de yfinance mientras tanto."}
      </div>
    </div>
  );

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

  // Modo web: no hay vault ni credenciales en el servidor, y conectar el broker
  // es opcional. Lo único que existe es el sobre de este navegador.
  if (brk?.modo === "web") return (
    <div className="panel">
      <Ficha f={f} />
      {f.conectado ? (
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <button className="btn peligro"
                  onClick={() => { sesion.tirar(); location.reload(); }}>
            Desconectar Cocos</button>
          <span className="pie" style={{ margin: 0 }}>
            {f.cuenta ? `Cuenta ${f.cuenta}.` : "Sesión activa."} Tu contraseña no
            está guardada en ningún lado: la sesión vive en este navegador y vence
            a las 24 horas.
          </span>
        </div>
      ) : (
        <EntrarCocos onEntrar={recargar} />
      )}
    </div>
  );

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

// El bookmarklet corre DENTRO de la pestaña de InvIU, con su propio origen:
// ahí `localStorage` es el de InvIU, no el nuestro, así que puede leer los
// tokens que la SPA de InvIU ya dejó después de un login común y silvestre —
// nada que automatizar, nada que instalar. Es la misma búsqueda que hace
// `_login_navegador` en Python, calcada a JS de una línea.
function bookmarkletInviu() {
  const fn = function () {
    let t = null;
    Object.entries(localStorage).forEach(([k, v]) => {
      if (!/token/i.test(k)) return;
      try {
        const j = JSON.parse(v);
        if (j && j.idToken && j.refreshToken) t = j;
      } catch (e) { /* no era JSON */ }
    });
    if (!t) {
      alert("No encontré una sesión de InvIU en esta pestaña. Iniciá sesión en InvIU y volvé a hacer clic.");
      return;
    }
    const b = btoa(JSON.stringify(t));
    window.open("__ORIGEN__/#inviu-web=" + encodeURIComponent(b), "_blank");
  };
  return "javascript:" + encodeURIComponent(
    "(" + fn.toString().replace("__ORIGEN__", location.origin) + ")();");
}

/* Modo web de InvIU: dos caminos, ninguno pasa la contraseña por acá.

   1. El bookmarklet: arrastralo a los marcadores, entrá a InvIU y logueate
      como siempre en tu navegador de todos los días —nada que instalar—, y
      con esa pestaña abierta hacé clic en el marcador. Lee los tokens que ya
      quedaron en el localStorage de InvIU y abre esta pantalla con el
      código cargado.
   2. `python -m core.broker.inviu_sesion_web`, para quien prefiere hacer el
      login desde una terminal en vez de tocar los marcadores del navegador.

   En los dos casos el servidor valida los tokens una vez contra InvIU y los
   devuelve envueltos en un sobre firmado que vive en ESTE navegador; no los
   guarda. */
function InviuWeb({ f, recargar }) {
  const [blob, setBlob] = useState("");
  const [msg, setMsg] = useState(null);
  const [yendo, setYendo] = useState(false);

  // El script local, al terminar, abre esta misma pantalla con el código en
  // `#inviu-web=...`: el fragmento nunca se manda al servidor, solo lo lee
  // este JavaScript. Se precarga el campo y se borra el fragmento enseguida
  // —no debe quedar un token dando vueltas en la URL ni en el historial—;
  // el envío en sí sigue siendo un clic aparte, no automático.
  useEffect(() => {
    const m = /^#inviu-web=(.+)$/.exec(location.hash);
    if (!m) return;
    try { setBlob(decodeURIComponent(m[1])); } catch { /* fragmento roto: se ignora */ }
    history.replaceState(null, "", location.pathname + location.search);
  }, []);

  const usar = async () => {
    let jwt;
    try {
      jwt = JSON.parse(atob(blob.trim()));
    } catch {
      setMsg(["mal", "Eso no es lo que copiaste de tu máquina local — revisá que esté completo."]);
      return;
    }
    setYendo(true); setMsg(null);
    const r = await post("/api/inviu/web/sesion", jwt);
    setYendo(false);
    if (r.error) { setMsg(["mal", r.error]); return; }
    sesionInviu.poner(r.sobre);
    setBlob("");
    recargar();
  };

  const salir = () => { sesionInviu.tirar(); recargar(); };

  return (
    <div className="panel">
      <Ficha f={f} />
      {f.conectado ? (
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <button className="btn peligro" onClick={salir}>Desconectar</button>
          <span className="pie" style={{ margin: 0 }}>
            {f.cuenta ? `Cuenta ${f.cuenta}.` : "Sesión activa."} Vive solo en este
            navegador — el servidor no la guarda. Cuando venza (hasta 24 h, o antes si
            InvIU la rechaza), hay que repetir este paso.
          </span>
        </div>
      ) : (
        <div style={{ display: "grid", gap: 14 }}>
          <div className="aviso">
            <b>Conectar InvIU, en 4 pasos</b>
            <ol style={{ margin: "8px 0 0 20px", padding: 0, display: "grid", gap: 6 }}>
              <li><b>Arrastrá</b> el botón <b>🔖 Conectar InvIU</b> de acá abajo a la barra
                de marcadores de tu navegador. Se hace una sola vez — después queda ahí
                para siempre, como cualquier otro marcador.</li>
              <li>Abrí InvIU en <b>otra pestaña</b> y entrá con tu usuario y clave, exactamente
                como cualquier día. Tu clave nunca pasa por acá: se tipea directo en la
                página real de InvIU, nunca en esta app.</li>
              <li>Con esa pestaña de InvIU todavía abierta, hacé clic en el marcador que
                guardaste. Se abre esta pantalla de nuevo, en una pestaña nueva, con el
                código ya cargado solo.</li>
              <li>Apretá <b>"Usar esta sesión"</b> ahí abajo. Listo — InvIU queda conectado.</li>
            </ol>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <a className="btn primario" href={bookmarkletInviu()}
               onClick={(e) => e.preventDefault()}
               title="Arrastrame a tus marcadores, no me hagas clic acá">
              🔖 Conectar InvIU
            </a>
            <span className="pie" style={{ margin: 0 }}>
              ☝️ Ese es el paso 1: arrastralo (no le hagas clic).
            </span>
          </div>
          <textarea rows={3} value={blob} onChange={(e) => setBlob(e.target.value)}
                    placeholder="El marcador completa esto solo al volver del paso 3. No hace falta tocar este campo a mano."
                    style={{ fontFamily: "monospace", fontSize: 12 }} />
          <button className="btn primario" disabled={yendo || !blob.trim()} onClick={usar}>
            {yendo ? "Validando…" : "Usar esta sesión"}
          </button>
          <div className="pie">
            <b>¿Por qué un marcador y no un botón acá mismo?</b> Porque esta pantalla y la de
            InvIU son sitios distintos, y ningún sitio puede leer los datos de otro — es la
            protección más básica que tiene tu navegador. El marcador funciona porque se
            ejecuta parado en la pestaña de InvIU, con sus propios permisos, en el momento en
            que vos lo apretás.
          </div>
          <div className="pie">
            <b>Alternativa sin marcadores:</b> desde una terminal, con Python y esta app
            clonada, <code>python -m core.broker.inviu_sesion_web</code> pide tu usuario y
            clave, hace el login en una ventana real y trae el código acá solo.
          </div>
          <div className="pie">
            En los dos caminos viajan únicamente los tokens que InvIU ya emitió — nunca tu
            usuario ni tu clave — y este servidor los valida una sola vez contra InvIU antes
            de devolverlos envueltos en un código firmado que queda solo en este navegador.
            No quedan copiados en ningún lado del lado del servidor.
          </div>
        </div>
      )}
      {msg && <div className={"aviso " + msg[0]}>{msg[1]}</div>}
    </div>
  );
}

/* InvIU no tiene formulario de contraseña acá: el login exige un reCAPTCHA
   real de Google, que solo un navegador de verdad puede resolver. El botón
   abre un Chrome aparte con la página oficial de InvIU — la contraseña y el
   código que llega por mail se tipean ahí, nunca en esta app — y esta
   pantalla sondea el estado hasta que se resuelve. */
function Inviu({ f, brk, recargar }) {
  const [msg, setMsg] = useState(null);
  const [yendo, setYendo] = useState(false);
  const pollRef = useRef(null);
  // React exige el mismo número de hooks en cada render de un mismo
  // componente — así que el corte hacia `InviuWeb` tiene que ir DESPUÉS de
  // declararlos todos, nunca antes: `brk` llega en `null` en el primer
  // render y recién trae "web" cuando responde `/api/broker/estado`, y ese
  // cambio de rama a mitad de vida disparaba "Rendered fewer hooks than
  // expected" (error #300) si el `return` cortaba antes del `useEffect`.
  useEffect(() => () => clearInterval(pollRef.current), []);

  // El login (el reCAPTCHA) sigue haciendo falta hacerlo en la máquina local,
  // que tiene pantalla; el servidor no. Lo que viaja a la web son solo los
  // tokens ya obtenidos —nunca la contraseña—, y quedan en un sobre firmado
  // en ESTE navegador, igual que el de Cocos: el servidor no los guarda en
  // ningún lado, ni un instante más de lo que tarda en atender cada request.
  if (brk?.modo === "web") return <InviuWeb f={f} recargar={recargar} />;

  const empezarPoll = () => {
    clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      const e = await api("/api/inviu/estado");
      if (e.detalle !== "esperando login en el navegador") {
        clearInterval(pollRef.current);
        setYendo(false);
        recargar();
      }
    }, 2000);
  };

  const conectar = async () => {
    setYendo(true); setMsg(null);
    const r = await post("/api/inviu/conectar", {});
    if (r.conectado) { setYendo(false); recargar(); return; }
    if (r.error) { setYendo(false); setMsg(["mal", r.error]); return; }
    setMsg(["ojo", "Se abrió una ventana de Chrome con la página de InvIU — " +
                   "logueate ahí con tu usuario, tu contraseña y el código que " +
                   "te llega por mail. Esta pantalla lo detecta sola."]);
    empezarPoll();
  };

  const salir = async () => { await post("/api/inviu/desconectar"); setMsg(null); recargar(); };
  const borrar = async () => {
    if (!confirm("¿Borrar la sesión de InvIU guardada?")) return;
    await post("/api/inviu/borrar"); setMsg(null); recargar();
  };

  return (
    <div className="panel">
      <Ficha f={f} />
      {f.conectado ? (
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <button className="btn peligro" onClick={salir}>Desconectar</button>
          <button className="btn peligro" onClick={borrar}>Borrar sesión</button>
          <span className="pie" style={{ margin: 0 }}>
            {f.cuenta ? `Cuenta ${f.cuenta}.` : "Sesión activa."} Se reconecta sola
            mientras la sesión no venza; no hace falta volver a loguearse cada vez.
          </span>
        </div>
      ) : (
        <div style={{ display: "grid", gap: 7 }}>
          <button className="btn primario" disabled={yendo} onClick={conectar}>
            {yendo ? "Esperando login en el navegador…" : "Conectar InvIU"}
          </button>
          <div className="pie">
            Tu contraseña y tu código de mail se tipean en la ventana de Chrome que
            se abre, nunca acá. La sesión queda guardada cifrada para las próximas veces.
          </div>
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
  // Un error del servidor llega como {error: ...} y no trae las listas. Sin esta
  // guarda, el .find() de abajo tiraba TypeError y se caía la app entera.
  if (d.error || !Array.isArray(d.con_credencial))
    return <div className="aviso mal">{d.error || "No se pudieron leer las fuentes."}</div>;
  const fuente = (t) => d.con_credencial.find((f) => f.nombre.includes(t)) || {};

  return (
    <>
      <div className="aviso">
        Ninguna de las tres es obligatoria: sin ellas la aplicación funciona igual, con
        menos cobertura.
      </div>
      <div className="fila f2">
        <Cocos f={fuente("Cocos")} brk={brk} recargar={cargar} />
        <Fmp f={fuente("Financial Modeling")} brk={brk} recargar={cargar} />
      </div>
      <div style={{ marginBottom: 14 }}>
        <Inviu f={fuente("InvIU")} brk={brk} recargar={cargar} />
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
  const [impRes, setImpRes] = useState(null);     // importación del resultado cerrado
  const [ops, setOps] = useState(null);           // compras y ventas apareadas
  const [impOps, setImpOps] = useState(null);     // importación de posiciones / cerradas

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
    setTenFci(null); setImportando(null); setImpRes(null);
    setOps(null); setImpOps(null); setSinImportar(null);
    api("/api/cocos/resumen").then((r) => {
      if (r.error) { setErr(r.error); return; }
      setD(r);
      if (!r.conectado) return;
      traerMovs(0);
      api("/api/cocos/fci").then((f) => {
        setFci(f);
        if (f.cartera) setDestino((prev) => prev || f.cartera);
      });
      api("/api/cocos/operaciones").then((o) => {
        setOps(o);
        if (o.cartera) setDestino((prev) => prev || o.cartera);
      });
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

  // Qué operaciones cerradas NO van. Arranca con las que la cartera ya tiene
  // cargadas: importarlas de nuevo cuenta el resultado dos veces, así que el
  // caso sano es el que viene tildado, y destildar es una decisión explícita.
  const [sinImportar, setSinImportar] = useState(null);
  const fuera = sinImportar ?? new Set((ops?.ya_cerradas || []).map((c) => c.clave));
  const alternar = (clave) => {
    const s = new Set(fuera);
    s.has(clave) ? s.delete(clave) : s.add(clave);
    setSinImportar(s);
  };

  const importarOps = (que) => {
    setImpOps({ estado: "yendo", que });
    const cuerpo = { cartera: destino };
    if (que === "cerradas") {
      cuerpo.solo = (ops.cerrados || []).map((c) => c.clave).filter((k) => !fuera.has(k));
    }
    api(`/api/cocos/operaciones/${que}`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cuerpo),
    }).then((r) => setImpOps({ ...r, que }));
  };

  const importarResultadoFci = () => {
    setImpRes({ estado: "yendo" });
    api("/api/cocos/fci/resultados/importar", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cartera: destino }),
    }).then((r) => setImpRes(r));
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

      {/* ── Compras y ventas: la cartera y la historia, por separado ── */}
      {ops && !ops.error && ((ops.abiertos || []).length > 0 || (ops.cerrados || []).length > 0) &&
       (() => {
        const cuantasCerradas = (ops.cerrados || []).filter((c) => !fuera.has(c.clave)).length;
        return (
        <div className="panel" style={{ marginBottom: 14 }}>
          <h3>Compras y ventas · lo que tenés y lo que ya cerraste</h3>

          {/* Lo que hay que saber ANTES de apretar nada. */}
          {(ops.ya_cargados || []).length > 0 && (
            <div className="aviso ojo">
              <b>{ops.cartera}</b> ya tiene cargados a mano {ops.ya_cargados.length} de estos
              papeles: <b className="mono">{ops.ya_cargados.join(", ")}</b>. Importar
              las posiciones <b>no los pisa</b> —lo cargado a mano no se toca nunca— así que
              quedarían <b>dos veces</b> y la cartera valdría el doble. Borralos antes, o
              importá sólo las operaciones cerradas.
            </div>)}
          {(ops.ya_cerradas || []).length > 0 && (
            <div className="aviso ojo">
              <b>{ops.ya_cerradas.length} de estas operaciones cerradas ya están cargadas</b> en{" "}
              {ops.cartera}: {ops.ya_cerradas.map((c) => `${c.ticker} ${c.sell_date} × ${num(c.qty, 0)}`).join(" · ")}.
              El deduplicado no las ve —vienen con otros precios, porque una convierte de una
              forma y la otra con el MEP— así que <b>el resultado se contaría dos veces</b>.
              Borrá las que ya tenés antes de importar, con la ✕ de la tabla de cerradas.
            </div>)}
          {(ops.control || []).length > 0 && (
            <div className="aviso ojo">
              <b>El historial no cuadra con la cuenta</b> en {ops.control.length}{" "}
              {ops.control.length === 1 ? "papel" : "papeles"}:{" "}
              {ops.control.map((c) => `${c.ticker} (broker ${num(c.broker, 0)}, historial ${num(c.historial, 0)})`).join(" · ")}.
              Suele ser historial que no llega hasta la primera compra.
            </div>)}
          {ops.cortado && (
            <div className="aviso ojo">Historial recortado: faltan movimientos viejos y el
              apareo puede quedar incompleto.</div>)}

          <div className="tabla-wrap"><table>
            <thead><tr>
              <th>Ticker</th><th>Compra</th><th>Venta</th><th className="n">Cantidad</th>
              <th className="n">Precio compra</th><th className="n">Precio venta</th>
              <th className="n">Resultado</th>
            </tr></thead>
            <tbody>
              {(ops.abiertos || []).map((a, i) => (
                <tr key={"a" + i}>
                  <td className="mono"><b>{a.ticker}</b>
                    <span className="chip ok" style={{ marginLeft: 6, minWidth: 0 }}>abierta</span></td>
                  <td className="mono">{a.buy_date}</td>
                  <td style={{ color: "var(--texto-3)" }}>—</td>
                  <td className="n">{num(a.qty, 2)}</td>
                  <td className="n">{usd(a.buy_price, 4)}</td>
                  <td className="n">—</td><td className="n">—</td>
                </tr>))}
              {(ops.cerrados || []).map((c, i) => (
                <tr key={"c" + i} style={fuera.has(c.clave) ? { opacity: .45 } : undefined}>
                  <td className="mono">
                    <label style={{ display: "inline-flex", alignItems: "center", gap: 6,
                                    cursor: "pointer" }}
                           title={fuera.has(c.clave) ? "No se importa" : "Se importa"}>
                      <input type="checkbox" checked={!fuera.has(c.clave)}
                             onChange={() => alternar(c.clave)} />
                      {c.ticker}
                    </label></td>
                  <td className="mono">{c.buy_date}</td>
                  <td className="mono">{c.sell_date}</td>
                  <td className="n">{num(c.qty, 2)}</td>
                  <td className="n">{usd(c.buy_price, 4)}</td>
                  <td className="n">{usd(c.sell_price, 4)}</td>
                  <td className={"n " + signo(c.pnl)}>{usd(c.pnl)}</td>
                </tr>))}
              {(ops.cerrados || []).length > 0 && (
                <tr style={{ fontWeight: 700 }}>
                  <td colSpan={6}>Resultado de lo cerrado</td>
                  <td className={"n " + signo(ops.cerrados.reduce((s, c) => s + c.pnl, 0))}>
                    {usd(ops.cerrados.reduce((s, c) => s + c.pnl, 0))}</td>
                </tr>)}
            </tbody>
          </table></div>

          <div style={{ borderTop: "1px solid var(--borde)", marginTop: 12, paddingTop: 12,
                        display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <span style={{ fontSize: 13 }}>Llevar a la cartera</span>
            <select value={destino} onChange={(e) => setDestino(e.target.value)}
                    disabled={!!ops.cartera}>
              <option value="">elegí una…</option>
              {(ops.carteras || []).map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
            <button className="btn" disabled={!destino || impOps?.estado === "yendo"
                                              || !(ops.abiertos || []).length}
                    onClick={() => importarOps("posiciones")}>
              {impOps?.estado === "yendo" && impOps.que === "posiciones"
                ? "Importando…" : `Importar ${(ops.abiertos || []).length} posiciones`}
            </button>
            <button className="btn"
                    disabled={!destino || impOps?.estado === "yendo" || !cuantasCerradas}
                    onClick={() => importarOps("cerradas")}>
              {impOps?.estado === "yendo" && impOps.que === "cerradas"
                ? "Importando…" : `Importar ${cuantasCerradas} operaciones cerradas`}
            </button>
            {impOps?.ok && <span className="ok" style={{ fontSize: 12 }}>
              {impOps.que === "posiciones"
                ? <>Listo: {impOps.importadas} posiciones en {impOps.cartera}
                   {impOps.reemplazadas ? ` (pisó ${impOps.reemplazadas})` : ""}.</>
                : <>Listo: {impOps.agregados} operaciones en {impOps.cartera}
                   {impOps.reemplazados ? ` (pisó ${impOps.reemplazados})` : ""}.</>}
            </span>}
            {impOps?.error && <span className="mal" style={{ fontSize: 12 }}>{impOps.error}</span>}
          </div>
          <div className="pie">
            Las dos importaciones son independientes: una trae <b>lo que tenés</b> y la otra
            <b> lo que hiciste</b>. Cada una pisa sólo lo suyo de la vez anterior y nunca lo
            que cargaste a mano. Una compra en pesos cierra contra su venta en dólares —es la
            misma posición, no dos— y cada pata se pasa a dólares con el MEP de <b>su</b> fecha:
            eso es lo que mide si dolarizarte por el CEDEAR o por el bono te convino. Vale
            igual si comprás y vendés las dos veces en pesos. El precio sale del neto
            liquidado, así que ya tiene la comisión adentro. Las cerradas se importan
            sólo si están tildadas: vienen destildadas las que la cartera ya tiene, para
            no contar el mismo resultado dos veces.
          </div>
        </div>);
      })()}

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
                  <th className="n">Cerrado USD</th><th className="n">Período</th>
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
                      <td className={"n " + signo(f.resultado_usd)}>{f.resultado_usd == null ? "—" : usd(f.resultado_usd)}</td>
                      <td className="mono" style={{ fontSize: 11 }}>{f.desde}<br />{f.hasta}</td>
                    </tr>);
                })}</tbody>
                {fci.total_usd != null && <tfoot><tr>
                  <td colSpan={6}><b>Resultado cerrado, en dólares</b></td>
                  <td className={"n " + signo(fci.total_usd)}><b>{usd(fci.total_usd)}</b></td>
                  <td />
                </tr></tfoot>}
              </table></div>
              <div className="pie">
                Resultado = tenencia de hoy + lo rescatado − lo suscripto (lo que sacaste más lo
                que aún tenés, contra lo que pusiste). En los de barrido diario (COCORMA) el capital
                rota muchas veces, así que mirá el <b>resultado en $</b> más que el %.
                {" "}<b>Cerrado USD</b> es otra cosa: sólo lo que ya rescataste, apareado FIFO
                contra lo que costó, y con cada movimiento pasado a dólares al MEP de
                <b> su</b> fecha. Por eso un fondo puede ganar en pesos y perder en dólares.
                {fci.cortado && <> · Historial recortado a los {fci.total_movs} movimientos más recientes.</>}
              </div>
            </>}

        {/* Llevar la participación a una cartera: sólo la posición y el resultado. */}
        {tenFci && !tenFci.error && ((tenFci.lotes || []).length > 0 || tenFci.cartera) && (
          <div style={{ borderTop: "1px solid var(--borde)", marginTop: 12, paddingTop: 12,
                        display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <span style={{ fontSize: 13 }}>
              {(tenFci.lotes || []).length
                ? <>Llevar los FCI de Cocos a la cartera</>
                : <>No te queda ningún FCI: sincronizá para sacarlos de la cartera</>}
            </span>
            <select value={destino} onChange={(e) => setDestino(e.target.value)}
                    disabled={!!tenFci.cartera}>
              <option value="">elegí una…</option>
              {(tenFci.carteras || []).map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
            <button className="btn" disabled={!destino || importando?.estado === "yendo"}
                    onClick={importarFci}>
              {importando?.estado === "yendo" ? "Sincronizando…"
                : (tenFci.lotes || []).length ? "Importar" : "Sincronizar"}
            </button>
            {importando?.ok && <span className="ok" style={{ fontSize: 12 }}>
              Listo: {importando.importadas} en {importando.cartera}
              {importando.reemplazadas ? ` (pisó ${importando.reemplazadas})` : ""}.
            </span>}
            {importando?.ok && !importando.importadas && !importando.reemplazadas &&
              <span style={{ fontSize: 12, color: "var(--texto-3)" }}>Nada que sincronizar.</span>}
            {importando?.error && <span className="mal" style={{ fontSize: 12 }}>{importando.error}</span>}
          </div>)}
        {/* Y el resultado de lo ya rescatado, que va a operaciones cerradas. */}
        {fci && !fci.error && (fci.trades || []).length > 0 && (
          <div style={{ borderTop: "1px solid var(--borde)", marginTop: 12, paddingTop: 12,
                        display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <span style={{ fontSize: 13 }}>
              Llevar el resultado cerrado de los FCI
              (<b className={signo(fci.total_usd)}>{usd(fci.total_usd)}</b> en {fci.trades.length}
              {fci.trades.length === 1 ? " fondo" : " fondos"}) a operaciones cerradas de
            </span>
            <select value={destino} onChange={(e) => setDestino(e.target.value)}
                    disabled={!!fci.cartera}>
              <option value="">elegí una…</option>
              {(fci.carteras || []).map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
            <button className="btn" disabled={!destino || impRes?.estado === "yendo"}
                    onClick={importarResultadoFci}>
              {impRes?.estado === "yendo" ? "Importando…" : "Importar resultados"}
            </button>
            {impRes?.ok && <span className="ok" style={{ fontSize: 12 }}>
              Listo: {impRes.agregados} en {impRes.cartera}
              {impRes.reemplazados ? ` (pisó ${impRes.reemplazados})` : ""}.
            </span>}
            {impRes?.error && <span className="mal" style={{ fontSize: 12 }}>{impRes.error}</span>}
          </div>)}
        {fci && !fci.error && (fci.trades || []).length > 0 && (
          <div className="pie">
            Un registro por fondo, no uno por rescate: el barrido diario son cientos de
            movimientos de centavos y el total dice lo mismo mejor. Reimportar pisa lo de
            la vez anterior —no duplica—, así que podés sincronizar cuando quieras. Lo que
            todavía tenés no entra acá: eso es tenencia, y va por el botón de arriba.
          </div>)}

        {tenFci && !tenFci.error && ((tenFci.lotes || []).length > 0 || tenFci.cartera) && (
          <div className="pie">
            Va sólo la tenencia y su resultado. Un FCI no tiene serie de precios, así que
            queda fuera del riesgo y de la optimización. Sincronizar pisa la importación
            anterior —no duplica— y si ya no te queda el fondo, lo saca de la cartera.
            El resultado de lo que rescataste vive en la tabla de arriba, no en la cartera.
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

/* ═══════════════ Mi InvIU · la cuenta real del broker ═══════════════ */
// Espejo de lo que InvIU expone hoy: cartera, operaciones y rentas, más los
// importadores hacia una cartera de la app. Login por navegador, ver Inviu().

function MiInviu() {
  const [conectado, setConectado] = useState(null);
  const [titular, setTitular] = useState(null);
  const [cart, setCart] = useState(null);
  const [errCart, setErrCart] = useState(null);
  const [ops, setOps] = useState(null);
  const [destino, setDestino] = useState("");
  const [impOps, setImpOps] = useState(null);
  const [sinImportar, setSinImportar] = useState(null);
  const [rentas, setRentas] = useState(null);
  const [impRentas, setImpRentas] = useState(null);
  const [caucion, setCaucion] = useState(null);
  const [evolucion, setEvolucion] = useState(null);
  const [flujoProyectado, setFlujoProyectado] = useState(null);

  const cargar = () => {
    setTitular(null); setCart(null); setErrCart(null); setOps(null); setImpOps(null);
    setSinImportar(null); setRentas(null); setImpRentas(null); setCaucion(null);
    setEvolucion(null); setFlujoProyectado(null);
    api("/api/inviu/estado").then((e) => {
      setConectado(e.conectado);
      if (!e.conectado) return;
      api("/api/inviu/titular").then(setTitular);
      api("/api/inviu/cartera").then((r) => {
        if (r.error) { setErrCart(r.error); return; }
        setCart(r);
      });
      api("/api/inviu/operaciones").then((o) => {
        setOps(o);
        if (o.cartera) setDestino(o.cartera);
      });
      api("/api/inviu/rentas").then(setRentas);
      api("/api/inviu/caucion").then(setCaucion);
      api("/api/inviu/evolucion").then(setEvolucion);
      api("/api/inviu/flujo-proyectado").then(setFlujoProyectado);
    });
  };
  useEffect(() => { cargar(); }, []);

  // Igual que en Cocos: arranca con las cerradas que la cartera ya tiene
  // destildadas, para no contar el mismo resultado dos veces.
  const fuera = sinImportar ?? new Set((ops?.ya_cerradas || []).map((c) => c.clave));
  const alternar = (clave) => {
    const s = new Set(fuera);
    s.has(clave) ? s.delete(clave) : s.add(clave);
    setSinImportar(s);
  };

  const importarOps = (que) => {
    setImpOps({ estado: "yendo", que });
    const cuerpo = { cartera: destino };
    if (que === "cerradas") {
      cuerpo.solo = (ops.cerrados || []).map((c) => c.clave).filter((k) => !fuera.has(k));
    }
    post(`/api/inviu/operaciones/${que}`, cuerpo).then((r) => setImpOps({ ...r, que }));
  };

  const importarRentas = () => {
    setImpRentas({ estado: "yendo" });
    post("/api/inviu/rentas/importar", { cartera: destino }).then(setImpRentas);
  };

  const [impCaucion, setImpCaucion] = useState(null);
  const importarCaucion = () => {
    setImpCaucion({ estado: "yendo" });
    post("/api/inviu/caucion/importar", { cartera: destino }).then(setImpCaucion);
  };

  if (conectado === null) return <div className="cargando">Consultando tu cuenta de InvIU…</div>;
  if (!conectado) return (
    <div className="vacio">
      No estás conectado a InvIU. Andá a <b>Conectores</b> y conectá tu cuenta para
      ver acá tu cartera, operaciones y rentas.
    </div>
  );

  const port = cart?.results?.[0]?.portfolio;
  const holdings = (port?.holdingsByCategory || [])
    .filter((c) => !["ARG_PESOS", "US_DOLLARS"].includes(c.categoryName))
    .flatMap((c) => c.holdings || []);
  const efectivoArs = port?.available?.["24HS"]?.ARS?.amount ?? null;
  const efectivoUsd = port?.available?.["24HS"]?.USD?.amount ?? null;
  const rentasImportables = (rentas?.movimientos || [])
    .filter((m) => m.tipo === "Renta" || m.tipo === "Amortización");
  const cuantasCerradas = (ops?.cerrados || []).filter((c) => !fuera.has(c.clave)).length;
  const mon = (o, dec = 2) => o?.amount == null ? "—"
    : o.currency === "ARS" ? ars(o.amount, dec) : num(o.amount, dec) + " " + (o.currency || "");

  return (
    <>
      <div className="aviso ojo">
        Todo lo de esta pantalla sale <b>en vivo de InvIU</b>. Es de solo lectura hasta que
        importás. <button className="btn" style={{ padding: "1px 9px", fontSize: 12, marginLeft: 4 }}
        onClick={cargar}>Actualizar</button>
      </div>

      {errCart && <div className="aviso mal">{errCart}</div>}

      {titular && !titular.error && (
        <div className="panel" style={{ marginBottom: 14 }}>
          <h3>Cuenta</h3>
          <div className="kpis">
            <Kpi etiqueta="Titular" valor={titular.titular || "—"} sub={titular.perfil_riesgo} />
            <Kpi etiqueta="N° de comitente" valor={titular.comitente || "—"} sub={titular.custodio} />
            <Kpi etiqueta="Gestor asignado" valor={titular.gestor || "sin asesor"}
                 sub={titular.mandato_discrecional === "ACCEPT_DISCRETIONARY_MANAGER"
                   ? "gestión discrecional" : titular.gestor_email} />
          </div>
        </div>
      )}

      {port && <div className="kpis">
        <Kpi etiqueta="Patrimonio total" valor={usd(port.totalPortfolioValue?.USD?.amount, 0)}
             sub={ars(port.totalPortfolioValue?.ARS?.amount, 0)} />
        <Kpi etiqueta="Tipo de cambio interno" valor={num(port.exchangeRate, 2)}
             sub="el que usa InvIU para su MEP" />
        <Kpi etiqueta="Efectivo ARS" valor={ars(efectivoArs, 2)} />
        <Kpi etiqueta="Efectivo USD" valor={num(efectivoUsd, 2)} tono={efectivoUsd < 0 ? "neg" : undefined}
             sub={efectivoUsd < 0 ? "negativo: caución tomadora" : null} />
      </div>}

      {/* ── Caución ──
          Solo se muestra el lado que sigue vigente hoy (ver `_inviu_caucion`
          en el backend): si `null`, esa posición ya venció y no queda
          ninguna abierta de ese lado — no es que falte cargar nada. */}
      {caucion && !caucion.error && (caucion.tomadora || caucion.colocadora
                                     || caucion.resultado_neto) && (
        <div className="panel" style={{ marginBottom: 14 }}>
          <h3>Caución abierta</h3>
          <div className="kpis">
            {caucion.tomadora ? (
              <Kpi etiqueta="Tomadora (deuda de corto plazo)"
                   valor={caucion.tomadora.moneda === "ARS" ? ars(caucion.tomadora.monto, 0)
                                                             : usd(caucion.tomadora.monto, 0)}
                   tono="neg recuadro"
                   sub={`desde ${caucion.tomadora.desde} · vence ${caucion.tomadora.vence}` +
                     (caucion.tomadora.tasa_tna != null
                       ? ` · ${num(caucion.tomadora.tasa_tna, 1)}% (TNA)` : "")} />
            ) : (
              <Kpi etiqueta="Tomadora" valor="sin deuda abierta" sub="no hay caución tomadora vigente hoy" />
            )}
            {caucion.colocadora ? (
              <Kpi etiqueta="Colocadora (plata prestada por vos)"
                   valor={caucion.colocadora.moneda === "ARS" ? ars(caucion.colocadora.monto, 0)
                                                               : usd(caucion.colocadora.monto, 0)}
                   tono="pos recuadro"
                   sub={`desde ${caucion.colocadora.desde} · vence ${caucion.colocadora.vence}` +
                     (caucion.colocadora.tasa_tna != null
                       ? ` · ${num(caucion.colocadora.tasa_tna, 1)}% (TNA)` : "")} />
            ) : (
              <Kpi etiqueta="Colocadora" valor="sin colocación abierta" sub="no hay caución colocadora vigente hoy" />
            )}
            {caucion.resultado_neto && (
              <Kpi etiqueta="Resultado neto del carry trade"
                   valor={usd(caucion.resultado_neto.total_usd)}
                   tono={caucion.resultado_neto.total_usd >= 0 ? "pos" : "neg"}
                   sub="interés cobrado − interés pagado, todo el historial" />
            )}
          </div>
          {caucion.resultado_neto && (
            <div className="tabla-wrap" style={{ marginTop: 10 }}><table>
              <thead><tr><th></th><th className="n">USD</th></tr></thead>
              <tbody>
                <tr><td>Interés pagado tomando caución (USD)</td>
                  <td className={"n " + signo(caucion.resultado_neto.tomadora_usd)}>
                    {usd(caucion.resultado_neto.tomadora_usd)}</td></tr>
                <tr><td>Cargos en pesos de esas cauciones (convertidos al MEP del día)</td>
                  <td className={"n " + signo(caucion.resultado_neto.tomadora_cargos_usd)}>
                    {usd(caucion.resultado_neto.tomadora_cargos_usd)}</td></tr>
                <tr><td>Interés cobrado colocando caución (convertido al MEP del día)</td>
                  <td className={"n " + signo(caucion.resultado_neto.colocadora_usd)}>
                    {usd(caucion.resultado_neto.colocadora_usd)}</td></tr>
                <tr style={{ fontWeight: 700 }}><td>Neto</td>
                  <td className={"n " + signo(caucion.resultado_neto.total_usd)}>
                    {usd(caucion.resultado_neto.total_usd)}</td></tr>
              </tbody>
            </table></div>
          )}
          {caucion.resultado_neto && (
            <div style={{ borderTop: "1px solid var(--borde)", marginTop: 12, paddingTop: 12,
                          display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
              <span style={{ fontSize: 13 }}>Llevar el resultado neto al P&L realizado</span>
              <select value={destino} onChange={(e) => setDestino(e.target.value)}>
                <option value="">elegí una…</option>
                {(ops?.carteras || []).map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
              <button className="btn" disabled={!destino || impCaucion?.estado === "yendo"}
                      onClick={importarCaucion}>
                {impCaucion?.estado === "yendo" ? "Importando…" : "Importar cauciones"}
              </button>
              {impCaucion?.ok && <span className="ok" style={{ fontSize: 12 }}>
                Listo: {impCaucion.agregados} en {impCaucion.cartera}
                {impCaucion.reemplazados ? ` (pisó ${impCaucion.reemplazados})` : ""}.
              </span>}
              {impCaucion?.error && <span className="mal" style={{ fontSize: 12 }}>{impCaucion.error}</span>}
            </div>
          )}
          <div className="pie">
            Se importan dos registros —"CAUCIONT" y "CAUCIONC"— con el resultado agregado de
            cada lado, no uno por rollover: son cientos de tomas diarias, y anotar cada una
            no diría nada que el neto no diga mejor.
          </div>
          <div className="pie">
            Esta cuenta viene renovando una caución tomadora todos los días —no es un
            movimiento suelto, es una posición que se re-toma sola cada rueda. El monto que
            de verdad afecta hoy tu patrimonio ya está descontado en "Efectivo USD/ARS" de
            arriba; los KPIs de arriba solo agregan desde cuándo corre y a qué tasa (TNA,
            confirmada contra el boleto real de InvIU). El <b>resultado neto</b> sí es un
            cálculo sobre todo el historial de tomas, colocaciones y vencimientos, con cada
            pata en pesos convertida al MEP de su propia fecha — ahí está la respuesta a si
            el carry trade rindió de verdad o no.
          </div>
        </div>
      )}

      {/* ── Posiciones ── */}
      <div className="panel" style={{ marginBottom: 14 }}>
        <h3>Posiciones ({holdings.length})</h3>
        {holdings.length === 0
          ? <div className="vacio">Sin tenencias en la cuenta.</div>
          : <div className="tabla-wrap"><table>
              <thead><tr>
                <th>Ticker</th><th>Instrumento</th>
                <th className="n">Cantidad</th><th className="n">PPC</th>
                <th className="n">Valor</th><th className="n">Resultado</th><th className="n">Rend.</th>
              </tr></thead>
              <tbody>{holdings.map((h) => {
                // InvIU ya manda el % como porcentaje (-0.58 = -0,58 %), no
                // como fracción — sin este comentario alguien lo multiplica
                // por 100 de nuevo la próxima vez que toque esto.
                const resPct = h.performance?.ppc?.percent ?? null;
                return (
                  <tr key={h.id}>
                    <td className="mono"><b>{h.ticker}</b></td>
                    <td>{h.name}</td>
                    <td className="n">{num(h.quantity, h.quantity % 1 ? 4 : 0)}</td>
                    <td className="n">{mon(h.averagePurchasePrice, 4)}</td>
                    <td className="n">{mon(h.totalValuation, 0)}</td>
                    <td className={"n " + signo(h.performance?.ppc?.value?.amount)}>
                      {mon(h.performance?.ppc?.value)}</td>
                    <td className={"n " + signo(resPct)}>{resPct == null ? "—" : pct(resPct)}</td>
                  </tr>);
              })}</tbody>
            </table></div>}
        <div className="pie">
          PPC y resultado, cada uno en la moneda en que InvIU los informa. El patrimonio
          total del panel de arriba ya viene convertido a dólares por InvIU con su MEP interno.
        </div>
      </div>

      {/* ── Compras y ventas ── */}
      {ops && !ops.error && ((ops.abiertos || []).length > 0 || (ops.cerrados || []).length > 0) && (
        <div className="panel" style={{ marginBottom: 14 }}>
          <h3>Compras y ventas · lo que tenés y lo que ya cerraste</h3>

          {(ops.ya_cargados || []).length > 0 && (
            <div className="aviso ojo">
              <b>{ops.cartera}</b> ya tiene cargados a mano {ops.ya_cargados.length} de estos
              papeles: <b className="mono">{ops.ya_cargados.join(", ")}</b>. Importar las
              posiciones no los pisa —lo cargado a mano no se toca nunca— así que quedarían
              dos veces.
            </div>)}
          {(ops.ya_cerradas || []).length > 0 && (
            <div className="aviso ojo">
              <b>{ops.ya_cerradas.length} operaciones cerradas ya están cargadas</b> en{" "}
              {ops.cartera}. Vienen destildadas en la tabla para no contar el mismo resultado
              dos veces.
            </div>)}

          <div className="tabla-wrap"><table>
            <thead><tr>
              <th>Ticker</th><th>Compra</th><th>Venta</th><th className="n">Cantidad</th>
              <th className="n">Precio compra</th><th className="n">Precio venta</th>
              <th className="n">Resultado</th>
            </tr></thead>
            <tbody>
              {(ops.abiertos || []).map((a, i) => (
                <tr key={"a" + i}>
                  <td className="mono"><b>{a.ticker}</b>
                    <span className="chip ok" style={{ marginLeft: 6, minWidth: 0 }}>abierta</span></td>
                  <td className="mono">{a.buy_date}</td>
                  <td style={{ color: "var(--texto-3)" }}>—</td>
                  <td className="n">{num(a.qty, 2)}</td>
                  <td className="n">{usd(a.buy_price, 4)}</td>
                  <td className="n">—</td><td className="n">—</td>
                </tr>))}
              {(ops.cerrados || []).map((c, i) => (
                <tr key={"c" + i} style={fuera.has(c.clave) ? { opacity: .45 } : undefined}>
                  <td className="mono">
                    <label style={{ display: "inline-flex", alignItems: "center", gap: 6,
                                    cursor: "pointer" }}
                           title={fuera.has(c.clave) ? "No se importa" : "Se importa"}>
                      <input type="checkbox" checked={!fuera.has(c.clave)}
                             onChange={() => alternar(c.clave)} />
                      {c.ticker}
                    </label></td>
                  <td className="mono">{c.buy_date}</td>
                  <td className="mono">{c.sell_date}</td>
                  <td className="n">{num(c.qty, 2)}</td>
                  <td className="n">{usd(c.buy_price, 4)}</td>
                  <td className="n">{usd(c.sell_price, 4)}</td>
                  <td className={"n " + signo(c.pnl)}>{usd(c.pnl)}</td>
                </tr>))}
              {(ops.cerrados || []).length > 0 && (
                <tr style={{ fontWeight: 700 }}>
                  <td colSpan={6}>Resultado de lo cerrado</td>
                  <td className={"n " + signo(ops.cerrados.reduce((s, c) => s + c.pnl, 0))}>
                    {usd(ops.cerrados.reduce((s, c) => s + c.pnl, 0))}</td>
                </tr>)}
            </tbody>
          </table></div>

          <div style={{ borderTop: "1px solid var(--borde)", marginTop: 12, paddingTop: 12,
                        display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <span style={{ fontSize: 13 }}>Llevar a la cartera</span>
            <select value={destino} onChange={(e) => setDestino(e.target.value)}
                    disabled={!!ops.cartera}>
              <option value="">elegí una…</option>
              {(ops.carteras || []).map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
            <button className="btn" disabled={!destino || impOps?.estado === "yendo"
                                              || !(ops.abiertos || []).length}
                    onClick={() => importarOps("posiciones")}>
              {impOps?.estado === "yendo" && impOps.que === "posiciones"
                ? "Importando…" : `Importar ${(ops.abiertos || []).length} posiciones`}
            </button>
            <button className="btn"
                    disabled={!destino || impOps?.estado === "yendo" || !cuantasCerradas}
                    onClick={() => importarOps("cerradas")}>
              {impOps?.estado === "yendo" && impOps.que === "cerradas"
                ? "Importando…" : `Importar ${cuantasCerradas} operaciones cerradas`}
            </button>
            {impOps?.ok && <span className="ok" style={{ fontSize: 12 }}>
              {impOps.que === "posiciones"
                ? <>Listo: {impOps.importadas} posiciones en {impOps.cartera}
                   {impOps.reemplazadas ? ` (pisó ${impOps.reemplazadas})` : ""}.</>
                : <>Listo: {impOps.agregados} operaciones en {impOps.cartera}
                   {impOps.reemplazados ? ` (pisó ${impOps.reemplazados})` : ""}.</>}
            </span>}
            {impOps?.error && <span className="mal" style={{ fontSize: 12 }}>{impOps.error}</span>}
          </div>
          <div className="pie">
            Se apea por bono/CEDEAR subyacente, no por ticker crudo: comprar en pesos y vender
            la misma especie en dólares —esta cuenta lo hace seguido— cierra como una sola
            posición, no dos, y cada pata se pasa a dólares con el MEP de <b>su</b> fecha. Las
            cauciones (colocadora/tomadora) no entran acá: son préstamos de corto plazo, no
            compra/venta de un instrumento.
          </div>
        </div>
      )}

      {/* ── Rentas, amortizaciones, depósitos y retiros ── */}
      <div className="panel" style={{ marginBottom: 14 }}>
        <h3>Rentas, amortizaciones, depósitos y retiros</h3>
        {!rentas
          ? <div className="cargando">Leyendo el historial…</div>
          : rentas.error
          ? <div className="aviso mal">{rentas.error}</div>
          : (rentas.movimientos || []).length === 0
          ? <div className="vacio">Sin movimientos de este tipo en el historial.</div>
          : <>
              <div className="tabla-wrap"><table>
                <thead><tr><th>Fecha</th><th>Tipo</th><th>Ticker</th><th className="n">Monto</th></tr></thead>
                <tbody>{rentas.movimientos.map((m, i) => (
                  <tr key={i}>
                    <td className="mono">{m.fecha}</td>
                    <td>{m.tipo}</td>
                    <td className="mono">{m.ticker}</td>
                    <td className="n">{m.moneda === "ARS" ? ars(m.monto, 2)
                      : num(m.monto, 2) + " " + m.moneda}</td>
                  </tr>))}</tbody>
              </table></div>
              <div className="pie">
                Depósitos y retiros son informativos —aportes de capital, no resultado— y no se
                importan. Solo Renta y Amortización van al P&L realizado. La pata en pesos de la
                renta de un bono dual no aparece acá: sale negativa y es un ajuste técnico de
                Caja de Valores, no plata real (verificado contra el extracto real de la cuenta).
              </div>

              {rentasImportables.length > 0 && (
                <div style={{ borderTop: "1px solid var(--borde)", marginTop: 12, paddingTop: 12,
                              display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                  <span style={{ fontSize: 13 }}>Llevar al P&L realizado</span>
                  <select value={destino} onChange={(e) => setDestino(e.target.value)}>
                    <option value="">elegí una…</option>
                    {(ops?.carteras || []).map((n) => <option key={n} value={n}>{n}</option>)}
                  </select>
                  <button className="btn" disabled={!destino || impRentas?.estado === "yendo"}
                          onClick={importarRentas}>
                    {impRentas?.estado === "yendo" ? "Importando…"
                      : `Importar ${rentasImportables.length} rentas/amortizaciones`}
                  </button>
                  {impRentas?.ok && <span className="ok" style={{ fontSize: 12 }}>
                    Listo: {impRentas.agregados} en {impRentas.cartera}
                    {impRentas.reemplazados ? ` (pisó ${impRentas.reemplazados})` : ""}.
                  </span>}
                  {impRentas?.error && <span className="mal" style={{ fontSize: 12 }}>{impRentas.error}</span>}
                </div>
              )}
            </>}
      </div>

      {/* ── Rendimiento según InvIU — control cruzado ──
          Esta TIR la calcula InvIU con sus propios flujos; la que ya
          calcula esta app con el MEP de cada fecha vive en Análisis →
          Posición → "Rendimiento anual · TIR". Si difieren mucho, hay algo
          para investigar de un lado o del otro. */}
      {evolucion && !evolucion.error && evolucion.summary && (
        <div className="panel" style={{ marginBottom: 14 }}>
          <h3>Rendimiento según InvIU</h3>
          <div className="kpis">
            <Kpi etiqueta="TIR del período" valor={pct(evolucion.summary.tir * 100, 2)}
                 tono={signo(evolucion.summary.tir)} />
            <Kpi etiqueta="TIR anualizada" valor={pct(evolucion.summary.annualTir * 100, 2)}
                 tono={signo(evolucion.summary.annualTir)}
                 sub="comparala contra Análisis → Posición" />
            <Kpi etiqueta="Ganancia estimada" valor={usd(evolucion.summary.estimatedEarnings)}
                 tono={signo(evolucion.summary.estimatedEarnings)} />
          </div>
          <div className="pie">
            Calculado por InvIU con sus propios flujos de caja (aportes, retiros, cobros), no
            con el MEP de cada fecha como hace esta app. Sirve de control cruzado: si esta TIR
            y la de Análisis → Posición se parecen, las dos cuentas están midiendo lo mismo
            bien; si difieren mucho, vale la pena mirar por qué.
          </div>
        </div>
      )}

      {/* ── Próximos cobros de bonos ── */}
      {flujoProyectado && !flujoProyectado.error && (flujoProyectado.data || []).length > 0 && (
        <div className="panel" style={{ marginBottom: 14 }}>
          <h3>Próximos cobros de bonos ({flujoProyectado.data.length})</h3>
          <div className="kpis">
            {Object.entries(flujoProyectado.metrics || {}).map(([moneda, m]) => (
              <Kpi key={moneda} etiqueta={`TIR de la renta fija (${moneda})`}
                   valor={pct(m.tir * 100, 2)}
                   sub={`duration ${num(m.modifiedDuration, 2)} · DV01 ${usd(m.dv01)} · convexidad ${num(m.convexity, 2)}`} />
            ))}
          </div>
          <div className="tabla-wrap"><table>
            <thead><tr><th>Fecha</th><th>Ticker</th><th>Tipo</th><th className="n">Monto</th></tr></thead>
            <tbody>{[...flujoProyectado.data].sort((a, b) => a.date < b.date ? -1 : 1).map((p, i) => (
              <tr key={i}>
                <td className="mono">{p.date}</td>
                <td className="mono">{p.ticker}</td>
                <td>{p.type === "INCOME" ? "Renta" : p.type === "AMORTIZATION" ? "Amortización" : p.type}</td>
                <td className="n">{p.currency === "ARS" ? ars(p.amount, 2) : num(p.amount, 2) + " " + p.currency}</td>
              </tr>))}</tbody>
          </table></div>
          <div className="pie">
            Lo que InvIU proyecta que vas a cobrar de tus bonos actuales, cupón por cupón,
            hasta el vencimiento de cada uno — no son movimientos que ya pasaron, es la
            proyección hacia adelante. Duration, DV01 y convexidad son los mismos conceptos
            que ya calcula <code>bonds.py</code> para esta cartera; sirven para cruzar contra
            eso también.
          </div>
        </div>
      )}
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

/* ═══════════════ Ingreso (sólo modo web) ═══════════════ */

/* Con Google no hay contraseña nuestra que guardar, y eso no es comodidad: los
   usuarios de esta app tienen cuenta en Cocos y una parte reusaría ahí la clave
   del broker. Una base de hashes nuestra sería, para esa gente, una copia de la
   llave de su cuenta comitente.

   Es un enlace, no un botón con JavaScript de Google: el navegador se va a
   Google y vuelve, sin correr código de terceros en una página que maneja
   sesiones de broker. */

const SLIDES = [
  ["Posición", "Toda tu cartera en una sola pantalla", "posicion",
   "Tenencias, composición y los KPIs de riesgo juntos: Sharpe, volatilidad, el día malo, lo que " +
   "llevás abierto y lo ya realizado. Debajo, correlaciones, distribución de retornos, comparación " +
   "contra el índice y momentum."],
  ["Riesgo", "El día malo, antes de que llegue", "riesgo",
   "VaR, drawdown y volatilidad, más el stress test contra las caídas que ya pasaron. No es el " +
   "riesgo promedio: es qué le hace a tu cartera un derrumbe concreto."],
  ["Optimización", "La mezcla que rinde más por el mismo riesgo", "optimizacion",
   "La frontera de Markowitz, con tu cartera ubicada sobre ella. Con Black-Litterman le sumás tu " +
   "propia visión del mercado y ves cómo se corren los pesos."],
  ["Monte Carlo", "Mil futuros, no un pronóstico", "montecarlo",
   "Simula el recorrido de la cartera miles de veces y te muestra el abanico completo de " +
   "resultados, con sus percentiles. El promedio miente; la banda no."],
  ["Regímenes", "En qué mercado estás parado", "regimenes",
   "Detecta el régimen en el que viene operando el mercado y desde cuándo, para que no leas una " +
   "racha tranquila con la vara de una crisis, ni al revés."],
  ["Comparación y simulación", "Probá la compra antes de hacerla", "comparacion",
   "Agregá un activo imaginario y toda la pantalla se recalcula con él adentro, sin tocar tu " +
   "cartera. O poné dos carteras enteras una contra la otra y mirá cuál aguanta mejor."],
];

const LAPSO = 6000;   // ms que dura cada slide en el autoplay

/* El logo de Google, inline: el CSP no deja traer imágenes de afuera. */
function LogoGoogle() {
  return (
    <span className="bv-g" aria-hidden="true">
      <svg width="16" height="16" viewBox="0 0 48 48">
        <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
        <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
        <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>
        <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
      </svg>
    </span>
  );
}

function Ingreso({ configurado }) {
  const pista = useRef(null);
  const barra = useRef(null);
  const [activa, setActiva] = useState(0);

  const ir = useCallback((i) => {
    const s = pista.current?.children[(i + SLIDES.length) % SLIDES.length];
    s?.scrollIntoView({ inline: "center", block: "nearest" });
  }, []);

  // En qué slide estamos lo decide el navegador, no una cuenta de píxeles: así
  // sigue siendo correcto cuando el que scrollea es el dedo o la rueda.
  useEffect(() => {
    const slides = [...pista.current.children];
    const io = new IntersectionObserver((es) => {
      for (const e of es) if (e.isIntersecting) setActiva(slides.indexOf(e.target));
    }, { root: pista.current, threshold: .6 });
    slides.forEach((s) => io.observe(s));
    return () => io.disconnect();
  }, []);

  // Autoplay con su barra. Se para al pasar el mouse, al entrar con el teclado
  // o si la pestaña deja de verse, y no arranca si el sistema pide menos
  // movimiento.
  const [pausado, setPausado] = useState(false);
  useEffect(() => {
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let t0 = performance.now(), raf = 0;
    const tick = (now) => {
      raf = requestAnimationFrame(tick);
      if (pausado || document.hidden) { t0 = now; return; }
      const p = (now - t0) / LAPSO;
      if (barra.current) barra.current.style.width = Math.min(p, 1) * 100 + "%";
      if (p >= 1) { t0 = now; ir(activa + 1); }
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [activa, pausado, ir]);

  return (
    <div className="bv">
      <div className="bv-luz a" />
      <div className="bv-luz b" />

      <header>
        <h1>Portfolio <span>Analyzer</span></h1>
        <p>{t("Armá tu cartera, medí su riesgo y compará estrategias.",
             "Build your portfolio, measure its risk and compare strategies.")}</p>
      </header>

      <div className="bv-carrusel" aria-roledescription="carrusel" aria-label={t("Qué hace la app", "What the app does")}>
        <div className="bv-pista" ref={pista} tabIndex={0}
             onPointerEnter={() => setPausado(true)}
             onPointerLeave={() => setPausado(false)}
             onFocus={() => setPausado(true)}
             onBlur={() => setPausado(false)}>
          {SLIDES.map(([kicker, titulo, img, bajada], i) => (
            <article key={img} className={"bv-slide" + (i === activa ? " on" : "")}
                     role="group" aria-roledescription="slide"
                     aria-label={`${i + 1} de ${SLIDES.length}`}
                     /* Tocar la que asoma al costado la trae al centro. Sólo si
                        no es la activa, para no comerse clicks de adentro. */
                     onClick={() => { if (i !== activa) ir(i); }}>
              <div className="bv-card">
                <img src={`capturas/${img}.png`} alt="" onError={(e) => e.target.remove()} />
                <div className="bv-texto">
                  <p className="bv-kicker">{kicker}</p>
                  <h2 className="bv-titulo">{titulo}</h2>
                  <p className="bv-bajada">{bajada}</p>
                </div>
              </div>
            </article>
          ))}
        </div>

        <div className="bv-controles">
          <button className="bv-flecha" aria-label={t("Anterior", "Previous")} onClick={() => ir(activa - 1)}>‹</button>
          <div className="bv-puntos">
            {SLIDES.map(([, , img], i) => (
              <button key={img} className="bv-punto" aria-current={i === activa}
                      aria-label={`Slide ${i + 1}`} onClick={() => ir(i)} />
            ))}
          </div>
          <button className="bv-flecha" aria-label={t("Siguiente", "Next")} onClick={() => ir(activa + 1)}>›</button>
        </div>
        <div className="bv-progreso"><i ref={barra} /></div>
      </div>

      <footer>
        {configurado ? (
          <a className="bv-entrar" href="/api/entrar"><LogoGoogle />{t("Entrar con Google", "Sign in with Google")}</a>
        ) : (
          <div className="bv-aviso">
            {t("El ingreso con Google todavía no está configurado en este servidor.",
               "Google sign-in isn't configured on this server yet.")}
          </div>
        )}
      </footer>
    </div>
  );
}

/* El formulario de Cocos vive en el panel de conectores, no en la puerta: es un
   accesorio de una cuenta que ya existe. Los autocomplete están puestos a
   propósito para que el gestor de contraseñas del navegador ofrezca guardar y
   rellenar — la bóveda de credenciales es la de él, en su máquina, no la
   nuestra. Poner autoComplete="off" en la contraseña, que es el reflejo típico,
   lograría lo contrario: sin gestor, el usuario elige una clave que pueda
   tipear de memoria. El campo del 2FA lleva one-time-code: en el celular el
   teclado sugiere el código, y le dice al gestor que ese valor no se guarda. */

function EntrarCocos({ motivo, onEntrar }) {
  const [c, setC] = useState({ email: "", password: "", codigo_2fa: "" });
  const [msg, setMsg] = useState(motivo || null);
  const [yendo, setYendo] = useState(false);
  const campo = (k, v) => setC((x) => ({ ...x, [k]: v }));
  const listo = c.email && c.password && c.codigo_2fa.trim().length === 6;

  const enviar = async (e) => {
    e.preventDefault();
    if (!listo || yendo) return;
    setYendo(true); setMsg(null);
    const r = await post("/api/broker/web/login", c);
    setYendo(false);
    if (!r.ok) { setMsg(r.error || "No se pudo conectar."); return; }
    sesion.poner(r.sobre);
    setC({ email: "", password: "", codigo_2fa: "" });
    onEntrar();
  };

  return (
    <>
      <form onSubmit={enviar} style={{ display: "grid", gap: 7 }}>
        <input name="email" type="email" placeholder="Email de Cocos"
               autoComplete="username" value={c.email}
               onChange={(e) => campo("email", e.target.value)} />
        <input name="password" type="password" placeholder="Contraseña"
               autoComplete="current-password" value={c.password}
               onChange={(e) => campo("password", e.target.value)} />
        <input name="totp" type="text" inputMode="numeric" maxLength={6}
               placeholder="Código de 6 dígitos" autoComplete="one-time-code"
               value={c.codigo_2fa}
               onChange={(e) => campo("codigo_2fa", e.target.value.replace(/\D/g, ""))} />
        <button className="btn primario" type="submit" disabled={!listo || yendo}>
          {yendo ? "Conectando…" : "Conectar Cocos"}</button>
      </form>
      {msg && <div className="aviso mal">{msg}</div>}
      <div className="pie" style={{ marginTop: 10 }}>
        Tu contraseña de Cocos <b>no se guarda</b>: se usa para el login y se
        descarta. Queda una sesión en este navegador que vence a las 24 horas,
        por eso el código de la app se pide una vez por día.
      </div>
    </>
  );
}

/* ═══════════════ Raíz ═══════════════ */

/* Cualquier excepción de un componente desmonta el árbol entero y deja la
   pantalla en negro, sin pista de qué pasó. Pasó de verdad el 2026-09-08: un
   401 devolvía {error} donde el panel de conectores esperaba una lista, y la
   aplicación desaparecía. La red no arregla el bug, pero lo deja a la vista en
   vez de borrar todo. Tiene que ser una clase: no hay equivalente con hooks. */

class Red extends React.Component {
  constructor(p) { super(p); this.state = { falla: null }; }
  static getDerivedStateFromError(e) { return { falla: e }; }
  componentDidCatch(e, info) { console.error("se cayó un panel:", e, info); }
  render() {
    if (!this.state.falla) return this.props.children;
    return (
      <div className="hoja" style={{ maxWidth: 520, marginTop: 40 }}>
        <div className="panel">
          <h3>{t("Se cayó esta pantalla", "This screen crashed")}</h3>
          <div className="pie" style={{ marginTop: 6 }}>
            {t("El resto de la aplicación sigue bien. El detalle está en la consola del navegador.",
               "The rest of the app is fine. The detail is in the browser console.")}
          </div>
          <div className="aviso mal mono" style={{ fontSize: 12 }}>
            {String(this.state.falla)}
          </div>
          <button className="btn primario" style={{ marginTop: 10 }}
                  onClick={() => this.setState({ falla: null })}>{t("Reintentar", "Retry")}</button>
        </div>
      </div>
    );
  }
}

function App() {
  // El script local de InvIU abre esta app con `#inviu-web=...`: hay que
  // caer directo en Conectores, o el código queda precargado en una pantalla
  // que nadie está mirando.
  const [modo, setModo] = useState(
    () => location.hash.startsWith("#inviu-web=") ? "conectores" : "analisis");
  const [tema, setTema] = useState(() => localStorage.getItem("tema") || "auto");
  const movil = useMedia(ES_MOVIL);
  const [carteras, setCarteras] = useState([]);
  const [cartera, setCartera] = useState(null);
  // null = todavía no sabemos en qué modo corre el servidor ni quién sos.
  const [web, setWeb] = useState(null);
  const [yo, setYo] = useState(null);
  const [sims, setSims] = useState({});
  const [idioma, setIdioma] = useState(() => idiomaLocal.leer() || "es");

  // La simulación es de la cartera que estás mirando: cambiar de cartera trae la
  // suya, nunca la de la anterior.
  const sim = useMemo(
    () => (cartera ? sims[cartera] || simul.leer(cartera) : []), [cartera, sims]);
  // Se fija acá, en el render, y no en un efecto: los efectos de los hijos corren
  // ANTES que los del padre, así que Análisis lanzaría su POST con la cabecera de
  // la cartera anterior y el primer análisis de cada cambio saldría mal.
  SIM_ACTIVA = simul.cabecera(sim);

  // La plaza la trae la cartera: una de ASML y SAP se mira desde Europa, una de
  // .BA desde Argentina. El servidor la deduce de dónde cotizan los activos, y
  // en Carteras se puede fijar otra para el caso que ninguna posición puede
  // contar: un europeo con acciones de EE.UU. las mide igual en euros.
  //
  // Se resuelve en el MISMO render que la cartera, y no en un efecto: si llegara
  // un tick después, Análisis alcanzaba a pedir una corrida con la plaza vieja y
  // otra con la nueva —once modelos cada una, en un pool de seis— y la primera
  // no servía para nada salvo tapar a la segunda. Es estado derivado, no estado.
  const mercado = carteras.find((c) => c.nombre === cartera)?.mercado || "AR";
  MERCADO = mercado;
  IDIOMA = idioma;

  // Elegir idioma: a mano en el menú de la cuenta, o solo la primera vez con
  // lo que Google mandó (ver `store.anotar`). Si ya hay algo guardado en este
  // navegador, manda eso — así un cambio manual no se pisa en el próximo
  // ingreso mientras se sincroniza con el servidor.
  const cambiarIdioma = useCallback((v) => {
    setIdioma(v);
    idiomaLocal.poner(v);
    if (web) api("/api/yo/idioma", { method: "POST",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify({ idioma: v }) });
  }, [web]);
  useEffect(() => {
    if (yo?.idioma && !idiomaLocal.leer()) cambiarIdioma(yo.idioma);
  }, [yo, cambiarIdioma]);

  // El MEP, los conectores y Cocos no existen fuera de Argentina: quedarse
  // parado en una pestaña que ya no está en la barra deja la pantalla muerta.
  useEffect(() => {
    if (!MERCADOS[mercado].locales) {
      setModo((x) => (MODOS_LOCALES.includes(x) ? "analisis" : x));
    }
  }, [mercado]);
  const cambiarSim = useCallback((l) => {
    simul.poner(cartera, l);
    setSims((s) => ({ ...s, [cartera]: l }));
  }, [cartera]);

  const recargar = useCallback(async () => {
    const c = await api("/api/carteras");
    if (!Array.isArray(c)) return;
    setCarteras(c);
    // Si la que está abierta ya no existe (o no hay ninguna abierta), se elige
    // sola: nadie tiene que ir a buscarla en el desplegable para empezar.
    setCartera((actual) =>
      actual && c.some((x) => x.nombre === actual) ? actual : elegirCartera(c));
  }, []);

  const preguntarQuien = useCallback(() => api("/api/yo").then(setYo), []);

  useEffect(() => {
    api("/api/modo").then((r) => {
      const esWeb = r.modo === "web";
      setWeb(esWeb);
      if (esWeb) preguntarQuien(); else setYo({ dentro: true });
    });
    // Lo dispara api() cuando la sesión de la APP se cayó: hay que volver a
    // entrar con Google. La de Cocos es otra cosa y se maneja en su panel.
    const salio = () => setYo({ dentro: false, configurado: true });
    window.addEventListener("pa:ingresar", salio);
    return () => window.removeEventListener("pa:ingresar", salio);
  }, [preguntarQuien]);

  useEffect(() => { if (yo?.dentro) recargar(); }, [recargar, yo]);

  useEffect(() => {
    // "auto" = no marcar nada y dejar que mande prefers-color-scheme.
    if (tema === "auto") delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = tema;
    localStorage.setItem("tema", tema);
  }, [tema]);

  if (web === null || yo === null) return <div className="cargando">{t("Abriendo…", "Opening…")}</div>;
  if (!yo.dentro) return <Ingreso configurado={yo.configurado} />;

  const Cabecera = movil ? BarraMovil : Barra;
  return (
    <>
      <Cabecera modo={modo} setModo={setModo} tema={tema} setTema={setTema}
                carteras={carteras} cartera={cartera} setCartera={setCartera} yo={yo}
                mercado={mercado} idioma={idioma} cambiarIdioma={cambiarIdioma} />
      <div className="hoja">
        {/* Cambiar de plaza cambia la moneda de medición: lo que hay en pantalla
            está calculado en la anterior y hay que volver a pedirlo entero. */}
        <Red key={modo + ":" + mercado}>
        {modo === "analisis" && <Analisis cartera={cartera} sim={sim} setSim={cambiarSim} />}
        {modo === "comparacion" && <Comparacion carteras={carteras} cartera={cartera} sim={sim} />}
        {modo === "carteras" && <Carteras carteras={carteras} recargar={recargar}
                                    cartera={cartera} setCartera={setCartera} />}
        {modo === "mercado" && <Mercado cartera={cartera} />}
        {modo === "conectores" && <Conectores />}
        {modo === "cocos" && <MiCocos />}
        {modo === "inviu" && <MiInviu />}
        </Red>
      </div>
      <footer>
        <span>© Leandro R. Bergero · Msc Finance and Banking BSM-UPF ·{" "}
          <a href="https://github.com/leabergero" target="_blank" rel="noopener">github.com/leabergero</a></span>
        <span>{t(MERCADOS[mercado].pie, MERCADOS[mercado].pie_en)}</span>
        {/* Ko-fi, el mismo de las otras apps. El badge va embebido en base64 y no
            traído del CDN: la CSP sólo deja imágenes propias y `data:`, y una
            imagen externa además le contaría a un tercero quién abre la app. */}
        <a className="kofi" href="https://ko-fi.com/Q4D822TFQL" target="_blank" rel="noopener"
           title="Invitame un café en Ko-fi" aria-label="Buy Me a Coffee at ko-fi.com">
          <img src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAkQAAACSCAMAAACTxiVzAAAAAXNSR0IArs4c6QAAAARnQU1BAACxjwv8YQUAAAFoUExURQAAAP9wQP9gMP9oOP9gMP9lNf9gMP9kNP9kMP9jM/9jMP9mM/9lNf9lMv9iMv9iMP9kNP9kMv9iMv9kMv9lM/9jM/9jMv9lM/9jMv9kM/9jMf9lM/9jMv9kM/9kM/9kMv9kM/9jMv9lM/9jMv9jMv9kM/9jMv/////18v/18f/18PHx8f/s5v/r5f/r4v/q4v/i2f/g1OPj4//YzP/Wxf/WxP/VxP/Ov//Mt//Mtv/LttXV1f/Fs//Fsv/Esv/BqP/Bp/+8pv+7pv+3mf+2mcfHx/+ymf+xmf+si/+siv+ojP+njP+ifP+ie7m5uf+egP+ef/+Ybf+Xbf+Vc/+Uc6urq/+NXv+LZv+KZv+DUP+BWf+AWZ2dnf94Tf93Tf95Qv93TP95Qf9uQP9vM/9uM5CQkI+Pj/9kM/9kJf9kJP9aFoKCgoGBgXR0dHNzc2ZmZmVlZVhYWFdXV0pKSklJSTw8PC4uLiAgINwb3EwAAAAndFJOUwAQECAgMDBAQFBQX2BgYGBwcHCPkJCQn5+goK+vsL/Az9Df3+Dv7+CCITYAAA9kSURBVHja7Nzxb9pGFAdwC6VttkqZaKW0WtYoEkuft5qIcp2oRuZMbpHVOgswsGAk0Ziz4c1radIU+PcXfE595ozPxkRk8D6/9YyMeXx7d74zkeLJrD/Y3NrJPbXRSnia297afLCekeYl89WjHJZ1Ne083libQ4IebGMpV9t2yhytY4LQla0vZ++EcBRDntyGNIsszqJRuhitYy+E0sVo7RssGeI9XpNiu48jGUrXGWUeYrHQNA8zsYYynA2hCLk1SeguDmUoUu6OcDqERUIi96VIWawQEstihlBqWRzL0M2NaHexNiiuO3hvj9LaXZNCZDBDKIFcRuLhOjVK5KHE2cCqoGTu44QIzX1a9DXWBCW1hYMZSu2exMLBDM0ghx0RSi2LHRFKazeDHRFKK4sdEZrbrOgLrAVKe4P2BEuBZrUtudawEmh2GZxWo/lMrfEvf6AUtnE0Q6llZhzNusfNqqHrqqqWyBQlVdV0vdpsd7HMy20j+f59Wy8pkIxMtCZGaWk9kiRpJ0mCNBlmVDAwR0u73phJECECqahtrPgyykjrdkyWBqmVsDdaQvdi/+i1o8AURR5MpWPNl05W2rRjqbGpOTJ7/f7F5WAwHEUYDi4vPvR7J5UyMPLYGS2bzZgbZzpcq/SHo6SGFydFP0UdLPtyeRJvvboBHnMwmtGFCR4ZU7RcdqRvbbFTGVzFi1EKAxNTtJRy0q4tpoDLHI7SeV/EedES2pXiT4jMUWoDL0UEK79MpNiDWSUYh0/n/Xe9nnnlqMIxx3q9d/2PHwcj1rAMLgMrv1oh2oex4uBzEPpm+RnEVzbPh36KijAmW1j6VQqRpcDY++sUnCQJEH9XN3iGi46rF6IqjBVH1HnyCE3Myv/Frmj1QkTYjugcZsOOh0WcFd2cbrN6xQppWmSILJoAfyxKnaL3ohu0hj7BaB5jPGKwdBlcrZCmRYaozd7em5BGeeQa0iRaETN5Xl7FtaX4e+QtrmmxIdJh7APtiCCxIrv92hu5TgSfah8fAODE3VegWlzTYkNUgjE6EvUh4MWbev3wYA88e6/r9frr58DqsQvV8GzEnEZPGiIgOBmPogCXGAVuR4gI8+2bwHj1j0PV99wI/eZQZwfgu6QDWAWoj0yHpiYOEfyESZmuDb4W17TYECnMbMbLgp8Z6mwP4KUbKeoQPhsEpkFwMnK5/yokDxE0MCtTaUDJJVXthDQtMkTslkfRz9CZ47Apeumw6kyIqL/AdTRyleFKXhSi/ZbHIAC45yZCwJW3IppuV4jqTsDvZ07A4WSIBuAqsj2aKES63/IWPHiLNhXhdyULTNPiQ3Q0EaIDR+C5HyIqXYhsHagahkUwr67xTa3bGaI/HIHDOYfIwtv8/3eI+OFszxH5+7t5hIivh37jmwbNthXZwuq2q9X2ccwzx36pdVxl3pN3TC8pRYi46xFfw/xDdOAIvQiG6AJc5bQhoiXSiKtp+1Ti6ox3TQgVrF2L+K8IaXd3CBRwkZpNtVWZbQlqEhn8o1Esw3+p0RX9xlgBqqB2w0/FLeHTDwFUgVwphTbxJ5HVZvQ16N0bC9EbR+jnYIhMcFXYu7NEIQKKRoBE/qezZHARbtE07F2r4LLshjzxuyarBMEWVkMBRj4qRoYMLM2ypzolwOJiVJXDD1chKB/WFH49+ePoa9CsGwrRr47Qm0CIBsF9DxgjSUJU9SshDJGtA9+NnwJVmxKiVg0gmJlTZbLFZ+3DBM0S5II/E68mQ1C+YTOsEnc4eYj469G5yHOXm36xkQ/RL47QK3aJ+rIIbKYuYayUIEQd2Y+AOEQWUCp/zrw9JUQ6BBWYDHGrLVYBOAUr4pE+7kyhdODV7Mh3rSUNEfexuNtgjty5kRXr147Qj+AqfxoOzk3wVNjH0oy4Ieq2NaBKtjBE7AnA4o6rU0LEy0fUuiTYkxGtvhM7jAE8tjsthB5OEiKaaZ4RXY18dy4hKgZD9IMj9BxCXLKn6cy6ASsOUQsonStONzJEBUJkCFAIUcAjW5PftqwahqaApxG1oaVohq5FPpdxCtfkAinw3ZbOHGcPJwqRxl7PvgKezuSuv0x0QyfgIWlDVGBCZAL1vSPyJ4Q4YSdIeTthiOS3NiUOkU38r50i/7V3/q9tW2scPk0oYbCOG1h3KSM3W26ClNkmpoKaSz1xK7CzRVCHJp1cERchRg4jbbZki/3vr3ZVvzr67ORIPso0yPv81NqKdPTq0Xu+SqZEBBKpzZph3tpEac0eU41ABaLvoZainOVmgg2xoi2elOMO0/lBhpQAVccWvc7JkZv/ehJFUVaqIPpArHwUZh/RTjqRWh6vEPkgVeu+qI5ZfEeVyHljkuiVZk0a7cWvKJEfy3ISYSqi4MW3SDSkKZaMQKp785UN3KS4kCeUAOmn2q3PWZ2kULCuGpShLKicmseJoGUI3bpICdOw2AzzLCSi405nc86dsvXZgQMMpkpPLTYcEvGTkhJhKurrYzGCLrAL7V9P2QSv1qFu92PyQPUxwZMGz1/kP0nVYuKNYpaIJEngsEG+suthHZvaSRTgojRzKnqlqcsoEXlGb5FOXFIiUuMYAqyT6JTOWNvclHNi7OelpGyBZEFKW2pTogsVXep/JMq/UiOCfOyVl+gEZY/yZ9OFY1CorSQKc8tjf3MoFVVLRIPfZxkXUCrTUpCTsEedTaNE6jXpwigTAYJknMCFfru8H6lZ7Y1zuKCGDt2y+ZgkQcjsDpbcLSkR7SQYE6fLU6N7YZwjC31QXSIM8iXVRCWGin5Q3qI2eH0xndGzi5iIzONEky7VMGaJYMCxS9vrJOpi6wSbNkl2JRDKZkh6GvTan9C5MjbUG71lTQNqJ6Ul8hwtSVYGDb6dRDEsSVzwHU3kAz85S6aaNzokpSTCMbvDchKpcx8xBUorkQcXx9VI1He0HOsf4yFQIkwriEcZAarG0hJ1V5aoV8dzZy9hfezBz9ru/T7VYjMiP3Q9lKUkwrq7a5YIU1Gf7qYKEnXqkIhm5MpJ1NFKpJ9PjEpL1L5dopGjxVtdIjpya7nKlSz6RePQAbamMy5aVKSKEqV0sgaJIBVRn+SuJTpFhxyi/kxUv0T1ZyJ8ZujKISAXgUOL9jhxPaChkCoS4W1HEuHX0MlKRhSHGiU6TJBUEuponesfLujrJDoxtIkwm8rxqm2i4wTJD0gkSGopUZhrWc9aJove7Ds5QCFwqKpEp8ptiZ0bHOIIKJS1SBTS5TQyKs7xj3QSvVWSGXKImSqs3DvrawZFoTGIWEoU5Z+jPnPyfPcKl8UuoT+a/nF51nLAoUoSjSn6MHZIn8AQB9GRNUkUwaCQ+QkMmLpFo10oxyS/uC7CP2xXHicK4RgEbG8tEZ5ei1YoFp9gJH555ihcL1eQEL1UVpMIB3SppoIniKOC/cRxXRJJF4rX8xaEuqviU3bUShRAOfvKUWGCLqQ/KCtRCkef9HKiygBiEXoLvreWyMsLMXBUDt7kuvb7jsJTEg9mUatJlAZKPhlRn6GwSCbCgoMSthId5nxWPkiM6cWDcoLyblyQpKse5PtUbUS5iVkiyIwJrPeEmRSllRBaSxTme+vvnSL//zlrUf/PKfAeHr72ElleIn+cMQpcddArXe5vPP/fqA29HkhFfn0SpcsJ9EQR3JdAW/Et7WE5JSrvzxesjvuUQtWjdo7T/NdDWUGiSF3OO/EKO/HUacrQJelsJKLiT6luUjl4Na/Jftx3CrykMWpaxFBeIoTOxqPU1iaDKF44uJbUJJE6z+/5vudQStCfiT+iW0Ej0cTNnRT9u0sPcNL3sErSIBFM6jqu5/tdStNQhm7P7y3/cyTtJKKcd06VE2j07Nm+A9woicgLUyltJTrGHJPRo3gRI0hEthKRw8CJRLCcHSyneVUhhgXMLSlR2tbshExFAmkpEYWiNaVWURnOKRFR19VOoiO8ozKGI4oXkS7zRFyTRPrVzkOJoG4elRMZGtY39/VfmyWC5iPsRFcGT1pLRKE4o+mvErxUVn50pL1EnQhrqoy+jDFeMBhQm0QyLUrsajp/8MjIW51E+BwSNkaGuDamikTUDoKdEEcu5KF6JIqUJdK/txwzz6fZxnRqdhIVO9Av1C4fXBx4UKgmiTKyxryxwzDpF4Y3XCgnbk0LZcEy+LqaRFj0IIUywJ1rIRGkosGstEXPb5R3n3dkFUZ+gcPwJMWAZ+vM2x9j6S+IQUfT4aPsELAYLJCE/xGlEFE/y4bd4a2Bjj6VM1hsNlTKCUw+PZ3qKo1IOCp+HfgLIvgID3bSzzzyMg+hDJmmtDdbiSgVndNkPIJLYWmEO5Z3QhpHMKtjSET1kkRQAE0546TCXuMoSUx7syRNbt9JAqG1lIgGpa6VX53S0booLGP0ZRPQ1Di/1ehuEZXeTNq6yf3qlI7BcqPfGvllKpx14MvchETIiF5onvF+4DhI6+wq+57aTlFTiYhfr9aoRMgLsGh28/71c7U5ffbrdEaWtWgEpclE1OOr3LxE6gDb0+uZws3V1eWcX69IL2UVZND0O3kjvspNS4TjZuczM/Tq6q5sBpqh5ovcpERoEVVpBi5a9MaVhpjwu0Ibk8hskfmXza8HuTHapuhzIvqnSUTPEGYaXWsrsncDmHdpMBEFfI3vHLEnS4EzVk/pp12Jm3eDFixjbIRD7t//XeyJXVkanL17/vLs3eX1gsvL89eDFsxKNkaaLGCH7p7/im+kGZzkNeMecXTvCdtiS1Zl4pVQaMi/TXZv2BJfyepM+qwQs+QrsSlXYTLytAb5PER8v9gUG3JF0ijwXEel7Yds0L1jQ6zZLgs7GWVE3BO6n6wJsctRYGz4RgjxhMPA2PBvIcQXHAbGhkdCiDUOA2PDuvjAfzgOjM149ZxNDgRjVZtxfcZY12ZcnzFWbImPbHAomFX5TGTscCyY1dgRH+CmNWPZrM5Y2+NoMCsmIk5FTA2JiFtFjH0i4g4aY5mIiK85Ikz1+XuVdW5bMxXZWRcFHnFQmKqVGfCYo8JU4bFA1riHxlRg54GYw80ixrJBhDzk0DBleSgyuHHNrMjnQoWnP5iq/EsItoipwyGu0Zi66jLkIff0mVvZeyiMrLNFTMW+PbLGY9eMlscPRDkecTJi/pK9z0Vp1vktD4xEvs6qMk5GzIrsbIgPsEbMyuwtBodYI2ZldjYfiBX5bIvDx0i5vSFsWH+0zTG832xTErLx6Mm3HMr7ye6TL8ggWx5sbH65tb3Ly9buCXu73259ublRUqA/AWMP15JLBAPEAAAAAElFTkSuQmCC" alt="Buy Me a Coffee at ko-fi.com" />
        </a>
      </footer>
    </>
  );
}

ReactDOM.createRoot(document.getElementById("raiz")).render(<App />);
