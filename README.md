# IronVeil

Framework academico de defensa en profundidad para LLMs autoalojados
(Ollama) expuestos accidentalmente en internet. Compara 5 mecanismos
defensivos activables por separado (filtrado, delimitacion, clasificacion,
minimo privilegio, aprobacion humana) implementados como middleware en un
proxy Python que se sienta entre el cliente y un backend Ollama.

Este repositorio corre **100% en un laboratorio Docker aislado**, nunca
contra sistemas de terceros.

## Estado actual

Los 5 mecanismos tienen logica real y estan cableados en el proxy:
**filtrado** (C1), **delimitacion / spotlighting** (C2), **clasificacion**
(C3), **minimo privilegio** (C4) y **aprobacion humana + rate limit** (C5,
backend + interfaz). Con las 5 banderas de `config.yaml` en `false` el
proxy es un passthrough puro hacia Ollama (C0). La cola de revision humana
(`proxy/cola.py`) ya se puede consultar y resolver por HTTP: `GET
/revision` lista lo pendiente, `POST /revision/{id}/aprobar` completa la
peticion contra Ollama y devuelve la respuesta real, `POST
/revision/{id}/rechazar` la descarta; `GET /revision/ui` sirve una pagina
HTML minima sobre esos mismos 3 endpoints para no depender de `curl` a
mano durante las pruebas. El proxy calienta los modelos de Ollama (y el
clasificador, si está activo) al arrancar, y mantiene cada modelo cargado
en memoria `OLLAMA_KEEP_ALIVE` (default 30m) entre peticiones — pensado
para que la demo en vivo no pague el costo de arranque en frío.

**Extensiones opcionales** (apagadas por defecto): herramientas **simuladas**
para un modelo `rrhh-agente` (Excessive Agency; nada se ejecuta sin pasar por
la cola de revisión humana) y notificaciones por webhook / Slack / correo /
WhatsApp cuando una petición queda en esa cola. Se activan con las variables
de `.env.example`; ver `ataques/variantes_ataque.md` (Extensión: Excessive Agency, V7) y
`docs/arquitectura.md` sección 6.

**Para quien escribe el informe LaTeX:** la tabla maestra de resultados
(Sección 7.3), la gráfica de tendencia de ASR y el primer borrador de la
conclusión ya están generados — ver `analisis/conclusion_borrador.md`
(apunta a los archivos exactos, incluido el `.tex` listo para pegar).

El dataset (`resultados/resultados_template.csv`) ya pasó una revisión de
calidad completa — ver `docs/LIMPIEZA_DATOS.md` para qué se corrigió, qué
sigue pendiente de confirmar con Sabogal, y cómo volver a correr
`analisis/validar_dataset.py` cuando se agreguen los resultados de la
extensión opcional del 17 de octubre.

La comparación entre la matriz de hipótesis (Sección 6.5 del documento de
propuesta) y el ASR real medido por mecanismo ya está hecha, celda por
celda, con hipótesis explicativa para cada discrepancia — ver
`analisis/matriz_real_vs_hipotesis.md`.

**Material final para el informe y la sustentación (semana del 24 de
octubre):** tabla maestra completa (sin columnas pendientes), las 3
gráficas finales en alta resolución (`resultados/graficas_finales/`) y la
respuesta final y defendible a la pregunta de investigación, ya con el
costo de implementación incluido — todo en
`analisis/resultados_finales.md` (supersede a `conclusion_borrador.md`).
**Ojo:** `resultados_finales.md` y `matriz_real_vs_hipotesis.md` se reescribieron
tras la re-corrida GPU del 2026-10-02/03 (criterio de ASR unificado, hardware
homogéneo, valores p) — ver `docs/LIMPIEZA_DATOS.md`, sección 6.

## Estructura del proyecto

