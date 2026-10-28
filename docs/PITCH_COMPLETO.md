# Pitch completo: lo que se dice, palabra por palabra

Sustituye la sección «Pitch» y los textos de la demo de `docs/GUION_EXPOSICION.md` (los tiempos, la preparación y la lista
de verificación de ese archivo siguen valiendo). Cada cifra sale de `analisis/` o del informe.

## 0. Reloj

Con lo de los ataques escondidos y el aviso por Slack (bloque B), el texto base son **≈ 640 palabras ≈ 4:15 a 150
palabras por minuto**, más 12 s del clip y la pausa del gancho = **≈ 4:30**. Quedan unos **30 segundos de colchón**.
Los **opcionales** (`[+]`) suman unos 25 s más: **si el ensayo da más de 4:50, se cortan en este orden**: primero el
aeropuerto (B), luego «una sola frase» (A) y «uno de cada siete» (C). La petición final de García no se corta.

| Bloque | Quién | Entra | Sale | Texto base | Con opcionales |
|---|---|---|---|---|---|
| A · Gancho y problema | Sabogal | 0:00 | 1:15 | ≈ 66 s (con clip) | ≈ 72 s |
| B · La solución | Piedrahita | 1:15 | 2:45 | ≈ 88 s | ≈ 96 s |
| C · La evidencia | Fiquitiva | 2:45 | 4:00 | ≈ 69 s | ≈ 75 s |
| D · Costo, negocio y cierre | García | 4:00 | 5:00 | ≈ 57 s | ≈ 57 s |

**Reglas del reloj**
- Cronómetro en el celular de **quien no habla en ese bloque** (A, B, C: García; D: Sabogal). Sin pantalla del profesor.
- Señales con la mano: **dos dedos** = «te quedan 2 minutos en total», **un dedo** = «un minuto», **mano plana** = «cierra
  ya».
- **Regla del relevo:** si un bloque se pasa más de 10 segundos, el siguiente arranca igual con su primera frase. Nadie
  termina el turno de otro.
- Cada bloque termina con una frase fija (la marcada con ▶). Con esa frase el siguiente sabe que le toca.

---

## A · Gancho y problema (Sabogal, 0:00–1:15)

*De pie, sin papeles, la pantalla del chat ya abierta. Hablar despacio en las dos primeras frases.*

> Voy a pedirle a una inteligencia artificial la clave secreta de una empresa. Se la voy a pedir con buena letra.

**[Clip de 10 segundos: el modelo suelta la credencial. Después, dos segundos de silencio completos.]**

> Eso no es un truco. Es nuestro laboratorio y la clave es ficticia, pero el ataque es real. Hoy hay unos **ciento setenta
> y cinco mil servidores Ollama** abiertos en internet, en ciento treinta países, sin usuario ni contraseña. Casi la mitad
> puede ejecutar acciones: no solo responden, **actúan**.

**[+]** > Y el ataque que acaban de ver es una sola frase.

> Un atacante puede robar las instrucciones secretas del modelo, hacerlo obedecer a otro, o saltar de un modelo a otro con
> la clave robada. Son riesgos del **Top 10 de OWASP para modelos de lenguaje**. Y las soluciones comerciales protegen
> modelos en la nube: el que corre en tu propio servidor queda sin cobertura.
>
> ▶ **Nuestra pregunta: ¿qué defensa vale la pena, y cuánto cuesta?**

*Diapositiva: «Un LLM autoalojado, abierto a internet». Mostrar solo mientras se dicen las cifras.*

## B · La solución (Piedrahita, 1:15–2:30)

> Nuestra respuesta es **IronVeil**, el velo de hierro para tus modelos. Un proxy que se pone delante del modelo, sin
> tocarlo, y revisa todo lo que entra y todo lo que sale. Cinco defensas, cinco formas distintas de pensar.

**[+]** > Piensen en un aeropuerto: detector de metales, perro, guardia, y alguien que decide en caso de duda. Ninguno es
> perfecto; juntos, sí protegen.

> El **filtrado** descarta lo obvio en una fracción de milisegundo. La **delimitación** separa lo que escribe el usuario de
> las órdenes del sistema. La **clasificación** usa inteligencia artificial para entender la intención. El **mínimo
> privilegio** impide usar la credencial de un asistente en otro. Y la **aprobación humana** pone a una persona a decidir,
> en lugar de rechazar a ciegas.
>
> Es el **mismo código**: con un archivo de configuración, cada defensa se enciende o se apaga. Así comparamos siete
> configuraciones, de la C cero, sin defensas, a la C seis, con todas, con los mismos ataques. El clasificador de IA es
> intercambiable, como Jev, sin tocar el resto.
>
> Y Garak nos enseñó un hueco: los ataques **escondidos**, en Base64, hexadecimal, ROT13 o con caracteres invisibles, no
> los ve ni el filtro ni la IA. Con nuestro modelo pequeño no pasa nada, porque no sabe decodificarlos; pero un modelo capaz
> los leería y obedecería. Por eso añadimos una extensión que los **decodifica y los revisa** antes de que lleguen.
>
> Cada bloqueo llega al SIEM y, cuando hace falta una persona, **el aviso le llega por el canal que la empresa ya usa**:
> Slack, correo, WhatsApp, o cualquier plataforma que reciba un webhook. Hoy se los mostramos por Slack.
>
> ▶ **Eso es lo que un equipo de seguridad necesita para operarlo.**

