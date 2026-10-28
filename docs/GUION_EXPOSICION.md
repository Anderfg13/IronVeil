# Guion de la exposición: 5 min de pitch, 5 de demo, 5 de preguntas

Equipo (4): **García** (infraestructura, filtrado, clasificación, mínimo privilegio, cola y costo) ·
**Piedrahita** (configuración, delimitación, aprobación humana, integración y SIEM) ·
**Sabogal** (ataques y resultados crudos) · **Fiquitiva** (log, consolidación, métricas e informe).
**Regla:** los cuatro hablan en el pitch y en la demo. Quien no habla en una parte, maneja la pantalla o el reloj.

| Bloque | Minutos | Quién habla |
|---|---|---|
| Pitch | 5:00 | Sabogal → Piedrahita → Fiquitiva → García |
| Demo | 5:00 | García, Sabogal, García, Piedrahita, Fiquitiva |
| Preguntas | 5:00 | Quien conoce el tema (ver tabla al final) |

Tiempo de habla aproximado: García 2:30 · Sabogal 2:30 · Piedrahita 2:15 · Fiquitiva 2:00, más las preguntas.

---

## 1. Pitch (5:00)

### 0:00–1:30 · Gancho y problema · **Sabogal**

**Gancho (30 s), sin diapositiva, con la pantalla del chat ya abierta:**

> «Voy a pedirle a una IA de una empresa que me dé su clave secreta. Se la voy a pedir educadamente… y ahora miren
> qué hace.»

Se reproduce el clip de 10 segundos donde el modelo suelta la credencial ficticia (la toma de `22-36-26`, de 3:55 a
4:08). Después:

> «Eso lo hicimos contra nuestro propio laboratorio. Pero hoy hay unos **175 000 servidores Ollama abiertos en 130
> países**, sin ninguna autenticación. Y casi la mitad puede ejecutar acciones, no solo responder.»

*(Usar el clip grabado y no una demo en vivo para el gancho: un modelo en CPU puede tardar un minuto en responder y
mata el ritmo.)*

**Problema (1 min).** Diapositiva «Un LLM autoalojado, abierto a internet». Decir: cualquiera puede extraer el prompt de
sistema, saltar entre modelos o agotar el servicio. Nombrar el marco: **OWASP Top 10 para LLM (2025)**, con LLM01,
LLM02, LLM07 y LLM10 en pantalla.

### 1:30–2:45 · La solución · **Piedrahita**

Diapositiva de **arquitectura** (la de colores). Tres ideas, nada más:

1. «Un solo proxy delante del modelo, con **cinco defensas** que se encienden por bandera.»
2. «El **mismo código** corre las siete configuraciones, de C0 sin defensas a C6 con todo. Por eso la comparación es
   justa.»
3. «Solo dos piezas son IA, las que se ven en rojo: Prompt Guard en la entrada y Llama Guard en la salida. Y se pueden
   cambiar por otro modelo, como Jev, sin tocar nada más.»

Cerrar con una frase de negocio: «Cada bloqueo queda en un registro y llega a su SIEM; eso es lo que un equipo de
seguridad necesita para operarlo.»

### 2:45–4:00 · La evidencia · **Fiquitiva**

Diapositiva de **cifras** (las cuatro grandes). Solo números que están en el informe:

- Sin defensas, el ASR promedio es **31,2 %**; con filtrado baja a **15,0 %**.
- El ataque completo de movimiento lateral pasa de **12/39 a 0/39** con mínimo privilegio.
- El agotamiento de recursos baja de **74,7 % a 0,2 %** con el límite de peticiones.
- Frente a un catálogo externo, **Garak**, con Jev como clasificador: de **51,2 % a 0,3 %**.

Y la honestidad que da credibilidad: «**Ninguna configuración llega a cero**, y la literatura tampoco lo espera. Lo que
medimos es qué capa aporta cuánto y a qué costo.»

### 4:00–5:00 · Costo, modelo de negocio y cierre · **García**

- **Costo:** las piezas deterministas suman menos de 1 ms; la clasificación con IA, unos 76 ms.
- **Decisión de compra:** autoalojar el clasificador cuesta unos USD 731 al mes de infraestructura (estimación del
  equipo); un clasificador por API, USD 0,042 por millón de tokens. El **punto de equilibrio es de unos 17 millones de
  prompts al mes**: por debajo, conviene pagar por token; por encima, autoalojar; y si el texto no puede salir de la red,
  autoalojar siempre.
- **Cómo se vendería (propuesta del equipo, no un dato medido):** núcleo abierto y gratuito, con servicio de
  integración y soporte para empresas que ya tienen Ollama en producción.
- **Cierre:** «Ya está publicado: `pip install ironveil`. Ahora lo vemos funcionando.»

---

## 2. Demo (5:00): que se vea desde el fondo del salón

### Preparación (antes de empezar, no durante)

- **Pantalla:** zoom del navegador al **150 %** y terminal con letra de **18 pt o más**. Un solo monitor, en espejo.
- **Distribución:** a la izquierda el chat; a la derecha el registro (`tail -f` del `eventos.jsonl`) o Wazuh. Así quien
  mira ve a la vez la petición y la decisión de la defensa.
- **Pestañas abiertas y ordenadas:** chat, consola de revisión, Slack, Wazuh. Nada más: sin VS Code, sin `.env`, sin
  archivos de credenciales, sin Claude ni Gemini.
