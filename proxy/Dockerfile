FROM python:3.12-slim

# Contexto de build = raiz del repo (ver docker-compose.yml: build.context: .)
# porque main.py necesita importar proxy.mecanismos como paquete, igual que
# lo hace pytest desde la raiz. config.yaml NO se copia aqui: se monta como
# volumen de solo lectura para poder cambiar de configuracion sin rebuild.
WORKDIR /app

# torch CPU-only, aparte de requirements.txt: el indice por defecto de PyPI
# trae la variante CUDA (varios GB), innecesaria sin GPU en el laboratorio.
# Usado por transformers (mecanismo 3, direccion "entrada", Prompt Guard).
RUN pip install --no-cache-dir torch==2.14.0 --index-url https://download.pytorch.org/whl/cpu

COPY proxy/requirements.txt proxy/requirements.txt
RUN pip install --no-cache-dir -r proxy/requirements.txt

COPY proxy/ proxy/

EXPOSE 8000

# --no-server-header: OWASP Error Handling Cheat Sheet (no revelar detalles
# tecnicos que ayuden a reconocimiento). Sin esto, Uvicorn agrega
# "Server: uvicorn" a cada respuesta -- exactamente lo que prueba V1-B/V1-E
# de ataques/variantes_ataque.md. Encontrado el 2026-09-19 (ver
# docs/FUENTE_DE_VERDAD.md, seccion 9). No se puede probar con TestClient
# (corre la app ASGI directo, sin pasar por Uvicorn); verificado a mano
# contra el contenedor real con curl -i.
CMD ["uvicorn", "proxy.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
