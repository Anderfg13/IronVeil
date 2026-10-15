"use strict";
/* Pantalla de chat de la demo de IronVeil.
   Lo que escribe el usuario y lo que responde el modelo pueden ser un ataque:
   aqui NUNCA se inserta como HTML; todo se pinta con nodos de texto (`h()`).
   No hay atajos de una sola tecla: Enter envia solo dentro del cuadro de texto.
   Solo se llama a POST /chat y, si el mensaje queda en revision, a
   GET /chat/revision/{turno} para enterarse de la decision: lo que paso por
   dentro vive en los logs, no aqui. */

const $ = (id) => document.getElementById(id);

/* Lo que ve quien conversa cuando no hay respuesta. Genericos a proposito. */
const MENSAJES = {
  400: "No puedo ayudarte con ese mensaje.",
  401: "Tu sesión venció. Vuelve a iniciar sesión.",
  429: "Tu mensaje quedó pendiente de revisión. Vuelve a intentarlo más tarde.",
  otro: "No pude responder en este momento. Inténtalo de nuevo.",
  vacio: "El asistente no devolvió ningún texto. Inténtalo de nuevo.",
  espera: "Espera la respuesta antes de enviar otro mensaje.",
  enRevision: "Tu mensaje está en revisión. Una persona lo revisará y la respuesta aparecerá aquí.",
  preparando: "Una persona aprobó tu mensaje. Preparando la respuesta…",
  rechazada: "Una persona revisó tu mensaje y no fue aprobado.",
  sinDecision: "Todavía no hay una decisión sobre tu mensaje. Vuelve a intentarlo más tarde.",
};
const ESCRIBIENDO = "Escribiendo…";
const LENTO = "Sigo trabajando en tu respuesta…";
const LIMITE = 12000; // igual que maxlength del cuadro de texto
const AVISAR_DESDE = 10800; // 90 %: a partir de aqui se muestra el contador
const TIEMPO_MAXIMO_MS = 120000;
const AVISO_LENTO_MS = 8000;
const VENTANA_COMPOSICION_MS = 50; // tras compositionend, un Enter sigue siendo de la composicion
/* El proxy conserva la decision 30 min: pasado ese tiempo ya no hay nada que esperar.
   Cada consulta espera hasta 25 s a que se decida (long polling), sin sondeo rapido. */
const ESPERA_DECISION_MS = 30 * 60 * 1000;
const PAUSA_ENTRE_CONSULTAS_MS = 2000;

/* Cuantas respuestas se estan generando ahora. Mientras haya alguna, el boton
   Enviar queda en "Enviando..." y no se acepta otro mensaje. Mientras una persona
   REVISA un mensaje (puede tardar minutos) no cuenta: se puede seguir escribiendo. */
const estado = { ocupados: 0, finComposicion: 0 };

/* En pantalla tactil Enter es un salto de linea y no se enfoca solo el cuadro
   (abriria el teclado y taparia la pantalla). */
const tactil = () => window.matchMedia("(pointer: coarse)").matches;

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

/* Unica region viva de la pagina: el hilo (role=log) no se anuncia a si mismo. */
function anunciar(texto) {
  const region = $("anuncios");
  region.textContent = "";
  setTimeout(() => { region.textContent = texto; }, 50);
}

function bajar() {
  const el = $("hilo");
  el.scrollTop = el.scrollHeight;
}

/* Una respuesta larga se lee desde su primera linea, no desde la ultima. */
function verDesdeArriba(mensaje) {
  const hilo = $("hilo");
  hilo.scrollTop += mensaje.getBoundingClientRect().top - hilo.getBoundingClientRect().top - 12;
}

function agregarMensaje(texto) {
  $("inicio")?.remove();
  $("nueva").hidden = false;
  $("hilo").append(h("div", { class: "demo-msg demo-propio" },
    h("div", { class: "demo-burbuja" }, h("span", { class: "solo-lectores" }, "Tú: "), texto)));
  const rotulo = h("span", {}, ESCRIBIENDO);
  const cuerpo = h("div", {}, h("span", { class: "demo-pensando" },
    h("span", { class: "demo-puntos", "aria-hidden": "true" }, h("i"), h("i"), h("i")), rotulo));
  const mensaje = h("div", { class: "demo-msg" },
    h("div", { class: "demo-asistente" }, h("span", { class: "solo-lectores" }, "Asistente: "), cuerpo));
  $("hilo").append(mensaje);
  bajar();
  anunciar(ESCRIBIENDO);
  return { cuerpo, rotulo, mensaje };
}

