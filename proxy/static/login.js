"use strict";

const formulario = document.getElementById("form");
const errorForm = document.getElementById("error");
const boton = document.getElementById("entrar");

const MENSAJES = {
  401: "Usuario o contraseña incorrectos.",
  429: "Demasiados intentos. Espera unos minutos y vuelve a probar.",
  503: "No se pudo validar tu identidad. Avisa a quien administra el sistema.",
};

formulario.addEventListener("submit", async (evento) => {
  evento.preventDefault();
  errorForm.textContent = "";
  const usuario = document.getElementById("usuario").value.trim();
  const clave = document.getElementById("clave").value;
  if (!usuario || !clave) {
    errorForm.textContent = "Escribe tu usuario y tu contraseña.";
    return;
  }
  boton.disabled = true;
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
    errorForm.textContent = MENSAJES[respuesta.status] || "No se pudo iniciar sesión.";
    document.getElementById("clave").select();
  } catch {
    errorForm.textContent = "No hay conexión con el proxy.";
  } finally {
    boton.disabled = false;
  }
});

document.getElementById("usuario").focus();
