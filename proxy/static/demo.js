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
  429: "Tu mensaje quedó pendiente de revisión. Vuelve a intentarlo más tarde.",
  otro: "No pude responder en este momento. Inténtalo de nuevo.",
  vacio: "El asistente no devolvió ningún texto. Inténtalo de nuevo.",
  espera: "Espera la respuesta antes de enviar otro mensaje.",
  enRevision: "Tu mensaje está en revisión. Una persona lo revisará y la respuesta aparecerá aquí.",
  rechazada: "Una persona revisó tu mensaje y no fue aprobado.",
  sinDecision: "Todavía no hay una decisión sobre tu mensaje. Vuelve a intentarlo más tarde.",
};
const ESCRIBIENDO = "Escribiendo…";
const LENTO = "Sigo trabajando en tu respuesta…";
const LIMITE = 12000; // igual que maxlength del cuadro de texto
const AVISAR_DESDE = 10800; // 90 %: a partir de aqui se muestra el contador
const TIEMPO_MAXIMO_MS = 120000;
const AVISO_LENTO_MS = 8000;
/* El proxy conserva la decision 30 min: pasado ese tiempo ya no hay nada que esperar.
   Cada consulta espera hasta 25 s a que se decida (long polling), sin sondeo rapido. */
const ESPERA_DECISION_MS = 30 * 60 * 1000;
const PAUSA_ENTRE_CONSULTAS_MS = 2000;

const estado = { enCurso: false };

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

function mostrar(vista, texto, esAviso) {
  vista.cuerpo.replaceChildren(h("p", { class: esAviso ? "demo-texto demo-aviso" : "demo-texto" }, texto));
  anunciar(texto);
  verDesdeArriba(vista.mensaje);
}

function marcarEnvio(enCurso) {
  const boton = $("enviar");
  if (enCurso) boton.setAttribute("aria-disabled", "true");
  else boton.removeAttribute("aria-disabled");
  boton.textContent = enCurso ? "Enviando…" : "Enviar";
}

/* Espera lo que decida la persona que revisa y actualiza el mensaje en pantalla. */
async function esperarDecision(vista, turno) {
  const inicio = Date.now();
  while (Date.now() - inicio < ESPERA_DECISION_MS) {
    const desde = Date.now();
    let datos = null;
    try {
      const r = await fetch(`/chat/revision/${encodeURIComponent(turno)}?espera=25`, { credentials: "same-origin" });
      if (r.ok) datos = await r.json();
    } catch { /* sin conexion: se reintenta */ }
    if (datos && datos.estado === "aprobada") {
      mostrar(vista, datos.respuesta || MENSAJES.vacio, !datos.respuesta);
      return;
    }
    if (datos && datos.estado === "rechazada") { mostrar(vista, MENSAJES.rechazada, true); return; }
    if (datos && (datos.estado === "fallida" || datos.estado === "desconocida")) { mostrar(vista, MENSAJES.otro, true); return; }
    // Sigue en revision (o no hubo conexion). Si la consulta volvio enseguida, una pausa evita un bucle rapido.
    if (Date.now() - desde < 1500) await new Promise((fin) => setTimeout(fin, PAUSA_ENTRE_CONSULTAS_MS));
  }
  mostrar(vista, MENSAJES.sinDecision, true);
}

async function enviar(texto) {
  estado.enCurso = true;
  marcarEnvio(true);
  const vista = agregarMensaje(texto);
  const control = new AbortController();
  const corte = setTimeout(() => control.abort(), TIEMPO_MAXIMO_MS);
  const lento = setTimeout(() => { vista.rotulo.textContent = LENTO; anunciar(LENTO); }, AVISO_LENTO_MS);
  let recuperar = false; // devolver el texto al cuadro para editarlo y reenviarlo
  try {
    const r = await fetch("/chat", {
      method: "POST", headers: { "Content-Type": "application/json" }, signal: control.signal,
      body: JSON.stringify({ modelo: $("modelo").value, mensaje: texto }), credentials: "same-origin",
    });
    if (!r.ok) {
      const turno = r.status === 429 ? r.headers.get("X-Revision-Id") : null;
      if (turno) {
        // Quedo en revision: se espera la decision sin bloquear el cuadro de texto.
        mostrar(vista, MENSAJES.enRevision, true);
        esperarDecision(vista, turno);
      } else {
        mostrar(vista, MENSAJES[r.status] || MENSAJES.otro, true);
      }
      recuperar = r.status !== 429; // si quedo en revision, reenviarlo duplicaria la peticion
    } else {
      const datos = await r.json();
      const respuesta = (datos.message && datos.message.content) || "";
      mostrar(vista, respuesta || MENSAJES.vacio, !respuesta);
      recuperar = !respuesta;
    }
  } catch {
    mostrar(vista, MENSAJES.otro, true);
    recuperar = true;
  } finally {
    clearTimeout(corte);
    clearTimeout(lento);
    estado.enCurso = false;
    marcarEnvio(false);
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

function iniciar() {
  $("formulario").addEventListener("submit", (ev) => {
    ev.preventDefault();
    // Mientras responde, el texto escrito se conserva: no se borra ni se descarta.
    if (estado.enCurso) { anunciar(MENSAJES.espera); return; }
    const texto = $("mensaje").value.trim();
    if (!texto) { $("mensaje").focus(); return; }
    $("mensaje").value = "";
    ajustarAltura();
    enviar(texto);
  });
  $("mensaje").addEventListener("input", ajustarAltura);
  $("mensaje").addEventListener("keydown", (ev) => {
    // keyCode 229: Safari confirma una composicion (IME) con un Enter que no es de envio.
    if (ev.key === "Enter" && !ev.shiftKey && !ev.isComposing && ev.keyCode !== 229 && !tactil()) {
      ev.preventDefault();
      $("formulario").requestSubmit();
    }
  });
  // Recargar descarta el hilo en un solo paso.
  $("nueva").addEventListener("click", () => location.reload());
  if (!tactil()) $("mensaje").focus();
}

iniciar();
