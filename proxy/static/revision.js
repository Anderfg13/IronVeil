"use strict";
/* Consola de revision humana de IronVeil.
   El texto de las peticiones puede ser un ataque: aqui NUNCA se inserta como
   HTML. Todo se pinta con textContent / nodos de texto (ver `h()`). */

const SONDEO_MS = 3000;

const estado = {
  pendientes: [],
  decisiones: [],
  seleccion: null,
  pestana: "pendientes",
  sesion: null,
  ultimaCarga: 0,
  resultado: null,
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
  const cabeceras = { ...(opciones.headers || {}) };
  if (opciones.method === "POST" && estado.sesion && estado.sesion.csrf) {
    cabeceras["X-CSRF-Token"] = estado.sesion.csrf;
  }
  const respuesta = await fetch(ruta, { credentials: "same-origin", ...opciones, headers: cabeceras });
  if (respuesta.status === 401) {
    window.location.assign("/revision/login");
    throw new Error("sesion");
  }
  return respuesta;
}

function aviso(texto, error = false) {
  const nodo = h("div", { class: error ? "aviso error" : "aviso" }, texto);
  $("avisos").append(nodo);
  setTimeout(() => nodo.remove(), 5000);
}

/* ---------- Encabezado ---------- */

function pintarVivo(ok) {
  const caja = $("vivo");
  caja.classList.toggle("caido", !ok);
  const segundos = Math.max(0, Math.round((Date.now() - estado.ultimaCarga) / 1000));
  $("vivo-texto").textContent = ok ? `En vivo · actualizado hace ${segundos} s` : "Sin conexión con el proxy";
}

function pintarEstadisticas(e) {
  $("c-pendientes").textContent = e.pendientes;
  $("c-espera").replaceChildren(duracion(e.espera_maxima_s));
  const total = e.aprobadas + e.rechazadas;
  $("c-decididas").replaceChildren(String(total), h("small", {}, total ? `${e.aprobadas} aprobadas · ${e.rechazadas} rechazadas` : ""));
  $("c-tiempo").textContent = e.tiempo_medio_decision_s === null ? "—" : duracion(e.tiempo_medio_decision_s);
  $("cuenta-pendientes").textContent = e.pendientes;
}

/* ---------- Lista ---------- */

