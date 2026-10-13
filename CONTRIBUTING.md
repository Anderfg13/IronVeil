# Cómo contribuir a IronVeil

IronVeil es un trabajo académico de seminario, mantenido por cuatro personas. Las contribuciones externas se
agradecen, pero el proyecto tiene un **alcance cerrado** (un experimento con 5 mecanismos, 7 configuraciones y 5
vectores): antes de abrir un cambio grande, abre un *issue* y lo conversamos.

## Reglas que no se negocian

1. **Laboratorio aislado.** Todo ataque, escaneo o prueba de carga va **solo** contra el stack propio en
   `localhost`/Docker. Nunca contra servidores de terceros.
2. **Credenciales ficticias.** Los canarios (`SPT-DEMO-*`, `RRHH-DEMO-*`) viven en `.env`/Modelfiles, no en el código
   ni en los tests. Nunca subas claves reales.
3. **Los datos crudos no se editan** (`resultados/**/eventos.jsonl`, `resultados_template.csv`). Se transforman con
   scripts reproducibles.
4. **No se fuerzan resultados.** Si un mecanismo funciona peor de lo esperado, se reporta tal cual, con su intervalo.

El detalle completo (contratos estables, esquema de log, principios de diseño) está en [`CLAUDE.md`](CLAUDE.md).

## Flujo de trabajo

```bash
git checkout develop && git pull
git checkout -b feat/mi-cambio          # ramas para trabajo exploratorio
pip install -r requirements-dev.txt
pytest                                   # la suite debe correr sin el stack levantado
ruff check . && black .
```

- Commits atómicos con prefijo: `feat:`, `fix:`, `test:`, `docs:`, `refactor:`, `chore:`.
- Los PR van a `develop`; `main` solo recibe fusiones con las pruebas en verde. Nada de `--force` sobre `main`.
- Usa la [plantilla de PR](.github/PULL_REQUEST_TEMPLATE.md).

## Qué se espera de un cambio

- **Pruebas** en el mismo commit: caso que bloquea, caso legítimo que no debe bloquearse y caso de error/timeout.
- **Type hints** en todas las funciones y docstrings en las públicas. Nada de `print()` fuera de scripts de demo.
- **Principios SOLID** y código limpio; el patrón de referencia es `proxy/siem/` y `proxy/memoria_decisiones/`
  (puertos y adaptadores, un solo lugar que lee el entorno).
- Si cambias un contrato compartido (firma en `mecanismos.py`, campo del log, columna del CSV), avisa y actualiza
  `CLAUDE.md` en el mismo commit.
- Cada cambio de comportamiento o resultado deja una fila fechada en
  [`docs/FUENTE_DE_VERDAD.md`](docs/FUENTE_DE_VERDAD.md), con sus límites y lo que **no** se verificó.

## Seguridad del código

Sin credenciales hardcodeadas, `yaml.safe_load()` siempre, sin `subprocess(shell=True)` con entrada externa, TLS
siempre verificado y rutas de la línea de comandos validadas con `analisis/rutas.py`. Si encuentras una vulnerabilidad,
sigue [`SECURITY.md`](SECURITY.md) en vez de abrir un *issue* público.
