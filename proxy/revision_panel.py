"""Consola de revision humana: pagina, sesion y datos para decidir.

Complementa los endpoints de `proxy/main.py` (`GET /revision`,
`POST /revision/{id}/aprobar|rechazar`, que siguen siendo la API estable) con:

- la pagina (`/revision/ui`) y su inicio de sesion (`/revision/login`),
  servidas desde `proxy/static/`;
- `GET /revision/panel`: la cola ya **analizada** para que una persona pueda
  decidir si es un falso positivo o un ataque (que mecanismo la retuvo y por
  que, que fragmentos coinciden con patrones conocidos, que senales hay, y una
  lectura orientativa);
- `GET /revision/historial`: las decisiones tomadas (quien, cuando, cuanto
  tardo), **sin guardar el texto de las peticiones**.

El analisis es **orientativo**: son reglas simples y legibles, no un veredicto.
La decision es del revisor (CLAUDE.md, mecanismo 5: humano en el loop).

El texto que llega aqui puede ser un ataque: el servidor nunca lo inserta en
HTML; viaja como JSON y la pagina lo pinta con `textContent`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
from collections import deque
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import (
    FileResponse,
    JSONResponse,
    RedirectResponse,
    StreamingResponse,
)
from pydantic import BaseModel, Field

import proxy.auth as auth
import proxy.cola as cola
import proxy.mecanismos as mecanismos
import proxy.memoria_decisiones as memoria_decisiones

logger = logging.getLogger(__name__)

DIRECTORIO_ESTATICO = Path(__file__).resolve().parent / "static"
LONGITUD_MAXIMA_MOSTRADA = 8_000
MAXIMO_HISTORIAL = 200
DOMINIO_INTERNO = "@empresa.demo"
# Canal en vivo (SSE): cada cuantos segundos se manda un latido (mantiene viva la
# conexion y es cuando se revisa que la sesion siga vigente) y cuantas
# consolas pueden estar conectadas a la vez (cada una es una conexion abierta).
INTERVALO_LATIDO_S = 15.0
MAXIMO_FLUJOS_EN_VIVO = 50
REINTENTO_CLIENTE_MS = 3000
MODO_LABORATORIO = "laboratorio"

CABECERAS_SEGURIDAD = {
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; "
        "connect-src 'self'; form-action 'self'; frame-ancestors 'none'; "
        "base-uri 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}

# motivo (campo `motivo` del item en cola) -> (titulo, explicacion)
MOTIVOS: dict[str, tuple[str, str]] = {
    "filtrado": (
        "Filtro de entrada",
        "Coincidió con un patrón conocido de inyección de prompt, o supera la "
        "longitud permitida.",
    ),
    "clasificacion": (
        "Clasificador de inyecciones",
        "Un modelo clasificador la puntuó como inyección o jailbreak. Es "
        "probabilístico: puede equivocarse en ambos sentidos.",
    ),
    "minimo_privilegio": (
        "Mínimo privilegio",
        "Incluye una credencial que pertenece a otro dominio (otro modelo).",
    ),
    "limite_de_peticiones": (
        "Límite por cliente",
        "Este cliente superó el máximo de peticiones por minuto. El contenido "
        "no fue evaluado.",
    ),
    "limite_global_de_peticiones": (
        "Límite global",
        "El proxy superó el máximo de peticiones por minuto entre todos los "
        "clientes. El contenido no fue evaluado.",
    ),
    "herramienta": (
        "Herramienta solicitada",
        "El modelo pidió ejecutar una herramienta (simulada). Nada se ejecuta "
        "sin tu aprobación.",
    ),
}

CATEGORIAS_PATRON: dict[str, str] = {
    "ignorar_instrucciones": "Pide ignorar las instrucciones del sistema",
    "olvidar_reglas_anteriores": "Pide olvidar las reglas anteriores",
    "modo_desarrollador": "Invoca un modo desarrollador o sin restricciones",
    "configuracion_inicial": "Pregunta por la configuración inicial del modelo",
    "system_prompt": "Menciona el system prompt",
}

_PATRONES_CONCEPTO: dict[str, tuple[re.Pattern[str], ...]] = {
    concepto: tuple(re.compile(p, re.IGNORECASE) for p in variantes.values())
    for concepto, variantes in (
        mecanismos.PATRONES_PROHIBIDOS_ENTRADA_POR_CONCEPTO.items()
    )
}
_PATRON_BLOQUE_CODIFICADO = re.compile(r"[A-Za-z0-9+/]{80,}={0,2}")
_PATRON_MODIFICA_DATOS = re.compile(
    r"\b(drop|delete|update|insert|alter|truncate)\b", re.IGNORECASE
)
_PATRON_SELECT_TODO = re.compile(r"select\s+\*", re.IGNORECASE)

NIVEL_ALTA = "alta"
NIVEL_MEDIA = "media"
NIVEL_INFO = "info"


# --- Analisis (funciones puras, sin red ni estado) ---------------------------


def _senal(nivel: str, titulo: str, detalle: str) -> dict[str, str]:
    return {"nivel": nivel, "titulo": titulo, "detalle": detalle}


def _segmentar(
    texto: str, rangos: list[tuple[int, int, str, str]]
) -> list[dict[str, Any]]:
    """Parte `texto` en segmentos; los que caen en un rango llevan categoria y
    detalle. Los rangos solapados se fusionan (gana el primero). Devolver
    segmentos, y no desplazamientos, evita errores entre la indexacion de
    Python (code points) y la de JavaScript (UTF-16)."""
    ordenados = sorted(rangos, key=lambda r: (r[0], -r[1]))
    segmentos: list[dict[str, Any]] = []
    cursor = 0
    for inicio, fin, categoria, detalle in ordenados:
        if inicio < cursor:
            continue
        if inicio > cursor:
            segmentos.append({"t": texto[cursor:inicio], "k": None, "d": None})
        segmentos.append({"t": texto[inicio:fin], "k": categoria, "d": detalle})
        cursor = fin
    if cursor < len(texto):
        segmentos.append({"t": texto[cursor:], "k": None, "d": None})
    return segmentos


def _evidencia_en_texto(
    texto: str,
) -> tuple[list[tuple[int, int, str, str]], list[dict[str, str]]]:
    """Rangos resaltables y senales encontradas en el texto de una peticion."""
    rangos: list[tuple[int, int, str, str]] = []
    senales: list[dict[str, str]] = []
    for concepto, patrones in _PATRONES_CONCEPTO.items():
        coincidencias = [m for p in patrones for m in p.finditer(texto)]
        if not coincidencias:
            continue
        detalle = CATEGORIAS_PATRON.get(concepto, concepto)
        for m in coincidencias:
            rangos.append((m.start(), m.end(), "patron", detalle))
        senales.append(
            _senal(NIVEL_ALTA, detalle, "Coincide con el filtro de entrada.")
        )
    for m in mecanismos.PATRON_CREDENCIAL_GENERICO.finditer(texto):
        rangos.append(
            (m.start(), m.end(), "credencial", "Formato de credencial interna")
        )
    if mecanismos.PATRON_CREDENCIAL_GENERICO.search(texto):
        senales.append(
            _senal(
                NIVEL_ALTA,
                "Contiene una credencial con formato interno",
                "Un usuario legítimo normalmente no conoce estos identificadores.",
            )
        )
    for m in _PATRON_BLOQUE_CODIFICADO.finditer(texto):
        rangos.append((m.start(), m.end(), "codificado", "Bloque largo codificado"))
    if _PATRON_BLOQUE_CODIFICADO.search(texto):
        senales.append(
            _senal(
                NIVEL_MEDIA,
                "Bloque largo que parece codificado",
                "Los filtros por patrón no ven dentro de un texto codificado.",
            )
        )
    if len(texto) > mecanismos.LIMITE_LONGITUD_MENSAJE:
        senales.append(
            _senal(NIVEL_MEDIA, "Mensaje muy largo", "Supera el límite de entrada.")
        )
    return rangos, senales


def analizar_herramienta(
    nombre: str, argumentos: dict[str, Any]
) -> list[dict[str, str]]:
    """Senales de una herramienta SIMULADA solicitada por el modelo (mismas
    condiciones que el system prompt de `rrhh-agente`)."""
    senales: list[dict[str, str]] = []
    if nombre == "enviar_correo":
        destinatario = str(argumentos.get("destinatario", ""))
        if not destinatario.lower().endswith(DOMINIO_INTERNO):
            senales.append(
                _senal(
                    NIVEL_ALTA,
                    "Destinatario externo",
                    f"El correo no es de {DOMINIO_INTERNO}: {destinatario or 'vacio'}.",
                )
            )
        if mecanismos.PATRON_CREDENCIAL_GENERICO.search(
            str(argumentos.get("contenido", ""))
        ):
            senales.append(
                _senal(
                    NIVEL_ALTA,
                    "Credencial dentro del correo",
                    "El cuerpo incluye una credencial.",
                )
            )
    elif nombre == "consultar_base_datos":
        consulta = str(argumentos.get("query", ""))
        if _PATRON_MODIFICA_DATOS.search(consulta):
            senales.append(
                _senal(
                    NIVEL_ALTA,
                    "La consulta modifica o borra datos",
                    "Se esperaba solo lectura.",
                )
            )
        elif _PATRON_SELECT_TODO.search(consulta) and "where" not in consulta.lower():
            senales.append(
                _senal(
                    NIVEL_MEDIA,
                    "Lectura masiva sin filtro",
                    "Pide todos los registros.",
                )
            )
    else:
        senales.append(
            _senal(NIVEL_ALTA, "Herramienta desconocida", f"No existe {nombre!r}.")
        )
    return senales


def _lectura(motivo: str, senales: list[dict[str, str]]) -> dict[str, Any]:
    """Puntaje 0-100 (0 = parece legitima, 100 = parece ataque) y su lectura."""
    altas = sum(s["nivel"] == NIVEL_ALTA for s in senales)
    medias = sum(s["nivel"] == NIVEL_MEDIA for s in senales)
    if motivo.startswith("limite") and not senales:
        puntaje = 10
    elif motivo == "clasificacion" and not senales:
        puntaje = 50
    else:
        # Una senal alta basta para leerla como ataque (70); cada alta extra y
        # las medias suben el puntaje. Sin senales: parece legitima (15).
        puntaje = 15
        if altas:
            puntaje += 55 + 15 * (altas - 1)
        if medias:
            puntaje += 10 if altas else 28
    puntaje = max(0, min(100, puntaje))
    if puntaje >= 70:
        nivel, texto = "alta", "Parece un ataque"
    elif puntaje >= 40:
        nivel, texto = "media", "Revisa con cuidado"
    else:
        nivel, texto = "baja", "Parece un falso positivo"
    return {"puntaje": puntaje, "nivel": nivel, "lectura": texto}


def _espera_s(encolado_en: str, ahora: datetime) -> int:
    try:
        return max(
            0, int((ahora - datetime.fromisoformat(encolado_en)).total_seconds())
        )
    except (TypeError, ValueError):
        return 0


def analizar_peticion(
    item: dict[str, Any], ahora: datetime | None = None
) -> dict[str, Any]:
    """Convierte un item de la cola en el expediente que ve el revisor."""
    ahora = ahora or datetime.now().astimezone()
    motivo = str(item.get("motivo", ""))
    titulo, explicacion = MOTIVOS.get(
        motivo, ("Retenida por un mecanismo", "Un mecanismo de IronVeil la retuvo.")
    )
    es_herramienta = item.get("tipo") == "herramienta"
    expediente: dict[str, Any] = {
        "id": item.get("id"),
        "tipo": "herramienta" if es_herramienta else "peticion",
        "modelo": item.get("modelo"),
        "vector_probado": item.get("vector_probado"),
        "motivo": motivo,
        "motivo_titulo": titulo,
        "motivo_explicacion": explicacion,
        "cliente": item.get("cliente", "desconocido"),
        "encolado_en": item.get("encolado_en"),
        "espera_s": _espera_s(str(item.get("encolado_en", "")), ahora),
        "herramienta": None,
        "segmentos": [],
        "truncado": False,
    }
    if es_herramienta:
        argumentos = item.get("argumentos")
        argumentos = argumentos if isinstance(argumentos, dict) else {}
        senales = analizar_herramienta(str(item.get("herramienta", "")), argumentos)
        expediente["herramienta"] = {
            "nombre": item.get("herramienta"),
            "argumentos": json.dumps(argumentos, ensure_ascii=False, indent=2),
            "simulada": True,
        }
    else:
        texto = str(item.get("mensaje", ""))
        if len(texto) > LONGITUD_MAXIMA_MOSTRADA:
            texto, expediente["truncado"] = texto[:LONGITUD_MAXIMA_MOSTRADA], True
        rangos, senales = _evidencia_en_texto(texto)
        expediente["segmentos"] = _segmentar(texto, rangos)
    expediente["senales"] = senales
    expediente["sospecha"] = _lectura(motivo, senales)
    return expediente


# --- Historial de decisiones (sin el texto de las peticiones) -----------------


class HistorialDecisiones:
    """Ultimas decisiones, en memoria y protegidas con lock."""

    def __init__(self, maximo: int = MAXIMO_HISTORIAL) -> None:
        self._decisiones: deque[dict[str, Any]] = deque(maxlen=maximo)
        self._lock = threading.Lock()

    def registrar(
        self,
        item: dict[str, Any],
        accion: str,
        identidad: auth.Identidad | None,
        tiempo_revision_ms: int,
    ) -> None:
        """`accion` es "aprobada" o "rechazada". Guarda metadatos, nunca el
        mensaje ni los argumentos."""
        with self._lock:
            self._decisiones.appendleft(
                {
                    "id": item.get("id"),
                    "accion": accion,
                    "revisor": identidad.usuario if identidad else MODO_LABORATORIO,
                    "tipo": (
                        "herramienta"
                        if item.get("tipo") == "herramienta"
                        else "peticion"
                    ),
                    "herramienta": item.get("herramienta"),
                    "modelo": item.get("modelo"),
                    "vector_probado": item.get("vector_probado"),
                    "motivo": item.get("motivo"),
                    "tiempo_revision_ms": tiempo_revision_ms,
                    "decidida_en": datetime.now().astimezone().isoformat(),
                }
            )

    def listar(self) -> list[dict[str, Any]]:
        """Mas reciente primero."""
        with self._lock:
            return list(self._decisiones)

    def vaciar(self) -> None:
        with self._lock:
            self._decisiones.clear()


historial = HistorialDecisiones()


def estadisticas(pendientes: list[dict[str, Any]]) -> dict[str, Any]:
    """Cifras del encabezado de la consola."""
    decisiones = historial.listar()
    tiempos = [
        d["tiempo_revision_ms"] for d in decisiones if d["tiempo_revision_ms"] >= 0
    ]
    return {
        "pendientes": len(pendientes),
        "espera_maxima_s": max((p["espera_s"] for p in pendientes), default=0),
        "aprobadas": sum(d["accion"] == "aprobada" for d in decisiones),
        "rechazadas": sum(d["accion"] == "rechazada" for d in decisiones),
        "tiempo_medio_decision_s": (
            round(sum(tiempos) / len(tiempos) / 1000) if tiempos else None
        ),
    }


# --- Rutas ---------------------------------------------------------------------

router = APIRouter()


class Credenciales(BaseModel):
    usuario: str = Field(min_length=1, max_length=64)
    clave: str = Field(min_length=1, max_length=auth.LONGITUD_MAXIMA_CLAVE)


def _json(contenido: dict[str, Any] | list[Any], estado: int = 200) -> JSONResponse:
    return JSONResponse(contenido, status_code=estado, headers=CABECERAS_SEGURIDAD)


def _pagina(nombre: str) -> FileResponse:
    return FileResponse(DIRECTORIO_ESTATICO / nombre, headers=CABECERAS_SEGURIDAD)


@router.get("/revision/ui", include_in_schema=False)
def interfaz_revision(request: Request) -> Response:
    """Consola de revision. Con login activo y sin sesion, redirige al login."""
    if auth.auth_habilitada() and auth.sesion_de(request) is None:
        return RedirectResponse("/revision/login", status_code=303)
    return _pagina("revision.html")


@router.get("/revision/login", include_in_schema=False)
def pagina_login(request: Request) -> Response:
    """Pagina de inicio de sesion (redirige a la consola si no hace falta)."""
    if not auth.auth_habilitada() or auth.sesion_de(request) is not None:
        return RedirectResponse("/revision/ui", status_code=303)
    return _pagina("login.html")


@router.post("/revision/login", include_in_schema=False)
def iniciar_sesion(credenciales: Credenciales, request: Request) -> Response:
    """Valida usuario y clave con el proveedor de identidad y abre la sesion."""
    if not auth.auth_habilitada():
        raise HTTPException(
            status_code=400, detail="El inicio de sesión no está habilitado."
        )
    clave_ip = "ip:" + auth.ip_cliente(request)
    clave_usuario = "u:" + credenciales.usuario.strip().lower()
    if auth.limitador.bloqueado(clave_ip) or auth.limitador.bloqueado(clave_usuario):
        logger.warning(
            "login bloqueado por demasiados intentos (ip=%s)", auth.ip_cliente(request)
        )
        raise HTTPException(
            status_code=429, detail="Demasiados intentos. Espera unos minutos."
        )
    try:
        identidad = auth.obtener_proveedor().autenticar(
            credenciales.usuario, credenciales.clave
        )
    except Exception:  # noqa: BLE001 - un fallo del proveedor no debe filtrar detalles
        logger.exception("el proveedor de identidad fallo")
        raise HTTPException(
            status_code=503, detail="No se pudo validar la identidad."
        ) from None
    if identidad is None:
        auth.limitador.registrar_fallo(clave_ip)
        auth.limitador.registrar_fallo(clave_usuario)
        logger.warning("login fallido (ip=%s)", auth.ip_cliente(request))
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos.")
    auth.limitador.reiniciar(clave_usuario)
    token, sesion = auth.sesiones.crear(identidad)
    logger.info(
        "sesion iniciada (usuario=%s, rol=%s)", identidad.usuario, identidad.rol
    )
    respuesta = _json(
        {"usuario": identidad.usuario, "rol": identidad.rol, "csrf": sesion.csrf}
    )
    respuesta.set_cookie(
        auth.NOMBRE_COOKIE,
        token,
        httponly=True,
        samesite="strict",
        secure=auth.cookie_secure(),
        path="/",
    )
    return respuesta


@router.post("/revision/logout", include_in_schema=False)
def cerrar_sesion(request: Request) -> Response:
    """Cierra la sesion actual (idempotente)."""
    auth.sesiones.cerrar(request.cookies.get(auth.NOMBRE_COOKIE))
    respuesta = _json({"ok": True})
    respuesta.delete_cookie(auth.NOMBRE_COOKIE, path="/")
    return respuesta


@router.get("/revision/sesion", include_in_schema=False)
def sesion_actual(request: Request) -> Response:
    """Quien soy y que puedo hacer; la pagina lo usa para saber si hay login."""
    if not auth.auth_habilitada():
        return _json(
            {
                "autenticacion": False,
                "usuario": MODO_LABORATORIO,
                "rol": auth.ROL_REVISOR,
                "csrf": "",
            }
        )
    sesion = auth.sesion_de(request)
    if sesion is None:
        raise HTTPException(status_code=401, detail="Inicia sesión para continuar.")
    return _json(
        {
            "autenticacion": True,
            "usuario": sesion.identidad.usuario,
            "rol": sesion.identidad.rol,
            "csrf": sesion.csrf,
        }
    )


@router.get("/revision/panel", include_in_schema=False)
def panel(_: Annotated[auth.Identidad | None, Depends(auth.exigir_lector)]) -> Response:
    """Cola pendiente ya analizada, mas las cifras del encabezado."""
    ahora = datetime.now().astimezone()
    pendientes = [analizar_peticion(i, ahora) for i in cola.cola_global.listar()]
    return _json({"pendientes": pendientes, "estadisticas": estadisticas(pendientes)})


@router.get("/revision/historial", include_in_schema=False)
def historial_decisiones(
    _: Annotated[auth.Identidad | None, Depends(auth.exigir_lector)],
) -> Response:
    """Decisiones ya tomadas, la mas reciente primero."""
    return _json({"decisiones": historial.listar()})


# --- Memoria de decisiones (extension opcional) ------------------------------
#
# Cuando un humano rechaza una peticion retenida, el proxy recuerda ese mensaje y
# rechaza al instante los identicos (proxy/memoria_decisiones.py). Aqui se ven las
# reglas y se revocan: un rechazo equivocado no puede ser permanente. Nunca viaja el
# mensaje completo: solo una vista previa corta con las credenciales redactadas.

_HUELLA_VALIDA = re.compile(r"^[0-9a-f]{64}$")


@router.get("/revision/memoria", include_in_schema=False)
def ver_memoria(
    _: Annotated[auth.Identidad | None, Depends(auth.exigir_lector)],
) -> Response:
    """Reglas recordadas; `activa: false` si la extension esta apagada."""
    memoria = memoria_decisiones.obtener()
    if memoria is None:
        return _json({"activa": False, "reglas": []})
    return _json(
        {
            "activa": True,
            "persistente": memoria.persistente,
            "maximo": memoria.maximo,
            "reglas": memoria.listar(),
        }
    )


@router.delete("/revision/memoria/{huella}", include_in_schema=False)
def olvidar_regla(
    huella: str,
    revisor: Annotated[auth.Identidad | None, Depends(auth.exigir_revisor)],
) -> Response:
    """Revoca una regla (solo revisores, con el token CSRF de la sesion)."""
    memoria = memoria_decisiones.obtener()
    if memoria is None or not _HUELLA_VALIDA.match(huella):
        raise HTTPException(
            status_code=404, detail="No hay ninguna regla con esa huella."
        )
    quien = revisor.usuario if revisor else MODO_LABORATORIO
    if not memoria.olvidar(huella, quien):
        raise HTTPException(
            status_code=404, detail="No hay ninguna regla con esa huella."
        )
    logger.info("regla de memoria olvidada (por=%s)", quien)
    return _json({"huella": huella, "estado": "olvidada"})


# --- Canal en vivo (SSE) ----------------------------------------------------
#
# La consola no pregunta cada pocos segundos: abre UNA conexion que el servidor
# mantiene abierta y le avisa en cuanto la cola cambia. El aviso no lleva datos
# (solo "cambio"): al recibirlo la consola vuelve a pedir `/revision/panel` por la
# via de siempre, con su autenticacion. Asi por este canal nunca viaja el texto
# de una peticion.

_flujos_abiertos = 0
_lock_flujos = threading.Lock()


def _reservar_flujo() -> bool:
    global _flujos_abiertos  # noqa: PLW0603 - contador compartido entre conexiones
    with _lock_flujos:
        if _flujos_abiertos >= MAXIMO_FLUJOS_EN_VIVO:
            return False
        _flujos_abiertos += 1
        return True


def _liberar_flujo() -> None:
    global _flujos_abiertos  # noqa: PLW0603
    with _lock_flujos:
        _flujos_abiertos = max(0, _flujos_abiertos - 1)


def flujos_en_vivo() -> int:
    """Consolas conectadas ahora mismo al canal en vivo."""
    with _lock_flujos:
        return _flujos_abiertos


def _evento_sse(nombre: str) -> bytes:
    return f"event: {nombre}\ndata: {{}}\n\n".encode()


async def flujo_eventos(
    request: Request,
    cola_revision: cola.ColaRevision,
    token: str | None,
    latido_s: float = INTERVALO_LATIDO_S,
) -> AsyncIterator[bytes]:
    """Eventos SSE de una consola: `cambio` cuando la cola cambia, `sesion` cuando
    su sesion vencio (y se cierra), `lleno` si no hay cupo, y un latido si no pasa
    nada. Al terminar (el navegador se fue, o vencio la sesion) deja de escuchar."""
    if not _reservar_flujo():
        yield _evento_sse("lleno")
        return
    bucle = asyncio.get_running_loop()
    cambios: asyncio.Queue[None] = asyncio.Queue(maxsize=1)

    def _marcar() -> None:
        if cambios.empty():  # varios cambios seguidos se funden en un solo aviso
            cambios.put_nowait(None)

    def avisar() -> None:
        # Lo llama el hilo que cambio la cola, no el del bucle de eventos.
        try:
            bucle.call_soon_threadsafe(_marcar)
        except RuntimeError:  # el bucle ya se cerro (apagado del servidor)
            pass

    cola_revision.suscribir(avisar)
    try:
        yield f"retry: {REINTENTO_CLIENTE_MS}\n\n".encode()
        while True:
            if auth.auth_habilitada() and auth.sesiones.obtener(token, False) is None:
                yield _evento_sse("sesion")
                return
            try:
                await asyncio.wait_for(cambios.get(), timeout=latido_s)
            except TimeoutError:
                if await request.is_disconnected():
                    return
                yield b": latido\n\n"
            else:
                yield _evento_sse("cambio")
    finally:
        cola_revision.cancelar(avisar)
        _liberar_flujo()


@router.get("/revision/eventos", include_in_schema=False)
async def eventos_en_vivo(
    request: Request,
    _: Annotated[auth.Identidad | None, Depends(auth.exigir_lector)],
) -> StreamingResponse:
    """Canal en vivo de la consola (SSE). Exige sesion si el login esta activo."""
    return StreamingResponse(
        flujo_eventos(
            request, cola.cola_global, request.cookies.get(auth.NOMBRE_COOKIE)
        ),
        media_type="text/event-stream",
        headers={**CABECERAS_SEGURIDAD, "X-Accel-Buffering": "no"},
    )
