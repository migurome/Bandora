# Fase 3 · App de móvil sola — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Weave Bands funciona sola en el móvil (PWA): mapa, búsqueda, desplegar y caminos sin conexión sobre datos exportados; música y artistas nuevos en vivo desde Deezer.

**Architecture:** `python -m weave.export` vuelca la base de datos a `weave/static/data/weave.json`. La página deja de usar `/api/*`: un módulo `weave/static/data.js` carga el JSON y resuelve búsqueda, ficha, relacionadas y caminos en el navegador; lo que no está en los datos y las canciones se piden a Deezer por JSONP. Un service worker guarda la app, D3, los datos y las fotos vistas. `tools/publish.py` sube `weave/static/` a GitHub Pages.

**Tech Stack:** Python 3.12 (solo stdlib), JavaScript sin dependencias salvo D3 v7 (copia local), Service Worker, Edge sin ventana para las pruebas.

**Spec:** `docs/superpowers/specs/2026-11-26-app-movil-design.md`

## Global Constraints

- Python 3.12, solo librería estándar. Pruebas con `unittest`.
- Sin claves ni el contacto de Wikidata dentro de la app publicada; nunca `resources/` ni datos personales.
- Solo los colores de la app; táctil primero (sin hover, objetivos ≥ 44 px donde se toque).
- Nada a medio cargar: un artista entra en el mapa con su ficha completa.
- `weave/static/data/` fuera de git (ya cubierto por `data/` en `.gitignore`).
- Servidor de desarrollo: `python -m weave.server` → http://localhost:8766 (sirve los estáticos).

## Review Focus

1. Sin conexión: buscar, desplegar y `/from` con lo exportado; la música falla en silencio (sin romper nada).
2. Artista que no está en los datos (búsqueda en vivo): entra con familia por los géneros de Deezer y se puede desplegar.
3. Un artista de los datos sin relacionadas (solo nombre): con red, despliega las de Deezer; sin red, aviso (temblor), sin colgarse.
4. Datos nuevos publicados: la app los recoge al volver a abrirla (versión), sin quedarse con la copia vieja para siempre.
5. Tamaño: `weave.json` < 3 MB y carga + índice en < 1 s en el móvil.

---

### Task 1: Exportación de la base de datos

**Files:**
- Create: `weave/export.py`
- Test: `tests/test_export.py`

**Interfaces:**
- Produces: `build(store) -> dict` y `python -m weave.export` → `weave/static/data/weave.json`:
  `{"version": str, "families": [{"name","color","pattern"}], "rockFirst": str,`
  ` "artists": [[id, name, fans, pic, deezerId, familyIdx, genre], ...],`
  ` "related": {"<id>": [[otherId, kind], ...]}}` — `pic` = hash de Deezer (32 hex) o URL completa o "";
  `kind` 0 similar, 1 influence, 2 member; `related` solo de artistas con relacionadas, en el orden de `Store.artist`.

- [ ] Prueba `test_export_shape`: dos artistas con relación member → `related[str(a)] == [[b, 2]]`, artista con
  foto `.../images/artist/<32hex>/250x250-...jpg` → `pic` es el hash, familia de «rock» → índice de Rock.
- [ ] Prueba `test_related_order_matches_store`: el orden de `related` es el de `store.artist(id)["related"]`.
- [ ] Verlas fallar; implementar; verlas pasar; suite completa; commit `feat(fase3): exportación a JSON estático`.

### Task 2: La página lee los datos exportados (sin `/api`)

**Files:**
- Create: `weave/static/data.js`
- Modify: `weave/static/index.html` (getArtist, searchArtists, weavePath, tracksOf; `<script src="data.js">`)
- Test: `tools/smoke.js` (la prueba de humo corre contra `weave.json`)

**Interfaces:**
- Produces (globales en `data.js`): `Data.ready: Promise`, `Data.search(q) -> [{id,name,fans,picture}]`,
  `Data.artist(id) -> Promise<full>` (misma forma que hoy `/api/artist`), `Data.path(a, b) -> [{id,name}] | null`,
  `Data.tracks(id) -> Promise<[{title, preview}]>`.

- [ ] Smoke: `ok('sin /api', !performance.getEntriesByType('resource').some(e => e.name.includes('/api/')))`.
- [ ] Verla fallar; implementar `data.js` (índice por `norm`, BFS bidireccional no dirigido como `weave/graph.py`);
  `tracks` aún por `/api/top` hasta la Tarea 3; smoke completa en verde; commit.

### Task 3: Deezer en vivo (JSONP)

**Files:** Modify `weave/static/data.js`; Test `tools/smoke.js`

**Interfaces:**
- Produces: `Data.tracks(id)` por JSONP (`/artist/{deezerId}/top?limit=10`); `Data.search` mezcla los resultados en
  vivo (ids `dz<deezerId>` si no están en los datos); `Data.artist('dz…')` y los artistas sin relacionadas piden a
  Deezer nombre, fans, foto, géneros del primer álbum (familia con las reglas exportadas) y `/related` (kind similar).

- [ ] Smoke: buscar un artista que no esté en los datos (o forzar `Data.artist('dz' + id)`) → ficha completa con
  familia y relacionadas; `Data.tracks` de Marea devuelve canciones con `preview`.
- [ ] Smoke: con `Data.offline = true` (simula sin red) la búsqueda devuelve lo local y desplegar un artista sin
  relacionadas hace temblar la barra sin colgarse.
- [ ] Implementar; verde; commit.

### Task 4: Instalable y sin conexión

**Files:** Create `weave/static/sw.js`, `weave/static/d3.min.js` (copia de D3 v7.9.2), `tools/pwa.py`;
Modify `weave/static/index.html` (D3 local, registrar el service worker).

- [ ] `tools/pwa.py` (como el de Stocks, puerto 8766): el service worker guarda `./`, `index.html`, `data.js`,
  `d3.min.js`, `manifest.json`, iconos y `data/weave.json`; imprime `ok …` o `MAL …`.
- [ ] `sw.js`: página, `data.js` y `weave.json` primero red y si no la copia; lo demás primero caché; fotos de
  Deezer (`/images/` en `dzcdn.net`) en caché aparte con límite de 500; nunca las canciones.
- [ ] Verlo fallar; implementar; `pwa.py` y smoke en verde; commit.

### Task 5: Publicar y documentar

**Files:** Create `tools/publish.py`; Modify `README.md`, `ROADMAP.md`.

- [ ] `publish.py`: exporta y sube `weave/static/` (sin `_smoke.html`) a la rama `gh-pages` de un repositorio
  remoto con `git worktree` temporal; recibe el remoto por argumento. **Crear el repositorio de GitHub y la
  primera subida se confirman con el usuario antes.**
- [ ] README (instalar en el móvil, publicar), ROADMAP (Fase 3 hecha); commit `docs: fase 3`.
