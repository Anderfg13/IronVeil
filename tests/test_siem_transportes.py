"""Los transportes de red: syslog (UDP/TCP/TLS) con sockets reales en loopback, y
los SIEM por HTTPS (Splunk, Elastic, Azure Monitor, CloudWatch) con un servidor
falso en memoria.
"""

from __future__ import annotations

import json
import socket
import threading
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from urllib.parse import parse_qs

import httpx
import pytest

from proxy.siem import ErrorSIEM
from proxy.siem.registro import ContextoConector
from proxy.siem.transportes import aws, azure, elastic, https_generico, splunk
from proxy.siem.transportes.aws import ConectorCloudWatch, fabrica_cloudwatch
from proxy.siem.transportes.azure import ProveedorTokenAzure, fabrica_azure
from proxy.siem.transportes.elastic import fabrica_elastic
from proxy.siem.transportes.https_generico import ConectorHTTP, fabrica_https
from proxy.siem.transportes.sigv4 import CredencialesAWS
from proxy.siem.transportes.splunk import fabrica_splunk
from proxy.siem.transportes.syslog_red import (
    ConectorSyslog,
    envolver_rfc5424,
    fabrica_syslog,
)

INSTANTE = datetime(2026, 10, 6, 14, 30, 0, tzinfo=UTC)
# Valores claramente ficticios: no son ni se parecen a los canarios del proyecto.
CLAVE_DE_PRUEBA = "clave-ficticia-de-prueba"


# --- syslog -------------------------------------------------------------------


def test_el_mensaje_syslog_sigue_rfc5424() -> None:
    texto = envolver_rfc5424("hola", host="equipo", app="ironveil", instante=INSTANTE)

    assert texto == "<134>1 2026-10-06T14:30:00.000Z equipo ironveil - - - hola"


def test_un_salto_de_linea_no_parte_el_mensaje_syslog() -> None:
    texto = envolver_rfc5424("a\nb\r\nc", host="h", app="a", instante=INSTANTE)

    assert "\n" not in texto
    assert texto.endswith("a\\nb\\r\\nc")


def test_syslog_por_udp_entrega_un_datagrama_por_evento() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as servidor:
        servidor.bind(("127.0.0.1", 0))
        servidor.settimeout(2)
        conector = ConectorSyslog(
            "127.0.0.1",
            servidor.getsockname()[1],
            "udp",
            nombre_host="equipo",
            reloj=lambda: INSTANTE,
        )

        conector.enviar("CEF:0|IronVeil|x")
        datos, _ = servidor.recvfrom(4096)
        conector.cerrar()

    assert datos.decode() == (
        "<134>1 2026-10-06T14:30:00.000Z equipo ironveil - - - CEF:0|IronVeil|x"
    )


@pytest.fixture
def servidor_tcp() -> Iterator[tuple[int, list[bytes]]]:
    """Un colector TCP que acumula lo recibido por cada conexion."""
    escucha = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    escucha.bind(("127.0.0.1", 0))
    escucha.listen(5)
    escucha.settimeout(5)
    recibido: list[bytes] = []

    def atender() -> None:
        try:
            while True:
                conexion, _ = escucha.accept()
                with conexion:
                    conexion.settimeout(2)
                    try:
                        while datos := conexion.recv(4096):
                            recibido.append(datos)
                    except OSError:
                        pass
        except OSError:
            return  # el servidor se cerro

    hilo = threading.Thread(target=atender, daemon=True)
    hilo.start()
    yield escucha.getsockname()[1], recibido
    escucha.close()
    hilo.join(2)


def _esperar(condicion: Callable[[], bool], segundos: float = 3.0) -> bool:
    fin = datetime.now(UTC).timestamp() + segundos
    while datetime.now(UTC).timestamp() < fin:
        if condicion():
            return True
        threading.Event().wait(0.02)
    return False


def test_syslog_por_tcp_termina_cada_mensaje_en_salto_de_linea(
    servidor_tcp: tuple[int, list[bytes]],
) -> None:
    puerto, recibido = servidor_tcp
    conector = ConectorSyslog(
        "127.0.0.1", puerto, "tcp", nombre_host="equipo", reloj=lambda: INSTANTE
    )

    conector.enviar("uno")
    conector.enviar("dos")
    conector.cerrar()

    assert _esperar(lambda: b"".join(recibido).count(b"\n") == 2)
    lineas = b"".join(recibido).decode().splitlines()
    assert lineas[0].endswith("- - - uno")
    assert lineas[1].endswith("- - - dos")


