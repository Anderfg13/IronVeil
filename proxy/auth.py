"""Autenticacion de la consola de revision humana (mecanismo 5).

Hasta ahora `/revision` era abierto: cualquiera que alcanzara el puerto 8000
podia aprobar una peticion que un mecanismo habia retenido. Este modulo agrega
inicio de sesion, sin dependencias nuevas (solo biblioteca estandar):

- **Opt-in.** Con `REVISION_USUARIOS` vacia (el valor por defecto) no hay login
  y todo se comporta como antes: los scripts de ataque y los tests del
  experimento no cambian. Con la variable definida, los endpoints de revision
  exigen sesion.
- **Cuentas.** `REVISION_USUARIOS=usuario:rol:hash,usuario2:rol:hash`. El rol es
  `revisor` (puede aprobar y rechazar) u `observador` (solo ve). El hash lo
  genera `python -m proxy.auth` (scrypt con sal propia): nunca hay claves en
  texto plano ni valores por defecto.
- **Conexion con la empresa.** `ProveedorAutenticacion` es la interfaz (patron
  Adapter, igual que `proxy/siem/`): una organizacion que quiera validar
  contra su LDAP, su base de datos de usuarios o su SSO implementa
  `autenticar(usuario, clave) -> Identidad | None` y la registra con
  `registrar_proveedor()`. El resto (sesiones, CSRF, limite de intentos) no
  cambia. `ProveedorLocal` es la implementacion de referencia.
- **Sesion.** Token aleatorio (`secrets`) en una cookie `HttpOnly`,
  `SameSite=Strict` y `Secure`; expira por inactividad. Las acciones que
  cambian estado exigen ademas la cabecera `X-CSRF-Token` de esa sesion.
- **Fuerza bruta.** Maximo de fallos por usuario y por IP en una ventana; la
  verificacion de clave cuesta lo mismo exista o no el usuario (no revela
  cuentas validas).

Las sesiones viven en memoria del proceso: reiniciar el proxy las cierra.
"""

from __future__ import annotations

import base64
import getpass
import hashlib
import hmac
import logging
import os
import secrets
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)

ENV_USUARIOS = "REVISION_USUARIOS"
ENV_SESION_MINUTOS = "REVISION_SESION_MINUTOS"
ENV_COOKIE_SECURE = "REVISION_COOKIE_SECURE"
ENV_CHAT_AUTENTICACION = "CHAT_REQUIERE_AUTENTICACION"

NOMBRE_COOKIE = "ironveil_sesion"
ESQUEMA_BASIC = "basic"
REINO_BASIC = "IronVeil"
CABECERA_CSRF = "X-CSRF-Token"
ROL_REVISOR = "revisor"
ROL_OBSERVADOR = "observador"
ROLES_VALIDOS = (ROL_REVISOR, ROL_OBSERVADOR)

SESION_INACTIVIDAD_MINUTOS_DEFECTO = 30
SESION_DURACION_MAXIMA_S = 8 * 3600
MAXIMO_SESIONES = 200

INTENTOS_FALLIDOS_MAXIMOS = 5
VENTANA_INTENTOS_S = 300
MAXIMO_CLAVES_LIMITADOR = 5000

# Parametros de scrypt (memoria = 128 * N * r bytes = 16 MiB).
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_LONGITUD = 32
_PREFIJO_HASH = "scrypt"
LONGITUD_MAXIMA_CLAVE = 256


# --- Hash de claves ---------------------------------------------------------


def _b64(datos: bytes) -> str:
    return base64.urlsafe_b64encode(datos).rstrip(b"=").decode("ascii")


def _desb64(texto: str) -> bytes:
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


