# IronVeil

Framework academico de defensa en profundidad para LLMs autoalojados
(Ollama) expuestos accidentalmente en internet. Compara 5 mecanismos
defensivos activables por separado (filtrado, delimitacion, clasificacion,
minimo privilegio, aprobacion humana) implementados como middleware en un
proxy Python que se sienta entre el cliente y un backend Ollama.

Este repositorio corre **100% en un laboratorio Docker aislado**, nunca
contra sistemas de terceros.

## Estado actual

Mecanismos con logica real y cableados en el proxy: **filtrado** (C1),
**delimitacion / spotlighting** (C2) y **clasificacion / Llama Guard** (C3).
Con sus banderas de `config.yaml` en `false` el proxy es un passthrough puro
hacia Ollama (C0). Minimo privilegio y aprobacion humana siguen como stubs
neutros: se conectan en las siguientes semanas.

## Estructura del proyecto

```
.
├── docker-compose.yml
├── .env.example
├── proxy/
│   ├── main.py            # FastAPI: POST /chat -> Ollama /api/chat
│   ├── requirements.txt
│   └── Dockerfile
├── ollama/
│   ├── init.sh             # crea los modelos "soporte" y "rrhh" al arrancar
│   └── modelfiles/
│       ├── Modelfile.soporte.template
│       └── Modelfile.rrhh.template
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

## Apagar el entorno

```bash
docker compose down
```

Para borrar tambien los modelos descargados/creados (volumen de Ollama):

```bash
docker compose down -v
```
