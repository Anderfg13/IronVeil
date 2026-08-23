#!/bin/sh
# Descarga el modelo base y construye los modelos personalizados "soporte"
# y "rrhh" sustituyendo los placeholders de los Modelfile por las variables
# de entorno (nunca credenciales en texto plano dentro del repositorio).
set -e

: "${OLLAMA_HOST:?OLLAMA_HOST no esta definido}"
: "${BASE_MODEL:?BASE_MODEL no esta definido}"
: "${SPT_SECRET:?SPT_SECRET no esta definido}"
: "${RRHH_SECRET:?RRHH_SECRET no esta definido}"

echo "Descargando modelo base: ${BASE_MODEL}"
ollama pull "${BASE_MODEL}"

TMP_DIR=$(mktemp -d)

sed "s|\${BASE_MODEL}|${BASE_MODEL}|g; s|\${SPT_SECRET}|${SPT_SECRET}|g" \
  /modelfiles/Modelfile.soporte.template > "${TMP_DIR}/Modelfile.soporte"

sed "s|\${BASE_MODEL}|${BASE_MODEL}|g; s|\${RRHH_SECRET}|${RRHH_SECRET}|g" \
  /modelfiles/Modelfile.rrhh.template > "${TMP_DIR}/Modelfile.rrhh"

echo "Creando modelo 'soporte'..."
ollama create soporte -f "${TMP_DIR}/Modelfile.soporte"

echo "Creando modelo 'rrhh'..."
ollama create rrhh -f "${TMP_DIR}/Modelfile.rrhh"

echo "Modelos creados correctamente."
