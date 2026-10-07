"""Genera `resultados/JEV_COLAB.ipynb`: medir a Jev (TypeSafe) desde Google Colab.

El notebook es AUTOCONTENIDO a proposito: lleva embebidos `ataques/medir_clasificador_entrada.py`
y `analisis/estadistica.py`, asi que no depende de que lo ultimo del repo este subido a GitHub
(del repo clonado solo usa el backend de Jev y los prompts legitimos, que ya estan alli). Se
GENERA desde esos archivos y una prueba (`tests/test_notebook_jev.py`) falla si el notebook del
repo no coincide con lo que produce este script.

    python ataques/generar_notebook_jev.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "resultados" / "JEV_COLAB.ipynb"
ARCHIVOS_EMBEBIDOS = (
    "analisis/estadistica.py",
    "ataques/corpus_multilingue.py",
    "ataques/medir_clasificador_entrada.py",
)


def _lineas(texto: str) -> list[str]:
    """Formato de `source` de un notebook: una cadena por linea, con su salto."""
    return texto.strip("\n").splitlines(keepends=True)


def _md(texto: str) -> dict[str, Any]:
    return {"cell_type": "markdown", "metadata": {}, "source": _lineas(texto)}


def _codigo(texto: str) -> dict[str, Any]:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": _lineas(texto),
    }


def _escribir_archivo(ruta: str) -> dict[str, Any]:
    """Una celda `%%writefile` con el contenido exacto del archivo del repo."""
    contenido = (RAIZ / ruta).read_text(encoding="utf-8")
    return _codigo(f"%%writefile /content/IronVeil/{ruta}\n{contenido}")


def construir_notebook() -> dict[str, Any]:
    """El notebook completo (nbformat 4.5), a partir de los archivos del repo."""
    celdas = [
        _md("""
# IronVeil — medir a Jev (TypeSafe) desde Colab (extensión)

**Objetivo:** enviar a Jev ataques y consultas legítimas, y sacar de **cada** envío: latencia (p50/p95), cuántos ataques detecta, cuántas consultas legítimas bloquea por error, cuántas veces falla y por qué, y cómo cambiaría el resultado con otro umbral. Es una **extensión**: no es el núcleo C0–C6 y no entra en las tablas del experimento. Guía: `docs/CAMBIAR_MODELO_CLASIFICADOR.md`.

**Qué se envía (lo eliges en la celda 4):** `MODO = "solo_idiomas"` (por defecto) envía **24 textos en 8 idiomas** (inglés, francés, portugués, alemán, italiano, ruso, chino y árabe: 2 ataques y 1 consulta legítima por idioma); el español ya se midió el 2026-10-06 y no se vuelve a pagar. `"todo"` envía los 29 en español **más** los 24 (53). `"espanol"` envía solo los 29 en español. Las traducciones las hizo un asistente de IA, sin revisión de hablantes nativos.

**No necesita GPU:** el modelo corre en TypeSafe, no aquí. Sirve el entorno de ejecución normal (CPU). Ejecuta las celdas en orden.

**Cuesta dinero:** cada envío se cobra. Por eso:
- La celda 4 dice **cuántos envíos** se harán antes de hacer ninguno.
- **Cada envío se guarda al instante** en un archivo; si algo se corta, lo pagado no se pierde, y puedes re-analizar sin volver a pagar.
- Si fallan **3 envíos seguidos** (clave inválida, sin crédito, límite de uso) se corta solo.

**Seguridad:** la clave la escribes TÚ en la celda 3 (`getpass`, no se muestra). No la pegues en una celda como texto ni en un chat. El archivo de resultados **no** lleva la clave ni el texto de los envíos.

**Privacidad:** Jev es un **tercero**: el texto de cada envío sale de tu laboratorio. Aquí son textos sintéticos (los ataques del experimento y consultas inventadas), sin datos reales. Aun así, la celda 3 activa `CLASIFICADOR_PERMITIR_REMOTO=1` de forma visible: es el permiso que el equipo debe aprobar.
"""),
        _md("## 1. Clonar el repo (rama `develop`)"),
        _codigo("""
%cd /content
!test -d IronVeil || git clone https://github.com/Anderfg13/IronVeil.git
%cd /content/IronVeil
!git checkout develop
!git pull
!python --version
"""),
        _md("""
## 2. Archivos de esta medición

Se escriben desde este notebook (son los mismos del repo) para no depender de lo último que haya en GitHub. Del repo clonado solo se usa el backend de Jev (`proxy/backends_entrada.py`) y los prompts legítimos.
"""),
        *(_escribir_archivo(ruta) for ruta in ARCHIVOS_EMBEBIDOS),
        _codigo("""
# Comprueba que todo importa antes de pedir la clave (httpx y yaml ya vienen en Colab).
import subprocess, sys

r = subprocess.run(
    [sys.executable, "-c", "import ataques.medir_clasificador_entrada; print('importa: OK')"],
    cwd="/content/IronVeil", capture_output=True, text=True)
print(r.stdout + r.stderr[-800:])
assert r.returncode == 0, "No importa: revisa el error de arriba antes de seguir."
"""),
        _md("""
