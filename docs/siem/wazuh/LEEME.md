# Wazuh con IronVeil (extensión opcional, SIEM)

Cómo exportar los eventos del log de IronVeil a Wazuh y verificar que los
ingiere. **No es parte del núcleo del experimento** y el proxy aún no envía
nada a Wazuh por su cuenta: `exportar_a_siem()` (`proxy/siem.py`) es una
función pura y el envío se hace hoy por lotes (ver abajo).

## ⚠ Requisitos de recursos (leer antes de levantarlo)

Wazuh es **mucho más pesado que el resto del stack del proyecto**. Medido el
2026-10-02 en un equipo con 8 hilos y Docker Desktop (WSL2) con 8,7 GiB de RAM
asignada, v4.14.8 single-node:

| Concepto | Documentación oficial (mínimo) | Medido, stack en reposo |
|---|---|---|
| RAM | 8 GB para el stack single-node | indexer 1,4 GiB + manager 0,6 GiB + dashboard 0,2 GiB ≈ **2,2 GiB** (más el arranque, que es mucho mayor) |
| CPU | 4 núcleos | 8 hilos disponibles; pico alto en los primeros ~2 min |
| Disco | 50 GB | **≈ 7,8 GB de imágenes** a descargar (manager 2,65 + indexer 2,56 + dashboard 2,14 + generador de certificados 0,44) más volúmenes |
| Kernel | `vm.max_map_count ≥ 262144` | obligatorio, si no el indexer no arranca |

Si tu máquina tiene 8 GB de RAM **en total**, no lo levantes: se quedará sin
memoria junto a Ollama (que ya es lo más pesado del proyecto). Tarda ~1–2
minutos en estar listo tras `docker compose up -d`.

## Qué se exporta

`exportar_a_siem(evento)` devuelve una línea JSON por evento:

- Conserva los nombres del esquema del log (`resultado`, `vector_probado`,
  `configuracion`, …): en Wazuh son `data.resultado`, `data.vector_probado`…
- `mecanismos_activos` (lista) pasa a una cadena separada por comas.
- Los valores `null` se **omiten**: verificado con `wazuh-logtest` que Wazuh
  los convierte en la cadena `"null"`.
- Se añade `integration: "ironveil"`, que es lo que reconocen las reglas.

`exportar_a_siem(evento, "cef")` devuelve una línea CEF:0 para otros SIEM
(severidad: bloqueado 5, exitoso_para_atacante 9, permitido_normal 1).

## Reglas de IronVeil (`ironveil_rules.xml`)

Wazuh no deduce la gravedad del evento: la fija una regla.

| Regla | Nivel | Cuándo |
|---|---|---|
| 100100 | 3 | cualquier evento de IronVeil |
| 100101 | 5 | `resultado = bloqueado` |
| 100102 | 12 | `resultado = exitoso_para_atacante` |
| 100103 | 8 | solicitud de herramienta simulada en la cola de aprobación humana (extensión V7) |
| 100104 | 10 | 5 o más bloqueos del mismo `vector_probado` en 60 s |

## Despliegue (oficial: <https://documentation.wazuh.com/current/deployment-options/docker/wazuh-container.html>)

```bash
# 1. Una sola vez (Linux). En Docker Desktop/WSL2:
#    wsl -d docker-desktop sysctl -w vm.max_map_count=262144
sudo sysctl -w vm.max_map_count=262144

# 2. Clonar la versión oficial FUERA de este repo
git clone https://github.com/wazuh/wazuh-docker.git -b v4.14.8
cd wazuh-docker/single-node

# 3. Certificados
docker compose -f generate-indexer-certs.yml run --rm generator

# 4. Archivos de IronVeil (rutas desde la raíz del repo de IronVeil)
cp <IronVeil>/docs/siem/wazuh/ironveil_rules.xml .
cp <IronVeil>/docs/siem/wazuh/docker-compose.override.yml .
mkdir -p ironveil_logs && touch ironveil_logs/ironveil.json
# y pegar el bloque de localfile_ironveil.xml dentro de un <ossec_config> de
# config/wazuh_cluster/wazuh_manager.conf (basta añadirlo al final entre
# <ossec_config> y </ossec_config>)

# 5. Levantar
docker compose up -d
```

El panel queda en `https://localhost` con las credenciales **por defecto** del
repo oficial (están en su `docker-compose.yml`). Son públicas: sirven solo para
un laboratorio local y no deben exponerse fuera de tu máquina.

## Probar la ingesta

```bash
# Lote sintético (marcado "sintetico": true; NO es evidencia del experimento)
python analisis/exportar_lote_siem.py --ejemplo --salida docs/siem/exportados/ironveil_wazuh.json
# o eventos reales del proxy, sin modificarlos:
python analisis/exportar_lote_siem.py --entrada resultados/<fecha>/eventos.jsonl

# Entregar el lote al manager (carpeta montada)
cat docs/siem/exportados/ironveil_wazuh.json >> <wazuh-docker>/single-node/ironveil_logs/ironveil.json

# Ver las alertas generadas (en Git Bash anteponer MSYS_NO_PATHCONV=1)
docker exec single-node-wazuh.manager-1 grep ironveil /var/ossec/logs/alerts/alerts.json
# Probar una línea sin generar alerta:
echo '<una línea del lote>' | docker exec -i single-node-wazuh.manager-1 /var/ossec/bin/wazuh-logtest
```

## Apagar

```bash
docker compose down        # conserva imágenes y datos
docker compose down -v     # además borra los volúmenes de Wazuh
```

## Qué se verificó (2026-10-02) y qué no

Verificado, Wazuh 4.14.8 single-node con Docker: un lote de 7 eventos
sintéticos (uno por resultado posible, más V7 y V4 paso 2) produjo
**7 alertas** del manager con la regla y el nivel esperados, y 6 bloqueos
seguidos del mismo vector disparan la regla de ráfaga 100104.

**No verificado:** la entrega por agente remoto ni por syslog/CEF (CEF solo
está probado con tests unitarios de formato, no contra un colector real), ni
la visualización de las alertas en el panel (se comprobó en el
`alerts.json` del manager, no en el dashboard, para no usar las credenciales
por defecto desde un navegador).