function pintarLista() {
  const ul = $("elementos");
  ul.replaceChildren();
  if (estado.pestana === "historial") return pintarHistorial(ul);
  if (!estado.pendientes.length) {
    ul.append(
      h("li", { class: "vacio" },
        h("img", { src: "/revision/static/logo.svg", alt: "", width: 56, height: 56 }),
        h("h3", {}, "No hay nada por revisar"),
        h("p", {}, "Cuando un mecanismo retenga una petición, aparecerá aquí.")));
    return;
  }
  for (const p of estado.pendientes) {
    const titulo = p.tipo === "herramienta" ? `Herramienta · ${p.herramienta.nombre}` : p.motivo_titulo;
    ul.append(
      h("li", {},
        h("button", {
            class: `elemento nivel-${p.sospecha.nivel}`,
            type: "button",
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
    ul.append(h("li", { class: "vacio" }, h("h3", {}, "Aún no hay decisiones"), h("p", {}, "Las que tomes aparecerán aquí, con quién y cuánto tardó.")));
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
      hayPatron && h("span", {}, h("b", { class: "l-patron" }), "Coincide con un patrón de ataque"),
      hayCodificado && h("span", {}, h("b", { class: "l-codificado" }), "Texto que parece codificado")),
    p.truncado && h("div", { class: "nota-truncado" }, "Se muestran los primeros 8 000 caracteres."));
}

function evidenciaDeHerramienta(p) {
  return h("div", { class: "herramienta" },
    h("div", { class: "nombre" }, `${p.herramienta.nombre}(…)`),
    h("pre", { class: "evidencia", tabindex: "0", "aria-label": "Argumentos de la herramienta" }, p.herramienta.argumentos),
    h("div", { class: "banner-simulada" }, "Herramienta SIMULADA: aunque la apruebes no envía correos ni consulta datos reales; solo escribe en el log."));
}

function lectura(p) {
  const s = p.sospecha;
  return h("div", { class: "lectura" },
    h("div", { class: "veredicto" }, h("strong", {}, s.lectura), h("span", {}, "Lectura orientativa de reglas simples. La decisión es tuya.")),
    h("div", {},
      h("div", { class: "espectro", role: "img", "aria-label": `Posición ${s.puntaje} de 100, de falso positivo a ataque` },
        h("div", { class: "marcas" }), h("div", { class: "pin", id: "pin" })),
      h("div", { class: "extremos" }, h("span", {}, "Falso positivo"), h("span", {}, "Ataque"))),
    p.senales.length
      ? h("ul", { class: "senales" }, p.senales.map((x) => h("li", { class: `senal ${x.nivel}` }, h("i", {}), h("div", {}, h("b", {}, x.titulo), h("span", {}, x.detalle)))))
      : h("p", { class: "sin-senales" }, "No se encontraron señales en el contenido. Mira la razón por la que se retuvo."));
}

function pintarExpediente() {
  const caja = $("expediente");
  if (estado.resultado) return pintarResultado(caja);
  const p = estado.pendientes.find((x) => x.id === estado.seleccion);
  if (!p) {
    caja.replaceChildren(h("div", { class: "vacio" }, h("img", { src: "/revision/static/logo.svg", alt: "", width: 56, height: 56 }),
      h("h3", {}, estado.pendientes.length ? "Elige una petición" : "Todo en orden"),
      h("p", {}, estado.pendientes.length ? "Selecciónala en la lista para ver la evidencia y decidir." : "No hay peticiones esperando una decisión.")));
    return;
  }
  const puedeDecidir = estado.sesion && estado.sesion.rol === "revisor";
  caja.replaceChildren(
    h("header", {},
      h("h2", {}, p.tipo === "herramienta" ? "Solicitud de herramienta" : "Petición retenida"),
      h("span", { class: "etiqueta" }, p.modelo),
      h("span", { class: "etiqueta mono" }, p.vector_probado || "sin vector"),
      p.tipo === "herramienta" && h("span", { class: "etiqueta simulada" }, "Simulada"),
      h("span", { class: "espera-grande", id: "espera-grande", "data-id": p.id }, `En cola hace ${duracion(p.espera_s)}`)),
    h("div", { class: "bloque" }, h("h3", {}, "Lectura"), lectura(p)),
    h("div", { class: "bloque" }, h("h3", {}, `Por qué se retuvo: ${p.motivo_titulo}`), h("p", {}, p.motivo_explicacion)),
    h("div", { class: "bloque" }, h("h3", {}, p.tipo === "herramienta" ? "Lo que el modelo quiere ejecutar" : "Lo que escribió el usuario"),
      p.tipo === "herramienta" ? evidenciaDeHerramienta(p) : evidenciaDeTexto(p)),
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
  });
}

function pintarResultado(caja) {
  const r = estado.resultado;
  caja.replaceChildren(h("div", { class: "resultado" },
    h("h2", { class: r.accion }, r.accion === "aprobada" ? "Aprobada: se reconoció como falso positivo" : "Rechazada: se confirmó el ataque"),
    h("p", {}, `Decisión de ${r.revisor} registrada en ${duracion(Math.round(r.tiempoMs / 1000))}.`),
    r.detalle && h("div", {}, h("h3", {}, r.tituloDetalle), h("pre", { tabindex: "0" }, r.detalle)),
    h("button", { class: "siguiente", type: "button", onclick: () => { estado.resultado = null; seleccionarPrimera(); } }, "Ver siguiente")));
}

/* ---------- Decidir ---------- */

function confirmar(p, accion) {
  const dialogo = $("confirmar");
  const aprobar = accion === "aprobar";
  $("confirmar-titulo").textContent = aprobar ? "¿Confirmas que es un falso positivo?" : "¿Confirmas que es un ataque?";
  $("confirmar-texto").textContent = aprobar
    ? (p.tipo === "herramienta" ? "Se ejecutará la versión simulada de la herramienta." : "La petición se enviará al modelo y recibirás su respuesta.")
    : "La petición se descarta y no llega al modelo. Esta acción queda registrada.";
  const ok = $("confirmar-ok");
  ok.className = `accion ${aprobar ? "aprobar" : "rechazar"}`;
  ok.textContent = aprobar ? "Sí, aprobar" : "Sí, rechazar";
  ok.onclick = () => { dialogo.close(); decidir(p, accion); };
  $("confirmar-cancelar").onclick = () => dialogo.close();
  dialogo.showModal();
  ok.focus();
}

async function decidir(p, accion) {
  const inicio = Date.now();
  try {
    const respuesta = await api(`/revision/${encodeURIComponent(p.id)}/${accion}`, { method: "POST" });
    if (respuesta.status === 404) { aviso("Otra persona ya resolvió esta petición.", true); await cargar(); return; }
    if (respuesta.status === 403) { aviso("Tu sesión no puede decidir. Vuelve a iniciar sesión.", true); return; }
    if (!respuesta.ok) { aviso("No se pudo registrar la decisión. Inténtalo otra vez.", true); return; }
    const cuerpo = await respuesta.json();
    const aprobada = accion === "aprobar";
    let detalle = null, tituloDetalle = "";
    if (aprobada && cuerpo.resultado_simulado) { detalle = JSON.stringify(cuerpo.resultado_simulado, null, 2); tituloDetalle = "Resultado simulado"; }
    else if (aprobada && cuerpo.message) { detalle = cuerpo.message.content; tituloDetalle = "Respuesta del modelo"; }
    estado.resultado = {
      accion: aprobada ? "aprobada" : "rechazada",
      revisor: estado.sesion.usuario,
      tiempoMs: cuerpo.tiempo_revision_humana_ms ?? Date.now() - inicio,
      detalle, tituloDetalle,
    };
    await cargar();
  } catch (e) {
    if (e.message !== "sesion") aviso("Sin conexión con el proxy.", true);
  }
}

/* ---------- Seleccion y carga ---------- */

function seleccionar(id) { estado.seleccion = id; estado.resultado = null; pintarLista(); pintarExpediente(); }
function seleccionarPrimera() { estado.seleccion = estado.pendientes[0] ? estado.pendientes[0].id : null; pintarLista(); pintarExpediente(); }

async function cargar() {
  try {
    const [panel, historial] = await Promise.all([api("/revision/panel").then((r) => r.json()), api("/revision/historial").then((r) => r.json())]);
    const vistoAntes = estado.pendientes.map((p) => p.id).join();
    estado.pendientes = panel.pendientes;
    estado.decisiones = historial.decisiones;
    estado.ultimaCarga = Date.now();
    pintarEstadisticas(panel.estadisticas);
    const existe = estado.pendientes.some((p) => p.id === estado.seleccion);
    if (!existe && !estado.resultado) estado.seleccion = estado.pendientes[0] ? estado.pendientes[0].id : null;
    const cambio = vistoAntes !== estado.pendientes.map((p) => p.id).join();
    if (cambio || !existe) { pintarLista(); if (!document.querySelector("dialog[open]")) pintarExpediente(); }
    pintarVivo(true);
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
  if (estado.ultimaCarga) pintarVivo(!$("vivo").classList.contains("caido"));
}

/* ---------- Arranque ---------- */

function aplicarTema(tema) {
  document.documentElement.setAttribute("data-theme", tema);
  try { localStorage.setItem("ironveil-tema", tema); } catch { /* sin almacenamiento: se ignora */ }
}

function iniciarTema() {
  let guardado = null;
  try { guardado = localStorage.getItem("ironveil-tema"); } catch { /* idem */ }
  if (guardado) document.documentElement.setAttribute("data-theme", guardado);
  $("tema").addEventListener("click", () => {
    const actual = document.documentElement.getAttribute("data-theme")
      || (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    aplicarTema(actual === "dark" ? "light" : "dark");
  });
}

function atajos(evento) {
  if (evento.target.closest("input, textarea, dialog") || evento.ctrlKey || evento.metaKey || evento.altKey) return;
  const idx = estado.pendientes.findIndex((p) => p.id === estado.seleccion);
  const actual = estado.pendientes[idx];
  if (evento.key === "j" && estado.pendientes[idx + 1]) seleccionar(estado.pendientes[idx + 1].id);
  else if (evento.key === "k" && idx > 0) seleccionar(estado.pendientes[idx - 1].id);
  else if (actual && estado.sesion.rol === "revisor" && !estado.resultado && evento.key === "a") confirmar(actual, "aprobar");
  else if (actual && estado.sesion.rol === "revisor" && !estado.resultado && evento.key === "r") confirmar(actual, "rechazar");
}

function cambiarPestana(nombre) {
  estado.pestana = nombre;
  $("tab-pendientes").setAttribute("aria-selected", String(nombre === "pendientes"));
  $("tab-historial").setAttribute("aria-selected", String(nombre === "historial"));
  pintarLista();
}

async function iniciar() {
  iniciarTema();
  const respuesta = await api("/revision/sesion");
  estado.sesion = await respuesta.json();
  $("usuario-nombre").textContent = estado.sesion.usuario;
  $("usuario-rol").textContent = estado.sesion.rol === "revisor" ? "Revisor" : "Observador";
  $("avatar").textContent = estado.sesion.usuario.slice(0, 1).toUpperCase();
  $("aviso-lab").hidden = estado.sesion.autenticacion;
  const salir = $("salir");
  salir.hidden = !estado.sesion.autenticacion;
  salir.addEventListener("click", async () => { await fetch("/revision/logout", { method: "POST", credentials: "same-origin" }); window.location.assign("/revision/login"); });
  $("tab-pendientes").addEventListener("click", () => cambiarPestana("pendientes"));
  $("tab-historial").addEventListener("click", () => cambiarPestana("historial"));
  document.addEventListener("keydown", atajos);
  await cargar();
  pintarExpediente();
  setInterval(() => { if (!document.hidden) cargar(); }, SONDEO_MS);
  setInterval(tictac, 1000);
}

iniciar().catch((e) => { if (e.message !== "sesion") $("vivo-texto").textContent = "No se pudo iniciar la consola"; });
