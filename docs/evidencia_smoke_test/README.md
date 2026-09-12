# Evidencia — smoke test de Garak y Promptfoo

Prueba de humo de las dos herramientas de ataque antes de que el entorno
Docker del equipo (Ollama + proxy) estuviera listo. Ejecutada contra un
Ollama **instalado localmente por mí** (`deepseek-coder:latest`, ya
presente en la máquina) — no contra el stack del equipo ni contra los
modelos reales "soporte"/"rrhh", y no contra ningún servidor de terceros.

## Promptfoo

- Config: [`../../ataques/promptfooconfig.yaml`](../../ataques/promptfooconfig.yaml)
- Comando: `npx promptfoo@0.120.19 eval -c ataques/promptfooconfig.yaml --no-cache -o docs/evidencia_smoke_test/promptfoo_resultado.json`
- Resultado: `docs/evidencia_smoke_test/promptfoo_log.txt` — **2 passed, 0 failed, 0 errors (100%)**
- **Nota de version:** `promptfoo@latest` (0.122.1 al momento de escribir esto)
  exige Node >=22.22.0; esta máquina tiene v22.15.0. Se fijó `0.120.19`
  (requiere Node >=20.0.0) para que corriera. Si alguien del equipo tiene
  Node más reciente, `promptfoo@latest` también debería funcionar sin
  cambios al config.

## Garak

- Comando: `python -m garak --model_type ollama.OllamaGeneratorChat --model_name deepseek-coder --probes test.Test`
- Resultado: `docs/evidencia_smoke_test/garak_log.txt` — **always.Pass: PASS ok on 40/40**, `garak run complete in 188.66s`
- `test.Test` es el probe mínimo de garak para verificar que el generador
  habla correctamente con el modelo (no dispara payloads de ataque reales;
  eso se hace la semana que el proxy esté listo, con probes específicos
  por vector).
- **Nota de instalación (Windows):** `pip install garak` directo en el
  Python del sistema falló con `WinError 206` (ruta demasiado larga) por
  la profundidad de carpetas de una dependencia de `torch`. Se resolvió
  creando un venv en una ruta corta (`D:\ivenv`) fuera del árbol del
  repo y instalando ahí. Si a alguien más del equipo le pasa lo mismo en
  Windows, la solución es esa (o activar rutas largas de Windows, que no
  se hizo aquí por no tocar configuración del sistema sin acordarlo antes
  con el equipo).
- Requiere además el paquete `ollama` (cliente Python), instalado aparte
  del paquete `garak` (dependencia opcional del generador de Ollama).

## Próxima semana

Cuando el proxy y los modelos reales estén arriba, este smoke test se
reemplaza por corridas reales contra `soporte`/`rrhh` a través del proxy
(`http://localhost:8000/chat`), usando las variantes de
`ataques/variantes_ataque.md` como probes/payloads.