*Diapositiva: arquitectura (la de colores). Señalar con el puntero las dos cajas rojas cuando diga «inteligencia artificial».*

## C · La evidencia (Fiquitiva, 2:30–3:50)

> ¿Funciona? **Lo medimos.** Sin defensas, el ataque tiene éxito en el treinta y uno por ciento de los intentos; con el
> filtrado, baja a quince. El ataque completo de movimiento lateral pasa de doce de treinta y nueve a cero. Y el
> agotamiento de recursos baja de setenta y cinco por ciento a casi cero.

**[+]** > Dicho de otra forma: de uno de cada tres intentos exitosos, a uno de cada siete.

> Para no depender de nuestros propios ataques, usamos trescientos treinta y nueve del catálogo público de **Garak**. Sin
> defensas, el cincuenta y uno por ciento funciona. Con Jev y el resto de defensas, **cero de trescientos treinta y nueve**,
> en una sola corrida.
>
> Y un hallazgo que nos sorprendió: la defensa **más barata**, el filtrado, fue la que **más redujo**. La IA, con nuestro
> modelo pequeño, no redujo de forma medible, pero ve lo que las reglas no ven: el francés, cuatro de cuatro contra cero de
> cuatro.
>
> ▶ **Ninguna llega a cero, ni la literatura lo espera, y los falsos positivos son un costo que aún no medimos bien.
> Preferimos decirlo antes de que nos lo pregunten.**

*Diapositiva: «Lo que logra IronVeil, en cifras» (las cuatro cifras grandes). Una sola diapositiva; repetir «treinta y uno a
quince» dos veces seguidas si hace falta: los números hablados se olvidan.*

## D · Costo, negocio y cierre (García, 3:50–5:00)

> ¿Cuánto cuesta? Las piezas sin IA, menos de un milisegundo. La IA, unos setenta y seis. **Ese es el precio de pensar.**
>
> La decisión de negocio: autoalojar el clasificador cuesta unos setecientos treinta dólares al mes; un servicio por token,
> como Jev, unos cuatro centavos por millón de tokens. El equilibrio está en unos **diecisiete millones de prompts al mes**:
> por debajo, pagar por token; por encima, autoalojar; y si el texto no puede salir de tu red, autoalojar siempre.
>
> Cómo se vendería, y esto es una propuesta nuestra: núcleo abierto y gratuito, y servicio de integración y soporte para quien
> ya tiene modelos propios en producción.

**[+]** > Lo que buscamos: probarlo con un modelo menos alineado y con una empresa piloto, y que ustedes nos digan qué les
> faltaría para usarlo.

> ▶ **Ya está publicado: pip install ironveil. Y ahora no se lo contamos: se lo mostramos.**

*Diapositiva: costo / punto de equilibrio. Al terminar, cambiar de pantalla al chat sin decir nada más.*

---

## Demo (5:00): lo que se dice

El texto es corto a propósito: **lo que se ve es el protagonista**. Mientras el modelo responde (puede tardar), se explica lo
que pasa por dentro; no se queda nadie callado.

| Min | Quién | Se ve | Se dice |
|---|---|---|---|
| 0:00–0:45 | **García** | C0 en la terminal; el ataque en el chat | «C cero: sin defensas. El mismo ataque. La petición entra al proxy, nada la revisa, llega al modelo, y el modelo responde con lo que no debería. Ahí está la credencial.» |
| 0:45–1:45 | **Sabogal** | C1; el mismo ataque; a la derecha, el registro | «Enciendo la primera defensa, el filtrado. El mismo ataque ni llega al modelo: el usuario solo ve un aviso, y el registro dice qué defensa lo detuvo. Pero un atacante inteligente no escribe en español…» |
| 1:45–2:45 | **García** | C3; ataque en francés; el bloque `clasificador_entrada` del registro | «…escribe en francés. Un filtro por patrones no lo reconoce. La IA sí: bloqueado. Y miren el registro: qué modelo decidió, qué etiqueta y con cuánta seguridad.» |
| 2:45–3:45 | **Piedrahita** | C5/C6; «en revisión»; Slack; consola; Wazuh | «Lo más parecido a una empresa real: el mensaje no se rechaza, queda en revisión. Llega el aviso a Slack, una persona ve qué se escribió y por qué se retuvo, y decide. Rechazo. Y la alerta ya está en el SIEM.» |
| 3:45–4:30 | **Fiquitiva** | Reporte de Wazuh; tabla de resultados | «Para quien tiene que reportar, Wazuh genera el reporte de las alertas. Y esto que vieron, lo medimos: de treinta y uno a quince. Ninguna llega a cero; por eso son capas.» |
| 4:30–5:00 | **Todos** | Diapositiva de cierre | Una frase de cinco segundos cada uno: Sabogal «atacamos con cinco vectores», Piedrahita «se defiende con capas», García «la IA aporta donde las reglas no llegan», Fiquitiva «y todo se mide, sin esconder lo que falló». |

