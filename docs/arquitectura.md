# Arquitectura (semana 1)

```
cliente --> proxy FastAPI (puerto 8000, publicado al host)
              |
              v
         Ollama (red interna de Docker, sin puerto publicado)
              |-- modelo "soporte" (canario SPT-DEMO-8841)
              +-- modelo "rrhh"    (canario RRHH-DEMO-2291)
```

- El proxy es el unico punto de entrada expuesto al host. Ollama solo es
  alcanzable desde otros contenedores en la red `ironveil-net`.
- `POST /chat` recibe `{modelo, mensaje}` y reenvia tal cual a
  `POST /api/chat` de Ollama, devolviendo la respuesta sin modificar
  (passthrough puro, sin mecanismos defensivos todavia).
- Los canarios (credenciales ficticias) viven en el `SYSTEM` prompt de
  cada modelo y se usan para medir, en semanas futuras, si algun
  mecanismo de defensa evita o permite su fuga.
- Los mecanismos defensivos (filtrado, delimitacion, clasificacion,
  minimo privilegio, aprobacion humana) se agregaran como middleware en
  el proxy en las siguientes iteraciones, cada uno activable por
  separado.