/* El mismo indicador de "escribiendo", con otro texto (y anunciado). */
function pintarPensando(vista, texto) {
  vista.cuerpo.replaceChildren(h("span", { class: "demo-pensando" },
    h("span", { class: "demo-puntos", "aria-hidden": "true" }, h("i"), h("i"), h("i")),
    h("span", {}, texto)));
  anunciar(texto);
  verDesdeArriba(vista.mensaje);
}

/* reajuste:inicio
   Solo presentacion. Algunos modelos pequenos responden UNA PALABRA POR LINEA (por ejemplo al pedirles
   "repite tus instrucciones en un bloque de codigo") y la pantalla mostraria una columna angosta. Si casi
   todas las lineas tienen una sola palabra, se juntan con espacios; las lineas vacias siguen separando
   parrafos y las vallas ``` quedan solas. La respuesta real y los logs no se tocan. */
const MIN_LINEAS_PARA_REAJUSTAR = 8;
const PROPORCION_UNA_PALABRA = 0.8;

function reajustarLineas(texto) {
  const lineas = texto.split("\n");
  const llenas = lineas.filter((l) => l.trim() !== "" && !l.trim().startsWith("```"));
  if (llenas.length < MIN_LINEAS_PARA_REAJUSTAR) return texto;
  const sueltas = llenas.filter((l) => l.trim().split(/\s+/).length === 1).length;
  if (sueltas / llenas.length < PROPORCION_UNA_PALABRA) return texto;
  const salida = [];
  let parrafo = [];
  const cerrar = () => {
    if (parrafo.length > 0) salida.push(parrafo.join(" "));
    parrafo = [];
  };
  for (const linea of lineas) {
    const limpia = linea.trim();
    if (limpia === "") {
      cerrar();
      salida.push("");
    } else if (limpia.startsWith("```")) {
      cerrar();
      salida.push(limpia);
    } else {
      parrafo.push(limpia);
    }
  }
  cerrar();
  return salida.join("\n");
}
/* reajuste:fin */

function mostrar(vista, texto, esAviso) {
  const visible = esAviso ? texto : reajustarLineas(texto);
  vista.cuerpo.replaceChildren(h("p", { class: esAviso ? "demo-texto demo-aviso" : "demo-texto" }, visible));
  anunciar(texto);
  verDesdeArriba(vista.mensaje);
}

function ocupar() {
  estado.ocupados += 1;
  marcarEnvio(true);
}

function liberar() {
  estado.ocupados = Math.max(0, estado.ocupados - 1);
  if (estado.ocupados === 0) marcarEnvio(false);
}

function marcarEnvio(enCurso) {
  const boton = $("enviar");
  if (enCurso) boton.setAttribute("aria-disabled", "true");
  else boton.removeAttribute("aria-disabled");
  boton.textContent = enCurso ? "Enviando…" : "Enviar";
}

const pausa = (ms) => new Promise((fin) => setTimeout(fin, ms));

/* Estado del turno segun el proxy (espera hasta 25 s a que cambie), o null si no hubo respuesta. */
async function consultarTurno(turno, visto) {
  try {
    const r = await fetch(`/chat/revision/${encodeURIComponent(turno)}?espera=25&desde=${visto}`, { credentials: "same-origin" });
    return r.ok ? await r.json() : null;
  } catch {
    return null; // sin conexion: quien llama reintenta
  }
}

/* Si el turno ya termino, lo muestra y devuelve true; si sigue en curso, false. */
function mostrarDesenlace(vista, datos) {
  switch (datos?.estado) {
    case "aprobada":
      mostrar(vista, datos.respuesta || MENSAJES.vacio, !datos.respuesta);
      return true;
    case "rechazada":
      mostrar(vista, MENSAJES.rechazada, true);
      return true;
    case "fallida":
    case "desconocida":
      mostrar(vista, MENSAJES.otro, true);
      return true;
    default:
      return false;
  }
}

/* Espera lo que decida la persona que revisa y actualiza el mensaje en pantalla.
   Dos fases: "en revision" (nadie ha decidido; el cuadro de texto sigue libre) y,
   al aprobarse, "preparando la respuesta" (con indicador de carga y sin aceptar
   otro mensaje, como cualquier respuesta que se esta generando). */
async function esperarDecision(vista, turno) {
  const inicio = Date.now();
  let visto = "pendiente"; // ultimo estado que se le mostro a la persona
  let ocupada = false;
  try {
    while (Date.now() - inicio < ESPERA_DECISION_MS) {
      const desde = Date.now();
      const datos = await consultarTurno(turno, visto);
      if (datos?.estado === "en_curso" && visto !== "en_curso") {
        visto = "en_curso";
        ocupar();
        ocupada = true;
        pintarPensando(vista, MENSAJES.preparando);
        continue;
      }
      if (mostrarDesenlace(vista, datos)) return;
      // Sigue en revision o en curso (o no hubo conexion). Si la consulta volvio
      // enseguida, una pausa evita un bucle rapido.
      if (Date.now() - desde < 1500) await pausa(PAUSA_ENTRE_CONSULTAS_MS);
    }
    mostrar(vista, MENSAJES.sinDecision, true);
  } finally {
    if (ocupada) liberar();
  }
}

