# Weave Bands en el móvil — diseño

## Intención

El usuario quiere usar Weave Bands **él mismo en su móvil Android**, por la calle, igual que ya hace con
Weave Stocks. No se publica en Google Play: se instala como app desde el navegador (PWA).

## Objetivos

- La app funciona sola en el móvil, **sin el PC ni servidor propio**.
- El mapa, la búsqueda, desplegar, `/from`, la corona y las familias funcionan **sin conexión** con lo
  último descargado.
- Con conexión: suena la música (previews de Deezer) y se pueden añadir artistas que no están en los datos.
- Se maneja con el dedo en pantalla vertical (como Stocks: toques de 44 px, teclado que tapa media vista).
- El escritorio sigue funcionando igual.

## No objetivos

- Google Play / TWA.
- Manejar Spotify (Premium + Web API): mejora posterior si el usuario la pide.
- Last.fm y Wikidata en vivo desde el móvil (sus claves y su contacto no salen del PC).
- Música sin conexión.

## Anti-objetivos

- Que algo se vea a medio cargar o que la app se rompa sin red.
- Meter claves (Last.fm) o el contacto de Wikidata dentro de la app publicada.
- Publicar datos personales: solo se exporta la red de artistas, nunca `resources/` ni el export de Spotify.

## Enfoques considerados

- **A. App sola + datos exportados (elegido por el usuario).** Igual que Stocks. Funciona en cualquier
  sitio; lo nuevo llega con lo básico de Deezer hasta la siguiente exportación.
- B. El móvil usa el servidor del PC por la wifi: completo pero solo en casa y con el PC encendido.
- C. Las dos: lo más completo y lo más complejo de mantener.

## Diseño

**Datos.** `python -m weave.export` escribe `weave/static/data/weave.json` (ignorado en git):
artistas (id, nombre, fans, foto como el hash de Deezer, familia, géneros, país, id de Deezer) y
relaciones con su motivo (similar con su puntuación combinada, member, influence), ya ordenadas como hoy
las sirve `Store.artist`. Más `version` para saber si hay datos nuevos. Objetivo: < 3 MB.

**La página sin API.** `index.html` deja de depender de `/api/*`: carga `weave.json` y resuelve en el
navegador la búsqueda (normalizando como `weave/text.py`), las relacionadas, las familias y los caminos
(BFS bidireccional, como `weave/graph.py`). Un único camino de código para móvil y escritorio; el
servidor Python queda como herramienta de desarrollo que sirve los estáticos.

**En vivo (con red).** Deezer por JSONP (su API no permite llamadas normales desde otra web):
- canciones del artista para la música (las URLs caducan: nunca se guardan);
- buscar un artista que no está en los datos y desplegar sus relacionados de Deezer (familia por los
  géneros de sus discos, como el respaldo actual). Sin red, la búsqueda solo ve los datos.

**Instalable y sin conexión.** `manifest.json`, iconos (del logo de Weave) y `sw.js` como en Stocks:
la app y D3 (copiado al proyecto, ya no desde la CDN) se guardan al instalar; `weave.json` se baja de
nuevo cuando cambia `version`; las fotos se guardan al verlas (límite de unas 500); sin foto, el círculo
lleva su color de familia, como ahora.

**Móvil.** Lo validado en Stocks: botones del menú de 44 px, sin depender de hover ni doble clic,
encuadre en pantallas estrechas, la barra sobre el teclado. Se comprueba con capturas de 390 × 844.

**Publicar.** `python -I tools/publish.py`: exporta y sube `weave/static/` a la rama `gh-pages` de un
repositorio de GitHub del usuario (HTTPS gratis). GitHub Pages gratuito exige repositorio público: la red
de artistas es visible para quien tenga el enlace. Crear el repositorio y la primera subida se confirman
con el usuario. Actualizar: relanzar `publish` cuando crece la base de datos (a mano; tarea programada
si la pide).

**Pruebas.** Unitarias de la exportación; la prueba de humo pasa a usar `weave.json` (sin `/api`) y con
la red de Deezer cortada comprueba que el mapa sigue; `tools/pwa.py` como el de Stocks (service worker,
instalación, sin conexión); capturas de móvil.

## Decisiones mías (revisables)

- Una sola página para móvil y escritorio, siempre sobre `weave.json`.
- Fotos: solo las vistas se guardan; el resto se ve con conexión.
- Publicación manual con un comando, sin tarea diaria.
- Esto es la **Fase 3** del ROADMAP (explorador definitivo: sin conexión y D3 local), orientada a móvil;
  «guardar mapas» y «deshacer» quedan para después.

## Para quien lo construya

Orden de tareas, nombres internos del JSON y el detalle del service worker. Reutilizar de Weave_stocks
(`sw.js`, `manifest.json`, `tools/pwa.py`, la parte móvil de `index.html`) copiando y adaptando, sin
importar nada de ese repositorio.