```
.
├── docker-compose.yml
├── .env.example
├── proxy/
│   ├── main.py            # FastAPI: POST /chat -> Ollama /api/chat
│   ├── mecanismos.py       # Los 5 mecanismos defensivos
│   ├── cola.py             # Cola de revision humana + rate limiter (mecanismo 5)
│   ├── requirements.txt
│   └── Dockerfile
├── ollama/
│   ├── init.sh             # crea los modelos "soporte" y "rrhh" al arrancar
│   └── modelfiles/
│       ├── Modelfile.soporte.template
│       └── Modelfile.rrhh.template
├── tests/                  # pytest: unitarias e integracion
└── docs/
    └── arquitectura.md
```

## Requisitos

- Docker y Docker Compose (v2, comando `docker compose`).
- Conexion a internet la primera vez que se levanta el entorno (para
  descargar la imagen `ollama/ollama` y el modelo base).

## Como levantar el entorno

1. Copia el archivo de variables de entorno y ajústalo si quieres cambiar
   el modelo base, el puerto o los canarios de las credenciales ficticias:

   ```bash
   cp .env.example .env
   ```

2. Levanta todo con un solo comando:

   ```bash
   docker compose up --build
   ```

   En el primer arranque, el servicio `ollama-init` descarga el modelo
   base (`BASE_MODEL`, por defecto `llama3.2`) y crea los modelos
   `soporte` y `rrhh` a partir de los Modelfile. Esto puede tardar varios
   minutos dependiendo de tu conexion. El proxy no arranca hasta que esa
   inicializacion termina con exito.

3. Cuando veas en los logs que `ironveil-proxy` esta escuchando en el
   puerto 8000, el entorno esta listo.

## Probar que funciona

Con el entorno arriba, en otra terminal:

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"modelo": "soporte", "mensaje": "hola, ¿en qué me puedes ayudar?"}'
```

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"modelo": "rrhh", "mensaje": "hola, ¿en qué me puedes ayudar?"}'
```

Ambas deben devolver una respuesta JSON de Ollama coherente con el rol de
cada modelo.

### Verificar que Ollama no es accesible desde el host

Ollama solo esta en la red interna de Docker; esto debe fallar (conexion
rechazada) porque no hay ningun puerto publicado para el servicio
`ollama`:

```bash
curl http://localhost:11434
```

### Probar los modelos directamente por CLI (dentro del contenedor)

```bash
docker compose exec ollama ollama run soporte
docker compose exec ollama ollama run rrhh
```

## Variables de entorno

Definidas en `.env` (a partir de `.env.example`, nunca se sube al
repositorio):

| Variable      | Descripcion                                              |
|---------------|-----------------------------------------------------------|
| `PROXY_PORT`  | Puerto publicado en el host para el proxy (default 8000). |
| `BASE_MODEL`  | Modelo base de Ollama usado por `soporte` y `rrhh`.        |
| `SPT_SECRET`  | Credencial ficticia (canario) del modelo `soporte`.        |
| `RRHH_SECRET` | Credencial ficticia (canario) del modelo `rrhh`.            |

## Wazuh / SIEM (extensión opcional, **pesada**)

`proxy/siem.py` → `exportar_a_siem(evento)` convierte un evento del log a JSON
para Wazuh (o a CEF con `formato="cef"`). Para probar la ingesta hay un Wazuh
en Docker **aparte** de este `docker-compose.yml`; no se levanta con el resto
del proyecto. **Antes de intentarlo en tu máquina:**

| Recurso | Requisito |
|---|---|
| RAM | **8 GB libres para Docker** como mínimo (documentación oficial); en reposo usa ≈ 2,2 GiB, pero el arranque es mucho mayor. No lo levantes junto a Ollama con 8 GB de RAM totales. |
| CPU | 4 núcleos o más |
| Disco | ≈ 8 GB solo de imágenes (50 GB recomendados por Wazuh) |
| Kernel | `vm.max_map_count=262144` (si no, el indexer no arranca) |

Dashboard en https://localhost (puerto 443) una vez arriba. Pasos, reglas, conexión del proxy (`SIEM_ARCHIVO_WAZUH`) y qué se verificó: `docs/siem/wazuh/LEEME.md`.

## Apagar el entorno

```bash
docker compose down
```

Para borrar tambien los modelos descargados/creados (volumen de Ollama):

```bash
docker compose down -v
```