def test_syslog_por_tcp_sin_servidor_falla_con_error_siem_reintentable() -> None:
    with socket.socket() as libre:
        libre.bind(("127.0.0.1", 0))
        puerto = libre.getsockname()[1]  # nadie escucha aqui

    conector = ConectorSyslog("127.0.0.1", puerto, "tcp", timeout=1)

    with pytest.raises(ErrorSIEM) as exc:
        conector.enviar("hola")

    assert exc.value.reintentable
    assert "syslog tcp" in str(exc.value)  # tipo del fallo segun el sistema operativo
    assert "127.0.0.1" not in str(exc.value)


def test_syslog_tls_contra_un_servidor_sin_tls_no_cae_a_texto_claro(
    servidor_tcp: tuple[int, list[bytes]],
) -> None:
    puerto, recibido = servidor_tcp
    conector = ConectorSyslog("127.0.0.1", puerto, "tls", timeout=1)

    with pytest.raises(ErrorSIEM):
        conector.enviar("secreto-que-no-debe-viajar-sin-cifrar")

    assert b"secreto" not in b"".join(recibido)


def test_un_protocolo_syslog_desconocido_se_rechaza() -> None:
    with pytest.raises(ErrorSIEM, match="protocolo"):
        ConectorSyslog("127.0.0.1", 514, "carrier-pigeon")  # type: ignore[arg-type]


def test_la_fabrica_syslog_usa_los_puertos_por_defecto() -> None:
    contexto = ContextoConector()

    assert isinstance(fabrica_syslog("udp")("127.0.0.1", contexto), ConectorSyslog)
    assert isinstance(fabrica_syslog("tls")("127.0.0.1:6514", contexto), ConectorSyslog)


@pytest.mark.parametrize("destino", ["", "host con espacios", "h:99999", "a@b:1", "/x"])
def test_la_fabrica_syslog_rechaza_hosts_invalidos(destino: str) -> None:
    with pytest.raises(ErrorSIEM):
        fabrica_syslog("tcp")(destino, ContextoConector())


def test_syslog_tls_con_una_ca_inexistente_falla_sin_desactivar_la_verificacion() -> (
    None
):
    contexto = ContextoConector(entorno={"SIEM_CA_ARCHIVO": "/no/existe.pem"})

    with pytest.raises(ErrorSIEM, match="SIEM_CA_ARCHIVO"):
        fabrica_syslog("tls")("127.0.0.1", contexto)


# --- HTTPS: servidor falso en memoria -----------------------------------------


class _Servidor:
    """Un SIEM falso: guarda las peticiones y responde lo que se le diga."""

    def __init__(self, estado: int = 200, cuerpo: object | None = None) -> None:
        self.peticiones: list[httpx.Request] = []
        self.estado = estado
        self.cuerpo = cuerpo if cuerpo is not None else {}

    def __call__(self, peticion: httpx.Request) -> httpx.Response:
        self.peticiones.append(peticion)
        return httpx.Response(self.estado, json=self.cuerpo)

    def cliente(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self))


@pytest.fixture
def servidor(monkeypatch: pytest.MonkeyPatch) -> _Servidor:
    """Hace que TODAS las fabricas de red hablen con el servidor falso."""
    falso = _Servidor()
    for modulo in (https_generico, splunk, elastic, azure, aws):
        if hasattr(modulo, "cliente_httpx"):
            monkeypatch.setattr(
                modulo, "cliente_httpx", lambda *a, **k: falso.cliente()
            )
    return falso


def _contexto(
    entorno: dict[str, str], tipo: str = "application/json"
) -> ContextoConector:
    return ContextoConector(entorno=entorno, tipo_contenido=tipo)


def test_https_sin_http_plano() -> None:
    with pytest.raises(ErrorSIEM, match="https"):
        ConectorHTTP("http://siem.local/x", nombre="X", tipo_contenido="text/plain")


def test_https_generico_envia_con_portador_si_hay_token(servidor: _Servidor) -> None:
    conector = fabrica_https(
        "siem.local/ingesta", _contexto({"SIEM_HTTPS_TOKEN": CLAVE_DE_PRUEBA})
    )

    conector.enviar('{"a":1}')

    peticion = servidor.peticiones[0]
    assert str(peticion.url) == "https://siem.local/ingesta"
    assert peticion.headers["Authorization"] == f"Bearer {CLAVE_DE_PRUEBA}"
    assert peticion.headers["Content-Type"] == "application/json"
    assert peticion.content == b'{"a":1}'


def test_https_generico_no_acepta_credenciales_dentro_de_la_url() -> None:
    with pytest.raises(ErrorSIEM, match="SIEM_HTTPS_TOKEN"):
        fabrica_https("usuario:clave@siem.local/x", _contexto({}))


