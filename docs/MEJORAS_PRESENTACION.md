# Mejoras a la presentación técnica (textos listos para pegar)

Revisión de las 19 diapositivas de `FDSI_IronVeil` contra los cinco criterios (problema e hipótesis, estado del arte,
arquitectura, IA, métricas). Cada cifra de abajo sale de `analisis/` o del informe; nada es nuevo ni inventado.
Lo que **no se pudo verificar** (citas externas) está marcado como pendiente.

Orden de prioridad: 1 → 6.

---

## 1. Diapositiva 14 · Métricas y criterios de éxito (nueva tabla con «¿Cumple?»)

**Por qué:** la columna «Observado» no decía si el criterio se cumplía, y el criterio «reducción ≥ 50 puntos» frente
a «31,2 → 15,0 %» parecía incumplirse. En realidad ese criterio se aplica **por mecanismo y por vector**
(`analisis/matriz_real_vs_hipotesis.py`: ≥ 50 puntos = directo, entre 0 y 50 = parcial), no al promedio.
También el «0/60» de falsos positivos necesitaba su matiz.

**Título:** Métricas y criterios de éxito

| Métrica | Método de evaluación | Criterio de éxito | Observado | ¿Cumple? |
|---|---|---|---|---|
| ASR por mecanismo y vector | Fuga verificada del canario; k/n por celda; Fisher exacto contra C0 | Directo: reducción ≥ 50 puntos y p < 0,05 †. Parcial: entre 0 y 50 puntos | Directo en 1 caso: aprobación humana en V5, 74,7 → 0,2 %. Parcial: filtrado en V2, V3 y V4; delimitación y mínimo privilegio en V4 | **Parcial** |
| ASR promedio V1–V4 | Promedio de los cuatro vectores, mismas 7 configuraciones | H2: C6 logra el ASR más bajo; ninguna llega a 0 % (esperado por la literatura) | C0 31,2 % → C1 y C6 15,0 %. C6 no mejora a C1 | **Parcial** |
| Ataque completo V4 | Extracción + uso cruzado, medidos por pasos | Bajar a 0 % tras el paso 2 † | 12/39 → 0/39 (p = 0,0002) | **Sí** |
| Falsos positivos | 60 mensajes legítimos (12 distintos) en C0, C3 y C6 | 0 legítimos bloqueados ‡ | 0/60 en la entrada. La salida puede retener una respuesta legítima (visto en una prueba aparte en C3 y C6): tasa real no medida | **No concluyente** |
| Latencia propia | Tiempo total menos tiempo del modelo, por pieza (µs) | Mediana < 100 ms ‡ | 76,6 ms (p95 ≈ 91 ms); piezas deterministas < 1 ms. Con Jev, p50 de 92 a 221 ms | **Sí** (local) · **Parcial** (Jev) |
| Fiabilidad del clasificador | Estado de cada veredicto en `eventos.jsonl` | Ninguna caída disfrazada de detección ‡ | 462/462 con estado ok | **Sí** |
| Abuso por volumen (V5) | ASR con ráfagas crecientes, C0 contra C5 | Límite de tasa activo ‡ | 74,7 % → 0,2 % (datos previos, falta re-correr) | **Sí** (a confirmar) |
| Costo de implementación | Líneas de código del módulo y horas registradas | Sin umbral fijo; se pondera contra la protección ‡ | C1 248 líneas / 21 h; C6 1599 / 153 h | Informativo |

**Nota al pie:** † Umbral definido por el equipo en la fase de análisis (`analisis/matriz_real_vs_hipotesis.py`); se
declara para poder discutirlo. ‡ Umbral propuesto por el equipo para esta evaluación. Con n pequeño, dos intervalos que se
solapan no son distinguibles. Una celda «parcial» significa efecto real pero menor que el umbral, no «sin efecto».

---

## 2. Diapositiva 12 · Clasificador local frente a Jev (corregir la fila de idiomas)

**Por qué:** «Más de 50» es una cifra que el fabricante no publica (ver `docs/GUIA_PARA_EL_PAPER.md`); la nota al pie la
matizaba, pero la celda la afirmaba.

Cambiar solo esta fila:

| Criterio | Llama Prompt Guard 2 (autoalojado) | Jev (servicio de pago) |
|---|---|---|
| Idiomas | 8 (ficha del modelo en Hugging Face) | Cifra no publicada por el fabricante. Medimos 8 idiomas: 16/16 ataques y 0/8 legítimas bloqueadas |

Y borrar la nota ¹ o reemplazarla por: «¹ El fabricante no publica una cifra de idiomas; solo se informan los idiomas
que el equipo midió.»

---

## 3. Diapositiva 11 (y 12) · Contar la IA sin que parezca que falló

**Por qué:** los datos son buenos, pero el orden muestra primero «sin reducción medible» y deja el resultado fuerte
(Jev + Garak) para la diapositiva 16.

Reemplazar el recuadro «Lectura de Modelos / Dónde sí aporta» de la diapositiva 11 por:

> **Lo que mostró la IA.** Con el modelo base de 1B, que ya rechaza casi todo, el clasificador local no redujo la fuga
> de forma medible (V2 a V4, p = 0,72; 0,34; 0,86) y cuesta ≈ 76 ms.
> **Dónde sí aporta.** Donde las reglas no ven: en francés detectó 4 de 4 ataques frente a 0 de 4 del filtro, y frente a
> un catálogo externo (Garak, 339 ataques) con Jev como clasificador el ASR bajó de 51,2 % a 0,3 % (diapositiva 16).
> **Lo importante.** El valor está en el proxy: los cinco mecanismos no cambian si cambia el clasificador.

