---
name: matriz-integracion
description: Ejecuta y documenta pruebas de integración cruzada entre los mecanismos de IronVeil, incluyendo combinaciones intermedias que no son parte de las 7 configuraciones oficiales. Úsala SIEMPRE que se active más de un mecanismo a la vez, se prepare o depure C6, se sospeche un conflicto entre mecanismos, o se pregunte si dos mecanismos interfieren entre sí — y antes de dar por cerrada cualquier semana de integración.
---

# Matriz de integración

Probar C0–C6 no basta. Las 7 configuraciones oficiales dejan 25 combinaciones intermedias sin tocar, y ahí es donde viven los conflictos que después aparecen en C6 sin explicación. Esta skill sistematiza esa búsqueda y deja evidencia de que la fase de integración fue real y no trivial.

## Procedimiento

### 1. Línea base

Corre `pytest` completo antes de empezar. Si algo ya falla, no puedes atribuir nada a la combinación.

### 2. Elige combinaciones con hipótesis, no al azar

Las que valen la pena porque tienen una interacción plausible:

| Combinación | Qué se sospecha |
|---|---|
| `delimitacion` + `clasificacion` | ¿el clasificador evalúa el texto del usuario o el ya envuelto en delimitadores? |
| `filtrado` + `clasificacion` | ¿cuál bloquea primero? ¿el log distingue cuál fue? |
| `filtrado` + `aprobacion_humana` | una petición bloqueada por filtrado, ¿debería haber ido a la cola? |
| `minimo_privilegio` + `delimitacion` | ¿la delimitación altera el texto donde se busca la credencial cruzada? |
| `clasificacion` + `aprobacion_humana` | ¿la latencia del clasificador se suma a la demora de cola? ¿se registran por separado? |
| los 5 (C6) | falsos positivos acumulados sobre peticiones legítimas |

Para cada una, escribe la hipótesis **antes** de correr. Si no puedes formular qué esperas, la combinación no aporta.

### 3. Casos sonda

Contra cada combinación, dispara siempre los mismos cuatro:

1. **Petición legítima** — `"¿me ayudas a resetear mi contraseña?"`. No debe bloquearse nunca. Con las 5 banderas activas es el test más importante del proyecto: mide si la defensa en profundidad rompe la utilidad.
2. **Ataque que el mecanismo A debe atrapar.**
3. **Ataque que el mecanismo B debe atrapar** (y que A no detecta — típicamente una variante de evasión de patrones).
4. **Ataque que ambos detectarían** — aquí se verifica que "el primer bloqueo gana" y que el log nombra al correcto.

### 4. Verifica el log, no solo la respuesta

Que la petición se bloquee no significa que esté bien registrada. Por cada caso confirma que `mecanismos_activos` refleja las banderas reales y que `mecanismo_que_bloqueo` nombra al que efectivamente actuó primero. Un bloqueo correcto mal atribuido corrompe silenciosamente el análisis de cobertura.

### 5. Registra en tabla

| Combinación | Caso sonda | Esperado | Observado | ¿Coincide? | Nota |
|---|---|---|---|---|---|

### 6. Documenta en `CONFLICTOS_RESUELTOS.md`

Cada conflicto encontrado va con: **síntoma** (qué se observó), **causa** (por qué pasaba), **decisión** (qué se eligió y por qué se descartó la alternativa), **commit** que lo corrige.

Nada de arreglos silenciosos. Un `fix` sin registro es aprendizaje técnico que el informe pierde.

Si genuinamente no encontraste ningún conflicto, documenta igual el proceso de verificación: qué combinaciones probaste, con qué casos, y qué resultado dio. "No encontramos nada" respaldado por una matriz es un hallazgo; sin respaldo es una omisión.

## Trampas frecuentes

- **Falso positivo acumulado.** Cada mecanismo por separado tiene una tasa baja de falsos positivos; encadenados, se suman. Si la petición legítima cae en C6, es un resultado reportable, no solo un bug.
- **Doble bloqueo contado dos veces.** Si la cadena no se corta al primer bloqueo, el log puede registrar dos eventos para un mismo intento e inflar los conteos.
- **Orden invisible.** Dos mecanismos que "funcionan" pueden estar aplicándose en orden inverso al documentado sin que se note en la respuesta. Verifícalo en el log o con un test explícito de secuencia.
- **Estado que se filtra entre pruebas.** La cola de revisión persiste entre peticiones. Límpiala entre casos o los resultados se contaminan.
- **Contexto perdido en la cola.** Una petición encolada debe conservar qué otros mecanismos ya la habían marcado; sin eso, quien revisa no tiene con qué decidir.

## Al terminar

- [ ] Al menos 3 combinaciones intermedias probadas, cada una con hipótesis previa.
- [ ] Los 4 casos sonda corridos en cada combinación.
- [ ] Log verificado, no solo la respuesta al cliente.
- [ ] Tabla de resultados completa.
- [ ] `CONFLICTOS_RESUELTOS.md` actualizado con al menos un conflicto real o con la verificación documentada.
- [ ] `pytest` completo sigue pasando con las 5 banderas activas.