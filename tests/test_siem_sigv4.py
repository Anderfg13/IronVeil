"""La firma AWS SigV4 contra el vector publicado por AWS (get-vanilla)."""

from __future__ import annotations

from datetime import UTC, datetime

from proxy.siem.transportes.sigv4 import CredencialesAWS, firmar

# Vector de la suite de pruebas de firma de AWS (aws-sig-v4-test-suite, `get-vanilla`):
# claves de ejemplo PUBLICAS de la documentacion de AWS, no son credenciales reales.
CREDENCIALES_DE_EJEMPLO = CredencialesAWS(
    clave_acceso="AKIDEXAMPLE",
    clave_secreta="wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY",  # NOSONAR documentada
)
FIRMA_ESPERADA = "5fa00fa31553b73ebf1942676e86291e8372ff2a2260956d9b8aae1d763fbf31"


def test_coincide_con_el_vector_publicado_por_aws() -> None:
    cabeceras = firmar(
        metodo="GET",
        host="example.amazonaws.com",
        ruta="/",
        consulta="",
        cabeceras={},
        cuerpo=b"",
        region="us-east-1",
        servicio="service",
        credenciales=CREDENCIALES_DE_EJEMPLO,
        ahora=datetime(2015, 8, 30, 12, 36, 0, tzinfo=UTC),
    )

    assert cabeceras["X-Amz-Date"] == "20150830T123600Z"
    assert cabeceras["Authorization"] == (
        "AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/20150830/us-east-1/service/"
        f"aws4_request, SignedHeaders=host;x-amz-date, Signature={FIRMA_ESPERADA}"
    )


def test_el_token_de_sesion_se_firma_y_se_devuelve() -> None:
    credenciales = CredencialesAWS(
        "AKIDEXAMPLE", "secreto-de-prueba", "token-de-prueba"
    )

    cabeceras = firmar(
        metodo="POST",
        host="logs.us-east-1.amazonaws.com",
        ruta="/",
        consulta="",
        cabeceras={"Content-Type": "application/x-amz-json-1.1"},
        cuerpo=b"{}",
        region="us-east-1",
        servicio="logs",
        credenciales=credenciales,
        ahora=datetime(2026, 10, 6, tzinfo=UTC),
    )

    assert cabeceras["X-Amz-Security-Token"] == "token-de-prueba"
    assert "x-amz-security-token" in cabeceras["Authorization"]
    assert "content-type" in cabeceras["Authorization"]


def test_las_claves_no_aparecen_en_el_repr() -> None:
    texto = repr(CredencialesAWS("AKIDEXAMPLE", "no-debe-verse", "tampoco"))

    assert "no-debe-verse" not in texto
    assert "tampoco" not in texto
