## Qué hace este PR

<!-- Descripción breve: qué cambia y por qué. -->

## Tipo de cambio

- [ ] `feat` — nueva funcionalidad
- [ ] `fix` — corrección de bug
- [ ] `test` — pruebas
- [ ] `docs` — documentación
- [ ] `refactor` — refactor sin cambio de comportamiento
- [ ] `chore` — mantenimiento (config, dependencias, etc.)

## Checklist antes de pedir revisión

- [ ] `pytest` pasa completo
- [ ] `ruff check .` y `black .` limpios
- [ ] Si cambié una firma en `mecanismos.py`, un campo del log o una columna del CSV, avisé al equipo y actualicé `CLAUDE.md` en este mismo PR
- [ ] Si agregué un mecanismo nuevo, incluí sus pruebas unitarias (caso bloqueo, caso falso positivo, caso timeout/error)
- [ ] Si resolví un conflicto de integración, quedó documentado en `CONFLICTOS_RESUELTOS.md`
- [ ] No hay credenciales (`SPT-DEMO-...`, `RRHH-DEMO-...`, tokens, etc.) hardcodeadas fuera de `.env` / Modelfiles

## Cómo se probó

<!-- Comandos ejecutados, configuración usada (C0–C6), evidencia relevante. -->

## Notas para quien revisa

<!-- Cualquier cosa que facilite la revisión: contexto, decisiones de diseño, dudas abiertas. -->
