"""Cola de revision humana y limitador de peticiones (mecanismo 5).

Infraestructura de backend sobre la que Piedrahita construye la interfaz
de aprobacion/rechazo esta misma semana, en paralelo. Este modulo NO
decide si una peticion es sospechosa -- eso lo deciden filtrado /
clasificacion / minimo_privilegio, o el propio limite de tasa de aqui --
solo ofrece donde guardarla y como saber si un cliente se paso del limite.

A diferencia de las funciones de proxy/mecanismos.py (filtrar, delimitar,
clasificar, validar_privilegio), la cola SI mantiene estado compartido
entre peticiones concurrentes a proposito: es su unica razon de existir
(ver el contrato de enviar_a_revision() en CLAUDE.md: "encola y devuelve
senal de pendiente"). Por eso toda mutacion pasa por threading.Lock -- el
V5 (agotamiento de recursos) dispara justamente rafagas concurrentes, y
una condicion de carrera aqui seria un bug real, no teorico (CLAUDE.md,
seccion 7).
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections import deque
from collections.abc import Callable
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# Constantes configurables (documentadas con su justificacion en
# docs/FUENTE_DE_VERDAD.md, seccion 4). Una sola vez aqui, nunca repetidas
# ni incrustadas en la logica.
#
# LIMITE_PETICIONES_POR_MINUTO=10 / VENTANA_LIMITE_S=60: un usuario legitimo
# normal no manda 10+ mensajes en un minuto: es un techo generoso para
# trafico humano real, pero bien por debajo de la concurrencia tipica de
# una rafaga V5 (ataques/vector5_carga.py usa --concurrencia=20 por
# defecto), para que el limite se dispare de forma clara y medible durante
# el experimento.
LIMITE_PETICIONES_POR_MINUTO: int = 10
VENTANA_LIMITE_S: float = 60.0
# LIMITE_GLOBAL_PETICIONES_POR_MINUTO=50: limite por cliente/IP arriba no
# protege contra un ataque distribuido (muchas IPs distintas, cada una por
# debajo de su propio limite, saturando el servicio entre todas). Este
# limite es independiente y se aplica al total de peticiones de TODOS los
# clientes juntos, en la misma ventana deslizante. 50 = 5x el limite por
# cliente: generoso para varios usuarios legitimos concurrentes (p. ej. 5
# personas cada una cerca de su propio limite de 10), pero bien por debajo
# de una rafaga V5 real (niveles de concurrencia de 50/100, ver
# docs/FUENTE_DE_VERDAD.md hallazgo 7).
LIMITE_GLOBAL_PETICIONES_POR_MINUTO: int = 50
# Limite de seguridad de la cola misma: sin este techo, un atacante podria
# agotar memoria encolando peticiones sin limite -- el propio V5 contra la
# cola de revision, no solo contra Ollama. 200 es generoso para una sola
# corrida de experimento (nunca se llena en uso normal) pero acotado.
MAX_TAMANO_COLA: int = 200


class Avisos:
    """Lista de oyentes que se avisan (sin datos) cuando algo cambia.

    La comparten la cola y el registro de resultados. Se avisa desde el hilo que
    provoco el cambio, SIN tener tomado el lock de quien cambio: un oyente lento
    nunca frena a `encolar()` ni a `retirar()`. Un oyente que falla se registra y
    no impide avisar a los demas.
    """

    def __init__(self) -> None:
        self.oyentes: list[Callable[[], None]] = []
        self._lock = threading.Lock()

    def suscribir(self, aviso: Callable[[], None]) -> None:
        """Registra `aviso()`; debe ser rapido y seguro entre hilos."""
        with self._lock:
            self.oyentes.append(aviso)

    def cancelar(self, aviso: Callable[[], None]) -> None:
        """Quita un aviso (si ya no esta, no hace nada)."""
        with self._lock:
            if aviso in self.oyentes:
                self.oyentes.remove(aviso)

    def avisar(self) -> None:
        """Llama a todos los oyentes registrados."""
        with self._lock:
            copia = list(self.oyentes)
        for aviso in copia:
            try:
                aviso()
            except Exception:  # noqa: BLE001 - un oyente roto no frena a los demas
                logger.warning("un aviso de cambio fallo", exc_info=True)


class ColaRevision:
    """Cola de peticiones pendientes + rate limiter por cliente.

    Instancia con su propio estado (lock, cola FIFO, contadores de
    peticiones por cliente en una ventana deslizante de `ventana_s`
    segundos). `cola_global`, al final de este modulo, es la instancia
    compartida que usan proxy/main.py y mecanismos.enviar_a_revision() en
    produccion; los tests crean sus propias instancias para no compartir
    estado entre casos (evita pruebas fragiles / dependientes del orden
    en que corre la suite).
    """

    def __init__(
        self,
        limite_por_minuto: int = LIMITE_PETICIONES_POR_MINUTO,
        ventana_s: float = VENTANA_LIMITE_S,
        tamano_maximo: int = MAX_TAMANO_COLA,
        limite_global_por_minuto: int = LIMITE_GLOBAL_PETICIONES_POR_MINUTO,
    ) -> None:
        self.limite_por_minuto = limite_por_minuto
        self.ventana_s = ventana_s
        self.tamano_maximo = tamano_maximo
        self.limite_global_por_minuto = limite_global_por_minuto
        self._lock = threading.Lock()
        self._cola: deque[dict[str, Any]] = deque()
        self._peticiones_por_cliente: dict[str, deque[float]] = {}
        self._peticiones_globales: deque[float] = deque()
        # Quien quiere enterarse al instante de que la cola cambio (la consola
        # de revision en vivo, y quien espera una decision).
        self._avisos = Avisos()

    @property
    def _suscriptores(self) -> list[Callable[[], None]]:
        return self._avisos.oyentes

    def suscribir(self, aviso: Callable[[], None]) -> None:
        """Registra `aviso()`, que se llama (sin argumentos) cada vez que la cola
        cambia: una peticion se encola o se retira.

        Se invoca desde el hilo que provoco el cambio, asi que debe ser rapido y
        seguro entre hilos. No recibe datos a proposito: quien escucha vuelve a
        leer la cola con `listar()` (y su autenticacion), nada sensible viaja aqui.
        """
        self._avisos.suscribir(aviso)

    def cancelar(self, aviso: Callable[[], None]) -> None:
        """Quita un aviso registrado con `suscribir()` (si ya no esta, no hace nada)."""
        self._avisos.cancelar(aviso)

    def _avisar_cambio(self) -> None:
        self._avisos.avisar()

    def contiene(self, id_peticion: str) -> bool:
        """True si hay una peticion pendiente con ese `id`."""
        with self._lock:
            return any(item.get("id") == id_peticion for item in self._cola)

    def excede_limite(self, cliente: str) -> bool:
        """True si `cliente` ya alcanzo `limite_por_minuto` peticiones en
        los ultimos `ventana_s` segundos (ventana deslizante, no de
        ventana fija: evita el efecto "de golpe" en el borde del minuto).

        Cuenta esta llamada como una peticion mas del cliente, se exceda o
        no el limite. Si no se contara, un cliente ya excedido podria
        "resetear" su propio conteo con la sola llamada de verificacion,
        sin que el mecanismo hubiera hecho ningun trabajo real.

        Thread-safe: protegida con el mismo lock que `encolar()`, para que
        una rafaga concurrente (V5) nunca deje el contador en un estado
        inconsistente.
        """
        ahora = time.monotonic()
        limite_inferior = ahora - self.ventana_s
        with self._lock:
            marcas = self._peticiones_por_cliente.setdefault(cliente, deque())
            while marcas and marcas[0] < limite_inferior:
                marcas.popleft()
            excede = len(marcas) >= self.limite_por_minuto
            marcas.append(ahora)
        return excede

    def excede_limite_global(self) -> bool:
        """True si TODOS los clientes juntos ya alcanzaron
        `limite_global_por_minuto` peticiones en los ultimos `ventana_s`
        segundos, sin importar de que cliente venga cada una.

        Complementa a `excede_limite()` (por cliente), no lo reemplaza: un
        ataque distribuido (muchas IPs distintas, cada una por debajo de su
        propio limite individual) puede seguir saturando el servicio sin
        que ninguna IP dispare `excede_limite()` sola. Quien llama debe
        evaluar los dos, siempre, sin cortocircuito -- ver
        `proxy/main.py::_verificar_limite_de_tasa()`.

        Misma logica de ventana deslizante y el mismo conteo-siempre
        (cuenta esta llamada aunque exceda) que `excede_limite()`, por la
        misma razon: si no se contara, el servicio ya saturado podria
        "resetear" el conteo global con la sola llamada de verificacion.

        Thread-safe: mismo lock que el resto de la clase.
        """
        ahora = time.monotonic()
        limite_inferior = ahora - self.ventana_s
        with self._lock:
            while (
                self._peticiones_globales
                and self._peticiones_globales[0] < limite_inferior
            ):
                self._peticiones_globales.popleft()
            excede = len(self._peticiones_globales) >= self.limite_global_por_minuto
            self._peticiones_globales.append(ahora)
        return excede

    def encolar(self, peticion: dict[str, Any]) -> bool:
        """Agrega una copia de `peticion` a la cola de revision.

        Le asigna un `id` unico y un `encolado_en` (ISO 8601) si la
        peticion no los trae ya, para que la interfaz de
        aprobacion/rechazo pueda referenciarla sin ambiguedad.

        Devuelve True si se encolo. Devuelve False si la cola ya tiene
        `tamano_maximo` elementos: limite de seguridad para que un
        atacante no pueda agotar memoria encolando peticiones sin limite.
        Quien llama debe tratar False como "no se pudo diferir, rechazar
        la peticion" -- nunca como exito silencioso (fail closed, igual
        que el resto de mecanismos del proyecto ante una condicion de
        error).
        """
        item = dict(peticion)
        item.setdefault("id", uuid.uuid4().hex)
        item.setdefault("encolado_en", datetime.now().astimezone().isoformat())
        with self._lock:
            if len(self._cola) >= self.tamano_maximo:
                return False
            self._cola.append(item)
        self._avisar_cambio()
        return True

    def tamano(self) -> int:
        """Numero de peticiones pendientes de revision ahora mismo."""
        with self._lock:
            return len(self._cola)

    def listar(self) -> list[dict[str, Any]]:
        """Copia de las peticiones pendientes, en orden de llegada (la
        mas antigua primero).

        Copia, no la deque interna: quien la use no puede mutar el estado
        compartido salvo a traves de `encolar()`/`retirar()`. Pensada para
        que la interfaz de aprobacion/rechazo de Piedrahita liste lo
        pendiente.
        """
        with self._lock:
            return list(self._cola)

    def retirar(self, id_peticion: str) -> dict[str, Any]:
        """Quita y devuelve la peticion en cola con `id` == `id_peticion`.

        Por id, no por posicion: dos revisores concurrentes viendo la
        misma lista no deben poder retirar el elemento equivocado si algo
        cambio entre que listaron y que decidieron.

        Lanza KeyError si no existe (ya fue retirada, o el id no es
        valido) -- no un default silencioso; quien la use decide como
        manejarlo (p. ej. "ya la resolvio otro revisor").
        """
        retirada: dict[str, Any] | None = None
        with self._lock:
            for indice, item in enumerate(self._cola):
                if item.get("id") == id_peticion:
                    del self._cola[indice]
                    retirada = item
                    break
        if retirada is not None:
            self._avisar_cambio()
            return retirada
        raise KeyError(f"No hay ninguna peticion en cola con id={id_peticion!r}")


# --- Resultado de una revision humana, para quien esta esperando -----------
#
# Cuando una peticion se encola, /chat responde 429 y cierra la conexion: quien
# escribio no recibe nunca lo que decida el revisor (aprobar devuelve la
# respuesta al REVISOR). Este registro guarda el resultado un rato, por el
# identificador del turno, para que el chat pueda preguntarlo y mostrarlo.

ESTADO_EN_CURSO = "en_curso"  # el revisor ya decidio y se esta completando
ESTADO_APROBADA = "aprobada"
ESTADO_RECHAZADA = "rechazada"
ESTADO_FALLIDA = "fallida"  # aprobada, pero no se pudo completar
ESTADOS_FINALES = (ESTADO_APROBADA, ESTADO_RECHAZADA, ESTADO_FALLIDA)
# 30 min: lo que tarda en irse el interes de quien espera, y poca retencion del
# texto de una respuesta en memoria. 500: tope para que no crezca sin limite.
TTL_RESULTADO_S: float = 1800.0
MAX_RESULTADOS: int = 500


class ResultadosRevision:
    """Resultado de cada revision, por id, con caducidad y tope de tamano.

    El id es un uuid4 (128 bits) que solo conoce quien envio el mensaje (viaja en
    la respuesta 429) y el revisor: funciona como llave. Todo en memoria del
    proceso y detras de un lock; nada se escribe a disco.
    """

    def __init__(
        self, ttl_s: float = TTL_RESULTADO_S, maximo: int = MAX_RESULTADOS
    ) -> None:
        self.ttl_s = ttl_s
        self.maximo = maximo
        self._lock = threading.Lock()
        self._datos: dict[str, tuple[float, dict[str, Any]]] = {}
        self._avisos = Avisos()

    def suscribir(self, aviso: Callable[[], None]) -> None:
        """Registra `aviso()` para cuando cambie algun resultado."""
        self._avisos.suscribir(aviso)

    def cancelar(self, aviso: Callable[[], None]) -> None:
        """Quita un aviso registrado con `suscribir()`."""
        self._avisos.cancelar(aviso)

    def _guardar(self, id_peticion: str, dato: dict[str, Any]) -> None:
        with self._lock:
            ahora = time.monotonic()
            self._datos.pop(id_peticion, None)  # reinsertar la deja como la mas nueva
            self._datos[id_peticion] = (ahora, dato)
            vencidos = [
                k for k, (t, _) in self._datos.items() if ahora - t > self.ttl_s
            ]
            for clave in vencidos:
                del self._datos[clave]
            while len(self._datos) > self.maximo:
                del self._datos[next(iter(self._datos))]  # la mas vieja
        self._avisos.avisar()

    def reservar(self, id_peticion: str) -> None:
        """Marca la revision como `en_curso` (ya se decidio, falta completarla).

        Se llama ANTES de sacarla de la cola: asi, quien espera nunca ve un
        instante en que no esta ni pendiente ni en curso.
        """
        self._guardar(id_peticion, {"estado": ESTADO_EN_CURSO})

    def olvidar(self, id_peticion: str) -> None:
        """Descarta una reserva (la peticion no existia)."""
        with self._lock:
            self._datos.pop(id_peticion, None)

    def registrar(
        self, id_peticion: str, estado: str, respuesta: str | None = None
    ) -> None:
        """Guarda el resultado final de una revision y avisa a quien espera."""
        if estado not in ESTADOS_FINALES:
            raise ValueError(f"estado final invalido: {estado!r}")
        dato: dict[str, Any] = {"estado": estado}
        if respuesta is not None:
            dato["respuesta"] = respuesta
        self._guardar(id_peticion, dato)

    def consultar(self, id_peticion: str) -> dict[str, Any] | None:
        """Estado guardado de `id_peticion`, o None si no hay (o ya caduco)."""
        with self._lock:
            hallado = self._datos.get(id_peticion)
            if hallado is None:
                return None
            if time.monotonic() - hallado[0] > self.ttl_s:
                del self._datos[id_peticion]
                return None
            return dict(hallado[1])


# Instancia compartida por proxy/main.py (rate limiting) y
# mecanismos.enviar_a_revision() (encolar). Un solo proceso de uvicorn por
# contenedor (ver docker-compose.yml): un lock en memoria de proceso es
# suficiente, no hace falta coordinacion entre procesos.
cola_global = ColaRevision()

resultados_global = ResultadosRevision()
