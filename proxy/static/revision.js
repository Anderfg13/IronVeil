"use strict";
/* Consola de revision humana de IronVeil.
   El texto de las peticiones puede ser un ataque: aqui NUNCA se inserta como
   HTML. Todo se pinta con textContent / nodos de texto (ver `h()`). */

/* Tiempo real: el servidor avisa por un canal abierto (SSE) cuando la cola cambia.
   El sondeo queda solo como red de seguridad: cada SONDEO_MS si el canal esta
   caido, y cada RESPALDO_MS aunque este vivo (por si se perdiera un aviso). */
const SONDEO_MS = 3000;
const RESPALDO_MS = 30000;
const AVISO_INFO_MS = 6000;
const CLAVE_ATAJOS = "ironveil-atajos";

const estado = {
  pendientes: [],
  decisiones: [],
  memoria: { activa: false, persistente: true, reglas: [] },
  estadisticas: null,
  seleccion: null,
  pestana: "pendientes",
  sesion: null,
  ultimaCarga: 0,
  resultado: null,
  mostrado: null,
  moverFoco: false,
  cargado: false,
  enLinea: null,
  enVivo: false,
  atajos: true,
};

const $ = (id) => document.getElementById(id);

/* Crea un elemento; los hijos string se insertan como texto, nunca como HTML. */
function h(etiqueta, atributos, ...hijos) {
  const nodo = document.createElement(etiqueta);
  for (const [clave, valor] of Object.entries(atributos || {})) {
    if (valor === null || valor === undefined || valor === false) continue;
    if (clave === "class") nodo.className = valor;
    else if (clave.startsWith("on")) nodo.addEventListener(clave.slice(2), valor);
    else nodo.setAttribute(clave, valor === true ? "" : String(valor));
  }
  for (const hijo of hijos.flat()) {
    if (hijo === null || hijo === undefined || hijo === false) continue;
    nodo.append(hijo instanceof Node ? hijo : document.createTextNode(String(hijo)));
  }
  return nodo;
}

function plural(n, uno, varios) {
  return n === 1 ? uno : varios;
}

function duracion(segundos) {
  if (segundos < 60) return `${segundos} s`;
  const m = Math.floor(segundos / 60);
  if (m < 60) return `${m} min ${String(segundos % 60).padStart(2, "0")} s`;
  return `${Math.floor(m / 60)} h ${m % 60} min`;
}