---

## Cómo lo escucharía un jurado crítico y aburrido (mi lectura honesta)

**Lo que funciona:** el gancho (se ve, no se cuenta), la cifra de 175 000, y la honestidad sobre lo que no llega a cero:
vende credibilidad. El hallazgo «la defensa más barata fue la que más redujo» es lo más memorable del pitch; no lo escondan.

**Dónde se me iría la atención, y cómo lo arreglé o cómo arreglarlo:**

1. **B nombra cinco defensas seguidas.** Es una lista y los números de la lista se olvidan. Por eso añadí el aeropuerto
   (`[+]`): una imagen que se recuerda. Cada defensa vuelve a aparecer en la demo, así que no hace falta explicarlas a fondo.
2. **C dice muchos números.** Los hablados se evaporan. Una sola diapositiva con las cifras grandes, y repetir la clave («de
   treinta y uno a quince») dos veces.
3. **El negocio es la parte más delgada.** Dice quién ahorra (punto de equilibrio) pero no *quién compra*. La frase de A
   («las soluciones comerciales protegen la nube; el autoalojado queda sin cobertura») es el nicho; en la ronda de preguntas,
   si preguntan «¿quién es el cliente?», responder con eso: empresas que no pueden mandar sus datos a una nube.
4. **No había una petición al final.** Un pitch termina pidiendo algo. El `[+]` de D lo hace: un modelo menos alineado y una
   empresa piloto, y qué les faltaría para usarlo. Para el ensayo de hoy, ese es el feedback que le piden al profesor.
5. **La honestidad puede sonar a disculpa.** Decirla de pie, firme y sin bajar la voz: «Preferimos decirlo antes de que nos
   lo pregunten» es una frase de fuerza, no de duda.
6. **El gancho depende de un clip.** Si el clip falla, la alternativa es decir la frase y mostrar la captura de la fuga;
   pero no improvisar un ataque en vivo en el gancho.

**Preguntas duras que haría (con respuesta corta)**

| Pregunta | Respuesta |
|---|---|
| «Si C6 queda en 15 %, ¿por qué compraría?» | Porque cada capa baja algo distinto: el ataque completo de movimiento lateral baja de 12/39 a 0 y el agotamiento de 75 % a casi 0. Y la combinación recomendada (filtrado, delimitación y mínimo privilegio) cuesta menos de un milisegundo. |
| «Su modelo es muy pequeño y ya rechaza casi todo. ¿Eso no invalida la prueba?» | Es una limitación que declaramos: el ASR de C0 sería mayor con un modelo más capaz. Por eso el siguiente paso es probar uno menos alineado. |
| «¿No ajustaron las defensas a sus propios ataques?» | Por eso usamos 339 ataques de Garak, que no escribimos nosotros. Fue una sola corrida; hay que repetirla. |
| «¿76 ms es aceptable?» | Para un chat sí; para un sistema en tiempo real habría que medirlo. Las piezas sin IA suman menos de 1 ms. |
| «¿Y si el clasificador falla?» | Falla cerrada: un error o un tiempo agotado cuenta como malicioso, nunca como permitido. |
| «¿Cubren ataques en binario?» | No. La extensión decodifica Base64, hexadecimal, ROT13 y caracteres invisibles. El binario puro, un cifrado propio o un idioma raro **no** están cubiertos: es una limitación declarada. |
| «¿Eso lo probaron con un modelo capaz?» | No: con el modelo de 1B esos ataques dan 0 % incluso sin defensas, porque no los decodifica. Que un modelo capaz los obedecería es el motivo de la extensión, no un resultado medido. Con 6 ataques por tipo, el filtro pasó de 0/6 a 6/6. |
| «¿Cómo se entera el equipo de un ataque?» | El aviso llega por el canal que la empresa use: ya vienen **Slack, correo (SMTP), WhatsApp (por Twilio) y un webhook genérico** para cualquier plataforma que lo reciba. Lleva el vector, el modelo y un enlace a la consola de revisión; ahí una persona decide. Y todo queda en el SIEM. |
| «¿Funciona con Teams, Discord u otra?» | Con cualquiera que reciba un webhook; no la probamos una por una. Hoy se demuestra con Slack. |
| «¿Cuál es la tasa de falsos positivos?» | En la entrada, 0 de 60. La salida puede retener una respuesta legítima y esa tasa no la medimos; es un próximo paso. |

---

## Ensayo de hoy (miércoles 28) con el profesor

1. **Antes de entrar:** Docker arriba y modelos calentados, zoom al 150 %, pestañas listas, el video de 4:50 abierto como
   plan B.
2. **Pedirle feedback concreto** (no «¿qué tal?»): ¿el gancho funciona?, ¿se entiende quién compraría?, ¿en qué parte
   se aburrió?, ¿le quedó claro dónde está la IA?
3. **Un cronómetro por bloque**, anotar a qué hora real terminó cada uno y ajustar los opcionales.
4. **Después del ensayo**, diez minutos: lo que se repite en el feedback se corrige en el guion; lo demás se ignora.
