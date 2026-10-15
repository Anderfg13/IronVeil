# Autenticación del proxy

Por defecto el laboratorio está **abierto**: los scripts de ataque llaman a `POST /chat` sin credenciales y las 7
configuraciones se miden así. La autenticación es **opcional** y se activa solo con variables de entorno.

| Qué protege | Variable | Cómo se pasa la credencial |
|---|---|---|
| Consola de revisión (`/revision/*`) | `REVISION_USUARIOS` | Formulario de login (sesión en cookie `HttpOnly`) |
| Chat (`POST /chat`, `GET /chat/revision/{id}`) | `CHAT_REQUIERE_AUTENTICACION=1` | `Authorization: Basic` (curl, scripts) o la sesión de `/demo` |

Las dos usan **las mismas cuentas** (`usuario:rol:hash`, hash scrypt con sal propia): una sola lista, un solo lugar.

## Usuario de prueba (sin claves en el código)

```bash
python -m proxy.auth --demo          # crea la cuenta "admin" con una clave ALEATORIA
```

Escribe `REVISION_USUARIOS=admin:revisor:<hash>` en tu `.env` y la clave en `credenciales-demo.local.txt` (Git lo ignora).
Cada máquina genera la suya: **no existe una clave por defecto publicada**, que es justo lo que se quiere evitar.

```bash
# en .env
CHAT_REQUIERE_AUTENTICACION=1
docker compose up -d proxy

curl -u admin:LA_CLAVE_DEL_ARCHIVO -X POST http://localhost:8000/chat \
  -H 'Content-Type: application/json' -d '{"modelo":"soporte","mensaje":"hola"}'
# sin -u  ->  401 (con WWW-Authenticate: Basic)
```

## Comportamiento

- **Falla cerrada:** con `CHAT_REQUIERE_AUTENTICACION=1` y sin cuentas configuradas, `/chat` responde `503`; nunca deja pasar.
- **Fuerza bruta:** 5 fallos por usuario o por IP en 5 minutos bloquean con `429`; la verificación cuesta lo mismo exista o
  no el usuario (no revela cuentas válidas).
- **Sesión de `/demo`:** cookie `SameSite=Strict`; `POST /chat` con cookie exige además la cabecera `X-CSRF-Token`
  (la pantalla la envía sola).
- **Conectar la identidad de una empresa** (LDAP, SSO, base de datos): implementar `ProveedorAutenticacion` y registrarlo con
  `proxy.auth.registrar_proveedor()`; el resto no cambia (ver `proxy/auth.py`).
- **Mensajes genéricos:** el detalle de un fallo se registra en el servidor, nunca en la respuesta.

## Para los experimentos

No actives `CHAT_REQUIERE_AUTENTICACION` mientras corres los vectores de ataque (`ataques/`): los scripts no envían
credenciales y cambiar eso alteraría lo medido. Es una capa de despliegue, no uno de los 5 mecanismos del experimento.
