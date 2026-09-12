FROM python:3.12-slim

# Contexto de build = raiz del repo (ver docker-compose.yml: build.context: .)
# porque main.py necesita importar proxy.mecanismos como paquete, igual que
# lo hace pytest desde la raiz. config.yaml NO se copia aqui: se monta como
# volumen de solo lectura para poder cambiar de configuracion sin rebuild.
WORKDIR /app

COPY proxy/requirements.txt proxy/requirements.txt
RUN pip install --no-cache-dir -r proxy/requirements.txt

COPY proxy/ proxy/

EXPOSE 8000

CMD ["uvicorn", "proxy.main:app", "--host", "0.0.0.0", "--port", "8000"]
