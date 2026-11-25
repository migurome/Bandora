# Weave Bands · Hoja de ruta

## Para qué es

Un explorador visual de música para **descubrir grupos nuevos** y, más adelante, **ver la huella de tus gustos**.
Escribes un artista, aparece su círculo con su foto y la red de grupos relacionados va creciendo a tu
alrededor, como neuronas que se conectan. Se puede trazar el camino de un artista a otro
(Marea → … → Michael Jackson) y escuchar sus canciones sin salir del mapa.

Todo en local. A futuro, cada usuario tendrá su perfil construido a partir de su export de Spotify.

## Comportamiento validado (referencia para todas las fases)

Validado por el usuario en noviembre de 2026 sobre la prueba de concepto, ya integrada en `weave/`.

| Comportamiento | Detalle |
|---|---|
| Barra = terminal | Texto normal busca artistas (Intro añade el primer resultado); comandos con `/`: `/from A to B`, `/label on\|off`, `/clear`. Al escribir `/` se listan. Error = la barra tiembla en rojo, sin mensajes |
| Autocompletado en comandos | En `/from` se sugieren artistas para A y para B; Tab, clic o Enter completan el nombre exacto |
| Círculo = foto del artista | Recorte circular con aro del color de su familia de género; nombre debajo |
| Clic | Un clic abre el círculo (ampliado, con menú en semicírculo por debajo); otro clic lo cierra. Sin doble clic |
| Menú del círculo | Desplegar (amarillo) · conector · ▶/❚❚ · siguiente canción · quitar · Spotify |
| Conector | Arrastrar desde el conector: un cable suelto cuelga hasta el puntero; al soltarlo en otro círculo se conecta, «corre» y los artistas del camino salen de él |
| Máximo 5 conexiones por artista | Desplegar desde el botón amarillo del menú; sin repeticiones (nombre normalizado); abanico hacia fuera; aro punteado cuando está completo |
| Nada entra a medio cargar | Arco que gira en la banda que se explora; los artistas entran ya completos |
| Logo de Weave animado = trabajando | Grande en el centro con el mapa vacío; pequeño en la barra si hay bandas |
| Música | Preview de las 10 canciones más escuchadas; pausa real; al acabar sigue la siguiente; el círculo que suena se oscurece con ▶ encima |
| Pie | ▶/❚❚ (seleccionado o lo que suena) y ✕ (limpia y para la música) |
| Camino | `/from A to B`: cadena dorada con n intermedios, artistas uno a uno |
| Géneros | Ocultos por defecto; `/label on` muestra la leyenda, que es también filtro |
| Quitar | Papelera del menú o Supr; se lleva la rama que colgaba de la banda |
| Marca | Con el mapa vacío, logo y «weave bands» en el centro |
| Sonidos de burbuja | Siempre activos |
| Interfaz sin texto | Iconos y colores en vez de etiquetas: usable en cualquier idioma |

**Descartado** (no volver a meterlo sin motivo): enlaces indirectos punteados, vista de géneros al
alejar el zoom, contadores, ficha lateral, pila de carga, carga de listas en la interfaz (se importarán
en la fase de tu huella), marcas de «tu huella» en el mapa, botones de silenciar y de fotos.

### Lo que aprendimos y condiciona el diseño

1. **Un nombre no identifica a un artista.** Deezer duplica fichas («B.B. King» / «B.B.King») y mezcla
   homónimos (Leño con un rapero italiano). → Identidad propia con ids de cada fuente cruzados (hecho en fase 1).
2. **Consultar en vivo es lento** (MusicBrainz: 1 petición/s). → Base de datos local (hecho en fase 1).
3. **Los géneros de MusicBrainz son pobres** y los de Deezer a veces erróneos; faltan familias
   (clásica, bandas sonoras, folk…). → Fase 2.
4. **Las relacionadas de Deezer son buenas para descubrir**, pero solo 25 por artista y no simétricas.
5. **Las URLs de preview caducan**: las canciones se piden siempre en vivo, no se guardan.
6. **En Windows, `localhost` prueba antes IPv6**: el servidor escucha en `127.0.0.1` y `::1`.

