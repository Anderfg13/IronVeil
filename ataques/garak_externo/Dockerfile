# Garak (NVIDIA) en su propia imagen: escaner de vulnerabilidades de LLMs usado como
# validacion EXTERNA del proxy (extension, no parte del nucleo; docs/GARAK.md).
#
# Aislado a proposito: instala muchas dependencias (torch, transformers...) que no deben
# mezclarse con el Python del equipo ni con la imagen del proxy. Version EXACTA fijada
# (CLAUDE.md, seccion 7). torch CPU: no hay GPU en esta imagen y la variante CUDA pesa GBs.
#
# Construir (desde la raiz del repo):
#   docker build -t ironveil-garak ataques/garak_externo
FROM python:3.12-slim

ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

RUN pip install --extra-index-url https://download.pytorch.org/whl/cpu garak==0.17.0

# Usuario sin privilegios; el HOME es donde garak deja su configuracion y cache.
RUN useradd --create-home --uid 1000 --shell /usr/sbin/nologin garak
USER garak
WORKDIR /home/garak

# El generador que habla con el proxy se monta como volumen (no se copia): ver
# ataques/garak_externo/ejecutar_garak.py.
ENV PYTHONPATH=/home/garak/ironveil
ENTRYPOINT ["garak"]
