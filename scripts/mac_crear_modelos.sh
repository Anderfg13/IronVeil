#!/bin/sh
# Crea en el Ollama NATIVO de la Mac los modelos del proyecto (soporte, rrhh, rrhh-agente) y descarga el
# modelo base y el clasificador. Es el equivalente de ollama/init.sh, pero fuera de Docker.
#
# Uso, desde la raiz del repo, con Ollama abierto y .env ya creado (cp .env.example .env):
#   sh scripts/mac_crear_modelos.sh
#
# Lee BASE_MODEL, SPT_SECRET, RRHH_SECRET y MODELO_CLASIFICADOR de .env. Las credenciales son los
# canarios FICTICIOS del proyecto; no se escriben en ningun archivo del repositorio.
set -e

[ -f .env ] || { echo "Falta .env: ejecuta primero 'cp .env.example .env'"; exit 1; }
command -v ollama >/dev/null 2>&1 || { echo "Falta Ollama: instalalo desde https://ollama.com/download y abrelo"; exit 1; }

leer() { grep -E "^$1=" .env | tail -n 1 | cut -d= -f2-; }
BASE_MODEL=$(leer BASE_MODEL);   BASE_MODEL=${BASE_MODEL:-llama3.2}
SPT_SECRET=$(leer SPT_SECRET);   RRHH_SECRET=$(leer RRHH_SECRET)
MODELO_CLASIFICADOR=$(leer MODELO_CLASIFICADOR); MODELO_CLASIFICADOR=${MODELO_CLASIFICADOR:-llama-guard3:1b}
[ -n "$SPT_SECRET" ] && [ -n "$RRHH_SECRET" ] || { echo "SPT_SECRET o RRHH_SECRET vacios en .env"; exit 1; }

echo "Descargando modelo base: $BASE_MODEL"
ollama pull "$BASE_MODEL"
echo "Descargando clasificador de salida: $MODELO_CLASIFICADOR"
ollama pull "$MODELO_CLASIFICADOR"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
M=ollama/modelfiles

sed "s|\${BASE_MODEL}|$BASE_MODEL|g; s|\${SPT_SECRET}|$SPT_SECRET|g"     "$M/Modelfile.soporte.template"      > "$TMP/soporte"
sed "s|\${BASE_MODEL}|$BASE_MODEL|g; s|\${RRHH_SECRET}|$RRHH_SECRET|g"   "$M/Modelfile.rrhh.template"         > "$TMP/rrhh"
sed "s|\${BASE_MODEL}|$BASE_MODEL|g; s|\${RRHH_SECRET}|$RRHH_SECRET|g"   "$M/Modelfile.rrhh_agente.template"  > "$TMP/rrhh_agente"

echo "Creando 'soporte'...";      ollama create soporte -f "$TMP/soporte"
echo "Creando 'rrhh'...";         ollama create rrhh -f "$TMP/rrhh"
echo "Creando 'rrhh-agente'..."; ollama create rrhh-agente -f "$TMP/rrhh_agente"
echo "Listo. Comprueba con: ollama list"
