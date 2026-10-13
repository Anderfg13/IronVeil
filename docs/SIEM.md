# Conectar IronVeil a un SIEM

IronVeil exporta cada evento de `/chat` a **uno o varios SIEM**, además de escribir el dataset del
experimento (que no se toca: `resultados/<fecha>/eventos.jsonl` sigue siendo la evidencia cruda).
Es una **extensión opcional**: apagada salvo que definas `SIEM_DESTINOS` (o la forma histórica
`SIEM_ARCHIVO_WAZUH`).

Dos garantías que no cambian con ningún SIEM:

- **Un SIEM caído nunca frena ni rompe `/chat`.** Los destinos de red se entregan en un hilo aparte,
  con reintentos; si la cola se llena se descartan los eventos más nuevos y se cuentan. El dataset
  del experimento no se ve afectado: se escribe antes y aparte.
- **Los mensajes de error y los logs nunca llevan claves, tokens ni el contenido del evento.**

## Cómo se configura

Una variable, una lista separada por comas de destinos:

```
SIEM_DESTINOS=[formato@]esquema://destino,[formato@]esquema://destino
```

El **formato** (cómo se escribe el evento) y el **transporte** (por dónde viaja) son piezas
**independientes** y se combinan libremente: `cef@syslog+tls://…`, `ecs@elastic://…`,
`leef@syslog+tcp://…`. Si omites el formato se usa el que mejor le va al transporte.

| Formato | Qué es | Lo entienden |
|---|---|---|
| `json` | JSON plano de una línea (con `integration: "ironveil"`, sin nulos) | Wazuh, Splunk, Sentinel, Graylog, cualquiera que lea JSON |
| `cef` | ArcSight Common Event Format | Sentinel, Splunk, QRadar, ArcSight, Graylog… |
| `leef` | IBM LEEF 1.0 | QRadar |
| `ecs` | Elastic Common Schema (campos propios bajo `ironveil.*`) | Elasticsearch, OpenSearch, Security Onion |

| Esquema | Destino | Formato por defecto | Credenciales (en `.env`) |
|---|---|---|---|
| `archivo` | `archivo:///ruta/dentro/del/contenedor.jsonl` | `json` | — |
| `syslog+udp` / `syslog+tcp` | `host[:puerto]` (514) | `cef` | — |
| `syslog+tls` | `host[:puerto]` (6514) | `cef` | `SIEM_CA_ARCHIVO` solo si usas una CA propia |
| `https` | `host/ruta` (un webhook) | `json` | `SIEM_HTTPS_TOKEN` (opcional, va como portador) |
| `splunk` | `host[:puerto]` (8088, HEC) | `json` | `SIEM_SPLUNK_TOKEN` |
| `elastic` | `host[:puerto]/indice` (9200) | `ecs` | `SIEM_ELASTIC_API_KEY`, o `SIEM_ELASTIC_USUARIO` + `SIEM_ELASTIC_CLAVE` |
| `azure-logs` | `host/id-del-DCR/nombre-del-stream` | `json` | `SIEM_AZURE_TENANT_ID`, `_CLIENT_ID`, `_CLIENT_SECRET` |
| `aws-cloudwatch` | `region/grupo/flujo` (el grupo con `%2F` por cada `/`) | `json` | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` (y `AWS_SESSION_TOKEN` si son temporales) |

**Las credenciales van solo en `.env`, nunca dentro de la URL** (una URL con `usuario:clave@` se
rechaza). Todo lo que viaja por HTTPS verifica el certificado y no sigue redirecciones.

## Tu SIEM → qué poner

| SIEM | Configuración | Notas |
|---|---|---|
| **Wazuh** (open source) | `SIEM_DESTINOS=json@archivo:///app/siem/ironveil.json` (o `SIEM_ARCHIVO_WAZUH`) | Validado contra un Wazuh 4.14.8 real: `docs/siem/wazuh/`. También sirve `cef@syslog+tcp://…` si abres un receptor syslog. |
| **Graylog** (open source) | `cef@syslog+tcp://graylog:514` | Entrada Syslog TCP de Graylog. |
| **Security Onion / Elastic / OpenSearch** | `ecs@elastic://es:9200/ironveil` | Siempre por HTTPS. Para OpenSearch usa usuario y clave. |
| **Splunk** | `splunk://splunk:8088` | HTTP Event Collector, endpoint `raw`. |
| **Microsoft Sentinel / Azure Monitor** | `azure-logs://<dce>/<dcr-id>/Custom-IronVeil` | Necesitas una app de Entra ID con el rol *Monitoring Metrics Publisher* sobre el DCR y un DCR cuyo stream acepte el JSON (o lo transforme con KQL). Alternativa sin API: `cef@syslog+tcp` hacia el agente de Azure Monitor. |
| **AWS CloudWatch Logs** | `aws-cloudwatch://us-east-1/%2Fironveil%2Fproxy/principal` | El grupo y el flujo deben existir. Claves de un usuario IAM con `logs:PutLogEvents`. |
| **IBM QRadar** | `leef@syslog+tcp://qradar:514` (o `cef@…`) | |
| **ArcSight** | `cef@syslog+tcp://arcsight:514` | |
| **Cualquier otro** (Datadog, Google SecOps, Sumo…) | `https://…` si recibe un POST con un token, o un adaptador propio (abajo) | |

> Para que el archivo llegue al agente del SIEM, `docker-compose.yml` monta `./docs/siem/exportados`
> como `/app/siem`. Un agente (Wazuh, Filebeat, el agente de Azure Monitor o el de CloudWatch) puede
> leer ese archivo en vez de usar un transporte de red: es el camino que menos puede fallar.

