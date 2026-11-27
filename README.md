# Bandora

Explorador visual de música: escribes un artista, aparece su círculo y la red de grupos relacionados va
creciendo a tu alrededor. Es una app de móvil (se instala desde el navegador) que funciona sola: los datos van
dentro y sirven sin conexión; con red suena la música y se pueden añadir artistas nuevos desde Deezer.

## Arrancar

```bash
python -m weave.server          # http://localhost:8766
```

Requisitos: Python 3.12 (solo librería estándar). La página lee `weave/static/data/weave.json`: genéralo antes con
`python -m weave.export` (y cada vez que crezca la base de datos).

## En el móvil

1. Publicar: `python -I tools/publish.py <remoto de GitHub>` exporta y sube la app a la rama `gh-pages`; en GitHub,
   Settings → Pages → rama `gh-pages`. Queda en `https://<usuario>.github.io/<repositorio>/` (el repositorio de
   Pages gratuito es público: cualquiera con el enlace ve la red de artistas; nada personal).
2. Instalar: abrir esa dirección en Chrome del móvil → ⋮ → «Instalar app».
3. Sin conexión funciona con los últimos datos descargados; al abrirla con red recoge los nuevos.

## Uso

| Acción | Cómo |
|---|---|
| Añadir artista | Escríbelo en la barra y elige una sugerencia |
| Abrir / cerrar su menú | Clic en el círculo |
| Menú del círculo | Desplegar relacionadas · corona · ▶/❚❚ · siguiente canción · quitar · Spotify |
| Favoritas | Corona del menú; ✕ deja solo las favoritas y un segundo ✕ borra todo |
| Desplegar relacionadas | Botón amarillo del menú (máx. 5 conexiones por artista) |
| Conectar dos artistas | Arrastra el botón amarillo del menú hasta otro círculo |
| Mover un círculo | Arrástralo: se queda donde lo sueltes |
| Quitar artista | Papelera del menú o Supr (se lleva la rama que colgaba de él) |
| Camino entre artistas | `/from Marea to Michael Jackson` (Tab completa los nombres) |
| Leyenda y filtro de géneros | `/tag on` · `/tag off` |
| Limpiar mapa y parar música | `/clear` o ✕ (dos veces si hay favoritas) |
| Deshacer el último cambio del mapa | `/undo` o Ctrl+Z |
| Guardar y recuperar mapas (en el móvil, sin conexión) | `/save nombre` · `/load nombre` |
| Lista de comandos y enlace a la ayuda (`ayuda.html`) | `/help` |
| Esperas | «searching» en la barra y un minijuego (Pong o burbujas, por turnos) |
| Probar los minijuegos | `/debug pong` · `/debug bobble` · `/debug off` (o `?debug=bobble` en la dirección) |

## Base de datos de artistas

`data/weave.db` (SQLite, fuera del repositorio). Se rellena sola al explorar y, de golpe, con:

```bash
python -m weave.ingest seed     # encola tus artistas del export de Spotify (resources/)
python -m weave.ingest crawl    # los completa (reanudable; Ctrl+C para parar)
python -m weave.ingest lastfm   # géneros y parecidos de Last.fm (clave en data/lastfm_key.txt)
python -m weave.ingest wikidata # miembros e influencias (contacto en data/wikidata_contact.txt)
python -m weave.ingest status
```

## Pruebas

```bash
python -m unittest discover -s tests -t . -v   # unitarias (sin red)
python -I tools/smoke.py                        # interfaz en Edge sin ventana (servidor arrancado)
python -I tools/pwa.py                          # instalable y sin conexión (servidor arrancado)
```

## Estructura

| Ruta | Qué es |
|---|---|
| `weave/` | Paquete: servidor, base de datos, ingesta, grafo, clientes de Deezer, MusicBrainz, Last.fm y Wikidata |
| `weave/static/` | La página (HTML + D3) |
| `tests/` | Pruebas unitarias |
| `tools/` | Prueba de humo de la interfaz y la web de estadísticas de Spotify |
| `docs/` | Planes de cada fase |
| `ROADMAP.md` | Hoja de ruta |
