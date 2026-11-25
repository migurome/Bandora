# Weave · Hoja de ruta

## Para qué es

Un buscador visual de música para **descubrir grupos nuevos** y **ver la huella de tus gustos**.
Escribes una banda, aparece un círculo; con doble clic se abren sus relacionadas como una red
neuronal que va creciendo. Tus listas de Spotify se pueden volcar en el grafo, y se puede trazar
el camino de un artista a otro (Marea → … → Michael Jackson).

A futuro, cada usuario tendrá su perfil local construido a partir de su export de Spotify.

## Punto de partida: la prueba de concepto (`poc/`)

Validada en noviembre de 2026. Qué funciona y se conserva como comportamiento de referencia:

| Comportamiento | Detalle |
|---|---|
| Búsqueda → círculo origen | Barra superior a todo el ancho |
| Clic = ficha, doble clic = relacionadas | Ficha en barra lateral a toda altura, sin scroll, iconos Deezer/Spotify/quitar |
| Máximo 5 conexiones por artista | Sin repeticiones; las bandas se reparten en abanico hacia fuera |
| Nada entra al grafo a medio cargar | Arco de carga en la banda que se explora |
| Listas de Spotify y «Mi top» | Desplegable; pila lateral izquierda con salida animada hacia el grafo; se puede interactuar mientras carga |
| Camino de x a y | Botón «De → a»; cadena dorada con n artistas intermedios |
| Filtro de género | La leyenda oculta/muestra familias |
| Quitar | Botón o tecla Supr; se lleva la rama que colgaba de esa banda |
| Huella | Aro dorado en las bandas que ya escuchas |
| Sonidos de burbuja | Silenciables |
| Colores pastel por familia | Nombre dentro del círculo |

Descartado en la prueba (no volver a meterlo sin motivo): enlaces indirectos punteados, vista
de géneros al alejar el zoom, contadores (fans, conexiones), botón «Mi huella».

### Lo que aprendimos y condiciona el diseño

1. **Un nombre no identifica a un artista.** Deezer duplica fichas («B.B. King» / «B.B.King») y
   mezcla homónimos (Leño con un rapero italiano). Hace falta un identificador propio con los ids
   de cada fuente cruzados.
2. **Consultar en vivo es lento.** MusicBrainz admite 1 petición/s: una lista de 146 artistas
   tarda ~5 min la primera vez. Hay que tener los datos **antes**, en una base de datos local.
3. **Los géneros de MusicBrainz son pobres** (casi todo «rock») y los de Deezer a veces erróneos.
   Faltan familias (clásica, bandas sonoras, folk…).
4. **Las relacionadas de Deezer son buenas para descubrir**, pero solo 25 por artista y no simétricas;
   algunos artistas no tienen ninguna.
5. **El camino entre artistas funciona** con búsqueda bidireccional priorizando bandas populares
   (hacen de puente entre estilos), pero en vivo puede tardar 20 s o no encontrarlo.

---

## Fases

Cada fase termina con algo que se puede usar. El orden pone primero los datos porque casi todos
los problemas de la prueba vienen de ahí.

### Fase 1 · Base de datos de artistas

**Objetivo:** que todo lo que hoy se consulta en vivo salga de una base de datos local, rápida y sin duplicados.

- Base de datos local (SQLite) con: artistas, ids por fuente (Deezer, MusicBrainz, Spotify, Wikidata),
  géneros, familias y relaciones (con su orden de parecido y su fuente).
- Resolución de identidad: un artista = un registro aunque tenga varias fichas o nombres;
  los homónimos se separan por id de MusicBrainz.
- Ingesta con respeto al ritmo de cada API, reanudable si se corta, y que reaproveche `poc/cache/`.
- Semilla: los artistas de tu export de Spotify + sus relacionadas a dos saltos (unos miles de artistas).
- El servidor de la prueba pasa a leer de la base de datos; la web no cambia.

**Hecho cuando:** cargar «Mercurio» (146 artistas) tarda segundos, no minutos; B.B. King sale una
sola vez; el camino Marea → Michael Jackson se calcula sin conexión.

### Fase 2 · Géneros y relaciones de calidad

**Objetivo:** que el color y las conexiones signifiquen algo.

- Géneros finos y grado de parecido desde Last.fm (necesita clave gratuita).
- Sinergias desde Wikidata: miembros compartidos, colaboraciones, influencias. Se guardan como tipos de relación distintos.
- Taxonomía de familias revisada (añadir clásica, bandas sonoras, folk, cantautor…) y editable.
- Relación combinada: peso a partir de varias fuentes, para elegir las 5 mejores con más criterio.

**Hecho cuando:** Leño sale como rock y no como hip hop; la lista «Classic» no aparece toda gris;
en la ficha se ve por qué dos artistas están relacionados.

### Fase 3 · Explorador definitivo

**Objetivo:** convertir la prueba en la aplicación, sin perder lo validado (tabla de arriba).

- Reescritura ordenada del front (módulos, sin parches) y del servidor (API sobre la base de datos).
- Rendimiento con cientos de nodos (valorar canvas/WebGL si SVG no aguanta).
- Deshacer, guardar y recuperar mapas en local.
- Ficha enriquecida con lo de la fase 2 (por qué está relacionado, sinergias).
- Pruebas automáticas de lo crítico: límite de 5, no duplicar, quitar rama, camino, carga en cola.

**Hecho cuando:** la prueba de concepto se puede borrar.

### Fase 4 · Tu huella

**Objetivo:** el segundo propósito del proyecto: ver tus gustos.

- Perfil local a partir del export: peso por artista (minutos, recencia, listas, «Me gusta»).
- Importar el historial ampliado de Spotify (pendiente de recibir) para tener todos los años.
- «Mi mapa»: tus familias de género, tus zonas de confort y las zonas vacías.
- Evolución en el tiempo: cómo cambia el mapa año a año.
- Integrar aquí la web de estadísticas actual (`web/`, generada por `build.py`).

**Hecho cuando:** abres la app y ves tu mapa sin buscar nada.

### Fase 5 · Descubrimiento

**Objetivo:** que la app te proponga música, no solo que la explores.

- Bandas puente: artistas que no escuchas pero se relacionan con muchos de los tuyos.
- Rutas guiadas: de tu zona de confort hacia un estilo que elijas, paso a paso.
- Exportar lo descubierto a una lista de Spotify (requiere conectar la cuenta).

**Hecho cuando:** la app te recomienda grupos que acabas guardando.

### Fase 6 · Varios perfiles y empaquetado

**Objetivo:** que otra persona pueda usarlo con su propio export.

- Varios perfiles locales (cada uno con su export), sin mezclar datos.
- Instalación sencilla en local.
- Documentación de uso.

---

## Decisiones pendientes

- **Clave de Last.fm** (fase 2): ¿la sacamos?
- **Tecnología del explorador definitivo** (fase 3): seguir con HTML + D3 sin framework, o pasar a un framework.
- **Alcance de los perfiles** (fase 6): ¿solo local o algún día publicado?

## Datos del usuario

`resources/` contiene el export personal de Spotify. Pagos, dirección e identificadores no se usan
en ninguna fase. Nada se publica sin decisión expresa.
