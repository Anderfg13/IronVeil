# Identidad de IronVeil

Referencia de la marca para el chat de la demo (`/demo`), la consola de revisión humana (`/revision/ui`) y el inicio de sesión. Decidida en una entrevista el 2026-10-06; los valores de color de esta página se comprueban contra `proxy/static/consola.css` en `tests/test_consola_accesibilidad.py`.

## Idea

**Hierro y velo.** El hierro es lo que protege (grafito, sólido, quieto). El velo es lo que deja ver con claridad sin estorbar (vidrio azul glaciar, translúcido). El logo, los colores y las superficies cuentan lo mismo: una capa de vidrio sobre algo firme.

**Personalidad** (elegida): *protectora* y *serena*. Quien revisa una petición retenida debe decidir sin ansiedad; quien conversa en la demo debe sentir calma, no vigilancia.

**Voz:** breve, sin culpa y sin jerga. «No puedo ayudarte con ese mensaje.» (no «Tu mensaje fue bloqueado por…»). Nada de interjecciones ni signos de exclamación. Los avisos al usuario nunca nombran mecanismos de defensa.

## Logo

Hexágono burdeos con un velo blanco en forma de «V» y un punto de luz, junto al nombre «**Iron**Veil» y el lema «Defensa en profundidad para LLMs».

| Archivo | Uso |
| --- | --- |
| `docs/identidad/ironveil-logo.png` | Logo completo (icono + nombre + lema), fondo blanco: README, informe y diapositivas. |
| `docs/identidad/ironveil-icono.png` | Solo el hexágono, fondo transparente, 256 px. |
| `proxy/static/logo.png` | El mismo icono, el que muestran la consola, el login y la pestaña del navegador. |
| `docs/identidad/logo_*.svg` | Propuestas anteriores (escudo de grafito y vidrio), solo como historial. |

- **Tamaños:** el icono de 20 a 160 px; por debajo de 20 px usa solo el hexágono, sin el nombre.
- **Zona libre:** un cuarto del ancho del hexágono por cada lado.
- **Nombre:** «**Iron**Veil» como texto en la interfaz (`.nombre-marca`); en el logo completo ya viene dibujado.
- **No:** girarlo, estirarlo, cambiarle los colores, añadirle sombras o ponerlo repetido en la misma pantalla.

### Cómo poner otro logo

1. Guarda el tuyo como `proxy/static/logo.png` (cuadrado, fondo transparente; si es `.svg`, cambia la ruta en `revision.html`, `login.html` y `demo.html`).
2. Cabe solo en la caja `.marca-logo` (36 px en las barras, 64 px en el login; se cambia con `--logo` en el CSS) y se ajusta con `object-fit: contain`.
3. Reconstruye con `docker compose up -d --build proxy`: los estáticos van dentro de la imagen.

## Color

Dirección elegida: **azul glaciar + grafito**. El azul es el único color de marca; el resto son neutros fríos. Rojo, ámbar y verde solo significan estado (ataque, atención, correcto) y siempre van acompañados de forma o texto.