## Cómo se entrega

- `archivo`: síncrono (un `append` local, sin red), con su propio *lock*.
- Todo lo demás (red): `enviar()` solo **encola**; un hilo aparte entrega con hasta 3 intentos y
  espera exponencial. No se reintenta lo que no puede cambiar (una clave rechazada, una petición
  mal formada: HTTP 400/401/403) sino solo lo transitorio (red, 408, 429, 5xx).
- Cola de 1000 eventos por destino. Si el SIEM lleva rato caído y se llena, se **descarta el más
  nuevo** y se avisa en el log (`cola llena, N evento(s) descartado(s)`). Al apagar el proxy se
  entrega lo pendiente.
- Cada destino está **aislado**: si Splunk falla, Wazuh recibe el evento igual.
- Un destino mal configurado (falta una variable, host inválido) se **omite con un error claro**
  que dice qué falta (el nombre de la variable, nunca su valor); los demás siguen.
- Al arrancar, el log del proxy dice a qué destinos exporta.

## Agregar tu propio SIEM sin editar IronVeil

Un módulo tuyo expone `registrar(registro)` y se lista en `SIEM_ADAPTADORES`:

```python
# mi_empresa/ironveil_datadog.py
from proxy.siem import ErrorSIEM

class FormatoMio:
    tipo_contenido = "application/json"

    def formatear(self, evento: dict) -> str:           # el contrato del formato
        ...

class ConectorDatadog:
    def __init__(self, destino: str, contexto) -> None:  # contexto.entorno trae tus claves
        ...

    def enviar(self, mensaje: str) -> None:              # el contrato del transporte
        ...  # si falla: raise ErrorSIEM("sin claves ni contenido", reintentable=...)

    def cerrar(self) -> None:                            # opcional: libera un socket o cliente
        ...

def registrar(registro) -> None:
    registro.registrar_formato("mio", FormatoMio)
    registro.registrar_conector(
        "datadog", ConectorDatadog, formato_por_defecto="mio", de_red=True
    )
```

```
SIEM_ADAPTADORES=mi_empresa.ironveil_datadog
SIEM_DESTINOS=datadog://api.datadoghq.com
```

Reglas del contrato:

- Cualquier fallo se lanza como **`ErrorSIEM`** (traduce la excepción de tu controlador). El mensaje
  no puede llevar claves, la URL con identificadores ni el evento.
- `de_red=True` hace que se entregue en un hilo aparte (recomendado para todo lo que use red).
- **No leas `os.environ`**: tus claves llegan en `contexto.entorno` (las variables `SIEM_*` y
  `AWS_*`; usa un prefijo `SIEM_<TU_SIEM>_` para las tuyas).
- El módulo **se importa y se ejecuta con los permisos del proxy**: solo código de confianza. Solo
  se aceptan nombres de módulo (nada de rutas). Que sea importable dentro del contenedor (instalarlo
  en la imagen o montarlo) lo resuelve quien despliega.

## Qué se verificó y qué no

**Verificado** (pruebas automáticas; la suite completa pasa de 1450 pruebas):
- Los cuatro formatos y su escape (CEF, LEEF, ECS, JSON). El JSON de Wazuh, además, contra un Wazuh
  real (`docs/siem/wazuh/VALIDACION_FORMATO.md`).
- La **firma AWS SigV4** coincide con el vector de pruebas publicado por AWS.
- Syslog por **UDP y TCP con sockets reales** (en Windows y dentro de la imagen Docker, Python 3.12):
  el mensaje RFC 5424 llega entero. TLS **no cae a texto claro** si el servidor no habla TLS.
- La **forma de cada petición HTTPS** (URL, cabeceras, cuerpo) de Splunk, Elastic, Azure y CloudWatch,
  contra un servidor falso y contrastada con la documentación oficial de cada uno (Azure: URL, arreglo
  JSON, `Content-Type`; CloudWatch: `PutLogEvents`, `X-Amz-Target`; Splunk: endpoint `raw` y canal).
- El token de Azure se cachea y se renueva antes de caducar.

**No verificado** (no hay cuenta ni servidor para hacerlo; **no lo des por probado**):
- Contra una cuenta **real** de Azure, AWS, Splunk, Elastic o QRadar.
- LEEF en QRadar y CEF en Sentinel (el formato sigue la especificación; no se ingirió en esos productos).
- Syslog por TLS con un certificado válido (solo se probó que no se degrada a texto claro).

## Límites conocidos

- **UDP no garantiza la entrega** (es el protocolo, no IronVeil). Usa TCP o TLS si importa no perder eventos.
- **Syslog por TCP/TLS** usa salto de línea entre mensajes (encuadre no transparente), el habitual; no
  el de conteo de octetos. Solo IPv4 y nombres DNS (no literales IPv6).
- **CloudWatch**: claves estáticas de un usuario IAM; los roles de instancia / IAM Identity Center
  no se resuelven (haría falta el SDK completo, que no se agregó para no sumar una dependencia pesada).
  **Security Lake** no está cubierto: recibe OCSF en Parquet por S3, otro tipo de integración.
- Un evento por petición HTTP (sin lotes): suficiente para este tráfico; un SIEM con límites de
  tasa estrictos pediría agrupar.
- Un solo juego de credenciales por tipo de destino (dos Splunk distintos compartirían token).
- La memoria de eventos pendientes es solo en proceso: si el proxy se apaga con el SIEM caído, lo
  que no se entregó se pierde (el dataset sí conserva todo).
