# Vector 5 (agotamiento de recursos): C0 vs. C5, y costo operativo de la aprobación humana

Semana del 2026-09-24 · Fiquitiva · Datos: corridas de V5 del 2026-09-22 (García/Sabogal) y
todos los JSONL de `resultados/` hasta hoy.

Reproducible con:

```bash
python analisis/comparar_v5_c0_c5.py       # tabla_v5_c0_c5.{csv,md}, tabla_v5_punto_degradacion.{csv,md}
python analisis/tiempo_revision_humana.py  # tiempo_revision_humana.{csv,md}
python analisis/consolidar.py              # tabla_resumen_asr.{csv,md} + tabla_resumen_asr_costo_operativo.{csv,md}
```

Ningún dato crudo se modificó. Las cifras por nivel se recalcularon desde los JSONL crudos
(`resultados/2026-09-22/vector5_agotamiento_{C0,C5}[_colab]_c{nivel}.jsonl`) y coinciden con los
`*_resumen.json` de la corrida (verificado nivel por nivel).

---

## 1. Tabla comparativa C0 vs. C5 (efectividad técnica)

ASR = peticiones que agotaron el timeout de 90 s o devolvieron 5xx / peticiones totales del nivel.
Las dos corridas **se reportan por separado**: CPU local (Ryzen 5 3500U, sin GPU) y Google Colab
(GPU T4). No son comparables entre sí (FUENTE_DE_VERDAD.md, sección 7).

| Hardware | Nivel | C0 ASR | C0 timeouts/total | C0 p50 (ms) | C5 ASR | C5 timeouts/total | C5 bloqueados (429) | C5 p50 (ms) | C5 p95 (ms) |
|---|---:|---:|---|---:|---:|---|---:|---:|---:|
| CPU local | 2 | 0.0% | 0/2 | 73133 | 50.0% | 1/2 | 0 | 90277 | 90277 |
| CPU local | 4 | 50.0% | 2/4 | 90277 | 75.0% | 3/4 | 0 | 90314 | 90318 |
| CPU local | 6 | 83.3% | 5/6 | 90300 | 83.3% | 5/6 | 0 | 90320 | 90320 |
| CPU local | 8 | 100.0% | 8/8 | 90600 | 87.5% | 7/8 | 0 | 90328 | 90333 |
| CPU local | 10 | 90.0% | 9/10 | 90612 | 90.0% | 9/10 | 0 | 90603 | 90659 |
| CPU local | 50 | 98.0% | 49/50 | 90919 | 1.2% | 9/730 | 720 | 581 | 8893 |
| CPU local | 100 | 100.0% | 100/100 | 91163 | 1.4% | 10/695 | 685 | 1412 | 9793 |
| Colab T4 | 2 | 0.0% | 0/6 | 8356 | 0.0% | 0/2 | 0 | 41652 | 41652 |
| Colab T4 | 4 | 0.0% | 0/9 | 14470 | 0.0% | 0/8 | 0 | 18220 | 19196 |
| Colab T4 | 6 | 0.0% | 0/10 | 21453 | 0.0% | 0/3518 | 3516 | 20 | 72 |
| Colab T4 | 8 | 0.0% | 0/11 | 34233 | 0.0% | 0/3648 | 3648 | 19 | 131 |
| Colab T4 | 10 | 0.0% | 0/14 | 30687 | 0.0% | 0/3599 | 3599 | 29 | 193 |
| Colab T4 | 50 | 59.3% | 32/54 | 90081 | 0.0% | 0/3024 | 3024 | 364 | 621 |
| Colab T4 | 100 | 85.0% | 85/100 | 90320 | 0.0% | 0/3075 | 3075 | 736 | 1283 |

Fuente completa (con p95 de C0): `analisis/tabla_v5_c0_c5.md`.

### Punto de degradación

| Hardware | Config | Primer nivel con timeout/5xx | Primer nivel con p95 ≥ 2× nivel base | Primer nivel con rate limit activo | Timeouts totales / peticiones |
|---|---|---:|---:|---:|---|
| CPU local | C0 | 4 | — ¹ | — | 173 / 180 |
| CPU local | C5 | 2 ² | — ¹ | 50 | 44 / 1455 |
| Colab T4 | C0 | 50 | 6 | — | 117 / 204 |
| Colab T4 | C5 | — | — | 6 | 0 / 16874 |

¹ En CPU local el p95 ya está en el techo del timeout (~90 s) desde el nivel más bajo, así que no
puede duplicarse: la señal de latencia está saturada, no ausente.
² 1 de 2 peticiones. Con n=2 esto no permite afirmar que C5 degrade antes que C0 (ver hallazgo 7 de
FUENTE_DE_VERDAD.md): el rate limit todavía no se había disparado, y en ese régimen C5 se comporta
como C0.

Fuente: `analisis/tabla_v5_punto_degradacion.md`.

### Lectura

