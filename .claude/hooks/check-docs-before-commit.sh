#!/usr/bin/env bash
# Hook PreToolUse (matcher Bash, filtro "Bash(git commit*)"): antes de un
# "git commit", revisa si el conjunto de archivos en stage toca rutas de
# codigo/experimento relevantes sin tocar tambien la documentacion viva
# del proyecto (README.md / docs/FUENTE_DE_VERDAD.md). Si es asi, bloquea
# el commit y le pide a Claude que agregue una entrada corta antes de
# reintentar. Objetivo: que README.md y FUENTE_DE_VERDAD.md queden al dia
# solos, sin depender de que cada integrante se acuerde de actualizarlos.
#
# Sin dependencias externas (ni jq ni python): solo bash + git + grep,
# que ya son requisito del proyecto. No lee el JSON de stdin porque no lo
# necesita: el filtro "if" del hook ya garantiza que esto corre justo
# antes de un git commit.

set -u

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"
[ -z "$REPO_ROOT" ] && exit 0

STAGED=$(git -C "$REPO_ROOT" diff --cached --name-only 2>/dev/null)
[ -z "$STAGED" ] && exit 0

RUTA_RELEVANTE='^(proxy/|tests/|ollama/|docs/|ataques/|docker-compose\.yml$|config\.yaml$)'

toca_relevante=false
toca_docs=false

while IFS= read -r archivo; do
  [ -z "$archivo" ] && continue
  if echo "$archivo" | grep -qE "$RUTA_RELEVANTE"; then
    toca_relevante=true
  fi
  case "$archivo" in
    README.md|docs/FUENTE_DE_VERDAD.md)
      toca_docs=true
      ;;
  esac
done <<< "$STAGED"

if [ "$toca_relevante" = true ] && [ "$toca_docs" = false ]; then
  cat <<'JSON'
{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"Este commit toca proxy/, tests/, ollama/, docs/, ataques/, docker-compose.yml o config.yaml, pero no README.md ni docs/FUENTE_DE_VERDAD.md. Antes de reintentar: 1) agrega una linea corta a la seccion Estado actual de README.md, o una fila a la seccion 9 Registro de cambios de docs/FUENTE_DE_VERDAD.md, describiendo este cambio; 2) haz git add de esos archivos junto con lo demas que ya estaba en stage; 3) reintenta el commit."}}
JSON
  exit 0
fi

exit 0
