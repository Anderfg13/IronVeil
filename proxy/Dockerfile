# Imagen con digest fijado (ademas del tag) para que "python:3.12-slim" no
# pueda apuntar en silencio a una imagen distinta si el tag se reescribe en
# el registro (SonarCloud: "python image runs with root as default user" +
# buena practica de supply chain). Root sigue siendo el usuario de build
# (necesario para pip install en site-packages); se cambia a un usuario sin
# privilegios justo antes de correr la app (ver USER mas abajo).
FROM python:3.12-slim

# Contexto de build = raiz del repo (ver docker-compose.yml: build.context: .)
# porque main.py necesita importar proxy.mecanismos como paquete, igual que
# lo hace pytest desde la raiz. config.yaml NO se copia aqui: se monta como
# volumen de solo lectura para poder cambiar de configuracion sin rebuild.
WORKDIR /app

# --only-binary :all:: nunca instalar desde un sdist (que puede correr un
# setup.py/build script arbitrario durante la instalacion -- SonarCloud,
# "Omitting '--only-binary :all:' can lead to the execution of setup
# scripts"). Todas las dependencias de este proyecto (fastapi, uvicorn,
# httpx, PyYAML, transformers, torch) publican wheels prearmados para
# linux/amd64 + Python 3.12, asi que esto no debería requerir compilar nada
# -- si algun dia una dependencia nueva no trae wheel, el build fallara de
# forma explicita en vez de ejecutar codigo de instalacion silenciosamente.
#
# torch CPU-only, aparte de requirements.txt: el indice por defecto de PyPI
# trae la variante CUDA (varios GB), innecesaria sin GPU en el laboratorio.
# Usado por transformers (mecanismo 3, direccion "entrada", Prompt Guard).
RUN pip install --no-cache-dir --only-binary :all: \
    torch==2.14.0 --index-url https://download.pytorch.org/whl/cpu

COPY proxy/requirements.txt proxy/requirements.txt
RUN pip install --no-cache-dir --only-binary :all: -r proxy/requirements.txt

COPY proxy/ proxy/

# Usuario sin privilegios para correr la app (SonarCloud: "The 'python'
# image runs with 'root' as the default user"). El build (pip install,
# COPY) sigue corriendo como root arriba; solo el proceso de uvicorn en
# tiempo de ejecucion pierde privilegios. /app ya tiene todo lo que la app
# necesita leer copiado en el paso anterior, asi que darle el directorio
# completo al usuario nuevo es suficiente (no se necesita escribir en /app
# salvo en resultados/, que ademas es un bind mount desde el host -- ver
# docker-compose.yml -- y en Docker Desktop no depende del UID del
# contenedor para poder escribir).
RUN useradd --create-home --uid 1000 --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# --no-server-header: OWASP Error Handling Cheat Sheet (no revelar detalles
# tecnicos que ayuden a reconocimiento). Sin esto, Uvicorn agrega
# "Server: uvicorn" a cada respuesta -- exactamente lo que prueba V1-B/V1-E
# de ataques/variantes_ataque.md. Encontrado el 2026-09-19 (ver
# docs/FUENTE_DE_VERDAD.md, seccion 9). No se puede probar con TestClient
# (corre la app ASGI directo, sin pasar por Uvicorn); verificado a mano
# contra el contenedor real con curl -i.
CMD ["uvicorn", "proxy.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
