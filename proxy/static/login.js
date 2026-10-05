"use strict";

const formulario = document.getElementById("form");
const errorForm = document.getElementById("error");
const boton = document.getElementById("entrar");
const campoUsuario = document.getElementById("usuario");
const campoClave = document.getElementById("clave");
const verClave = document.getElementById("ver-clave");
const TEXTO_BOTON = "Iniciar sesión";

const MENSAJES = {
  401: "Usuario o contraseña incorrectos. Revísalos e inténtalo otra vez.",
  429: "Demasiados intentos. Espera unos minutos y vuelve a probar.",
  503: "No se pudo validar tu identidad. Avisa a quien administra el sistema.",
};

/* Marca como invalidos los campos indicados y deja el mensaje en la region de alerta. */
function fallo(texto, ...campos) {
  errorForm.textContent = texto;
  for (const campo of [campoUsuario, campoClave]) {
    if (campos.includes(campo)) campo.setAttribute("aria-invalid", "true");
    else campo.removeAttribute("aria-invalid");
  }
}

/* Mostrar u ocultar la contraseña es una decision de quien escribe; el campo
   sigue siendo type="password" por defecto y conserva el autocompletado. */
verClave.addEventListener("click", () => {
  const visible = verClave.getAttribute("aria-pressed") !== "true";
  verClave.setAttribute("aria-pressed", String(visible));
  campoClave.type = visible ? "text" : "password";
});

formulario.addEventListener("submit", async (evento) => {
  evento.preventDefault();
  fallo("");
  const usuario = campoUsuario.value.trim();
  const clave = campoClave.value;
  if (!usuario) { fallo("Escribe tu usuario.", campoUsuario); campoUsuario.focus(); return; }
  if (!clave) { fallo("Escribe tu contraseña.", campoClave); campoClave.focus(); return; }
  boton.disabled = true;
  boton.textContent = "Iniciando sesión…";
  try {
    const respuesta = await fetch("/revision/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ usuario, clave }),
      credentials: "same-origin",
    });
    if (respuesta.ok) {
      window.location.assign("/revision/ui");
      return;
    }
    fallo(MENSAJES[respuesta.status] || "No se pudo iniciar sesión. Inténtalo otra vez.", ...(respuesta.status === 401 ? [campoUsuario, campoClave] : []));
    campoClave.select();
  } catch {
    fallo("No hay conexión con el proxy. Comprueba que esté en marcha e inténtalo otra vez.");
  } finally {
    boton.disabled = false;
    boton.textContent = TEXTO_BOTON;
  }
});

campoUsuario.focus();
