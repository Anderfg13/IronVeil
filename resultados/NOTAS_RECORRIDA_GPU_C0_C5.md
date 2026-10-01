# Runbook: re-correr C0-C5 en Colab GPU (pendiente, para mañana)

> Objetivo: que C0-C5 queden en el MISMO hardware que C6 (GPU T4 de
> Colab), para que la columna "Latencia mediana" de
> `analisis/tabla_maestra.py` deje de mezclar laptop CPU con GPU.
> Decisión ya tomada con el usuario: las filas viejas de C0-C5 (CPU) se
> descartan (mueven a `descartados.csv`) y se reemplazan por las nuevas
> de GPU — no se quedan ambas mezcladas.
>
> Alcance: V1-V4 (lo que sí entra en la columna de latencia; V5 ya está
> excluido de esa métrica por diseño — ver docstring de
> `latencia_extra_por_config()`). Si se quiere parejo también en V5,
> correrlo aparte con `ataques/vector5_carga.py` o
> `vector5_agotamiento.py`, mismo patrón.

## 1. Celda de Colab — activar GPU y clonar el repo

Runtime → Change runtime type → **T4 GPU**, luego:

```python
!nvidia-smi
!git clone https://github.com/Anderfg13/IronVeil.git
%cd IronVeil
!git checkout develop
```

## 2. Instalar Ollama (zstd primero, si no lo hiciste ya)

```python
!apt-get -qq install -y zstd
!curl -fsSL https://ollama.com/install.sh | sh
```

## 3. Arrancar Ollama y crear los modelos (con TUS secretos, nunca los pego yo)

```python
import subprocess
ollama_proc = subprocess.Popen(['ollama', 'serve'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
```

```python
import getpass, os
os.environ['HF_TOKEN'] = getpass.getpass('HF_TOKEN: ')
os.environ['SPT_SECRET'] = getpass.getpass('SPT_SECRET: ')
os.environ['RRHH_SECRET'] = getpass.getpass('RRHH_SECRET: ')
os.environ['BASE_MODEL'] = 'llama3.2:1b'
os.environ['MODELO_CLASIFICADOR'] = 'llama-guard3:1b'
os.environ['MODELO_PROMPT_GUARD_ID'] = 'meta-llama/Llama-Prompt-Guard-2-86M'
```

```python
!ln -sf /content/IronVeil/ollama/modelfiles /modelfiles
!bash ollama/init.sh
!ollama list
```

## 4. Instalar dependencias del proxy y arrancarlo

```python
!pip install -q -r proxy/requirements.txt
```

```python
import subprocess, time
proxy_proc = subprocess.Popen(
    ['uvicorn', 'proxy.main:app', '--host', '0.0.0.0', '--port', '8000'],
    cwd='/content/IronVeil', stdout=subprocess.PIPE, stderr=subprocess.PIPE,
)
time.sleep(5)
!curl -s http://localhost:8000/health
```

## 5. Loop C0 → C5: escribir config.yaml y correr V1-V4 en cada una

Una celda por configuración (así puedes ver el resultado de cada una
antes de seguir). El contenido exacto de `config.yaml` por config:

| Config | filtrado | delimitacion | clasificacion | minimo_privilegio | aprobacion_humana |
|---|---|---|---|---|---|
| C0 | false | false | false | false | false |
| C1 | true | false | false | false | false |
| C2 | false | true | false | false | false |
| C3 | false | false | true | false | false |
| C4 | false | false | false | true | false |
| C5 | false | false | false | false | true |

Plantilla de celda (repetir 6 veces, cambiando `CONFIG` y los booleanos):

```python
CONFIG = "C0"  # <-- cambiar en cada pasada: C0, C1, C2, C3, C4, C5

config_yaml = """filtrado: false
delimitacion: false
clasificacion: false
minimo_privilegio: false
aprobacion_humana: false
"""
# Para C1..C5, poner en true SOLO el mecanismo correspondiente a esa fila
# de la tabla de arriba antes de correr esta celda.

with open('/content/IronVeil/config.yaml', 'w') as f:
    f.write(config_yaml)

!cat /content/IronVeil/config.yaml
```

```python
!python ataques/vectores_1_2_3.py --configuracion {CONFIG} --url-proxy http://localhost:8000 --permitir-host-remoto
!python ataques/vector4_movimiento_lateral.py --configuracion {CONFIG} --url-proxy http://localhost:8000 --permitir-host-remoto
```

Repetir el par de celdas de arriba 6 veces (C0, C1, C2, C3, C4, C5),
cambiando `CONFIG` y el `config_yaml` según la tabla. Los JSONL quedan en
`resultados/<fecha-de-hoy>/` (nombre con timestamp, p. ej.
`vectores_1_2_3_C1_143022.jsonl`).

## 6. Descargar los JSONL nuevos

Panel de archivos (ícono de carpeta, izquierda) → navegar a
`IronVeil/resultados/<fecha-de-hoy>/` → clic derecho sobre la carpeta
completa (o cada `.jsonl` si el navegador no deja carpetas) → **Download**.
Si sale el diálogo nativo de "Guardar como" de Windows (ya pasó antes),
guárdalo en la carpeta scratchpad de esta sesión:

```
C:\Users\ander\AppData\Local\Temp\claude\D--ander-Documents-SEMESTRE-8-FDSI-Proyecto-REPO-IronVeil\f15e013c-ac19-4deb-b5e2-81b54369d5b0\scratchpad
```

Avísame cuando estén ahí y yo me encargo de:
1. Mover las filas viejas de C0-C5 (CPU) a `resultados/descartados.csv`
   con la razón documentada (reemplazadas por corrida homogénea en GPU).
2. Ingestar los JSONL nuevos con
   `analisis/agregar_resultados_desde_jsonl.py`.
3. Regenerar `tabla_maestra.py`, `matriz_real_vs_hipotesis.py`,
   `graficas_finales.py` y `resultados_finales.md` con los datos ya
   homogéneos en hardware.
4. Dejar `config.yaml` de tu laptop como estaba (C0) al terminar, para no
   dejar el repo en un estado raro.

## Nota de seguridad (ya aplicada antes, se repite)

Los secretos (`HF_TOKEN`, `SPT_SECRET`, `RRHH_SECRET`) los escribes TÚ con
`getpass()` en tu propia sesión de Colab. Nunca me los pegues a mí ni los
pongas en una celda como texto plano — ese es precisamente el límite que
hemos respetado en todas las corridas anteriores.
