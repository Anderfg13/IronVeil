# Normalización de entrada (extensión opcional)

Cubre un hueco concreto: **los ataques que se esconden**. Un filtro que busca «ignora las
instrucciones anteriores» no ve esa frase si llega en Base64, en hexadecimal, en ROT13 o dentro de
caracteres Unicode invisibles; Prompt Guard tampoco (ve ruido). Con un modelo pequeño como
`llama3.2:1b` esto no se nota (no sabe decodificar, así que la orden escondida nunca funciona), pero
con un modelo más capaz sí es una puerta abierta. Detalle del hallazgo: `docs/GARAK.md`.

> **Es una extensión, no un mecanismo nuevo ni parte del núcleo.** Está **apagada por defecto**. Con
> ella encendida, C0–C6 **no** son las configuraciones medidas en el experimento: cada evento lleva
> `es_extension: true` y su bloque `normalizacion`. No se enciende durante las mediciones del núcleo.

## Qué hace

Actúa **antes** de la cadena de mecanismos y no reemplaza a ninguno:

1. **Quita los caracteres invisibles** (el bloque «Tags», selectores de variación, espacios de ancho
   cero, marcas de dirección…). El modelo recibe el mensaje **limpio**.
2. **Lee lo que esos invisibles escondían**: los del bloque «Tags» son ASCII disfrazado (`goodside.Tag`
   de Garak) y se leen como texto.
3. **Decodifica Base64, hexadecimal y ROT13**, hasta dos capas (un Base64 dentro de un hex), y solo si
   el resultado es texto imprimible. Lo que parece lenguaje se junta en una **variante**.
4. La cadena revisa el mensaje limpio y, si no bloqueó, **una segunda pasada revisa la variante** con
   los **mismos mecanismos** (filtrado, clasificación, mínimo privilegio, según su bandera). El primero
   que bloquea gana; el log dice que fue en la variante (`bloqueo_en_variante`).

```
mensaje ─► [normalizar] ─► texto limpio ─► cadena ─► (modelo recibe el texto limpio)
                │                           │
                └──► variante decodificada ─┘  segunda pasada con los mismos mecanismos
```

Importante: al modelo **no** se le entrega lo decodificado; recibe el mensaje limpio tal como lo
escribió el usuario. La extensión no cambia lo que dice el usuario: muestra a los mecanismos lo que
estaba escondido y quita lo invisible.

## Cómo se enciende

```
NORMALIZACION_ENTRADA=1
NORMALIZACION_DECODIFICADORES=base64,hex,rot13   # opcional; es el valor por defecto
NORMALIZACION_ADAPTADORES=mi_empresa.mi_codificacion   # opcional: decodificadores propios
```

Sin mecanismos activos (C0) la extensión **no bloquea nada** por sí sola: solo quita lo invisible.
Quien juzga lo decodificado son los mecanismos; no es una defensa independiente.

## Qué se midió

`python analisis/medir_normalizacion.py` (determinista: sin LLM ni red; informe en
`analisis/normalizacion_deteccion.md`). Con 6 ataques que el filtro ya bloquea en claro:

| Cómo se esconde | Sin la extensión | Con la extensión |
|---|---:|---:|
| Base64 | 0/6 | 6/6 |
| Hexadecimal | 0/6 | 6/6 |
| ROT13 | 0/6 | 6/6 |
| Caracteres invisibles (tags) | 0/6 | 6/6 |

Y **0 de 18 mensajes legítimos bloqueados** (incluidos hashes, UUID, números largos, palabras largas,
un Base64 inofensivo y emojis). En `/chat` (`tests/test_normalizacion_integracion.py`) se comprueba
de punta a punta: sin la extensión el ataque escondido pasa el filtro (200); con ella lo bloquea el
mismo mecanismo (400) y el modelo no llega a verlo.

