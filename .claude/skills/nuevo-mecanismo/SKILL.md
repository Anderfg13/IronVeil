---
name: nuevo-mecanismo
description: Procedimiento completo para implementar o cablear un mecanismo defensivo de IronVeil en el proxy. Úsala SIEMPRE que se vaya a implementar, modificar o conectar cualquiera de los 5 mecanismos (filtrado, delimitación, clasificación, mínimo privilegio, aprobación humana), se toque la cadena de mecanismos del endpoint /chat, o se cambie una firma en mecanismos.py — aunque el usuario solo diga "implementa X" o "conecta Y al proxy".
---

# Implementar o cablear un mecanismo

Los 5 mecanismos comparten una estructura deliberada. Salirse de ella rompe la premisa del experimento: **las 7 configuraciones corren con el mismo código, cambiando solo `config.yaml`.**

## Antes de escribir código

1. Lee la firma vigente en `CLAUDE.md` § Contratos estables. Si lo que vas a implementar exige cambiarla, **para y avísale al equipo primero** — hay tres personas más leyendo esa firma.
2. Confirma qué bandera de `config.yaml` gobierna el mecanismo.
3. Corre `pytest` completo antes de tocar nada. Necesitas saber si algo ya estaba roto.

## Estructura obligatoria

### 1. La función vive en `proxy/mecanismos.py`

- Type hints completos, docstring PEP 257 (qué recibe, qué devuelve, qué decide).
- **Sin efectos secundarios.** No escribe el log, no muta estado global, no toca disco. Recibe datos, devuelve una decisión.
- Si el mecanismo necesita red (clasificación), aísla la llamada en su propia función con timeout explícito y comportamiento por defecto **fail closed**: ante error o timeout, se asume peligroso. Nunca dejar pasar por defecto.
- Documenta en el docstring si el mecanismo es **determinista** (filtrado, delimitación, mínimo privilegio) o **probabilístico** (clasificación). Esa distinción — defensas "duras" vs "blandas" — es un punto conceptual del informe.

### 2. El cableado va en la cadena, no en un `if`

El endpoint `/chat` recorre una lista ordenada de pasos:

```
filtrado → delimitacion → clasificacion → minimo_privilegio → aprobacion_humana
```

Reglas:
- Un paso se ejecuta **solo si** su bandera está en `true`.
- **El primer bloqueo gana**: la cadena se corta y no se evalúa el resto (correcto y además más barato).
- El orden es fijo y justificado: lo barato computacionalmente primero, el modelo clasificador después.
- La clasificación evalúa el **texto original del usuario**, no el texto ya envuelto por la delimitación.
- Si agregar tu mecanismo hace que `/chat` pase de ~40 líneas, extrae a funciones auxiliares. No acumules ramas.

### 3. El registro lo hace el endpoint

El mecanismo devuelve su decisión; el endpoint construye el evento de log. Consulta la skill `esquema-log` para los campos exactos, incluidos los extendidos que tu mecanismo deba emitir (`latencia_clasificador_ms`, `tiempo_revision_humana_ms`, etc.).

`mecanismo_que_bloqueo` debe identificar **cuál** de los 5 actuó. Si el log no distingue tu mecanismo de los otros, Sabogal no puede medir su efectividad y el análisis de Fiquitiva queda ciego.

### 4. Constantes configurables arriba, una sola vez

Patrón de credencial, límite de peticiones por minuto, timeout del clasificador, lista de patrones prohibidos: definidos una vez, en el tope del módulo o en `.env`. Nunca repetidos en dos sitios ni incrustados en la lógica. Las credenciales ficticias (`SPT-DEMO-8841`, `RRHH-DEMO-2291`) jamás se hardcodean en el código del proxy.

## Tests mínimos por mecanismo

Ninguno es opcional. Van en el mismo commit que la implementación.

1. **Caso que bloquea** — al menos 2 entradas que el mecanismo debe detener.
2. **Caso legítimo** — al menos 2 entradas normales que **no** deben bloquearse. Esto mide falsos positivos, que son una columna de la tabla maestra. Ejemplo: `"¿me ayudas a resetear mi contraseña?"` nunca debe caer.
3. **Caso de error** — timeout, respuesta malformada, dependencia caída. Verifica que el comportamiento por defecto sea seguro.
4. **Bandera apagada** — con la bandera en `false`, el comportamiento es idéntico al passthrough. Este test se olvida siempre y es el que protege la validez de C0.

Si el mecanismo llama a un modelo, **mockea la respuesta**. La suite debe correr sin el stack levantado.

Si el mecanismo maneja estado compartido entre peticiones concurrentes (la cola), agrega un test de ráfaga con `asyncio.gather` o `ThreadPoolExecutor`, y córrelo varias veces: un test flaky aquí es una condición de carrera real, y el V5 dispara exactamente eso.

## Al terminar

- [ ] `pytest` completo pasa, no solo tus tests nuevos.
- [ ] `ruff check . && black .` limpios.
- [ ] Con la bandera en `false`, nada cambia respecto al comportamiento anterior.
- [ ] Con la bandera en `true` junto a otra ya existente, ambos actúan en el orden documentado — pruébalo, no lo asumas.
- [ ] El log identifica correctamente el mecanismo que bloqueó.
- [ ] Si cambió un contrato compartido, `CLAUDE.md` está actualizado **en el mismo commit**.
- [ ] Commit con prefijo (`feat:`, `fix:`, `test:`) y mensaje descriptivo.