def test_splunk_usa_el_endpoint_raw_con_token_y_canal(servidor: _Servidor) -> None:
    conector = fabrica_splunk(
        "splunk.local:8088", _contexto({"SIEM_SPLUNK_TOKEN": CLAVE_DE_PRUEBA})
    )

    conector.enviar("CEF:0|...")
    conector.enviar("CEF:0|otro")

    primera, segunda = servidor.peticiones
    assert primera.url.path == "/services/collector/raw"
    assert parse_qs(primera.url.query.decode()) == {"sourcetype": ["ironveil"]}
    assert primera.url.port == 8088
    assert primera.headers["Authorization"] == f"Splunk {CLAVE_DE_PRUEBA}"
    canal = primera.headers["X-Splunk-Request-Channel"]
    assert len(canal) == 36
    assert segunda.headers["X-Splunk-Request-Channel"] == canal  # estable
    assert primera.content == b"CEF:0|..."


def test_splunk_sin_token_dice_que_variable_falta() -> None:
    with pytest.raises(ErrorSIEM, match="SIEM_SPLUNK_TOKEN"):
        fabrica_splunk("splunk.local", _contexto({}))


def test_elastic_escribe_un_documento_por_evento_con_clave_de_api(
    servidor: _Servidor,
) -> None:
    conector = fabrica_elastic(
        "es.local:9200/ironveil-eventos",
        _contexto({"SIEM_ELASTIC_API_KEY": CLAVE_DE_PRUEBA}),
    )

    conector.enviar('{"@timestamp":"x"}')

    peticion = servidor.peticiones[0]
    assert peticion.method == "POST"
    assert str(peticion.url) == "https://es.local:9200/ironveil-eventos/_doc"
    assert peticion.headers["Authorization"] == f"ApiKey {CLAVE_DE_PRUEBA}"


def test_elastic_acepta_usuario_y_clave_como_autenticacion_basica(
    servidor: _Servidor,
) -> None:
    conector = fabrica_elastic(
        "os.local/idx",
        _contexto(
            {"SIEM_ELASTIC_USUARIO": "ana", "SIEM_ELASTIC_CLAVE": CLAVE_DE_PRUEBA}
        ),
    )

    conector.enviar("{}")

    assert servidor.peticiones[0].headers["Authorization"].startswith("Basic ")


@pytest.mark.parametrize(
    "destino", ["es.local", "es.local/", "es.local/MAYUSCULAS", "es.local/../x"]
)
def test_elastic_exige_un_indice_valido(destino: str) -> None:
    with pytest.raises(ErrorSIEM, match="indice"):
        fabrica_elastic(destino, _contexto({"SIEM_ELASTIC_API_KEY": CLAVE_DE_PRUEBA}))


def test_elastic_sin_credenciales_se_rechaza() -> None:
    with pytest.raises(ErrorSIEM, match="credenciales"):
        fabrica_elastic("es.local/idx", _contexto({}))


@pytest.mark.parametrize(
    ("estado", "reintentable"),
    [
        (500, True),
        (503, True),
        (429, True),
        (408, True),
        (400, False),
        (401, False),
        (403, False),
    ],
)
def test_solo_se_reintentan_los_estados_que_pueden_cambiar(
    estado: int, reintentable: bool
) -> None:
    servidor = _Servidor(estado=estado)
    conector = ConectorHTTP(
        "https://siem.local/x",
        nombre="X",
        tipo_contenido="text/plain",
        cliente=servidor.cliente(),
    )

    with pytest.raises(ErrorSIEM) as exc:
        conector.enviar("m")

    assert exc.value.reintentable is reintentable
    assert str(estado) in str(exc.value)