**Límites de esa medición (no los omitas al citarla):** son **6 ataques**, una muestra que demuestra
el mecanismo y no estima una tasa; solo mide el **filtro** (Prompt Guard y Llama Guard no se evaluaron
con la variante); y solo mide el hueco de la **ofuscación**, no la cobertura general del filtro.

## Límites conocidos

- **Solo cubre lo que conoce.** Base64, hexadecimal, ROT13 y caracteres invisibles. Un cifrado propio,
  más de dos capas, leetspeak, reemplazo de palabras, otros idiomas o una paráfrasis **no** se cubren.
  Es una capa más de la defensa en profundidad, no un seguro.
- **ROT13 se detecta por lenguaje natural** (español e inglés): el mensaje completo se acepta solo si
  su ROT13 parece lenguaje y el original no. En otro idioma no se detecta.
- **No toca `U+200C` ni `U+200D`** (unen letras en otros alfabetos y emojis): un atacante podría
  esconder datos ahí. Sí quita los selectores de variación, que cambian el estilo de algún emoji
  (`❤️` → `❤`): cosmético.
- **Un mensaje hecho para saturar** (más de 64 tramos codificados, o una variante de más de 50 000
  caracteres) se corta; el evento lo marca con `truncada: true`. No se bloquea por eso: un adjunto
  legítimo en Base64 no debe romper el servicio.
- **Falsos positivos:** solo se inspecciona lo decodificado que parece texto; un hash o un
  identificador no. Un token JWT o un adjunto en Base64 sí se decodifican y se inspeccionan (pasan si
  no dicen nada malicioso).
- **Costo:** una segunda pasada por la cadena **solo cuando algo se decodificó** (los mensajes
  normales no pagan nada extra). El tiempo de esa pasada se suma al de cada pieza.
- **Si la extensión falla** (un error de programación, no del usuario) el mensaje **sigue sin
  normalizar**, el evento lleva `normalizacion.error: true` y se registra la traza (sin el texto).
  Es la excepción consciente a «fail closed»: es una capa adicional, y que se rompa no debe tumbar el
  servicio. Los mecanismos siguen protegiendo igual que sin la extensión.

## Qué queda en el log

El campo extendido `normalizacion` (solo con la extensión encendida; **conteos, nunca texto**):

```json
{"invisibles_eliminados": 11,
 "decodificaciones": {"base64": 1, "tags_unicode": 1},
 "variante_inspeccionada": true,
 "bloqueo_en_variante": true}
```

`truncada` y `error` aparecen solo si ocurrieron. Los 8 campos base no cambian.

## Agregar tu propia codificación sin editar IronVeil

Un decodificador es un objeto con un `nombre` y un método `decodificar(texto) -> list[str]` que
devuelve las cadenas imprimibles que salen de decodificar tramos del texto (qué merece inspeccionarse
lo decide el servicio):

```python
# mi_empresa/mi_codificacion.py
class DecodificadorMio:
    nombre = "mio"

    def decodificar(self, texto: str) -> list[str]:
        ...  # nunca debe lanzar por una entrada rara

def registrar(registro) -> None:
    registro.registrar("mio", DecodificadorMio)
```

```
NORMALIZACION_ADAPTADORES=mi_empresa.mi_codificacion
NORMALIZACION_DECODIFICADORES=base64,hex,rot13,mio
```

El módulo se importa y se ejecuta con los permisos del proxy: solo código de confianza. Solo se
aceptan nombres de módulo.

## Cómo está construida

El mismo patrón de puertos y adaptadores que `proxy/siem/` y `proxy/memoria_decisiones/`, vigilado por
pruebas de arquitectura (`tests/test_normalizacion_servicio.py`): `dominio` (qué es invisible y qué es
texto legible, sin E/S) → `puerto` (`Decodificador`) → `servicio` (`Normalizador`, puro) → `registro`
(un objeto) → `decodificadores/` (un adaptador por codificación) → `composicion` (el único lugar que
lee el entorno). `proxy/main.py` solo conoce `normalizacion.analizar()`.
