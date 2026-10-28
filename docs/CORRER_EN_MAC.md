# Correr IronVeil en una Mac (para quien tiene el computador más potente)

No hay nada que «empaquetar»: **el repositorio ya es el paquete**. Quien lo corre clona, crea su `.env` y levanta con
Docker. Lo único que no está en git son los secretos (`.env`), y cada quien crea los suyos.

> **Aviso honesto:** esta guía se probó en la validación del archivo de Compose (`docker compose config`) y en la
> sintaxis del script, pero **no en una Mac real**. Si algo falla, copia el mensaje de error y se corrige; en la sección
> «Si algo falla» están los problemas más probables.

## 1. Qué necesita

| Qué | Mínimo | Por qué |
|---|---|---|
| Mac | Apple Silicon (M1 o superior) con **16 GB de RAM** | Ollama + modelos + Docker. Con 8 GB no. |
| Disco libre | **30 a 40 GB** | Modelos de Ollama (~5 GB), imagen del proxy con PyTorch y, si usa Wazuh, ~8 GB más |
| Docker Desktop | Reciente, con **Compose ≥ 2.24** | El archivo de la Mac usa `!reset` |
| Ollama | App nativa de <https://ollama.com/download> | En Mac, **Docker no pasa la GPU**: Ollama dentro de Docker correría solo en CPU |
| Git y Python 3 | Los de siempre (`git`, `python3`) | Para clonar y cambiar de configuración |
| Cuenta de Hugging Face | Con el token propio | Para Prompt Guard (ver paso 3) |

En Docker Desktop: **Settings → Resources**, memoria **10 a 12 GB** (si tiene 16 GB en total), y activar
**Use Rosetta for x86_64/amd64 emulation on Apple Silicon**.

## 2. Camino recomendado: Ollama nativo + proxy en Docker

Es el que usa la GPU de la Mac y el que debería dar respuestas rápidas.

```bash
# 1. Clonar
git clone https://github.com/Anderfg13/IronVeil.git && cd IronVeil
git checkout develop              # donde están estos archivos

# 2. Crear su .env (los canarios del .env.example son FICTICIOS)
cp .env.example .env
#    y editar .env: poner su HF_TOKEN= (ver paso 3)

# 3. Abrir la app de Ollama (icono en la barra de menú) y crear los modelos del proyecto (una sola vez)
sh scripts/mac_crear_modelos.sh

# 4. Levantar solo el proxy, apuntando al Ollama nativo
docker compose -f docker-compose.yml -f docker-compose.mac.yml up --build proxy
```

La primera vez tarda varios minutos (construye la imagen con PyTorch). Cuando el log diga que escucha en el puerto 8000:

```bash
curl -X POST http://localhost:8000/chat -H 'Content-Type: application/json' \
  -d '{"modelo":"soporte","mensaje":"hola"}'
```

Qué hace cada archivo nuevo:
- **`docker-compose.mac.yml`** apaga el Ollama de Docker, apunta el proxy a `host.docker.internal:11434` (el Ollama de la
  Mac) y fuerza `linux/amd64` para el proxy (ver «Si algo falla»).
- **`scripts/mac_crear_modelos.sh`** hace lo mismo que `ollama/init.sh`, pero fuera de Docker: descarga `llama3.2` y
  `llama-guard3:1b`, y crea `soporte`, `rrhh` y `rrhh-agente` con los canarios de `.env`.

> **Seguridad:** el Ollama nativo escucha en `127.0.0.1:11434` del propio computador. Es la excepción a la regla «Ollama
> no se expone al host», aceptable en un portátil personal **siempre que no pongas `OLLAMA_HOST=0.0.0.0`**. Si prefiere
> cumplir la regla al pie de la letra, usa el camino B.

## 3. El token de Hugging Face (Prompt Guard)

La clasificación de entrada (C3 y C6) usa Llama Prompt Guard 2, que tiene licencia restringida:

1. En <https://huggingface.co/meta-llama/Llama-Prompt-Guard-2-86M>, **aceptar la licencia con su cuenta**.
2. Crear un token de lectura en <https://huggingface.co/settings/tokens>.
3. Ponerlo en `.env`: `HF_TOKEN=hf_...`

Sin token, esa pieza **falla cerrada**: bloquea todo, por diseño. Las demás configuraciones funcionan igual.

## 4. Camino B: todo en Docker (más simple, más lento)

Igual que en Windows. Ollama corre **en CPU** dentro del contenedor.

```bash
git clone https://github.com/Anderfg13/IronVeil.git && cd IronVeil
cp .env.example .env              # y poner HF_TOKEN
docker compose up --build
```

## 5. Cambiar de configuración y comprobar

```bash
python3 scripts/seleccionar_config.py C3     # C0..C6; el proxy relee config.yaml en cada petición
```

Páginas: chat en <http://localhost:8000/demo> (con `IRONVEIL_DEMO=1` en `.env`) y consola de revisión en
`http://localhost:8000/revision/ui`. Los eventos quedan en `resultados/AAAA-MM-DD/eventos.jsonl`.

## 6. Los secretos: qué se comparte y qué no

| Secreto | Cómo llega a la Mac |
|---|---|
| `SPT_SECRET`, `RRHH_SECRET` | Son canarios **ficticios**, ya vienen en `.env.example`. |
| `HF_TOKEN` | **El suyo**, de su cuenta. No se comparte. |
| `TYPESAFE_API_KEY` (Jev, de pago) | Solo si va a probar Jev. Se pasa **en privado** (gestor de contraseñas, nunca por chat ni git) y con `CLASIFICADOR_PERMITIR_REMOTO=1`. |
| `NOTIFICAR_SLACK_WEBHOOK_URL` | Si no la necesita, la deja vacía; con ella vacía el aviso a Slack se omite. Si la necesita, también en privado. |

`.env` está en `.gitignore`: **no se sube**. Nunca pasar el `.env` completo de otra persona.

## 7. Wazuh (opcional, pesado)

Wazuh añade ~8 GB de imágenes y ~2,2 GiB de RAM en reposo, más un arranque mucho mayor. En una Mac de 16 GB **solo se
levanta si Ollama ya está estable**. La guía está en [`docs/siem/wazuh/LEEME.md`](siem/wazuh/LEEME.md). El indexer exige
`vm.max_map_count ≥ 262144`; Docker Desktop suele traerlo, y si el indexer no arranca, es lo primero que se revisa.

## 8. Si algo falla

| Síntoma | Probable causa | Qué hacer |
|---|---|---|
| El `build` del proxy falla en la línea de `torch` | `requirements-torch.txt` está fijado con hashes para Linux x86_64 | Ya se fuerza `platform: linux/amd64`; confirmar que Rosetta está activo y volver a construir con `--no-cache` |
| `host.docker.internal` no responde | Ollama no está abierto, o escucha solo en otra interfaz | Abrir la app de Ollama; probar `curl http://localhost:11434` en la Mac |
| `can't find model soporte` | No se corrió el script de modelos | `sh scripts/mac_crear_modelos.sh` y `ollama list` |
| `depends_on` o `!reset` da error | Docker Compose antiguo | Actualizar Docker Desktop (se necesita Compose ≥ 2.24) |
| C3 y C6 bloquean todo | Falta `HF_TOKEN` o no aceptó la licencia | Paso 3 |
| Respuestas muy lentas | Está usando Ollama dentro de Docker (CPU) | Usar el camino recomendado (nativo) |
| Wazuh se cuelga o se reinicia | Poca memoria | Subir la memoria de Docker, o no levantar Wazuh en esa máquina |

## 9. Para el día de la exposición

Si la Mac es la máquina de la demo, antes: Ollama abierto, `docker compose ... up` corriendo 20 minutos antes, **una
petición de prueba en cada configuración** (para calentar los modelos), zoom del navegador al 150 %, y el video de
respaldo abierto. La lista completa está en [`docs/GUION_EXPOSICION.md`](GUION_EXPOSICION.md).