def test_un_error_de_red_se_traduce_sin_mostrar_la_url() -> None:
    def cae(peticion: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no hay ruta", request=peticion)

    conector = ConectorHTTP(
        "https://siem.local/secreto-en-la-ruta",
        nombre="X",
        tipo_contenido="text/plain",
        cliente=httpx.Client(transport=httpx.MockTransport(cae)),
    )

    with pytest.raises(ErrorSIEM) as exc:
        conector.enviar("m")

    assert exc.value.reintentable
    assert "secreto-en-la-ruta" not in str(exc.value)
    assert "ConnectError" in str(exc.value)


def test_un_cliente_ajeno_no_se_cierra_pero_uno_cedido_si() -> None:
    ajeno = httpx.Client(transport=httpx.MockTransport(_Servidor()))
    cedido = httpx.Client(transport=httpx.MockTransport(_Servidor()))

    ConectorHTTP("https://a/", nombre="A", tipo_contenido="t", cliente=ajeno).cerrar()
    ConectorHTTP(
        "https://a/",
        nombre="A",
        tipo_contenido="t",
        cliente=cedido,
        cliente_propio=True,
    ).cerrar()

    assert not ajeno.is_closed
    assert cedido.is_closed


# --- Azure Monitor ------------------------------------------------------------

ENTORNO_AZURE = {
    "SIEM_AZURE_TENANT_ID": "tenant-de-prueba",
    "SIEM_AZURE_CLIENT_ID": "cliente-de-prueba",
    "SIEM_AZURE_CLIENT_SECRET": CLAVE_DE_PRUEBA,
}


def _servidor_azure(token_estado: int = 200) -> _Servidor:
    """Responde al token en login y a la ingesta en el DCE."""
    servidor = _Servidor()

    def responder(peticion: httpx.Request) -> httpx.Response:
        servidor.peticiones.append(peticion)
        if "login.microsoftonline.com" in str(peticion.url):
            if token_estado != 200:
                return httpx.Response(token_estado, json={"error": CLAVE_DE_PRUEBA})
            return httpx.Response(
                200, json={"access_token": "tok-1", "expires_in": 3600}
            )
        return httpx.Response(204)

    servidor.__call__ = responder  # type: ignore[method-assign]
    servidor.cliente = lambda: httpx.Client(  # type: ignore[method-assign]
        transport=httpx.MockTransport(responder)
    )
    return servidor


def test_azure_pide_token_y_envia_el_evento_dentro_de_un_arreglo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    servidor = _servidor_azure()
    monkeypatch.setattr(azure, "cliente_httpx", lambda *a, **k: servidor.cliente())
    conector = fabrica_azure(
        "dce.local/dcr-abc123/Custom-IronVeil", _contexto(ENTORNO_AZURE)
    )

    conector.enviar('{"a":1}')

    token, ingesta = servidor.peticiones
    assert (
        str(token.url)
        == "https://login.microsoftonline.com/tenant-de-prueba/oauth2/v2.0/token"
    )
    formulario = parse_qs(token.content.decode())
    assert formulario["grant_type"] == ["client_credentials"]
    assert formulario["scope"] == ["https://monitor.azure.com/.default"]
    assert formulario["client_secret"] == [CLAVE_DE_PRUEBA]
    assert str(ingesta.url) == (
        "https://dce.local/dataCollectionRules/dcr-abc123"
        "/streams/Custom-IronVeil?api-version=2023-01-01"
    )
    assert ingesta.headers["Authorization"] == "Bearer tok-1"
    assert ingesta.headers["Content-Type"] == "application/json"
    assert json.loads(ingesta.content) == [{"a": 1}]


def test_azure_reutiliza_el_token_y_lo_renueva_antes_de_caducar() -> None:
    reloj = [1000.0]
    servidor = _servidor_azure()
    proveedor = ProveedorTokenAzure(
        autoridad="https://login.microsoftonline.com",
        tenant="t",
        client_id="c",
        client_secret=CLAVE_DE_PRUEBA,
        alcance="https://monitor.azure.com/.default",
        cliente=servidor.cliente(),
        reloj=lambda: reloj[0],
    )

    proveedor()
    proveedor()
    assert len(servidor.peticiones) == 1  # cacheado

    reloj[0] += 3600 - 59  # faltan 59 s < margen de 60 s
    proveedor()
    assert len(servidor.peticiones) == 2


def test_azure_un_token_rechazado_no_se_reintenta_ni_muestra_el_secreto() -> None:
    servidor = _servidor_azure(token_estado=401)
    proveedor = ProveedorTokenAzure(
        autoridad="https://login.microsoftonline.com",
        tenant="t",
        client_id="c",
        client_secret=CLAVE_DE_PRUEBA,
        alcance="s",
        cliente=servidor.cliente(),
    )

    with pytest.raises(ErrorSIEM) as exc:
        proveedor()

    assert not exc.value.reintentable
    assert CLAVE_DE_PRUEBA not in str(exc.value)


@pytest.mark.parametrize(
    "destino",
    [
        "dce.local",
        "dce.local/dcr",
        "dce.local/dcr/stream/extra",
        "dce.local/../x/y",
        "dce.local/dcr/s ?x",
    ],
)
def test_azure_exige_host_dcr_y_stream(destino: str) -> None:
    with pytest.raises(ErrorSIEM):
        fabrica_azure(destino, _contexto(ENTORNO_AZURE))


def test_azure_dice_que_variables_faltan() -> None:
    with pytest.raises(ErrorSIEM, match="SIEM_AZURE_CLIENT_SECRET"):
        fabrica_azure(
            "dce.local/dcr/s",
            _contexto({"SIEM_AZURE_TENANT_ID": "t", "SIEM_AZURE_CLIENT_ID": "c"}),
        )


def test_azure_la_autoridad_debe_ser_https() -> None:
    entorno = {**ENTORNO_AZURE, "SIEM_AZURE_AUTORIDAD": "http://login.local"}

    with pytest.raises(ErrorSIEM, match="https"):
        fabrica_azure("dce.local/dcr/s", _contexto(entorno))


# --- CloudWatch Logs ----------------------------------------------------------

ENTORNO_AWS = {
    "AWS_ACCESS_KEY_ID": "AKIAFICTICIAPRUEBA",
    "AWS_SECRET_ACCESS_KEY": CLAVE_DE_PRUEBA,
}


def test_cloudwatch_envia_un_putlogevents_firmado(servidor: _Servidor) -> None:
    conector = ConectorCloudWatch(
        region="us-east-1",
        grupo="/ironveil/proxy",
        flujo="principal",
        credenciales=CredencialesAWS("AKIAFICTICIAPRUEBA", CLAVE_DE_PRUEBA),
        cliente=servidor.cliente(),
        reloj=lambda: INSTANTE,
    )

    conector.enviar('{"a":1}')

    peticion = servidor.peticiones[0]
    assert str(peticion.url) == "https://logs.us-east-1.amazonaws.com/"
    assert peticion.headers["X-Amz-Target"] == "Logs_20140328.PutLogEvents"
    assert peticion.headers["Content-Type"] == "application/x-amz-json-1.1"
    cuerpo = json.loads(peticion.content)
    assert cuerpo["logGroupName"] == "/ironveil/proxy"
    assert cuerpo["logStreamName"] == "principal"
    assert cuerpo["logEvents"] == [
        {"timestamp": int(INSTANTE.timestamp() * 1000), "message": '{"a":1}'}
    ]
    autorizacion = peticion.headers["Authorization"]
    assert autorizacion.startswith(
        "AWS4-HMAC-SHA256 Credential=AKIAFICTICIAPRUEBA/20261006/us-east-1/logs/"
    )
    assert "content-type;host;x-amz-date;x-amz-target" in autorizacion
    assert CLAVE_DE_PRUEBA not in autorizacion
    assert peticion.headers["X-Amz-Date"] == "20261006T143000Z"


def test_cloudwatch_la_fabrica_decodifica_el_grupo_con_barras(
    servidor: _Servidor,
) -> None:
    conector = fabrica_cloudwatch(
        "eu-west-1/%2Fironveil%2Fproxy/principal", _contexto(ENTORNO_AWS)
    )

    conector.enviar("m")

    assert (
        json.loads(servidor.peticiones[0].content)["logGroupName"] == "/ironveil/proxy"
    )
    assert servidor.peticiones[0].url.host == "logs.eu-west-1.amazonaws.com"


def test_cloudwatch_manda_el_token_de_sesion_si_las_claves_son_temporales(
    servidor: _Servidor,
) -> None:
    entorno = {**ENTORNO_AWS, "AWS_SESSION_TOKEN": "sesion-ficticia"}
    conector = fabrica_cloudwatch("us-east-1/grupo/flujo", _contexto(entorno))

    conector.enviar("m")

    assert servidor.peticiones[0].headers["X-Amz-Security-Token"] == "sesion-ficticia"


@pytest.mark.parametrize(
    "destino",
    [
        "us-east-1",
        "us-east-1/grupo",
        "region-mala/g/f",
        "us-east-1/g:malo/f",
        "us-east-1/g/f/extra",
    ],
)
def test_cloudwatch_valida_region_grupo_y_flujo(destino: str) -> None:
    with pytest.raises(ErrorSIEM):
        fabrica_cloudwatch(destino, _contexto(ENTORNO_AWS))


def test_cloudwatch_dice_que_variables_faltan() -> None:
    with pytest.raises(ErrorSIEM, match="AWS_SECRET_ACCESS_KEY"):
        fabrica_cloudwatch("us-east-1/g/f", _contexto({"AWS_ACCESS_KEY_ID": "k"}))


def test_cloudwatch_un_acceso_denegado_no_se_reintenta(servidor: _Servidor) -> None:
    servidor.estado = 400
    conector = fabrica_cloudwatch("us-east-1/g/f", _contexto(ENTORNO_AWS))

    with pytest.raises(ErrorSIEM) as exc:
        conector.enviar("m")

    assert not exc.value.reintentable