function hora(iso) {
  const fecha = new Date(iso);
  return Number.isNaN(fecha.getTime()) ? "" : fecha.toLocaleTimeString("es", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

/* ---------- Red ---------- */

async function api(ruta, opciones = {}) {
  const cabeceras = { ...opciones.headers };
  if ((opciones.method === "POST" || opciones.method === "DELETE") && estado.sesion?.csrf) {
    cabeceras["X-CSRF-Token"] = estado.sesion.csrf;
  }
  const respuesta = await fetch(ruta, { credentials: "same-origin", ...opciones, headers: cabeceras });
  if (respuesta.status === 401) {
    window.location.assign("/revision/login");
    throw new Error("sesion");
  }
  return respuesta;
}

/* Region viva, oculta y pequena: anuncia solo lo importante (un resultado, una
   peticion nueva, un cambio de conexion), sin que el lector relea la pagina. */
function anunciar(texto) {
  const region = $("anuncios");
  region.textContent = "";
  setTimeout(() => { region.textContent = texto; }, 50);
}

/* Los errores se quedan hasta que la persona los cierra (role="alert"); los
   informativos son temporales (role="status"). */
function aviso(texto, error = false) {
  const contenedor = $("avisos");
  if (error) {
    for (const previo of contenedor.querySelectorAll(".aviso.error")) {
      if (previo.dataset.texto === texto) previo.remove();
    }
  }
  const nodo = h("div", { class: error ? "aviso error" : "aviso", role: error ? "alert" : "status", "data-texto": texto },
    h("p", {}, texto),
    error && h("button", { class: "cerrar-aviso", type: "button", onclick: () => nodo.remove() }, "Cerrar", h("span", { class: "solo-lectores" }, " aviso")));
  contenedor.append(nodo);
  if (!error) setTimeout(() => nodo.remove(), AVISO_INFO_MS);
}

/* ---------- Encabezado ---------- */

/* El texto de estado cambia cada segundo, asi que NO es una region viva: solo
   se anuncia cuando la conexion cambia de estado. */
function pintarVivo(ok) {
  $("vivo").classList.toggle("caido", !ok);
  const segundos = Math.max(0, Math.round((Date.now() - estado.ultimaCarga) / 1000));
  $("vivo-estado").textContent = ok ? "En vivo" : "Sin conexión con el proxy";
  const detalle = estado.enVivo ? " · tiempo real" : ` · actualizado hace ${segundos} s`;
  $("vivo-detalle").textContent = ok ? detalle : "";
  if (estado.cargado && estado.enLinea !== null && estado.enLinea !== ok) {
    anunciar(ok ? "Conexión con el proxy recuperada." : "Se perdió la conexión con el proxy.");
  }
  estado.enLinea = ok;
}

function esperaMaxima() {
  const e = estado.estadisticas;
  if (!e?.pendientes) return 0;
  return e.espera_maxima_s + Math.round((Date.now() - estado.ultimaCarga) / 1000);
}

function pintarFranja() {
  const e = estado.estadisticas;
  if (!e) return;
  $("f-pendientes").replaceChildren(
    ...(e.pendientes
      ? [h("b", {}, String(e.pendientes)), ` ${plural(e.pendientes, "petición pendiente", "peticiones pendientes")}`]
      : ["No hay peticiones pendientes"]));
  $("f-espera").hidden = !e.pendientes;
  $("f-espera-valor").textContent = duracion(esperaMaxima());
}

function resumenHistorial(e) {
  const total = e.aprobadas + e.rechazadas;
  if (!total) return "";
  const tiempo = e.tiempo_medio_decision_s === null ? "" : ` · tiempo medio de decisión: ${duracion(e.tiempo_medio_decision_s)}`;
  return `${total} ${plural(total, "decidida", "decididas")}: ${e.aprobadas} ${plural(e.aprobadas, "aprobada", "aprobadas")} · ${e.rechazadas} ${plural(e.rechazadas, "rechazada", "rechazadas")}${tiempo}`;
}

function pintarEstadisticas(e) {
  estado.estadisticas = e;
  pintarFranja();
  $("cuenta-pendientes").textContent = e.pendientes;
  const resumen = $("resumen-historial");
  resumen.textContent = resumenHistorial(e);
  resumen.hidden = estado.pestana !== "historial" || !resumen.textContent;
  const prefijo = e.pendientes ? `(${e.pendientes}) ` : "";
  document.title = `${prefijo}Revisión humana · IronVeil`;
}

/* ---------- Lista ---------- */

function pintarLista() {
  const activo = document.activeElement?.dataset?.pid ?? null;
  construirLista();
  if (activo) {
    const mismo = document.querySelector(`[data-pid="${CSS.escape(activo)}"]`);
    if (mismo) mismo.focus();
  }
}

function construirLista() {
  const ul = $("elementos");
  ul.replaceChildren();
  $("resumen-historial").hidden = estado.pestana !== "historial" || !$("resumen-historial").textContent;
  $("resumen-memoria").hidden = estado.pestana !== "memoria" || !$("resumen-memoria").textContent;
  if (estado.pestana === "historial") return pintarHistorial(ul);
  if (estado.pestana === "memoria") return pintarMemoria(ul);
  if (!estado.pendientes.length) {
    ul.append(
      h("li", { class: "vacio" },
        h("h3", {}, "No hay nada por revisar"),
        h("p", {}, "Cuando un mecanismo retenga una petición, aparecerá aquí. La página se actualiza sola."),
        estado.decisiones.length > 0 && h("button", { class: "secundario", type: "button", onclick: () => cambiarPestana("historial") }, "Ver historial")));
    return;
  }
  for (const p of estado.pendientes) {
    const titulo = p.tipo === "herramienta" ? `Herramienta · ${p.herramienta.nombre}` : p.motivo_titulo;
    ul.append(
      h("li", {},
        h("button", {
            class: `elemento nivel-${p.sospecha.nivel}`,
            type: "button",
            "data-pid": p.id,
            "aria-current": p.id === estado.seleccion ? "true" : "false",
            onclick: () => seleccionar(p.id),
          },
          h("div", { class: "fila" }, h("strong", {}, titulo), h("span", { class: "espera", "data-id": p.id }, duracion(p.espera_s))),
          h("div", { class: "sub" }, `${p.modelo} · ${p.sospecha.lectura}`),
          h("div", { class: "vector" }, p.vector_probado || "sin vector etiquetado"))));
  }
}

function pintarHistorial(ul) {
  if (!estado.decisiones.length) {
    ul.append(h("li", { class: "vacio" },
      h("h3", {}, "Aún no hay decisiones"),
      h("p", {}, "Las que tomes aparecerán aquí, con quién y cuánto tardó."),
      estado.pendientes.length > 0 && h("button", { class: "secundario", type: "button", onclick: () => cambiarPestana("pendientes") }, "Ver pendientes")));
    return;
  }
  for (const d of estado.decisiones) {
    ul.append(
      h("li", { class: "fila-historial" },
        h("div", { class: "fila" },
          h("strong", { class: d.accion === "aprobada" ? "resultado aprobada" : "resultado rechazada" }, d.accion === "aprobada" ? "Falso positivo · aprobada" : "Ataque · rechazada"),
          h("small", {}, hora(d.decidida_en))),
        h("small", {}, `${d.tipo === "herramienta" ? d.herramienta : d.modelo} · ${d.vector_probado || "sin vector"} · ${d.revisor} · ${duracion(Math.round(d.tiempo_revision_ms / 1000))}`)));
  }
}

/* ---------- Memoria de decisiones (extension opcional) ---------- */

const MOTIVOS_MEMORIA = { filtrado: "Filtrado", clasificacion: "Clasificación", minimo_privilegio: "Mínimo privilegio" };

function fechaHora(iso) {
  const fecha = new Date(iso);
  return Number.isNaN(fecha.getTime()) ? "" : fecha.toLocaleString("es", { dateStyle: "short", timeStyle: "short" });
}

function resumenMemoria() {
  const m = estado.memoria;
  if (!m.activa) return "Apagada";
  const n = m.reglas.length;
  const guardado = m.persistente ? `guardadas en ${m.almacen}` : "SOLO en memoria: se perderán al reiniciar el proxy";
  return `${n} ${plural(n, "regla", "reglas")} · ${guardado}`;
}

function pintarMemoria(ul) {
  const reglas = estado.memoria.reglas;
  if (!estado.memoria.activa) {
    ul.append(h("li", { class: "vacio" },
      h("h3", {}, "La memoria está apagada"),
      h("p", {}, "Cuando está encendida, lo que rechazas aquí se recuerda y el mismo mensaje se rechaza solo la próxima vez."),
      h("p", {}, "Para encenderla, pon MEMORIA_RECHAZOS=1 en el archivo .env y reinicia el proxy.")));
    return;
  }
  if (!reglas.length) {
    ul.append(h("li", { class: "vacio" },
      h("h3", {}, "Aún no hay reglas"),
      h("p", {}, "Cuando rechaces una petición que un mecanismo retuvo, el proxy la recordará y rechazará sola la próxima vez que llegue igual.")));
    return;
  }
  const revisor = estado.sesion?.rol === "revisor";
  for (const r of reglas) {
    const veces = `${r.aciertos} ${plural(r.aciertos, "bloqueo automático", "bloqueos automáticos")}`;
    ul.append(
      h("li", { class: "fila-historial" },
        h("div", { class: "fila" },
          h("strong", { class: "resultado rechazada" }, "Rechazo recordado"),
          h("small", {}, fechaHora(r.decidido_en))),
        r.vista_previa && h("p", { class: "vista-previa" }, r.vista_previa),
        h("small", {}, `${r.modelo} · ${MOTIVOS_MEMORIA[r.motivo] || r.motivo} · ${r.decidido_por} · ${veces}`),
        revisor && h("div", {},
          h("button", { class: "secundario", type: "button", onclick: () => confirmarOlvidar(r) },
            "Olvidar", h("span", { class: "solo-lectores" }, " esta regla")))));
  }
}

function confirmarOlvidar(regla) {
  const dialogo = $("confirmar");
  $("confirmar-titulo").textContent = "¿Olvidar esta regla?";
  $("confirmar-texto").textContent = "La próxima vez que llegue este mensaje volverá a la cola de revisión. Esta acción queda registrada.";
  const ok = $("confirmar-ok");
  ok.className = "accion confirmar";
  ok.textContent = "Olvidar";
  ok.onclick = () => { dialogo.close(); void olvidar(regla); };
  $("confirmar-cancelar").onclick = () => dialogo.close();
  dialogo.showModal();
  $("confirmar-titulo").focus();
}

async function olvidar(regla) {
  try {
    const respuesta = await api(`/revision/memoria/${encodeURIComponent(regla.huella)}`, { method: "DELETE" });
    if (respuesta.status === 404) aviso("Esa regla ya no existía. La lista se actualizó.", true);
    else if (respuesta.status === 403) aviso("Tu cuenta no puede olvidar reglas, o la sesión caducó. Inicia sesión de nuevo con una cuenta de revisor.", true);
    else if (!respuesta.ok) aviso("No se pudo olvidar la regla. Inténtalo otra vez.", true);
    else { anunciar("Regla olvidada."); aviso("Regla olvidada: ese mensaje volverá a la cola de revisión."); }
    await cargar();
  } catch (e) {
    if (e.message !== "sesion") aviso("No hay conexión con el proxy y la regla no se olvidó. Comprueba que esté en marcha e inténtalo otra vez.", true);
  }
}

/* ---------- Expediente ---------- */

function evidenciaDeTexto(p) {
  const bloque = h("pre", { class: "evidencia", tabindex: "0", "aria-label": "Texto de la petición" });
  for (const s of p.segmentos) {
    bloque.append(s.k ? h("mark", { class: s.k, title: s.d }, s.t) : document.createTextNode(s.t));
  }
  const hayPatron = p.segmentos.some((s) => s.k === "patron" || s.k === "credencial");
  const hayCodificado = p.segmentos.some((s) => s.k === "codificado");
  return h("div", {},
    bloque,
    (hayPatron || hayCodificado) && h("div", { class: "leyenda" },
      hayPatron && h("span", {}, h("b", { class: "l-patron" }), "Subrayado continuo: coincide con un patrón de ataque"),
      hayCodificado && h("span", {}, h("b", { class: "l-codificado" }), "Subrayado punteado: texto que parece codificado")),
    p.truncado && h("div", { class: "nota-truncado" }, "Se muestran los primeros 8 000 caracteres."));
}

function evidenciaDeHerramienta(p) {
  return h("div", { class: "herramienta" },
    h("div", { class: "nombre" }, `${p.herramienta.nombre}(…)`),
    h("pre", { class: "evidencia", tabindex: "0", "aria-label": "Argumentos de la herramienta" }, p.herramienta.argumentos),
    h("div", { class: "banner-simulada" }, "Herramienta SIMULADA: aunque la apruebes no envía correos ni consulta datos reales; solo escribe en el log."));
}

const GRAVEDAD = { alta: "Alta", media: "Media", info: "Info" };

function lectura(p) {
  const s = p.sospecha;
  return h("div", { class: "lectura" },
    h("div", { class: "veredicto" }, h("strong", {}, s.lectura), h("span", {}, "Lectura orientativa de reglas simples. La decisión es tuya.")),
    h("div", {},
      h("div", { class: "espectro", role: "img", "aria-label": `Posición ${s.puntaje} de 100, de falso positivo a ataque` },
        h("div", { class: "marcas" }), h("div", { class: "pin", id: "pin" })),
      h("div", { class: "extremos" }, h("span", {}, "Falso positivo"), h("span", {}, "Ataque"))),
    p.senales.length
      ? h("ul", { class: "senales" }, p.senales.map((x) => h("li", { class: `senal ${x.nivel}` },
        h("span", { class: "gravedad" }, GRAVEDAD[x.nivel] || x.nivel),
        h("div", {}, h("b", {}, x.titulo), h("span", {}, x.detalle)))))
      : h("p", { class: "sin-senales" }, "No se encontraron señales en el contenido. Mira la razón por la que se retuvo."));
}

function pintarExpediente() {
  const caja = $("expediente");
  if (estado.resultado) { estado.mostrado = null; return pintarResultado(caja); }
  const p = estado.pendientes.find((x) => x.id === estado.seleccion);
  estado.mostrado = p ? p.id : null;
  if (!p) {
    caja.replaceChildren(h("div", { class: "vacio" },
      h("h2", { tabindex: "-1" }, estado.pendientes.length ? "Elige una petición" : "Todo en orden"),
      h("p", {}, estado.pendientes.length ? "Selecciónala en la lista para ver la evidencia y decidir." : "No hay peticiones esperando una decisión.")));
    enfocarTitulo(caja);
    return;
  }
  const puedeDecidir = estado.sesion?.rol === "revisor";
  caja.replaceChildren(
    h("header", {},
      h("h2", { tabindex: "-1" }, p.tipo === "herramienta" ? "Solicitud de herramienta" : "Petición retenida"),
      h("span", { class: "etiqueta" }, p.modelo),
      h("span", { class: "etiqueta mono" }, p.vector_probado || "sin vector"),
      p.tipo === "herramienta" && h("span", { class: "etiqueta simulada" }, "Simulada"),
      h("span", { class: "espera-grande", id: "espera-grande", "data-id": p.id }, `En cola hace ${duracion(p.espera_s)}`)),
    h("div", { class: "bloque" }, h("h3", {}, p.tipo === "herramienta" ? "Lo que el modelo quiere ejecutar" : "Lo que escribió el usuario"),
      p.tipo === "herramienta" ? evidenciaDeHerramienta(p) : evidenciaDeTexto(p)),
    h("div", { class: "bloque" }, h("h3", {}, `Por qué se retuvo: ${p.motivo_titulo}`), h("p", {}, p.motivo_explicacion)),
    h("div", { class: "bloque" }, h("h3", {}, "Lectura orientativa"), lectura(p)),
    h("div", { class: "bloque" }, h("h3", {}, "Contexto"),
      h("dl", { class: "contexto" },
        h("div", {}, h("dt", {}, "Cliente"), h("dd", {}, p.cliente)),
        h("div", {}, h("dt", {}, "Modelo"), h("dd", {}, p.modelo)),
        h("div", {}, h("dt", {}, "Vector probado"), h("dd", {}, p.vector_probado || "sin etiquetar")),
        h("div", {}, h("dt", {}, "Encolada"), h("dd", {}, hora(p.encolado_en))),
        h("div", {}, h("dt", {}, "Identificador"), h("dd", {}, p.id.slice(0, 8))))),
    h("div", { class: "decision" },
      h("div", { class: "ayuda" }, puedeDecidir ? "Rechazar confirma el ataque y no llega al modelo. Aprobar la reconoce como falso positivo y la deja pasar." : "Tu rol solo permite ver la cola."),
      h("button", { class: "accion aprobar", type: "button", disabled: !puedeDecidir, onclick: () => confirmar(p, "aprobar") }, "Es un falso positivo · aprobar", h("kbd", {}, "A")),
      h("button", { class: "accion rechazar", type: "button", disabled: !puedeDecidir, onclick: () => confirmar(p, "rechazar") }, "Es un ataque · rechazar", h("kbd", {}, "R"))));
  requestAnimationFrame(() => {
    const pin = $("pin");
    if (pin) pin.style.setProperty("--pos", `${p.sospecha.puntaje}%`);
    enfocarTitulo(caja);
  });
}

/* Tras una decision el expediente se reemplaza: el foco pasa al titulo nuevo
   para que quien usa teclado o lector de pantalla no se quede sin posicion. */
function enfocarTitulo(caja) {
  if (!estado.moverFoco) return;
  estado.moverFoco = false;
  const titulo = caja.querySelector("h2, h3");
  if (titulo) { titulo.setAttribute("tabindex", "-1"); titulo.focus(); }
}

const TEXTOS_MEMORIA = {
  recordada: "Se recordó este rechazo: el mismo mensaje se rechazará solo la próxima vez.",
  ya_recordada: "Este mensaje ya estaba recordado como rechazado.",
  memoria_llena: "La memoria está llena: este rechazo NO se recordó. Olvida alguna regla en la pestaña Memoria.",
  recordada_sin_guardar: "Se recordó, pero NO se pudo guardar en disco: se perderá al reiniciar el proxy.",
};

function textoMemoria(clave) {
  return TEXTOS_MEMORIA[clave] || "";
}

function pintarResultado(caja) {
  const r = estado.resultado;
  const quedan = estado.pendientes.length > 0;
  caja.replaceChildren(h("div", { class: "resultado" },
    h("h2", { class: r.accion, tabindex: "-1" }, r.accion === "aprobada" ? "Aprobada: se reconoció como falso positivo" : "Rechazada: se confirmó el ataque"),
    h("p", {}, `Decisión de ${r.revisor} registrada en ${duracion(Math.round(r.tiempoMs / 1000))}.`),
    r.memoria && h("p", { class: "nota-memoria" }, textoMemoria(r.memoria)),
    r.detalle && h("div", {}, h("h3", {}, r.tituloDetalle), h("pre", { tabindex: "0" }, r.detalle)),
    h("button", { class: "siguiente", type: "button", onclick: () => { estado.resultado = null; estado.moverFoco = true; seleccionarPrimera(); } }, quedan ? "Ver siguiente petición" : "Volver a la lista")));
  enfocarTitulo(caja);
}

/* ---------- Decidir ---------- */

/* El foco va al titulo, no a un boton: ninguna opcion queda como predeterminada,
   asi una tecla suelta (A, R) no confirma por accidente (HIG: alerts.md). */
/* Con la memoria encendida, rechazar una retencion de contenido la recuerda. */
function seRecordaria(p) {
  return estado.memoria.activa && p.tipo !== "herramienta" && Object.hasOwn(MOTIVOS_MEMORIA, p.motivo);
}

function textoConfirmacion(p, aprobar) {
  if (!aprobar) {
    const base = "La petición se descarta y no llega al modelo. Esta acción queda registrada.";
    return seRecordaria(p) ? `${base} Además se recordará: el mismo mensaje se rechazará solo la próxima vez (lo puedes olvidar en la pestaña Memoria).` : base;
  }
  if (p.tipo === "herramienta") return "Se ejecutará la versión simulada de la herramienta.";
  return "La petición se enviará al modelo y recibirás su respuesta.";
}

function confirmar(p, accion) {
  const dialogo = $("confirmar");
  const aprobar = accion === "aprobar";
  $("confirmar-titulo").textContent = aprobar ? "¿Confirmas que es un falso positivo?" : "¿Confirmas que es un ataque?";
  $("confirmar-texto").textContent = textoConfirmacion(p, aprobar);
  const ok = $("confirmar-ok");
  ok.className = "accion confirmar";
  ok.textContent = aprobar ? "Aprobar" : "Rechazar";
  ok.onclick = () => { dialogo.close(); void decidir(p, accion); };
  $("confirmar-cancelar").onclick = () => dialogo.close();
  dialogo.showModal();
  $("confirmar-titulo").focus();
}

async function decidir(p, accion) {
  const inicio = Date.now();
  try {
    const respuesta = await api(`/revision/${encodeURIComponent(p.id)}/${accion}`, { method: "POST" });
    if (respuesta.status === 404) { aviso("Otra persona ya resolvió esta petición. La lista se actualizó con las que siguen pendientes.", true); await cargar(); return; }
    if (respuesta.status === 403) { aviso("Tu cuenta no puede decidir, o la sesión caducó. Inicia sesión de nuevo con una cuenta de revisor.", true); return; }
    if (!respuesta.ok) { aviso("No se pudo registrar la decisión. Comprueba que la petición siga en la lista e inténtalo otra vez.", true); return; }
    const cuerpo = await respuesta.json();
    const aprobada = accion === "aprobar";
    let detalle = null, tituloDetalle = "";
    if (aprobada && cuerpo.resultado_simulado) { detalle = JSON.stringify(cuerpo.resultado_simulado, null, 2); tituloDetalle = "Resultado simulado"; }
    else if (aprobada && cuerpo.message) { detalle = cuerpo.message.content; tituloDetalle = "Respuesta del modelo"; }
    estado.resultado = {
      accion: aprobada ? "aprobada" : "rechazada",
      revisor: estado.sesion.usuario,
      tiempoMs: cuerpo.tiempo_revision_humana_ms ?? Date.now() - inicio,
      memoria: cuerpo.memoria || null,
      detalle, tituloDetalle,
    };
    estado.moverFoco = true;
    anunciar(aprobada ? "Petición aprobada como falso positivo." : "Petición rechazada como ataque.");
    await cargar();
    pintarExpediente();
  } catch (e) {
    if (e.message !== "sesion") aviso("No hay conexión con el proxy y la decisión no se registró. Comprueba que el proxy esté en marcha e inténtalo otra vez.", true);
  }
}

/* ---------- Seleccion y carga ---------- */

function seleccionar(id) { estado.seleccion = id; estado.resultado = null; pintarLista(); pintarExpediente(); }
function seleccionarPrimera() { estado.seleccion = estado.pendientes[0] ? estado.pendientes[0].id : null; pintarLista(); pintarExpediente(); }

/* Varios avisos seguidos se funden: si ya hay una carga en curso, se repite una
   sola vez al terminar, en vez de lanzar una peticion por aviso. */
let cargando = false;
let recargar = false;
async function cargar() {
  if (cargando) { recargar = true; return; }
  cargando = true;
  try { await cargarAhora(); } finally { cargando = false; }
  if (recargar) { recargar = false; void cargar(); }
}

async function cargarAhora() {
  try {
    const [panel, historial, memoria] = await Promise.all([api("/revision/panel").then((r) => r.json()), api("/revision/historial").then((r) => r.json()), api("/revision/memoria").then((r) => r.json())]);
    const vistoAntes = estado.pendientes.map((p) => p.id).join();
    const conocidas = new Set(estado.pendientes.map((p) => p.id));
    estado.pendientes = panel.pendientes;
    estado.decisiones = historial.decisiones;
    pintarPestanaMemoria(memoria);
    estado.ultimaCarga = Date.now();
    pintarEstadisticas(panel.estadisticas);
    const existe = estado.pendientes.some((p) => p.id === estado.seleccion);
    if (!existe && !estado.resultado) estado.seleccion = estado.pendientes[0] ? estado.pendientes[0].id : null;
    const cambio = vistoAntes !== estado.pendientes.map((p) => p.id).join();
    if (cambio || estado.pestana !== "pendientes") pintarLista();
    // El expediente solo se repinta si cambio la peticion mostrada: una llegada
    // nueva no debe borrar el scroll, la seleccion de texto ni el foco.
    if (!document.querySelector("dialog[open]") && !estado.resultado && estado.mostrado !== estado.seleccion) pintarExpediente();
    const nuevas = estado.pendientes.filter((p) => !conocidas.has(p.id)).length;
    const textoNuevas = nuevas === 1 ? "Llegó 1 petición nueva" : `Llegaron ${nuevas} peticiones nuevas`;
    if (estado.cargado && nuevas) anunciar(`${textoNuevas}. Pendientes: ${estado.pendientes.length}.`);
    pintarVivo(true);
    estado.cargado = true;
  } catch (e) {
    if (e.message !== "sesion") pintarVivo(false);
  }
}

/* Contadores de espera: cuentan en el navegador entre cargas, sin repintar. */
function tictac() {
  const pasados = Math.round((Date.now() - estado.ultimaCarga) / 1000);
  for (const p of estado.pendientes) {
    for (const nodo of document.querySelectorAll(`[data-id="${CSS.escape(p.id)}"]`)) {
      nodo.textContent = nodo.id === "espera-grande" ? `En cola hace ${duracion(p.espera_s + pasados)}` : duracion(p.espera_s + pasados);
    }
  }
  pintarFranja();
  if (estado.ultimaCarga) pintarVivo(!$("vivo").classList.contains("caido"));
}

/* ---------- Atajos de teclado ---------- */

/* Una tecla suelta puede dispararse por dictado por voz o por tecnologia de
   apoyo. Por eso solo actuan con el foco dentro de la lista o del expediente,
   nunca con modificadores ni repeticion, y se pueden desactivar (criterio
   propio; la HIG pide pocos atajos propios y con Command en keyboards.md). */
function atajos(evento) {
  if (!estado.atajos || evento.repeat || evento.isComposing) return;
  if (evento.ctrlKey || evento.metaKey || evento.altKey || evento.shiftKey) return;
  const destino = evento.target;
  if (!destino.closest || destino.closest("input, textarea, select, dialog, [contenteditable]")) return;
  if (!destino.closest(".lista, #expediente")) return;
  const tecla = evento.key.toLowerCase();
  const idx = estado.pendientes.findIndex((p) => p.id === estado.seleccion);
  const actual = estado.pendientes[idx];
  const revisor = estado.sesion.rol === "revisor" && !estado.resultado;
  if (tecla === "j" && estado.pendientes[idx + 1]) seleccionar(estado.pendientes[idx + 1].id);
  else if (tecla === "k" && idx > 0) seleccionar(estado.pendientes[idx - 1].id);
  else if (tecla === "a" && actual && revisor) confirmar(actual, "aprobar");
  else if (tecla === "r" && actual && revisor) confirmar(actual, "rechazar");
}

function aplicarAtajos(activos) {
  estado.atajos = activos;
  document.body.classList.toggle("sin-atajos", !activos);
  $("atajos-activos").checked = activos;
}

function iniciarAtajos() {
  let guardado = null;
  try { guardado = localStorage.getItem(CLAVE_ATAJOS); } catch { /* sin almacenamiento: se ignora */ }
  aplicarAtajos(guardado !== "no");
  $("atajos-activos").addEventListener("change", (evento) => {
    aplicarAtajos(evento.target.checked);
    try { localStorage.setItem(CLAVE_ATAJOS, evento.target.checked ? "si" : "no"); } catch { /* idem */ }
  });
  document.addEventListener("keydown", atajos);
}

/* ---------- Pestanas (patron tablist) ---------- */

const PESTANAS = ["pendientes", "historial", "memoria"];

/* La pestana Memoria siempre se ve: apagada, explica como encenderla (si se ocultara,
   quien no la ve no sabria por que "no pasa nada"). */
function pestanasVisibles() {
  return PESTANAS;
}

function pintarPestanaMemoria(memoria) {
  estado.memoria = memoria;
  $("cuenta-memoria").textContent = memoria.activa ? memoria.reglas.length : "–";
  $("resumen-memoria").textContent = resumenMemoria();
}

function cambiarPestana(nombre, enfocar = false) {
  estado.pestana = nombre;
  for (const id of PESTANAS) {
    const tab = $(`tab-${id}`);
    const activa = id === nombre;
    tab.setAttribute("aria-selected", String(activa));
    tab.setAttribute("tabindex", activa ? "0" : "-1");
  }
  $("panel-lista").setAttribute("aria-labelledby", `tab-${nombre}`);
  pintarLista();
  if (enfocar) $(`tab-${nombre}`).focus();
}

function teclasPestanas(evento) {
  const visibles = pestanasVisibles();
  const idx = visibles.indexOf(estado.pestana);
  let destino = null;
  if (evento.key === "ArrowRight") destino = (idx + 1) % visibles.length;
  else if (evento.key === "ArrowLeft") destino = (idx - 1 + visibles.length) % visibles.length;
  else if (evento.key === "Home") destino = 0;
  else if (evento.key === "End") destino = visibles.length - 1;
  if (destino === null) return;
  evento.preventDefault();
  cambiarPestana(visibles[destino], true);
}

/* ---------- Canal en vivo ---------- */

function conectarEnVivo() {
  if (!("EventSource" in window)) return;
  const fuente = new EventSource("/revision/eventos");
  // Al abrir se carga una vez: cubre lo que cambio entre la primera carga y la conexion.
  fuente.addEventListener("open", () => { estado.enVivo = true; void cargar(); });
  fuente.addEventListener("cambio", () => cargar());
  fuente.addEventListener("sesion", () => { fuente.close(); window.location.assign("/revision/login"); });
  fuente.addEventListener("lleno", () => { fuente.close(); estado.enVivo = false; });
  // Si se cae, el navegador reintenta solo; mientras tanto manda el sondeo.
  fuente.addEventListener("error", () => { estado.enVivo = false; });
}

/* ---------- Arranque ---------- */

async function iniciar() {
  iniciarAtajos();
  const respuesta = await api("/revision/sesion");
  estado.sesion = await respuesta.json();
  $("usuario-nombre").textContent = estado.sesion.usuario;
  $("usuario-rol").textContent = estado.sesion.rol === "revisor" ? "Revisor" : "Observador";
  $("avatar").textContent = estado.sesion.usuario.slice(0, 1).toUpperCase();
  $("aviso-lab").hidden = estado.sesion.autenticacion;
  const salir = $("salir");
  salir.hidden = !estado.sesion.autenticacion;
  salir.addEventListener("click", async () => { await fetch("/revision/logout", { method: "POST", credentials: "same-origin" }); window.location.assign("/revision/login"); });
  for (const id of PESTANAS) $(`tab-${id}`).addEventListener("click", () => cambiarPestana(id));
  document.querySelector('[role="tablist"]').addEventListener("keydown", teclasPestanas);
  await cargar();
  pintarExpediente();
  conectarEnVivo();
  setInterval(() => {
    if (document.hidden) return;
    if (!estado.enVivo || Date.now() - estado.ultimaCarga > RESPALDO_MS) void cargar();
  }, SONDEO_MS);
  setInterval(tictac, 1000);
}

/* Script de tipo "module" (ver revision.html): admite await en el nivel superior. */
try {
  await iniciar();
} catch (e) {
  if (e.message !== "sesion") $("vivo-estado").textContent = "No se pudo iniciar la consola";
}