def _derivar(clave: str, sal: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(
        clave.encode("utf-8"),
        salt=sal,
        n=n,
        r=r,
        p=p,
        dklen=_SCRYPT_LONGITUD,
        maxmem=256 * n * r,
    )


def hashear_clave(clave: str) -> str:
    """Hash scrypt con sal aleatoria: `scrypt.N.r.p.sal.hash`.

    Solo usa letras, digitos, `.`, `-` y `_`: es seguro dentro de un `.env`
    (sin `$`, `;`, `|` ni espacios que el shell o Docker Compose interpreten).
    """
    sal = secrets.token_bytes(16)
    derivado = _derivar(clave, sal, _SCRYPT_N, _SCRYPT_R, _SCRYPT_P)
    return ".".join(
        [
            _PREFIJO_HASH,
            str(_SCRYPT_N),
            str(_SCRYPT_R),
            str(_SCRYPT_P),
            _b64(sal),
            _b64(derivado),
        ]
    )


def verificar_clave(clave: str, almacenado: str) -> bool:
    """Compara `clave` con un hash de `hashear_clave()` en tiempo constante.

    Un hash mal formado devuelve False (nunca lanza ni deja pasar).
    """
    try:
        prefijo, n, r, p, sal, esperado = almacenado.split(".")
        if prefijo != _PREFIJO_HASH or len(clave) > LONGITUD_MAXIMA_CLAVE:
            return False
        derivado = _derivar(clave, _desb64(sal), int(n), int(r), int(p))
        return hmac.compare_digest(derivado, _desb64(esperado))
    except (ValueError, TypeError):
        return False


# Hash de relleno: si el usuario no existe se verifica contra este, para que
# la respuesta tarde lo mismo y no delate que cuentas existen.
_HASH_RELLENO = hashear_clave(secrets.token_urlsafe(16))


# --- Proveedores de identidad -----------------------------------------------


@dataclass(frozen=True)
class Identidad:
    """Quien inicio sesion y que puede hacer."""

    usuario: str
    rol: str

    @property
    def puede_decidir(self) -> bool:
        return self.rol == ROL_REVISOR


class ProveedorAutenticacion(Protocol):
    """Adapter hacia el sistema de identidad de la organizacion (LDAP, base de
    datos de usuarios, SSO...). Debe devolver None ante credenciales invalidas
    y NO lanzar por eso; un error de infraestructura si puede lanzar."""

    def autenticar(self, usuario: str, clave: str) -> Identidad | None: ...


class ProveedorLocal:
    """Implementacion de referencia: cuentas con hash scrypt en `REVISION_USUARIOS`."""

    def __init__(self, cuentas: dict[str, tuple[str, str]]) -> None:
        self._cuentas = cuentas

    @classmethod
    def desde_texto(cls, texto: str) -> ProveedorLocal:
        """Parsea `usuario:rol:hash,...`. Falla ruidosamente si algo esta mal
        formado: una cuenta mal escrita no debe ignorarse en silencio."""
        cuentas: dict[str, tuple[str, str]] = {}
        for entrada in filter(None, (e.strip() for e in texto.split(","))):
            partes = entrada.split(":", 2)
            if len(partes) != 3 or not all(partes):
                raise ValueError(
                    f"{ENV_USUARIOS}: entrada con formato invalido (usuario:rol:hash)"
                )
            usuario, rol, hash_clave = partes
            if rol not in ROLES_VALIDOS:
                raise ValueError(f"{ENV_USUARIOS}: rol desconocido {rol!r}")
            if not hash_clave.startswith(_PREFIJO_HASH + "."):
                raise ValueError(f"{ENV_USUARIOS}: hash invalido para {usuario!r}")
            cuentas[usuario.lower()] = (rol, hash_clave)
        return cls(cuentas)

    def autenticar(self, usuario: str, clave: str) -> Identidad | None:
        cuenta = self._cuentas.get(usuario.strip().lower())
        hash_clave = cuenta[1] if cuenta else _HASH_RELLENO
        valida = verificar_clave(clave, hash_clave)
        if cuenta and valida:
            return Identidad(usuario=usuario.strip().lower(), rol=cuenta[0])
        return None


_proveedor_registrado: ProveedorAutenticacion | None = None


def registrar_proveedor(proveedor: ProveedorAutenticacion | None) -> None:
    """Sustituye el proveedor de identidad (LDAP, SSO, BD...). None vuelve al
    local por entorno."""
    global _proveedor_registrado
    _proveedor_registrado = proveedor


def auth_habilitada() -> bool:
    """True si hay un proveedor registrado o cuentas definidas en el entorno."""
    return _proveedor_registrado is not None or bool(
        os.environ.get(ENV_USUARIOS, "").strip()
    )


def obtener_proveedor() -> ProveedorAutenticacion:
    """Proveedor activo (el registrado o el local construido desde el entorno)."""
    if _proveedor_registrado is not None:
        return _proveedor_registrado
    return ProveedorLocal.desde_texto(os.environ.get(ENV_USUARIOS, ""))


# --- Limite de intentos -----------------------------------------------------


class LimitadorIntentos:
    """Cuenta fallos por clave (usuario o IP) en una ventana deslizante."""

    def __init__(
        self,
        maximo: int = INTENTOS_FALLIDOS_MAXIMOS,
        ventana_s: float = VENTANA_INTENTOS_S,
    ) -> None:
        self._maximo = maximo
        self._ventana_s = ventana_s
        self._fallos: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _purgar(self, clave: str, ahora: float) -> list[float]:
        recientes = [
            t for t in self._fallos.get(clave, []) if ahora - t < self._ventana_s
        ]
        if recientes:
            self._fallos[clave] = recientes
        else:
            self._fallos.pop(clave, None)
        return recientes

    def bloqueado(self, clave: str) -> bool:
        with self._lock:
            return len(self._purgar(clave, time.monotonic())) >= self._maximo

    def registrar_fallo(self, clave: str) -> None:
        with self._lock:
            ahora = time.monotonic()
            if len(self._fallos) >= MAXIMO_CLAVES_LIMITADOR:
                # `.copy()`: _purgar() borra claves del dict mientras se recorre.
                for k in self._fallos.copy():
                    self._purgar(k, ahora)
            if len(self._fallos) < MAXIMO_CLAVES_LIMITADOR:
                self._fallos.setdefault(clave, []).append(ahora)

    def reiniciar(self, clave: str) -> None:
        with self._lock:
            self._fallos.pop(clave, None)


limitador = LimitadorIntentos()


# --- Sesiones ---------------------------------------------------------------


@dataclass
class Sesion:
    identidad: Identidad
    csrf: str
    creada: float
    ultima_actividad: float


class GestorSesiones:
    """Sesiones en memoria, con expiracion por inactividad y duracion maxima."""

    def __init__(self) -> None:
        self._sesiones: dict[str, Sesion] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _inactividad_s() -> float:
        try:
            minutos = float(
                os.environ.get(ENV_SESION_MINUTOS, SESION_INACTIVIDAD_MINUTOS_DEFECTO)
            )
        except ValueError:
            minutos = SESION_INACTIVIDAD_MINUTOS_DEFECTO
        return max(minutos, 1.0) * 60

    def crear(self, identidad: Identidad) -> tuple[str, Sesion]:
        token = secrets.token_urlsafe(32)
        ahora = time.monotonic()
        sesion = Sesion(identidad, secrets.token_urlsafe(24), ahora, ahora)
        with self._lock:
            if len(self._sesiones) >= MAXIMO_SESIONES:
                mas_vieja = min(self._sesiones, key=lambda k: self._sesiones[k].creada)
                del self._sesiones[mas_vieja]
            self._sesiones[token] = sesion
        return token, sesion

    def obtener(self, token: str | None, actualizar: bool = True) -> Sesion | None:
        """Sesion vigente de `token`, o None (y la borra si ya vencio).

        Con `actualizar=False` solo consulta: no cuenta como actividad. Lo usa el
        canal en vivo de la consola, que esta abierto aunque nadie toque nada y
        no debe mantener viva una sesion inactiva.
        """
        if not token:
            return None
        with self._lock:
            sesion = self._sesiones.get(token)
            if sesion is None:
                return None
            ahora = time.monotonic()
            if (
                ahora - sesion.ultima_actividad > self._inactividad_s()
                or ahora - sesion.creada > SESION_DURACION_MAXIMA_S
            ):
                del self._sesiones[token]
                return None
            if actualizar:
                sesion.ultima_actividad = ahora
            return sesion

    def cerrar(self, token: str | None) -> None:
        if token:
            with self._lock:
                self._sesiones.pop(token, None)

    def vaciar(self) -> None:
        with self._lock:
            self._sesiones.clear()


sesiones = GestorSesiones()


def cookie_secure() -> bool:
    """Secure por defecto; `REVISION_COOKIE_SECURE=0` solo para HTTP en claro
    fuera de localhost (los navegadores aceptan Secure en http://localhost)."""
    return os.environ.get(ENV_COOKIE_SECURE, "1").strip() != "0"


def ip_cliente(request: Request) -> str:
    """IP del cliente directo. No se confia en X-Forwarded-For: el proxy se
    publica sin otro proxy delante (si lo hubiera, hay que configurarlo aparte)."""
    return request.client.host if request.client else "desconocido"


# --- Dependencias de FastAPI --------------------------------------------------


def sesion_de(request: Request) -> Sesion | None:
    """Sesion valida de la peticion (cookie), o None."""
    return sesiones.obtener(request.cookies.get(NOMBRE_COOKIE))


def exigir_lector(request: Request) -> Identidad | None:
    """Con autenticacion activa exige sesion; sin ella no hace nada (None)."""
    if not auth_habilitada():
        return None
    sesion = sesion_de(request)
    if sesion is None:
        raise HTTPException(status_code=401, detail="Inicia sesión para continuar.")
    return sesion.identidad


def exigir_revisor(request: Request) -> Identidad | None:
    """Como `exigir_lector`, pero ademas exige rol `revisor` y la cabecera CSRF
    de la sesion (estos endpoints cambian estado)."""
    if not auth_habilitada():
        return None
    sesion = sesion_de(request)
    if sesion is None:
        raise HTTPException(status_code=401, detail="Inicia sesión para continuar.")
    if not sesion.identidad.puede_decidir:
        raise HTTPException(status_code=403, detail="Tu rol no puede decidir.")
    enviado = request.headers.get(CABECERA_CSRF, "")
    if not hmac.compare_digest(enviado.encode(), sesion.csrf.encode()):
        raise HTTPException(status_code=403, detail="Token CSRF inválido.")
    return sesion.identidad


# --- Autenticacion del chat (POST /chat) ------------------------------------


def chat_auth_requerida() -> bool:
    """True si `CHAT_REQUIERE_AUTENTICACION=1`: `/chat` exige usuario y clave."""
    return os.environ.get(ENV_CHAT_AUTENTICACION, "").strip() == "1"


def _no_autorizado(detalle: str = "Autenticación requerida.") -> HTTPException:
    return HTTPException(
        status_code=401,
        detail=detalle,
        headers={"WWW-Authenticate": f'Basic realm="{REINO_BASIC}"'},
    )


def _credenciales_basic(request: Request) -> tuple[str, str] | None:
    """Usuario y clave de la cabecera `Authorization: Basic`, o None si no hay
    una cabecera Basic bien formada."""
    cabecera = request.headers.get("Authorization", "")
    esquema, _, valor = cabecera.partition(" ")
    if esquema.lower() != ESQUEMA_BASIC or not valor:
        return None
    try:
        usuario, separador, clave = (
            base64.b64decode(valor.strip(), validate=True)
            .decode("utf-8")
            .partition(":")
        )
    except ValueError:  # base64 mal formado o bytes que no son UTF-8
        return None
    return (usuario, clave) if separador and usuario else None


def _identidad_basic(request: Request) -> Identidad | None:
    """Valida Basic con el proveedor activo y el limite de intentos fallidos."""
    credenciales = _credenciales_basic(request)
    if credenciales is None:
        return None
    usuario, clave = credenciales
    clave_ip = "chat-ip:" + ip_cliente(request)
    clave_usuario = "chat-usuario:" + usuario.strip().lower()
    if limitador.bloqueado(clave_ip) or limitador.bloqueado(clave_usuario):
        logger.warning("chat: autenticacion bloqueada (ip=%s)", ip_cliente(request))
        raise HTTPException(status_code=429, detail="Demasiados intentos.")
    try:
        identidad = obtener_proveedor().autenticar(usuario, clave)
    except Exception:
        logger.exception("chat: el proveedor de identidad fallo")
        raise HTTPException(status_code=503, detail="Servicio no disponible.") from None
    if identidad is None:
        limitador.registrar_fallo(clave_ip)
        limitador.registrar_fallo(clave_usuario)
        logger.warning("chat: autenticacion fallida (ip=%s)", ip_cliente(request))
        return None
    limitador.reiniciar(clave_usuario)
    return identidad


def _identidad_de_sesion(request: Request) -> Identidad | None:
    """Identidad de la cookie de sesion de la consola/demo; si la peticion cambia
    estado exige ademas el token CSRF de esa sesion."""
    sesion = sesion_de(request)
    if sesion is None:
        return None
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        enviado = request.headers.get(CABECERA_CSRF, "")
        if not hmac.compare_digest(enviado.encode(), sesion.csrf.encode()):
            raise HTTPException(status_code=403, detail="Token CSRF inválido.")
    return sesion.identidad


def exigir_cliente(request: Request) -> Identidad | None:
    """Dependencia de `/chat`: opt-in con `CHAT_REQUIERE_AUTENTICACION=1`.

    Apagada (el valor por defecto) no hace nada, asi que los scripts de ataque y
    las pruebas del experimento no cambian. Encendida acepta `Authorization:
    Basic` (curl, scripts) o la sesion de la pantalla `/demo`. FALLA CERRADA: si
    esta encendida y no hay ninguna cuenta configurada, responde 503 en vez de
    dejar pasar a todos.
    """
    if not chat_auth_requerida():
        return None
    if not auth_habilitada():
        logger.error(
            "%s=1 pero no hay cuentas (%s)", ENV_CHAT_AUTENTICACION, ENV_USUARIOS
        )
        raise HTTPException(status_code=503, detail="Servicio no disponible.")
    identidad = _identidad_basic(request) or _identidad_de_sesion(request)
    if identidad is None:
        raise _no_autorizado()
    return identidad


# --- Herramienta de linea de comandos: generar la entrada de una cuenta -----


USUARIO_DEMO = "admin"
ARCHIVO_CLAVE_DEMO = "credenciales-demo.local.txt"


ARCHIVO_ENV = ".env"


def crear_cuenta_demo(directorio: Path, forzar: bool = False) -> str:
    """Crea la cuenta de demo `admin` (rol revisor, el maximo que existe) con una
    clave ALEATORIA y la deja lista para usar.

    Escribe `REVISION_USUARIOS=admin:revisor:<hash>` en el `.env` de `directorio`
    (conserva el resto del archivo) y la clave en `ARCHIVO_CLAVE_DEMO`, un archivo
    local que Git ignora. Los nombres de archivo son FIJOS: la funcion no recibe
    rutas de archivo, asi que ningun argumento puede apuntar a otro lugar.
    No hay clave por defecto escrita en el codigo: cada maquina genera la suya.
    Si ya hay cuentas definidas no las pisa, salvo con `forzar=True`.
    Devuelve el nombre de usuario.
    """
    ruta_env = directorio / ARCHIVO_ENV
    ruta_clave = directorio / ARCHIVO_CLAVE_DEMO
    crudo = ruta_env.read_bytes().decode("utf-8") if ruta_env.exists() else ""
    salto = "\r\n" if "\r\n" in crudo else "\n"
    lineas = crudo.splitlines()
    prefijo = f"{ENV_USUARIOS}="
    indice = next(
        (i for i, linea in enumerate(lineas) if linea.startswith(prefijo)), None
    )
    if indice is not None and lineas[indice][len(prefijo) :].strip() and not forzar:
        raise FileExistsError(f"{ENV_USUARIOS} ya tiene cuentas (usa --forzar).")
    clave = secrets.token_urlsafe(12)
    nueva = f"{prefijo}{USUARIO_DEMO}:{ROL_REVISOR}:{hashear_clave(clave)}"
    if indice is None:
        lineas += [
            "",
            "# Cuenta de demo de la consola (python -m proxy.auth --demo)",
            nueva,
        ]
    else:
        lineas[indice] = nueva
    ruta_env.write_text(salto.join(lineas) + salto, encoding="utf-8", newline="")
    ruta_clave.write_text(
        "Cuenta de demo de IronVeil (solo laboratorio; no la subas a ningun lado)\n"
        f"Usuario: {USUARIO_DEMO}\nClave: {clave}\n",
        encoding="utf-8",
    )
    try:
        ruta_clave.chmod(0o600)
    except OSError:  # Windows: los permisos POSIX no aplican
        logger.debug("no se pudo ajustar el permiso de %s", ruta_clave)
    return USUARIO_DEMO


def _cli_demo(argv: list[str]) -> int:
    try:
        usuario = crear_cuenta_demo(Path.cwd(), forzar="--forzar" in argv)
    except FileExistsError as exc:
        sys.stderr.write(f"{exc}\n")
        return 1
    sys.stdout.write(
        f"Cuenta creada: usuario '{usuario}' (rol revisor).\n"
        f"La clave quedo en {ARCHIVO_CLAVE_DEMO} (no se muestra aqui).\n"
        "Reinicia el proxy para aplicarla: docker compose up -d proxy\n"
        f"Para que /chat tambien la exija, pon {ENV_CHAT_AUTENTICACION}=1 en el .env.\n"
    )
    return 0


def cli(argv: list[str]) -> int:
    """`python -m proxy.auth USUARIO [ROL]`: pide la clave sin eco e imprime la
    entrada `usuario:rol:hash` para pegar en `REVISION_USUARIOS` del `.env`.
    `python -m proxy.auth --demo` crea la cuenta `admin` de demo ya configurada."""
    if not argv or argv[0] in ("-h", "--help"):
        sys.stdout.write(
            "Uso: python -m proxy.auth USUARIO [revisor|observador]\n"
            "Imprime la entrada para REVISION_USUARIOS (separa varias con comas).\n"
            "     python -m proxy.auth --demo [--forzar]\n"
            "Crea la cuenta 'admin' de demo con clave aleatoria (en el .env y en\n"
            f"{ARCHIVO_CLAVE_DEMO}).\n"
        )
        return 0 if argv else 2
    if argv[0] == "--demo":
        return _cli_demo(argv[1:])
    usuario = argv[0].strip().lower()
    rol = argv[1] if len(argv) > 1 else ROL_REVISOR
    if rol not in ROLES_VALIDOS or not usuario or ":" in usuario or "," in usuario:
        sys.stderr.write("Usuario o rol invalido.\n")
        return 2
    clave = getpass.getpass("Clave (no se muestra): ")
    if len(clave) < 10 or clave != getpass.getpass("Repite la clave: "):
        sys.stderr.write("Las claves no coinciden o tienen menos de 10 caracteres.\n")
        return 1
    sys.stdout.write(f"{usuario}:{rol}:{hashear_clave(clave)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(cli(sys.argv[1:]))
