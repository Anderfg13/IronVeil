"use strict";
/* Pantalla de chat de la demo de IronVeil.
   Lo que escribe el usuario y lo que responde el modelo pueden ser un ataque:
   aqui NUNCA se inserta como HTML; todo se pinta con nodos de texto (`h()`).
   No hay atajos de una sola tecla: Enter envia solo dentro del cuadro de texto.
   Solo se llama a POST /chat: lo que paso por dentro vive en los logs, no aqui. */

const $ = (id) => document.getElementById(id);

/* Lo que ve quien conversa cuando no hay respuesta. Genericos a proposito. */
const MENSAJES = {
  400: "No puedo ayudarte con ese mensaje.",
  429: "Tu mensaje quedó pendiente de revisión. Vuelve a intentarlo más tarde.",
  otro: "No pude responder en este momento. Inténtalo de nuevo.",
};

const estado = { enCurso: false };

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

function anunciar(texto) {
  const region = $("anuncios");
  region.textContent = "";
  setTimeout(() => { region.textContent = texto; }, 50);
}

function bajar() {
  const el = $("hilo");
  el.scrollTop = el.scrollHeight;
}

function agregarMensaje(texto) {
  $("inicio")?.remove();
  $("nueva").hidden = false;
  $("hilo").append(h("div", { class: "demo-msg usuario" }, h("div", { class: "demo-burbuja" }, texto)));
  const cuerpo = h("div", {}, h("span", { class: "demo-pensando", role: "status" },
    h("i"), h("i"), h("i"), h("span", { class: "solo-lectores" }, "Escribiendo")));
  $("hilo").append(h("div", { class: "demo-msg" },
    h("div", { class: "demo-avatar" }, h("img", { src: "/revision/static/logo.svg", alt: "" })),
    h("div", { class: "demo-asistente" }, cuerpo)));
  bajar();
  return cuerpo;
}

function mostrar(cuerpo, texto, esAviso) {
  cuerpo.replaceChildren(h("p", { class: esAviso ? "demo-texto aviso" : "demo-texto" }, texto));
  anunciar(texto);
  bajar();
}

async function enviar(texto) {
  if (estado.enCurso) return;
  estado.enCurso = true;
  $("enviar").disabled = true;
  const cuerpo = agregarMensaje(texto);
  try {
    const r = await fetch("/chat", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ modelo: $("modelo").value, mensaje: texto }), credentials: "same-origin",
    });
    if (!r.ok) {
      mostrar(cuerpo, MENSAJES[r.status] || MENSAJES.otro, true);
    } else {
      const datos = await r.json();
      const respuesta = (datos.message && datos.message.content) || "";
      mostrar(cuerpo, respuesta || "(sin respuesta)", !respuesta);
    }
  } catch {
    mostrar(cuerpo, MENSAJES.otro, true);
  } finally {
    estado.enCurso = false;
    $("enviar").disabled = false;
    $("mensaje").focus();
  }
}

function ajustarAltura() {
  const campo = $("mensaje");
  campo.style.height = "auto";
  campo.style.height = `${Math.min(campo.scrollHeight, 176)}px`;
}

function iniciar() {
  $("formulario").addEventListener("submit", (ev) => {
    ev.preventDefault();
    const texto = $("mensaje").value.trim();
    if (!texto) { $("mensaje").focus(); return; }
    $("mensaje").value = "";
    ajustarAltura();
    enviar(texto);
  });
  $("mensaje").addEventListener("input", ajustarAltura);
  $("mensaje").addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && !ev.shiftKey && !ev.isComposing) { ev.preventDefault(); $("formulario").requestSubmit(); }
  });
  // Recargar descarta el hilo en un solo paso.
  $("nueva").addEventListener("click", () => location.reload());
  $("mensaje").focus();
}

iniciar();