## 3. Clave y permiso

Te pide `TYPESAFE_API_KEY` con `getpass` (no se muestra al escribirla). `CLASIFICADOR_PERMITIR_REMOTO=1` es el permiso para enviar texto a un tercero; está aquí, a la vista, a propósito.
"""),
        _codigo("""
import getpass, os

os.environ["TYPESAFE_API_KEY"] = getpass.getpass("TYPESAFE_API_KEY: ")
os.environ["CLASIFICADOR_PERMITIR_REMOTO"] = "1"   # permiso: el texto de las pruebas sale a TypeSafe
os.environ["CLASIFICADOR_ENTRADA_BACKEND"] = "jev"
print("Listo (la clave no se imprime).")
"""),
        _md("""
## 4. Cuántos envíos se harán (no llama a nadie, no cuesta)

Si el número no es el que esperas, cámbialo en `MODO` o `REPETICIONES` antes de seguir. Con `1` se hace **un** envío por texto; con `3` se mide además si Jev da siempre el mismo puntaje, pero triplica el costo.
"""),
        _codigo("""
REPETICIONES = 1
MODO = "solo_idiomas"   # "solo_idiomas" (24), "todo" (53) o "espanol" (29)
BANDERAS = {"solo_idiomas": "--solo-idiomas", "todo": "--con-idiomas", "espanol": ""}[MODO]
SALIDA = "/content/jev_out"
!mkdir -p {SALIDA}
!cd /content/IronVeil && python ataques/medir_clasificador_entrada.py --simular --repeticiones {REPETICIONES} {BANDERAS}
"""),
        _md("""
## 5. La medición (aquí sí se paga)

Se registra la hora de cada envío (`momento` en el archivo): sirve para saber con qué carga del servicio se midió la latencia. Una pausa de 0,2 s entre envíos evita saturar el límite de uso.
"""),
        _codigo("""
!cd /content/IronVeil && python ataques/medir_clasificador_entrada.py --repeticiones {REPETICIONES} {BANDERAS} --crudo {SALIDA}/jev_crudo.jsonl --salida {SALIDA}/jev_efectividad.md
"""),
        _md("""
## 6. Re-analizar sin pagar

El informe se puede regenerar desde el archivo crudo cuantas veces quieras, sin ningún envío. Útil si quieres otro formato o comparar umbrales con calma.
"""),
        _codigo("""
!cd /content/IronVeil && python ataques/medir_clasificador_entrada.py --resumir-desde {SALIDA}/jev_crudo.jsonl --salida {SALIDA}/jev_efectividad.md > /dev/null && echo "informe regenerado sin ningun envio"
"""),
        _md("""
## 7. Comprobar que el archivo no lleva la clave ni texto

Doble comprobación antes de descargar nada.
"""),
        _codigo("""
import json, os

contenido = open(f"{SALIDA}/jev_crudo.jsonl", encoding="utf-8").read()
informe = open(f"{SALIDA}/jev_efectividad.md", encoding="utf-8").read()
clave = os.environ["TYPESAFE_API_KEY"]
assert clave not in contenido and clave not in informe, "La clave aparece en los resultados: NO los compartas."
registros = [json.loads(l) for l in contenido.splitlines() if l.strip()]
print(f"{len(registros)} envios guardados; campos:", sorted(registros[0]))
print("OK: sin clave en los resultados")
"""),
        _md("""
## 8. Empaquetar y descargar

1. Se crea `/content/resultados_jev_colab.zip` con el archivo crudo y el informe.
2. Panel de archivos (ícono de carpeta, izquierda) → ese zip → clic derecho → **Descargar**. (`files.download()` desde una celda ya falló antes en silencio; este camino sí funciona.)
3. Si aparece el diálogo nativo de «Guardar como» de Windows, guárdalo en la carpeta scratchpad de la sesión de Claude Code.
4. Avísale a Claude: revisa los resultados y los anota en `docs/CAMBIAR_MODELO_CLASIFICADOR.md` con sus límites.
"""),
        _codigo("""
import os, zipfile

destino = "/content/resultados_jev_colab.zip"
with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
    z.write(f"{SALIDA}/jev_crudo.jsonl", "jev_crudo.jsonl")
    z.write(f"{SALIDA}/jev_efectividad.md", "jev_efectividad.md")
print(f"{destino} ({os.path.getsize(destino)/1024:.0f} KB)")
"""),
        _codigo("""
# Al terminar: borra la clave de la memoria de esta sesion.
os.environ.pop("TYPESAFE_API_KEY", None)
"""),
    ]
    return {
        "cells": celdas,
        "metadata": {
            "colab": {"provenance": []},
            "kernelspec": {"display_name": "Python 3", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def serializar(notebook: dict[str, Any]) -> str:
    """El JSON exacto que se guarda (la prueba compara contra esto)."""
    return json.dumps(notebook, indent=1, ensure_ascii=False) + "\n"


def main() -> None:
    DESTINO.write_text(serializar(construir_notebook()), encoding="utf-8")
    print(f"Escrito {DESTINO.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