- **C5 frena el agotamiento de recursos solo una vez que el rate limit se dispara, y el disparo es
  un umbral, no una curva.** Por debajo del umbral (CPU local, niveles 2 a 10) C5 es
  indistinguible de C0: 0 bloqueos y el mismo ~90% de timeouts. Por encima del umbral, los timeouts
  pasan de 98.0% a 1.2% (nivel 50) y de 100.0% a 1.4% (nivel 100), y la mediana de respuesta cae de
  ~91 s a menos de 1.5 s.
- **Dónde está el umbral depende del hardware, no de la configuración.** En CPU local cada petición
  tarda ~90 s, así que un worker no alcanza a superar 10 peticiones/min por cliente hasta el nivel 50.
  En Colab (GPU) las peticiones son más rápidas, el volumen crece antes y el límite se dispara desde
  el nivel 6. En Colab, C5 da 0.0% de timeouts en los 7 niveles, mientras que C0 cae a partir del
  nivel 50 (y su latencia ya se duplica en el nivel 6).
- **El ASR del nivel bajo el umbral no se debe comparar con el ASR sobre el umbral dentro de C5.** Por
  encima del umbral, el denominador de C5 se infla con los reintentos rápidos que reciben 429
  (hasta 3648 peticiones en 20 s). Por eso la tabla reporta también los timeouts en conteo absoluto:
  9 y 10 en CPU local, 0 en Colab.
- Estas corridas son anteriores al límite **global** de 50/min (commit `aa75df7`, 2026-09-22 18:03).
  Todos los datos de esta tabla reflejan solo el límite por cliente de 10/min.

---

## 2. Tiempo de revisión humana (costo operativo)

**Resultado: no se puede calcular. En todos los logs del proyecto hay 0 decisiones humanas
registradas.**

`analisis/tiempo_revision_humana.py` recorrió los 51 JSONL de `resultados/`, todas las fechas desde
2026-09-05, buscando eventos con `tiempo_revision_humana_ms`. Ese campo solo lo escriben
`POST /revision/{id}/aprobar` y `/rechazar`, que existen desde el 2026-09-20. No encontró ninguno.
`resultados_template.csv` tampoco tiene ninguna fila con ese campo lleno.

| Grupo | n | media | desv. estándar | mediana | mín. | máx. |
|---|---:|---:|---:|---:|---:|---:|
| Todas | 0 | — | — | — | — | — |

Por qué hay cero:

1. Las ráfagas de V5 no esperan una decisión humana. `enviar_a_revision()` encola y el proxy
   responde 429 de inmediato. Nadie abrió `/revision/ui` durante ni después de las corridas, así que
   nada se aprobó ni se rechazó.
2. La cola vive en memoria (`proxy/cola.py`). Lo que quedó pendiente se perdió al apagar el proxy
   sin dejar evento de decisión.
3. Ninguna otra prueba del proyecto ejerció la interfaz de revisión con personas reales. Solo la
   ejercen los tests de integración, que usan un `TestClient` y no escriben en `resultados/`.

**No se reporta ningún tiempo estimado.** La media, la desviación y el rango quedan vacíos en la
tabla maestra (sección 4) hasta que existan decisiones reales.

**Limitación adicional del esquema, independiente de lo anterior:** el log no registra *quién*
revisó. Aunque hubiera decisiones, la variabilidad entre integrantes que pide la tarea solo se
podría aproximar con la dispersión global (desviación estándar y rango), no desglosar por persona.
Desglosarla requiere un campo extendido nuevo, por ejemplo `revisor`. Es un cambio del esquema de
log compartido, así que se propone al equipo y no se aplica unilateralmente (CLAUDE.md, sección 8).

### Lo que los logs sí permiten medir sobre el costo

- **Volumen de intercepciones que en principio recaen sobre un revisor humano:** 18267 en C5 y 1090
  en C6 (`tabla_resumen_asr_costo_operativo.md`).
- **Ritmo de llegada durante la ráfaga, una vez activo el rate limit:** entre 68 y 69 por segundo
  en CPU local (niveles 50/100) y entre 152 y 183 por segundo en Colab (niveles 6 a 100). Se
  calculó con los timestamps de los eventos `bloqueado` de cada JSONL por nivel.
- **Capacidad de la cola:** `MAX_TAMANO_COLA = 200`. Con 0 decisiones, la cola se llena con las
  primeras 200 intercepciones. Todas las siguientes se rechazan sin llegar a un humano: la rama de
  cola llena falla cerrado, como está documentado. Si el proxy no se reinició entre niveles, al
  menos 1205 de las 1405 intercepciones de CPU local (85.8%) y 16662 de las 16862 de Colab (98.8%)
  fueron rechazos automáticos por cola llena, no revisiones pendientes. El log no distingue
  "encolado" de "cola llena" (ambos son `bloqueado`/`aprobacion_humana`), así que esta cifra es una
  cota inferior deducida del código y de los conteos, no un conteo directo.

---

## 3. Análisis: efectividad técnica vs. costo operativo