Mover la diapositiva 16 (Garak con Jev) justo después de la 12, o añadir en la 11 una referencia «→ ver resultado
externo, diapositiva 16».

---

## 4. Diapositivas 4 y 5 · Suavizar la afirmación absoluta

Cambiar la última línea de la diapositiva 4:

> **Vacío:** no encontramos estudios ni productos que comparen combinaciones heterogéneas de defensas sobre un mismo
> sistema autoalojado.

Y en la diapositiva 5, «Defensas sueltas»:

> Decenas de defensas propuestas por separado; en la búsqueda del equipo, pocos estudios comparan combinaciones
> heterogéneas con la misma batería de ataques.

---

## 5. Diapositivas 6 y 7 · Arquitectura (dos diapositivas con el número «6»)

- **Diapositiva 6 (la clara, con los colores):** es la principal. Ya identifica los componentes, el flujo de entrada y
  salida, el SIEM y las dos IA de defensa. Mantenerla como «Arquitectura de la solución».
- **Diapositiva 7 (la oscura, con extensiones):** pasarla al **anexo** con el título «Anexo · Arquitectura con
  extensiones opcionales (memoria de decisiones, autenticación, SIEM múltiple)». Hoy tiene letra muy pequeña y textos que
  se pisan («ENTRADA» con «a cualquier modelo»; el SIEM recortado). Si se deja en el cuerpo, renderizarla más grande
  y corregir el solape.
- **Numeración:** que cada diapositiva tenga un número único.
- **Frase para decir en voz alta sobre la diapositiva 6:** «Aquí se ve dónde está la IA: en rojo, Prompt Guard 2 en la
  entrada y Llama Guard 3 en la salida. Todo lo demás es determinista, o una persona en el bucle.»

---

## 6. Nueva diapositiva final · Referencias

**Por qué:** hay cifras de impacto en la primera diapositiva (≈ 175 000 servidores, ≈ 300 000 afectados, CVE) y en el
estado del arte (Geng, Hines, Unit 42, productos comerciales) sin lista de fuentes. Es lo primero que un jurado revisa.

Título: **Referencias**

| Cita en la diapositiva | Referencia (completar con enlace o DOI verificado) |
|---|---|
| Servidores Ollama expuestos (≈ 175 000, 130 países) | SentinelLabs y Censys, 2026. **Pendiente: título y enlace** |
| Bleeding Llama, CVE-2026-7482 (≈ 300 000) | Cyera, 2026. **Pendiente: título y enlace; confirmar el CVSS 9,1** |
| Revisión de 128 estudios (preprocesamiento detecta 60 a 80 %) | Geng et al., 2026. **Pendiente: título y enlace** |
| Spotlighting / delimitación | Hines et al., 2024, «Defending Against Indirect Prompt Injection Attacks With Spotlighting». **Verificar enlace** |
| «Bloquear el 100 % es imposible», aprobación humana | Unit 42 (Palo Alto Networks). **Pendiente: título y enlace** |
| Garak 0.17.0 | Derczynski et al., 2024, «garak: A Framework for Security Probing Large Language Models». **Verificar enlace y versión** |
| Llama Prompt Guard 2 (86M) y Llama Guard 3 (1B) | Fichas de modelo de Meta en Hugging Face |
| Jev | Documentación y tarifa publicada del fabricante (TypeSafe) |
| Estadística | Prueba exacta de Fisher; intervalos de Wilson |

> No se debe presentar ninguna cifra de esta tabla sin abrir su fuente y comprobarla.

---

## 7. Diapositivas 15 y 17 · La combinación recomendada

Hoy dice «aún no se ejecutó». Es honesto, pero es un hueco fácil de cerrar antes del 24: ejecutar filtrado +
delimitación + mínimo privilegio como configuración propia y medirla. Si se mide, reemplazar «≈ 50 h · < 1 ms (estimado;
aún no medido)» por el resultado real con su intervalo. Si no da tiempo, dejar el texto actual, que ya lo declara.

---

## Preguntas probables y respuesta honesta

| Pregunta | Respuesta corta |
|---|---|
| «¿Por qué la IA no redujo la fuga?» | El modelo base de 1B ya rechaza casi todo, así que hay poco margen. La IA aportó en idiomas (4/4 contra 0/4) y frente a Garak con Jev (51,2 % → 0,3 %). Con un modelo menos alineado es una hipótesis aún no probada. |
| «¿Cuál es la tasa de falsos positivos?» | En la entrada, 0 de 60. La clasificación de salida puede retener una respuesta legítima y esa tasa no se midió; es un próximo paso. |
| «¿Los umbrales se fijaron después de ver los datos?» | Algunos los definió el equipo en la fase de análisis; por eso se marcan con †/‡ y se declaran, para poder discutirlos. |
| «¿Jev es seguro para datos sensibles?» | No: el texto de cada petición sale a un tercero. Si no puede salir de la red, se autoaloja Prompt Guard. |
| «¿C6 no llega a 0 %?» | Correcto, y es lo esperado: ningún mecanismo garantiza cero. Es defensa en profundidad. |
