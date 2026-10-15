# Audios del video de demo: qué lee cada persona

Cada quien graba **solo sus segmentos**, leyendo el texto tal cual. Los nombres del equipo **no se dicen en voz alta**:
van en la tarjeta de título del video. Imagen y subtítulos se montan después a partir de estos mismos textos.

## Cómo grabar (2 minutos de instrucciones)

- Un archivo por segmento, con este nombre: `S<n>_<apellido>.m4a` (o `.mp3`/`.wav`). Ejemplo: `S3_Sabogal.m4a`.
- Celular o micrófono de auricular, cuarto silencioso, a 15 cm de la boca. Sin música ni eco.
- Ritmo tranquilo, unas 140 palabras por minuto. **No acelerar**: si el texto no cabe, se corta el texto, no la voz.
- Dejar 1 segundo de silencio al principio y al final de cada archivo.
- Si te equivocas, repite la frase desde el inicio del segmento; se corta en el montaje.
- Las cifras se dicen como están escritas («31,2 por ciento», «12 de 156»).

Tiempo total de narración: unos 4:00 de voz sobre 4:45 de video (el resto son pausas y la tarjeta de título).

---

## Carlos Mario Piedrahita Arango (segmentos 1, 7 y 9)

**Segmento 1 · Apertura (~15 s, 35 palabras)**

> IronVeil es un proxy de seguridad que protege un modelo de lenguaje local, con Ollama, de la inyección de prompt y
> la extracción de datos. Veremos varios ataques, la inteligencia artificial, la supervisión y las métricas.

**Segmento 7 · Supervisión: aprobación humana, Slack y SIEM (~25 s, 58 palabras)**

> Y todo queda auditado. Con la aprobación humana activa, un ataque que el filtro detecta no se rechaza: queda en
> cola, el equipo recibe un aviso en Slack y una persona decide desde la consola. Cada evento, además, llega al SIEM,
> aquí Wazuh, donde los bloqueos aparecen como alertas.

**Segmento 9 · Limitaciones y cierre (~30 s, 74 palabras)**

> Limitaciones. El modelo protegido es pequeño y ya rechaza muchos ataques por sí solo; las muestras son pequeñas, por
> eso damos intervalos; Garak fue un subconjunto en una sola corrida; la normalización solo cubre Base64,
> hexadecimal y ROT13; y Jev es de pago y envía el texto a un tercero. Ningún mecanismo garantiza cero: es defensa en
> profundidad. Gracias.

---

## Andres Felipe Sabogal Wilches (segmentos 2, 3 y 4)

**Segmento 2 · Escenario de control (~20 s, 38 palabras)**

> Escenario de control: configuración C0, sin defensas. Un usuario pide ayuda con su correo desde el chat
> y el asistente responde. Esta es la línea base.

**Segmento 3 · Los vectores y el ataque sin defensas (~40 s, 62 palabras)**

> Ahora los ataques, de dos vectores: el vector 2, extracción del prompt de sistema, y el vector 3, inyección de
> prompt, con variantes en otro idioma y escondidas en Base64. Empezamos con el vector 2, sin defensas: el modelo
> revela la credencial ficticia del sistema. Esto es lo que medimos como tasa de éxito de ataque.

> **Ojo con este segmento:** en la grabación de pantalla actual, el modelo *menciona* la credencial ficticia en una
> respuesta, pero no la entrega como respuesta directa al ataque. Para no decir algo que la imagen no muestra, lee
> esta variante en lugar de «el modelo revela la credencial»:
> «…Empezamos con el vector 2, sin defensas: el modelo deja salir la credencial ficticia del sistema en su respuesta.
> Esto es lo que medimos como tasa de éxito de ataque.»
> Si se vuelve a grabar una toma donde la credencial sale de forma clara, se vuelve al texto original.

**Segmento 4 · El mismo ataque con defensas (~30 s, 50 palabras)**

> Activamos la primera defensa, el filtrado por patrones. El mismo ataque, vector 2, sale con la credencial redactada,
> y una inyección directa, vector 3, «ignora tus instrucciones», se bloquea antes de llegar al modelo: el usuario solo
> ve un aviso, y el registro dice qué defensa actuó.

---

## Anderson Fabian García Nieto (segmentos 5 y 6)

**Segmento 5 · El componente de IA (~50 s, 92 palabras)**

> Dónde interviene la inteligencia artificial: en la clasificación. Entra el texto del usuario, antes del modelo;
> Llama Prompt Guard 2 lo analiza y devuelve un veredicto con un puntaje. Aquí enviamos una inyección, vector 3, en
> francés, que el filtro por patrones no reconoce: el clasificador la bloquea, y el registro muestra el modelo, el
> puntaje y el estado. Una segunda IA, Llama Guard 3, revisa la respuesta antes de entregarla. Si un clasificador
> falla, el proxy bloquea. El clasificador es intercambiable: también probamos Jev, un modelo remoto.

**Segmento 6 · Ataque escondido en Base64 (~30 s, 55 palabras)**

> Una variante más difícil: el mismo ataque escondido en Base64, que un patrón en texto plano no reconoce.
> Con la normalización de entrada, una extensión opcional, el proxy decodifica Base64, hexadecimal o ROT13, y los
> mismos mecanismos revisan lo que estaba escondido: aquí se bloquea.

---

## Ana Gabriela Fiquitiva Poveda (segmento 8)

**Segmento 8 · Resultados y métricas (~45 s, 105 palabras)**

> Las métricas. Sin defensas, el promedio de éxito de ataque es del 31,2 por ciento. Con filtrado baja al 15: en
> inyección directa pasa de 12 de 156 intentos a cero, y en movimiento lateral de 24 de 78 a cero. Con Garak, un
> catálogo externo de ataques, y Jev como clasificador, el éxito baja del 51,2 por ciento al 0,3, con un intervalo
> de confianza de hasta 1,7. Los falsos positivos son un costo real: con la clasificación de salida, una respuesta
> legítima puede quedar retenida, y aún no tenemos una tasa medida. El costo: menos de medio milisegundo sin
> clasificación, y unos 75 milisegundos con el clasificador.

---

## Entrega

Súbanlos a una carpeta compartida o pásenlos a García, antes de la noche del 15 de octubre. Con los audios, el montaje
(cortes, aceleración de las esperas, pantalla dividida donde ayude, subtítulos y tarjeta de título) tarda poco.