---

## Fases

### Fase 1 · Base de datos de artistas — ✅ hecha (25/11/2026)

SQLite local (`data/weave.db`) con identidad por fuente, MBID y nombre; ingesta reanudable con ritmo
por API; semilla desde tu export; caminos sin red; el servidor lee de la base de datos.
Plan: `docs/superpowers/plans/2026-11-25-fase1-base-de-datos.md`.

Criterios comprobados: B.B. King sale una sola vez · Marea → Michael Jackson sin red (0,0 s, 7 intermedios)
· un artista ya visto se abre al instante (~26 ms). El criterio original de «cargar Mercurio en segundos»
dejó de aplicar al salir las listas de la interfaz.

Pendiente operativo: el rastreo inicial va por 176 de ~2.500 (`python -m weave.ingest crawl`, reanudable).

### Fase 2a · Last.fm y familias — ✅ hecha (25/11/2026)

Géneros y parecidos de Last.fm (clave en `data/lastfm_key.txt`, fuera de git) con prioridad sobre
MusicBrainz y Deezer; familias en un único sitio editable (`weave/families.json`) con dos nuevas:
Clásica / Bandas sonoras y Folk / Cantautor; las 5 que se despliegan combinan el parecido de Last.fm
con el orden de Deezer. Relleno: `python -m weave.ingest lastfm` (858 artistas).
Plan: `docs/superpowers/plans/2026-11-25-fase2a-lastfm-familias.md`.

Criterios comprobados: Leño → Rock (rock urbano) · Vivaldi y Hans Zimmer → Clásica / Bandas sonoras ·
Camarón → Latina / Flamenco · Marea despliega primero Extremoduro y La Fuga.

### Fase 2b · Sinergias de Wikidata

- Miembros compartidos, colaboraciones e influencias como relaciones de otro tipo.
- Mostrar por qué dos artistas están conectados, sin texto (estilo de línea o icono).

**Hecho cuando:** dos bandas con un miembro en común aparecen conectadas aunque no «suenen» parecidas.

### Fase 3 · Explorador definitivo

**Objetivo:** pulir la aplicación sobre la base ya integrada.

- Funcionar sin internet para lo ya visto (D3 incluido en el proyecto, no desde CDN; fotos en caché).
- Deshacer, guardar y recuperar mapas en local.
- Rendimiento con cientos de bandas (valorar canvas si SVG no aguanta).
- Ampliar la prueba de humo (`tools/smoke.py`) con cada comportamiento nuevo.

**Hecho cuando:** se puede usar un mapa guardado sin conexión.

### Fase 4 · Tu huella

**Objetivo:** el segundo propósito del proyecto: ver tus gustos.

- Perfil local a partir del export: peso por artista (minutos, recencia, listas, «Me gusta»).
- Importar tus listas y el historial ampliado de Spotify (pendiente de recibir).
- «Mi mapa»: tus familias de género, tus zonas de confort y las zonas vacías.
- Evolución en el tiempo, año a año.
- Integrar la web de estadísticas (`tools/spotify-stats/`).

**Hecho cuando:** abres la app y ves tu mapa sin buscar nada.

### Fase 5 · Descubrimiento

- Bandas puente: artistas que no escuchas pero se relacionan con muchos de los tuyos.
- Rutas guiadas: de tu zona de confort hacia un estilo que elijas.
- Exportar lo descubierto a una lista de Spotify (requiere conectar la cuenta).

**Hecho cuando:** la app te recomienda grupos que acabas guardando.

### Fase 6 · Varios perfiles y empaquetado

- Varios perfiles locales (cada uno con su export), sin mezclar datos.
- Instalación sencilla y documentación de uso.

---

## Decisiones pendientes

- **Alcance de los perfiles** (fase 6): ¿solo local o algún día publicado?

## Datos del usuario

`resources/` contiene el export personal de Spotify: no se sube al repositorio. Pagos, dirección e
identificadores no se usan en ninguna fase. Nada se publica sin decisión expresa.