| Token | Claro | Oscuro | Rol |
| --- | --- | --- | --- |
| `--bg` | `#e8eef6` | `#090d12` | Fondo de página (bajo el hielo) |
| `--panel` | `#fbfdff` | `#10161d` | Superficie principal; es la base del vidrio |
| `--panel-2` | `#f0f5fa` | `#151d26` | Superficie secundaria (pestañas, evidencia) |
| `--ink` | `#0d1319` | `#ecf1f6` | Texto principal |
| `--ink-2` | `#414f5e` | `#aab7c5` | Texto secundario |
| `--ink-3` | `#536171` | `#8595a8` | Texto de apoyo (ayudas, tiempos) |
| `--line` | `#d3dce6` | `#243040` | Separadores (decorativos) |
| `--borde` | `#72849a` | `#66778b` | Límite de un control (3:1 mínimo) |
| `--iron` | `#181f27` | `#070a0e` | Grafito: barra superior y avisos |
| `--iron-ink` | `#eaf0f6` | `#eaf0f6` | Texto sobre grafito |
| `--veil` | `#0a63c9` | `#66b2ff` | Azul glaciar: acción principal, foco, burbuja propia |
| `--veil-soft` | `#dbeafc` | `#112640` | Azul suave: selección y contadores |
| `--on-veil` | `#ffffff` | `#06111d` | Texto sobre azul |
| `--hielo` | `#5aaeff` | `#1f6fd0` | Luz de marca (solo decorativa) |
| `--hielo-1` | `#cfe3fa` | `#0f2744` | Luz superior izquierda bajo el vidrio |
| `--hielo-2` | `#dde8f6` | `#0d1b2c` | Luz superior derecha bajo el vidrio |
| `--attack` | `#b3261e` | `#ff8d83` | Ataque |
| `--warn` | `#8f5400` | `#f0b24a` | Atención |
| `--media` | `#b87400` | `#d98c0a` | Gravedad media (marca con forma de rombo) |
| `--ok` | `#13795b` | `#55d4a8` | Correcto / falso positivo |

Contrastes medidos (claro / oscuro): texto principal sobre fondo 16,0 / 17,1; texto secundario 7,2 / 9,6; texto de apoyo 5,4 / 6,4; texto sobre azul 5,8 / 8,5; azul sobre superficie 5,7 / 8,1; texto sobre grafito 14,5 / 17,3. Con `prefers-contrast: more` el texto secundario sube a 7:1.

## Tipografía

**La del sistema**, sin archivos: San Francisco en Apple, Segoe UI Variable en Windows, Roboto en Android. Carga instantánea, se siente nativa y no necesita relajar la CSP.

- Interfaz: `--ui` (`system-ui, -apple-system, "SF Pro Text", "Segoe UI Variable Text"…`). Cuerpo 14 px en escritorio y 16 px en móvil.
- Títulos: `--display` (`"SF Pro Display"`, `"Segoe UI Variable Display"`), peso 650, tracking ajustado (−0,015 a −0,025 em).
- Datos (identificadores, evidencia, vectores): `--mono` (`ui-monospace`, SF Mono, Cascadia Mono).
- Mínimo 12 px; tamaños en `rem`; nunca peso fino en texto pequeño.

## Vidrio (liquid glass)

Una capa translúcida, con desenfoque y un canto de luz arriba, sobre una luz suave de hielo. Está en la **capa funcional** (barra superior, caja de mensaje, tarjetas, barra de decisión, diálogos y avisos) y nunca dentro del contenido.

Reglas:

1. **El texto largo no va sobre vidrio claro**: las superficies de lectura son casi opacas (78 % claro / 72 % oscuro) y se mide el contraste contra todo lo que puede haber detrás (`tests/test_consola_accesibilidad.py`).
2. **Siempre hay alternativa opaca**: sin `backdrop-filter`, con `prefers-reduced-transparency`, con `prefers-contrast: more` y en colores forzados el vidrio pasa a superficie sólida con borde.
3. **El límite de un campo no es de vidrio**: la caja de mensaje conserva un borde `--borde` (3:1).
4. **Un solo nivel**: no se apila vidrio sobre vidrio.

Por qué no se usa la librería [liqui.design](https://liqui.design/docs): se instala con `shadcn` y exige React, Tailwind v4 y una dependencia de npm, y la consola es HTML/CSS/JS sin build y con CSP estricta. El efecto se reproduce con CSS nativo. Lo que aporta de más (refracción real con filtros SVG) solo funciona en Chromium y necesitaría un mapa de desplazamiento como archivo propio; queda como mejora opcional.

## Forma y movimiento

- Radios generosos y concéntricos: barra 22, tarjetas 18, caja de mensaje 26, botones y selectores en cápsula.
- Una sola acción principal por pantalla, en azul glaciar.
- Movimiento breve y opcional: respeta `prefers-reduced-motion` y nada depende de una animación para entenderse.
- La apariencia sigue al sistema (claro/oscuro); no hay interruptor de tema.
