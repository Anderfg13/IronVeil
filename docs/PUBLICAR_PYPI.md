# Publicar IronVeil en PyPI (opcional)

El paquete se llama **`ironveil`** (el nombre estaba libre al revisarlo) y se importa como `proxy` (así lo usa todo el repo).
Instala el comando `ironveil`:

```bash
pip install ironveil                  # o: pip install "ironveil[prompt-guard]"  (suma PyTorch)
ironveil config C3                    # escribe ./config.yaml con la configuración C3
ironveil auth-demo                    # cuenta de demo "admin" con clave aleatoria
ironveil serve --puerto 8000          # lee ./config.yaml; resultados en ./resultados
```

El proxy necesita un Ollama alcanzable (`OLLAMA_BASE_URL`, por defecto `http://localhost:11434`) con los modelos `soporte` y
`rrhh`; el laboratorio completo con Docker sigue siendo el camino recomendado (README). El paquete **no** incluye los modelos.

## Preparación única (la hace una persona con acceso al repo y a PyPI)

1. Crea la cuenta en <https://pypi.org> y, en *Publishing → Add a new pending publisher*, registra:
   proyecto `ironveil`, propietario `Anderfg13`, repositorio `IronVeil`, workflow `pypi.yml`, entorno `pypi`.
   (Es *trusted publishing*: **no hay tokens ni claves en el repositorio**.)
2. En GitHub: *Settings → Environments → New environment* con el nombre `pypi` (conviene exigir aprobación manual).
3. Sube una etiqueta de versión que coincida con `version` de `pyproject.toml`:

   ```bash
   git tag -a v1.0.0 -m "IronVeil 1.0.0" && git push origin v1.0.0
   ```

   El workflow `.github/workflows/pypi.yml` construye, valida con `twine check` y publica.

## Antes de publicar, comprueba

- `python -m build && twine check dist/*` pasa (el job `paquete` de la CI ya lo hace en cada push).
- Los pines de `pyproject.toml` coinciden con `proxy/requirements.in`.
- Una versión publicada en PyPI **no se puede reemplazar**: si te equivocas, se sube la siguiente (`1.0.1`).

## Límites honestos

- El import se llama `proxy` (nombre genérico): puede chocar con otro paquete del mismo entorno. Instálalo en un entorno virtual.
- El paquete es el proxy y su CLI; los scripts de ataque (`ataques/`) y el análisis (`analisis/`) viven en el repositorio.
- Sigue siendo un trabajo académico validado en laboratorio, no un producto para producción.