- **Docker arriba y modelos calentados** al menos 20 minutos antes, con una petición de prueba en cada configuración que
  se vaya a usar.
- **Atajos escritos en un archivo de texto** para pegar los ataques (están en `docs/ATAQUES_PARA_COPIAR.md`): nadie
  teclea en vivo.
- **Plan B:** el video de 4:50 listo para reproducir. Si algo se cuelga más de 15 segundos, se dice «mientras esto
  responde, miren qué pasa por dentro» y se explica el flujo; si sigue, se pasa al video sin pedir disculpas largas.
- Silenciar notificaciones del sistema y cerrar todo lo que no se muestre.

### Guion

| Min | Quién | Qué se ve | Qué se dice |
|---|---|---|---|
| 0:00–0:45 | **García** | Terminal: `cfg false false false false false` (C0). Chat con el ataque V2 | «Sin defensas. Mismo ataque que vieron al inicio.» Se ve la credencial. |
| 0:45–1:45 | **Sabogal** | `cfg true false false false false` (C1). El mismo ataque, y el chat responde con el aviso. A la derecha, la línea del registro con `bloqueado` y `filtrado` | «Activo la primera defensa. El mismo ataque ya no llega al modelo, y el registro dice quién lo detuvo.» |
| 1:45–2:45 | **García** | C3. Ataque en francés; luego en la línea del registro, el bloque `clasificador_entrada` con modelo, etiqueta y puntaje | «El filtro por patrones no ve el francés. La IA sí: esto es lo que decidió y con cuánta seguridad.» |
| 2:45–3:45 | **Piedrahita** | C5/C6 con aprobación humana. El mensaje queda «en revisión»; aviso en Slack; la consola de revisión; se aprueba o rechaza; en Wazuh aparece la alerta | «Un ataque detectado no se rechaza a ciegas: una persona decide. Y todo llega al SIEM.» |
| 3:45–4:30 | **Fiquitiva** | Wazuh: reporte generado; tabla maestra de resultados | «Esto es lo que ve un equipo de seguridad, y esto es lo que medimos.» Mencionar el 31,2 → 15,0 y que ninguna llega a 0. |
| 4:30–5:00 | **Todos** | Diapositiva de cierre | Una frase cada uno, de cinco segundos. Ver abajo. |

**Cierre coral (cada quien dice una frase, 5 s):**

- Sabogal: «Atacamos con cinco vectores.»
- Piedrahita: «Se defiende con capas, no con una sola.»
- García: «La IA aporta donde las reglas no llegan.»
- Fiquitiva: «Y todo se mide, con intervalos, sin esconder lo que falló.»

---

## 3. Preguntas (5:00)

Quien tenga más cerca el tema responde; el otro completa solo si hace falta. Frase de relevo: «Eso lo explica mejor
X».

| Pregunta probable | Responde | Respuesta honesta, corta |
|---|---|---|
| «¿Por qué la IA no redujo la fuga?» | García | El modelo base de 1B ya rechaza casi todo. Aportó en idiomas (francés, 4/4 contra 0/4) y frente a Garak con Jev (51,2 % → 0,3 %). Con un modelo menos alineado, aún no lo probamos. |
| «¿Cuál es la tasa de falsos positivos?» | Fiquitiva | En la entrada, 0 de 60. La clasificación de salida puede retener una respuesta legítima y esa tasa no se midió: es un próximo paso. |
| «¿Los umbrales de éxito los fijaron después?» | Fiquitiva | Los definió el equipo en el análisis; se declaran en la tabla (†/‡) para poder discutirlos. |
| «¿Por qué no llega a 0 %?» | Sabogal | Ningún mecanismo garantiza cero. Es defensa en profundidad, y la literatura tampoco lo espera. |
| «¿Qué pasa si un clasificador falla?» | García | Falla cerrada: un error o tiempo agotado cuenta como malicioso, nunca como permitido. |
| «¿Es seguro mandar el texto a Jev?» | Piedrahita | No: sale a un tercero. Si no puede salir de la red, se usa Prompt Guard autoalojado. |
| «¿Cómo se integra con lo que ya tengo?» | Piedrahita | Es un proxy; el modelo no cambia. Exporta a Wazuh, Splunk, Elastic y otros en JSON, CEF, LEEF o ECS. |
| «¿Probaron contra ataques que no escribieron ustedes?» | Sabogal | Sí: 339 ataques del catálogo público de Garak, en una sola corrida. Hay que repetirlo. |
| «¿La combinación recomendada ya la midieron?» | Fiquitiva | No como configuración propia; es una estimación derivada de los efectos por mecanismo. Está en próximos pasos. |

---

## 4. Lista de verificación el día de la exposición

- [ ] Docker arriba y modelos calentados.
- [ ] Zoom del navegador al 150 % y letra de la terminal grande.
- [ ] Pestañas: chat, consola de revisión, Slack, Wazuh (nada más).
- [ ] Ataques en un archivo de texto para pegar.
- [ ] Video de 4:50 abierto, en pausa, listo.
- [ ] Clip del gancho (10 s) listo.
- [ ] Cada quien sabe cuándo habla y quién maneja la pantalla.
- [ ] Reloj visible; Fiquitiva o Piedrahita avisa a los 4:00 de cada bloque.
- [ ] Notificaciones silenciadas; nada de `.env`, credenciales, Claude ni Gemini en pantalla.
- [ ] La diapositiva de **Referencias** tiene los enlaces completos.
