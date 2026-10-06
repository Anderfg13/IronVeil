# Memoria de decisiones humanas (extensión opcional)

Cuando un humano **rechaza** una petición que un mecanismo retuvo, el proxy la **recuerda**:
la próxima vez que llegue el mismo mensaje (para el mismo modelo) se rechaza al instante, sin
pasar por la cola de revisión ni por la cadena. Es una **memoria de decisiones**, no
aprendizaje automático: es exacta, auditable y revocable.

Está **apagada por defecto** y vive en `proxy/memoria_decisiones.py`.

## Cómo se usa

1. Actívala en `.env`:
   ```
   MEMORIA_RECHAZOS=1
   ```
2. Reconstruye y levanta el proxy: `docker compose up -d --build proxy`.
3. Manda un mensaje que un mecanismo retenga (con `aprobacion_humana` activa). Queda en la cola
   (429).
4. En la consola (`/revision/ui`) **recházalo**. La respuesta trae `"memoria": "recordada"`.
5. Manda el mismo mensaje otra vez: ahora recibe un **400 inmediato**. No entra a la cola, no
   genera aviso y no llega al modelo.

En la consola aparece la pestaña **Memoria**, con las reglas recordadas, quién las decidió,
cuántas veces actuaron y un botón **Olvidar** (solo para revisores).

## Persistencia: sobrevive a reinicios

Cada regla se **anexa a un archivo** y se fuerza a disco (`fsync`) en el momento. Al arrancar, el
proxy lo lee y reconstruye todo. Por eso no se pierde si se apaga el contenedor, se reconstruye
la imagen, se hace `docker compose down` o se reinicia el equipo.

| Qué | Dónde |
|---|---|
| Archivo | `memoria/rechazos.jsonl` en la raíz del repo (carpeta ignorada por Git) |
| Dentro del contenedor | `/app/memoria/rechazos.jsonl` (montada desde `./memoria`) |
| Formato | JSON Lines: un renglón por decisión (`recordar` u `olvidar`) |

Es una carpeta de tu equipo (no un volumen de Docker), a propósito: se puede ver, copiar y
respaldar, y no se pierde con `docker compose down -v`. **Para borrar toda la memoria, borra el
archivo** (con el proxy apagado).

Detalles de robustez:
- Un renglón dañado se **omite con un aviso** y no impide arrancar.
- Un corte a mitad de escritura no pierde lo anterior.
- Si no se puede escribir en la carpeta, la memoria **funciona solo en memoria y lo dice en el
  log y en la consola** («SOLO en memoria: se perderán al reiniciar»).

## Qué se recuerda y qué no

- **Solo rechazos**, nunca aprobaciones: un rechazo de más falla del lado seguro; una aprobación
  de más dejaría pasar para siempre algo que un mecanismo retuvo.
- **Solo retenciones por contenido** (`filtrado`, `clasificacion`, `minimo_privilegio`). Lo
  retenido por **exceso de peticiones** no se recuerda (puede ser un «hola» legítimo), ni las
  solicitudes de herramientas.
- **Por modelo**: un rechazo de `soporte` no vale para `rrhh`.
- **Solo coincidencia exacta tras normalizar**: mayúsculas, tildes, espacios, puntuación de los
  bordes y caracteres invisibles (ceros de ancho cero) no cambian la huella.

## Límites que hay que tener claros

- **No frena paráfrasis.** Si el atacante cambia una palabra, la memoria no lo reconoce y el
  mensaje vuelve a los mecanismos y a la cola. Es un **complemento**, no una barrera: no debe
  presentarse como defensa contra variantes. Lo semántico (comparar significado, por ejemplo con
  embeddings) sería una segunda fase, más cara y probabilística.
- **Un rechazo equivocado se queda** hasta que alguien lo olvide: por eso existe **Olvidar**.
- **Solo decide el rol `revisor`**; el observador ve las reglas pero no puede olvidarlas. Revocar
  exige el token CSRF de la sesión.
- **Se guardan huellas (SHA-256), no el texto.** Solo se conserva una **vista previa de 60
  caracteres con las credenciales redactadas**, para que el revisor sepa qué está olvidando. Se
  puede apagar con `MEMORIA_RECHAZOS_VISTA_PREVIA=0` (entonces la lista solo muestra modelo,
  motivo y quién decidió).
- **Tope de reglas** (`MEMORIA_RECHAZOS_MAXIMO`, 5000): al llegar, no se agregan más y se avisa;
  nunca se descarta una regla en silencio.
- Los **aciertos** (cuántas veces actuó una regla) se cuentan **desde que arrancó el proxy**; ese
  contador no se guarda.

## Importante para el experimento

Las baterías de ataque repiten el mismo payload muchas veces. Con la memoria activa, tras el
primer rechazo el resto se bloquearía solo y **el ASR de C5 y C6 bajaría artificialmente**.
Por eso:

- **Los resultados de C0–C6 se midieron SIN la memoria** y no son comparables con una corrida que
  la tenga encendida. En el informe se presenta como **extensión aparte**: la respuesta a un
  ataque repetido pasa a ser instantánea («entre comillas», porque solo vale para el mismo
  mensaje).
- **No actives `MEMORIA_RECHAZOS` en una corrida del experimento.**
- Si se activa de todos modos, sus eventos no se confunden con el núcleo: llevan
  `es_extension: true`, `origen_decision: "memoria"` y `latencia_memoria_us`; el análisis de costo
  (`costo_por_mecanismo.py`) los excluye.

## En el log

Un rechazo por memoria se atribuye a `aprobacion_humana` (es una decisión humana recordada), así
que no aparece un sexto nombre de mecanismo y las invariantes del esquema se cumplen. Se
distingue por el campo extendido `origen_decision: "memoria"`.

## Variables (`.env`)

| Variable | Por defecto | Qué hace |
|---|---|---|
| `MEMORIA_RECHAZOS` | vacío (apagada) | `1` la enciende. Solo actúa con `aprobacion_humana` activa |
| `MEMORIA_RECHAZOS_ARCHIVO` | `/app/memoria/rechazos.jsonl` | Ruta dentro del contenedor |
| `MEMORIA_RECHAZOS_MAXIMO` | `5000` | Tope de reglas |
| `MEMORIA_RECHAZOS_VISTA_PREVIA` | `1` | `0` guarda solo la huella, sin vista previa |

## API (la usa la consola)

- `GET /revision/memoria` — reglas y estado (`activa`, `persistente`); requiere sesión.
- `DELETE /revision/memoria/{huella}` — olvida una regla; solo revisores, con token CSRF.
- `POST /revision/{id}/rechazar` — si recuerda la regla, la respuesta trae `"memoria"`:
  `recordada`, `ya_recordada`, `memoria_llena` o `recordada_sin_guardar`.