Contra el agotamiento de recursos, el mecanismo 5 es técnicamente efectivo, pero no por la
aprobación humana. Lo que protege es el rate limit que lo acompaña. Una vez que se dispara, el
porcentaje de peticiones que agotan el timeout cae de 98.0–100.0% en C0 a 1.2–1.4% en CPU local,
y de 59.3–85.0% a 0.0% en Colab. La mediana de respuesta baja de ~90 s a menos de 1.5 s, porque
Ollama deja de recibir la carga. Esa protección tiene un umbral y depende del hardware: bajo ese
umbral C5 no protege en absoluto (niveles 2 a 10 en CPU local).

El componente humano, que es lo que da nombre al mecanismo, tiene un costo que los datos muestran
fuera de escala frente a un revisor real. Durante el ataque, las peticiones interceptadas llegaron
a entre 68 y 183 por segundo. Un humano que decidiera cada una en un segundo, cifra optimista y no
medida, acumularía un atraso de minutos por cada 20 s de ráfaga. El diseño lo resuelve fallando
cerrado: con la cola llena (200), el resto se rechaza automáticamente. Así, contra V5, la "aprobación
humana" funciona en la práctica como un **rechazo automático con un búfer de 200 peticiones**, no
como revisión. Eso protege al servicio, pero también descarta sin revisar a cualquier usuario
legítimo que comparta el límite durante un ataque. Es un costo de utilidad que estas corridas no
midieron, porque no incluyeron tráfico legítimo simultáneo.

El costo en tiempo humano por petición, que es lo que la tarea pide cuantificar, **sigue sin
medirse**: hay 0 decisiones registradas. Por eso este análisis no puede afirmar cuántos segundos
de revisor cuesta cada petición encolada, ni si ese tiempo varía entre integrantes. Sí puede
afirmar que, bajo V5, el volumen de peticiones supera en órdenes de magnitud cualquier capacidad de
revisión humana plausible.

Esa es la tensión protección/costo de la pregunta de investigación para este mecanismo. La
protección contra V5 se obtiene con un control automático y barato (el rate limit, que en un
atacante de un solo cliente cuesta ~0 ms). El componente caro, el tiempo humano, no aporta
protección adicional contra este vector y se satura primero. La aprobación humana cobra sentido en
volúmenes bajos, sobre peticiones que otro mecanismo ya marcó como sospechosas (V2 a V4 en C6),
no como defensa contra el agotamiento de recursos. Medir su tiempo real en ese escenario es el paso
pendiente (sección 5).

---

## 4. Tabla maestra: columnas de costo operativo

`analisis/consolidar.py` genera ahora, además de `tabla_resumen_asr.{csv,md}`,
`tabla_resumen_asr_costo_operativo.{csv,md}`. Tiene una fila por configuración con
`aprobacion_humana` activa. Todo se calcula desde `resultados_template.csv` y nada se escribe a
mano:

| Configuración | Intercepciones aprobación humana | Decisiones humanas registradas (n) | Tiempo revisión media (ms) | desv. estándar (ms) | mín. (ms) | máx. (ms) |
|---|---:|---:|---:|---:|---:|---:|
| C5 | 18267 | 0 | — | — | — | — |
| C6 | 1090 | 0 | — | — | — | — |

Las columnas de tiempo se llenarán solas en cuanto el log tenga decisiones reales.

**Advertencia sobre la fila V5 de `tabla_resumen_asr.md`:** los valores C0/V5 = 75.5% (n=384) y
C5/V5 = 0.2% (n=18329) **no deben citarse**. Mezclan las corridas de CPU local y Colab, que tienen
hardware no comparable. En C5, además, el denominador está inflado por miles de reintentos rápidos.
Para V5 las cifras citables son las de la sección 1, por nivel y por hardware. Esto responde la
decisión pendiente de la sección 4 de FUENTE_DE_VERDAD.md (fila por petición vs. agregado por
nivel). **Propuesta, a confirmar con el equipo:** mantener una fila por petición en el CSV, por
fidelidad al dato crudo, y citar V5 únicamente desde `tabla_v5_c0_c5.md`, desagregado por nivel y
hardware.

---

## 5. Pendientes para cerrar el criterio "tiempo humano calculado desde datos reales"

1. Sesión de revisión real: con C5 activo y tráfico a un ritmo humano (por debajo del límite de
   revisión, no una ráfaga V5), que **cada uno de los cuatro integrantes** apruebe o rechace un
   bloque de peticiones desde `/revision/ui`. Los eventos resultantes alimentan
   `tiempo_revision_humana.py` sin cambiar código.
2. Para desglosar por integrante: acordar con el equipo un campo extendido `revisor` en los
   eventos de decisión (Piedrahita, dueña de la interfaz), o bien registrar qué integrante revisó
   cada franja horaria y cruzarlo después por timestamp.
3. Opcional: registrar en el log si una intercepción quedó encolada o fue rechazada por cola llena.
   Así la cota inferior de la sección 2 pasaría a ser un conteo directo.