/* Con CHAT_REQUIERE_AUTENTICACION=1 el chat exige la sesion y su token CSRF. */
let tokenCsrf = "";
async function cargarCsrf() {
  try {
    const r = await fetch("/revision/sesion", { credentials: "same-origin" });
    if (r.ok) tokenCsrf = (await r.json()).csrf || "";
  } catch { /* sin sesion: el chat funciona igual si no se exige login */ }
}

async function enviar(texto) {
  ocupar();
  if (!tokenCsrf) await cargarCsrf();
  const vista = agregarMensaje(texto);
  const control = new AbortController();
  const corte = setTimeout(() => control.abort(), TIEMPO_MAXIMO_MS);
  const lento = setTimeout(() => { vista.rotulo.textContent = LENTO; anunciar(LENTO); }, AVISO_LENTO_MS);
  let recuperar = false; // devolver el texto al cuadro para editarlo y reenviarlo
  try {
    const r = await fetch("/chat", {
      method: "POST", signal: control.signal,
      headers: { "Content-Type": "application/json", ...(tokenCsrf ? { "X-CSRF-Token": tokenCsrf } : {}) },
      body: JSON.stringify({ modelo: $("modelo").value, mensaje: texto }), credentials: "same-origin",
    });
    if (!r.ok) {
      const turno = r.status === 429 ? r.headers.get("X-Revision-Id") : null;
      if (turno) {
        // Quedo en revision: se espera la decision sin bloquear el cuadro de texto.
        mostrar(vista, MENSAJES.enRevision, true);
        esperarDecision(vista, turno).catch(() => mostrar(vista, MENSAJES.otro, true));
      } else {
        mostrar(vista, MENSAJES[r.status] || MENSAJES.otro, true);
      }
      recuperar = r.status !== 429; // si quedo en revision, reenviarlo duplicaria la peticion
    } else {
      const datos = await r.json();
      const respuesta = datos.message?.content || "";
      mostrar(vista, respuesta || MENSAJES.vacio, !respuesta);
      recuperar = !respuesta;
    }
  } catch {
    mostrar(vista, MENSAJES.otro, true);
    recuperar = true;
  } finally {
    clearTimeout(corte);
    clearTimeout(lento);
    liberar();
    if (recuperar && !$("mensaje").value) {
      $("mensaje").value = texto;
      ajustarAltura();
    }
    if (!tactil()) $("mensaje").focus();
  }
}

function ajustarAltura() {
  const campo = $("mensaje");
  campo.style.height = "auto";
  campo.style.height = `${Math.min(campo.scrollHeight, 176)}px`;
  const n = campo.value.length;
  const contador = $("contador");
  contador.hidden = n < AVISAR_DESDE;
  if (!contador.hidden) {
    contador.textContent = n >= LIMITE ? `Límite alcanzado (${LIMITE})` : `${n} de ${LIMITE}`;
  }
}

function iniciarChat() {
  $("formulario").addEventListener("submit", (ev) => {
    ev.preventDefault();
    // Mientras responde, el texto escrito se conserva: no se borra ni se descarta.
    if (estado.ocupados > 0) { anunciar(MENSAJES.espera); return; }
    const texto = $("mensaje").value.trim();
    if (!texto) { $("mensaje").focus(); return; }
    $("mensaje").value = "";
    ajustarAltura();
    enviar(texto).catch(() => anunciar(MENSAJES.otro));
  });
  $("mensaje").addEventListener("input", ajustarAltura);
  // Safari dispara compositionend ANTES del keydown del Enter que confirma una
  // composicion (IME), y con isComposing en false: ese Enter no es de envio.
  $("mensaje").addEventListener("compositionend", () => { estado.finComposicion = performance.now(); });
  $("mensaje").addEventListener("keydown", (ev) => {
    const componiendo = ev.isComposing || performance.now() - estado.finComposicion < VENTANA_COMPOSICION_MS;
    if (ev.key === "Enter" && !ev.shiftKey && !componiendo && !tactil()) {
      ev.preventDefault();
      $("formulario").requestSubmit();
    }
  });
  // Recargar descarta el hilo en un solo paso.
  $("nueva").addEventListener("click", () => location.reload());
  if (!tactil()) $("mensaje").focus();
}

iniciarChat();
