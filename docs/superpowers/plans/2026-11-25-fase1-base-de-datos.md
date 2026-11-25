# Fase 1 · Base de datos de artistas — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Todo lo que la prueba de concepto consulta en vivo (fichas, relacionadas, géneros, caminos) sale de una base de datos SQLite local, sin duplicados, y el explorador funciona igual que hoy.

**Architecture:** Paquete Python `weave/` (solo librería estándar) con capas separadas: texto/normalización, HTTP con ritmo por servicio, clientes Deezer y MusicBrainz, almacén SQLite con resolución de identidad, ingestor (bajo demanda + rastreo reanudable desde el export de Spotify) y grafo (relacionadas y caminos sin red). `poc/server.py` pasa a usar el almacén; el front (`poc/index.html`) no cambia: los ids que recibe pasan a ser ids internos.

**Tech Stack:** Python 3.12 (stdlib: `sqlite3`, `urllib`, `threading`, `unittest`), SQLite 3.49, front existente HTML + D3.

**Spec:** `ROADMAP.md` → «Fase 1 · Base de datos de artistas» (y «Lo que aprendimos»).

## Global Constraints

- Solo librería estándar de Python; no instalar paquetes (no hay pytest: las pruebas usan `unittest`).
- Ejecutar desde la raíz del proyecto: pruebas con `python -m unittest discover -s tests -t . -v`; CLI con `python -m weave.ingest …`; servidor con `python -I poc/server.py`.
- Base de datos en `data/weave.db`; `data/` no contiene nada más que la BD.
- Ritmo: MusicBrainz ≥ 1,1 s entre peticiones; Deezer ≥ 0,12 s. Reintentar HTTP 503 (esperas 2 s, 4 s, 6 s) y la respuesta Deezer `{"error": {"code": 4}}` (espera 5 s), máximo 4 intentos.
- User-Agent: `Weave/0.1 (prueba local)`.
- Del export (`resources/Spotify Account Data/`) solo se leen `StreamingHistory_music_*.json`, `Playlist1.json` y `YourLibrary.json`. Nunca Payments, UserAddress ni Identifiers.
- Puerto del servidor: 8766 (en el 8765 hay otro servidor del usuario: no tocarlo).
- Comentarios y mensajes en castellano.
- Comportamiento del front validado en la PoC (tabla de `ROADMAP.md`): no cambia en esta fase.
- El proyecto no es un repositorio git. Antes de la Tarea 1, preguntar al usuario si quiere `git init` (con `.gitignore` que excluya `data/`, `poc/cache/`, `resources/`). Si dice que sí, cada tarea termina con commit; si no, el paso de commit se sustituye por pasar todas las pruebas.

## Review Focus

1. **Rastreo interrumpido** (Ctrl+C, red caída a mitad): al relanzar continúa donde iba, sin filas duplicadas ni elementos perdidos en la cola. → Tarea 6, `test_crawl_resumes_after_failure`.
2. **El mismo artista por varias vías** (dos ids de Deezer, «B.B. King»/«B.B.King», stub que luego resulta ser otro ya existente): queda un único artista; sus relaciones se fusionan sin duplicados y sin relaciones consigo mismo. → Tarea 3, `test_merge_moves_everything_and_drops_self_relations`.
3. **Homónimos** (dos «Marea» con distinto MBID): siguen siendo dos artistas. → Tarea 3, `test_homonyms_with_different_mbid_stay_apart`.
4. **Peticiones simultáneas del servidor** (ThreadingHTTPServer + varias pestañas): sin `database is locked` ni datos a medias. → Tarea 2, `test_concurrent_writes_from_threads`.
5. **Artista sin relacionadas, sin coincidencia en MusicBrainz o con error de Deezer**: se guarda con lo que haya (géneros de Deezer de respaldo, relacionadas vacías) y el error queda anotado; nada se rompe. → Tarea 5, `test_full_ingest_without_musicbrainz_match_uses_deezer_genres` y Tarea 6, `test_crawl_records_errors`.

---

## Estructura de archivos

| Archivo | Responsabilidad |
|---|---|
| `weave/__init__.py` | vacío |
| `weave/text.py` | `norm()` |
| `weave/http.py` | `Fetcher`: GET JSON con ritmo por servicio y reintentos |
| `weave/sources.py` | `Deezer` y `MusicBrainz`: llamadas y parseo a dicts simples |
| `weave/db.py` | conexión y esquema |
| `weave/store.py` | `Store`: lecturas/escrituras, identidad y fusión |
| `weave/ingest.py` | `Ingestor` (bajo demanda) + rastreo, semilla, importación de la caché de la PoC y CLI |
| `weave/graph.py` | relacionadas para el grafo y caminos sin red |
| `poc/server.py` | API HTTP sobre `Store` + `Ingestor` |
| `tests/fakes.py` | `FakeDeezer`, `FakeMusicBrainz` en memoria |
| `tests/test_*.py` | una por módulo |

Niveles de carga de un artista (`artist.level`): `0` = stub (solo nombre/fans/id Deezer), `1` = relacionadas guardadas, `2` = completo (ficha + relacionadas + top + géneros). Una banda solo se muestra en el front si está a nivel 2 (regla de la PoC: nada a medio cargar).

---

### Task 1: Normalización y HTTP con ritmo

**Files:**
- Create: `weave/__init__.py`, `weave/text.py`, `weave/http.py`
- Test: `tests/__init__.py`, `tests/test_text.py`, `tests/test_http.py`

**Interfaces:**
- Produces: `norm(s: str) -> str`; `Fetcher(min_interval: dict[str, float], sleep=time.sleep, opener=urllib.request.urlopen)` con `get_json(url: str, service: str) -> dict | list`; constantes `DEEZER = "deezer"`, `MUSICBRAINZ = "musicbrainz"`.

- [ ] **Step 1: Pruebas que fallan**

```python
# tests/test_text.py
def test_norm_equivalences(self):
    self.assertEqual(norm("Platero Y Tu"), norm("Platero y tú"))
    self.assertEqual(norm("B.B. King"), norm("B.B.King"))
    self.assertEqual(norm("AC/DC"), "acdc")
    self.assertEqual(norm("Leño"), "leno")
    self.assertEqual(norm("坂本龍一"), "")   # sin caracteres latinos: el llamador usa otra clave

# tests/test_http.py  (opener falso que devuelve respuestas en orden; sleep falso que acumula)
def test_paces_per_service(self):            # dos GET seguidos a musicbrainz → sleep total ≥ 1.1 - tiempo transcurrido
def test_retries_503_then_succeeds(self):    # 503, 503, 200 → devuelve el JSON; sleeps incluyen 2 y 4
def test_retries_deezer_quota_error(self):   # {"error":{"code":4}} y luego {"data":[]} → devuelve {"data":[]}; un sleep de 5
def test_gives_up_after_4_attempts(self):    # cuatro 503 → lanza urllib.error.HTTPError
def test_sends_user_agent(self):             # la Request lleva "Weave/0.1 (prueba local)"
```

- [ ] **Step 2:** `python -m unittest discover -s tests -t . -v` → FAIL (`ModuleNotFoundError: weave`).
- [ ] **Step 3: Implementar.** `norm` igual que en `poc/server.py` (NFKD, sin tildes, solo `[a-z0-9]`). `Fetcher` porta `get_json` de `poc/server.py` con un lock y una marca de tiempo por servicio; `sleep` y `opener` inyectables para las pruebas.
- [ ] **Step 4:** pruebas → PASS.
- [ ] **Step 5:** commit `feat(fase1): normalización y HTTP con ritmo`.

---

### Task 2: Esquema y almacén básico

**Files:**
- Create: `weave/db.py`, `weave/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: `norm`.
- Produces:
  - `connect(path: str | Path) -> sqlite3.Connection` (crea el esquema si falta, `PRAGMA journal_mode=WAL`, `foreign_keys=ON`, `check_same_thread=False`).
  - `Store(conn)`; todas las escrituras bajo un `threading.Lock` del propio `Store` y dentro de una transacción.
  - `Store.upsert_deezer(deezer_id: int, name: str, fans: int = 0) -> int` → id interno; crea stub (nivel 0) o devuelve el existente por `(deezer, id)`. Registra el nombre como alias.
  - `Store.by_source(source: str, ext_id: str) -> int | None`
  - `Store.artist(artist_id: int) -> dict | None` con claves de la API actual de la PoC: `id, name, fans, picture, link, genres (list[str]), country, preview, previewTitle, related (list[{id,name,fans}]), level`.
  - `Store.set_details(artist_id, *, picture, link, fans, country, preview, preview_title)`
  - `Store.set_genres(artist_id, genres: list[tuple[str, int]], source: str)` (reemplaza los de esa fuente)
  - `Store.set_related(artist_id, related_ids: list[int], source="deezer")` (reemplaza; guarda el orden en `rank`) y sube el nivel a ≥ 1.
  - `Store.set_level(artist_id, level: int)` (nunca baja de nivel).
  - `Store.search(text: str, limit=6) -> list[dict]` por alias normalizado con prefijo (`LIKE norm||'%'`), nivel 2 primero y luego por fans.

Esquema (versión 1, en `db.py`):

```sql
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS artist (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, mbid TEXT UNIQUE, country TEXT, fans INTEGER DEFAULT 0,
  picture TEXT, link TEXT, preview TEXT, preview_title TEXT, level INTEGER NOT NULL DEFAULT 0, updated_at TEXT);
CREATE TABLE IF NOT EXISTS source_id (source TEXT, ext_id TEXT, artist_id INTEGER NOT NULL REFERENCES artist(id) ON DELETE CASCADE,
  PRIMARY KEY (source, ext_id));
CREATE TABLE IF NOT EXISTS alias (artist_id INTEGER NOT NULL REFERENCES artist(id) ON DELETE CASCADE, name TEXT, norm TEXT,
  PRIMARY KEY (artist_id, name));
CREATE INDEX IF NOT EXISTS alias_norm ON alias(norm);
CREATE TABLE IF NOT EXISTS genre (artist_id INTEGER NOT NULL REFERENCES artist(id) ON DELETE CASCADE, name TEXT, weight INTEGER, source TEXT,
  PRIMARY KEY (artist_id, name, source));
CREATE TABLE IF NOT EXISTS relation (a INTEGER NOT NULL REFERENCES artist(id) ON DELETE CASCADE, b INTEGER NOT NULL REFERENCES artist(id) ON DELETE CASCADE,
  kind TEXT NOT NULL DEFAULT 'similar', rank INTEGER, source TEXT NOT NULL, PRIMARY KEY (a, b, kind, source), CHECK (a <> b));
CREATE TABLE IF NOT EXISTS crawl (artist_id INTEGER PRIMARY KEY REFERENCES artist(id) ON DELETE CASCADE, target_level INTEGER, hops INTEGER,
  state TEXT DEFAULT 'pending', attempts INTEGER DEFAULT 0, error TEXT);
```

Orden de géneros en `Store.artist`: fuente `musicbrainz` antes que `deezer`, y por `weight` descendente; si no hay ninguno, `["sin género"]`.

- [ ] **Step 1: Pruebas que fallan** (BD en `":memory:"` salvo la de hilos, que usa un archivo temporal)

```python
def test_upsert_is_idempotent(self):         # dos upsert_deezer(3614, "B.B. King") → mismo id; 1 fila en artist
def test_artist_shape_matches_poc_api(self): # tras set_details/set_genres/set_related: claves exactas de la API; related en orden de rank
def test_genres_prefer_musicbrainz(self):    # set_genres([("rock",3)],"musicbrainz") y [("alternativo",1)],"deezer" → genres[0] == "rock"
def test_level_never_decreases(self):        # set_level(id,2) y luego set_level(id,1) → level == 2
def test_search_by_alias_prefix(self):       # "plat" encuentra "Platero y tú"; "b.b.k" encuentra "B.B. King"
def test_relation_rejects_self(self):        # set_related(a, [a, b]) → solo guarda a→b
def test_concurrent_writes_from_threads(self):  # 8 hilos × 50 upsert_deezer sobre el mismo archivo → sin excepciones, 400 artistas
```

- [ ] **Step 2:** pruebas → FAIL.
- [ ] **Step 3:** implementar `db.py` y `store.py` con las firmas de arriba.
- [ ] **Step 4:** pruebas → PASS.
- [ ] **Step 5:** commit `feat(fase1): esquema SQLite y almacén`.

---

### Task 3: Identidad y fusión

**Files:**
- Modify: `weave/store.py`
- Test: `tests/test_identity.py`

**Interfaces:**
- Produces:
  - `Store.attach_mbid(artist_id: int, mbid: str) -> int` → si otro artista ya tiene ese MBID, fusiona `artist_id` en él y devuelve el superviviente; si no, lo asigna.
  - `Store.merge(keep: int, drop: int) -> int` → mueve `source_id`, `alias`, `genre` y relaciones de `drop` a `keep` (sin duplicar ni crear `a == b`), conserva el nivel máximo, los fans máximos, el nombre del que tenga más fans y los detalles no nulos; borra `drop`; devuelve `keep`.
  - `Store.dedupe_by_name(artist_id: int) -> int` → si hay otro artista con el mismo `norm(name)` y **ninguno de los dos** tiene MBID distinto del otro (ambos nulos, o uno nulo), fusiona y devuelve el superviviente (el de menor id).

Regla de identidad (de lo aprendido en la PoC): 1) mismo `(fuente, id)` → mismo artista; 2) mismo MBID → mismo artista; 3) mismo nombre normalizado sin MBIDs en conflicto → mismo artista; 4) MBIDs distintos → artistas distintos aunque se llamen igual.

- [ ] **Step 1: Pruebas que fallan**

```python
def test_same_mbid_merges_two_deezer_ids(self):     # 3614 y 54984 «B.B. King» + attach_mbid(mismo) → 1 artista, 2 source_id
def test_same_name_without_mbid_merges(self):       # «B.B. King» y «B.B.King» sin MBID → dedupe_by_name → 1 artista
def test_homonyms_with_different_mbid_stay_apart(self):  # dos «Marea» con MBID distinto → dedupe_by_name no fusiona
def test_merge_moves_everything_and_drops_self_relations(self):
    # x→drop y drop→x, drop→y, keep→y ; merge(keep, drop) → keep→y una sola vez, ninguna fila con a == b,
    # x→keep existe, alias de ambos presentes, level = max, fans = max
def test_merge_keeps_name_of_most_popular(self):     # keep fans 10 «B.B.King», drop fans 1.7M «B.B. King» → name «B.B. King»
```

- [ ] **Step 2:** pruebas → FAIL.
- [ ] **Step 3:** implementar las tres funciones. Para relaciones: `INSERT OR IGNORE … SELECT` reescribiendo `drop`→`keep` y `DELETE … WHERE a = b` antes de borrar `drop`.
- [ ] **Step 4:** pruebas → PASS.
- [ ] **Step 5:** commit `feat(fase1): identidad por fuente, MBID y nombre; fusión`.

---

### Task 4: Clientes Deezer y MusicBrainz

**Files:**
- Create: `weave/sources.py`
- Create: `tests/fakes.py`
- Test: `tests/test_sources.py`

**Interfaces:**
- Consumes: `Fetcher`, `norm`.
- Produces (todas devuelven estructuras simples; los clientes reciben un `Fetcher`):
  - `Deezer.artist(id) -> {id, name, fans, picture, link}`; lanza `SourceError` si la respuesta trae `error`.
  - `Deezer.related(id, limit=25) -> list[{id, name, fans}]`
  - `Deezer.top(id) -> {title, preview} | None`
  - `Deezer.album_genres(id) -> list[str]` (géneros del primer álbum, en minúsculas; de respaldo)
  - `Deezer.search(q, limit=10) -> list[{id, name, fans, picture}]`
  - `MusicBrainz.lookup(name) -> {mbid, country, genres: list[tuple[str, int]]} | None` — coincidencia con `score ≥ 95`, primero nombre idéntico (sin distinguir mayúsculas), si no igual por `norm`; géneros oficiales y, si no hay, etiquetas del resultado de búsqueda; máximo 3, por `count` descendente.
  - `class SourceError(Exception)`
  - `tests/fakes.py`: `FakeDeezer` y `FakeMusicBrainz` con la misma interfaz, alimentados con dicts, y un contador de llamadas por método.

- [ ] **Step 1: Pruebas que fallan** (Fetcher falso que devuelve JSON fijo por URL)

```python
def test_mb_prefers_exact_name(self):         # resultados «Leno»(100) y «Leño»(100) buscando «Leño» → el MBID de «Leño»
def test_mb_falls_back_to_tags(self):         # sin genres; tags rock urbano(2), hard rock(1) → [("rock urbano",2),("hard rock",1)]
def test_mb_no_match_below_95(self):          # único resultado score 88 → None
def test_deezer_error_payload_raises(self):   # {"error":{"type":"DataException"}} → SourceError
def test_deezer_related_shape(self):          # → [{"id":4163,"name":"Extremoduro","fans":…}, …] en el orden de la API
```

- [ ] **Step 2:** pruebas → FAIL.
- [ ] **Step 3:** implementar portando `mb_genres`, `deezer_genre`, `search` y `related` de `poc/server.py`.
- [ ] **Step 4:** pruebas → PASS.
- [ ] **Step 5:** commit `feat(fase1): clientes Deezer y MusicBrainz`.

---

### Task 5: Ingestor bajo demanda

**Files:**
- Create: `weave/ingest.py`
- Test: `tests/test_ingest.py`

**Interfaces:**
- Consumes: `Store` (Tareas 2–3), `Deezer`, `MusicBrainz`.
- Produces: `Ingestor(store, deezer, mb)` con:
  - `ensure_full(artist_id: int) -> int` → deja el artista en nivel 2 y devuelve su id (puede cambiar si una fusión lo absorbe). Pasos: ficha Deezer → `set_details`; top → preview; `mb.lookup(name)` → `attach_mbid` + `set_genres(…, "musicbrainz")` + país; si MB no da géneros, `album_genres` → `set_genres(…, "deezer")`; relacionadas → `upsert_deezer` de cada una + `set_related`; `dedupe_by_name`; `set_level(2)`. Si ya está en nivel 2, no llama a ninguna fuente.
  - `ensure_related(artist_id: int) -> int` → nivel ≥ 1 solo con `Deezer.related` (sin MusicBrainz).
  - `resolve_name(name: str) -> int | None` → busca por alias normalizado en la BD; si no, `Deezer.search` y se queda con el de más fans entre los de `norm` idéntico (como `resolve` de la PoC); crea el stub; devuelve id o `None`.
  - `search(text: str) -> list[dict]` → `Deezer.search` en vivo convertido a ids internos (vía `upsert_deezer`), sin duplicados por id interno, con un resultado por artista (el de más fans); si la red falla, `Store.search(text)`.

- [ ] **Step 1: Pruebas que fallan** (con `FakeDeezer`/`FakeMusicBrainz`)

```python
def test_full_ingest_sets_level_genres_related(self):   # Marea → level 2, genres[0]=="rock", 6 related en orden, preview presente
def test_full_ingest_is_cached(self):                   # segunda llamada → contadores de los fakes sin cambios
def test_full_ingest_without_musicbrainz_match_uses_deezer_genres(self):  # MB None → genres == ["alternativo","rock"]
def test_two_deezer_ids_same_artist_become_one(self):   # ensure_full(3614) y ensure_full(54984) con mismo MBID → mismo id devuelto, 1 artista
def test_resolve_name_matches_normalized(self):         # "Platero Y Tu" → artista «Platero y tú»; "Nadie Existe" → None
def test_related_only_skips_musicbrainz(self):          # ensure_related → mb.lookup no llamado, level == 1
```

- [ ] **Step 2:** pruebas → FAIL.
- [ ] **Step 3:** implementar.
- [ ] **Step 4:** pruebas → PASS.
- [ ] **Step 5:** commit `feat(fase1): ingestor bajo demanda`.

---

### Task 6: Semilla, rastreo reanudable, importación de la caché y CLI

**Files:**
- Modify: `weave/ingest.py`
- Test: `tests/test_crawl.py`

**Interfaces:**
- Consumes: `Ingestor`, `Store`.
- Produces:
  - `spotify_artists(export_dir: Path) -> list[str]` → nombres únicos (por `norm`) de historial, playlists y «Me gusta», ordenados por minutos escuchados y después por canciones guardadas.
  - `seed(ingestor, names: list[str]) -> int` → `resolve_name` de cada uno y encola con `target_level=2, hops=0`; devuelve cuántos encoló. Reanudable: lo ya encolado no se duplica.
  - `crawl(ingestor, limit: int | None = None, on_progress=None) -> dict` → procesa la cola `pending` por `hops` ascendente y fans descendente; `target_level 2` → `ensure_full`, `1` → `ensure_related`. Al completar un artista con `hops == 0`, encola sus relacionadas con `target_level=1, hops=1`. Error → `attempts+1`, `error` guardado, vuelve a `pending` hasta 3 intentos; luego `state='error'`. Devuelve `{"done": n, "errors": n, "pending": n}`.
  - `import_poc_cache(store, cache_dir: Path) -> int` → convierte `artist_*.json` (nivel 2), `related_*.json` (nivel 1) y `resolve_*.json` (alias) de `poc/cache/` sin llamar a la red (2.108 archivos hoy).
  - CLI `python -m weave.ingest {import-poc | seed | crawl [--limit N] | status}`; `status` imprime artistas por nivel y la cola por estado. Ctrl+C durante `crawl` termina el artista en curso y sale sin dejar nada a medias.

Volumen esperado (para el mensaje de `status`, no para las pruebas): ~1.270 artistas semilla a nivel 2 (~1 h la primera vez por MusicBrainz) y sus relacionadas a nivel 1 (~20 min).

- [ ] **Step 1: Pruebas que fallan**

```python
def test_spotify_artists_order_and_dedupe(self):   # export mínimo en tmp: "Marea" (674 min) antes que "Robe" (663); "Platero Y Tu"/"Platero y tú" una vez
def test_seed_is_idempotent(self):                 # seed dos veces → filas en crawl sin cambios
def test_crawl_promotes_neighbours(self):          # 1 semilla → tras crawl: semilla level 2, sus related level 1, ninguna en pending
def test_crawl_resumes_after_failure(self):        # FakeDeezer falla en la 2.ª ficha; crawl(limit=…) → 1 done; quitar el fallo; crawl → resto done, sin duplicados
def test_crawl_records_errors(self):               # ficha que falla siempre → tras 3 crawl: state 'error', attempts 3, error con el mensaje
def test_import_poc_cache_offline(self):           # carpeta tmp con un artist_9148.json y un related_4163.json de muestra → niveles 2 y 1, fakes sin llamadas
```

- [ ] **Step 2:** pruebas → FAIL.
- [ ] **Step 3:** implementar.
- [ ] **Step 4:** pruebas → PASS.
- [ ] **Step 5: Ejecución real.** `python -m weave.ingest import-poc`, `… seed`, `… status` → la mayoría de semillas ya en nivel 2 gracias a la caché. Lanzar `… crawl` en segundo plano (puede tardar ~1 h); no bloquea las tareas siguientes.
- [ ] **Step 6:** commit `feat(fase1): semilla, rastreo reanudable e importación de la caché`.

---

### Task 7: Grafo sin red

**Files:**
- Create: `weave/graph.py`
- Test: `tests/test_graph.py`

**Interfaces:**
- Consumes: `Store`.
- Produces:
  - `related_ids(store, artist_id: int) -> list[int]` → relacionadas en orden de `rank`.
  - `find_path(store, a: int, b: int, max_nodes: int = 200_000) -> list[int] | None` → camino más corto por BFS bidireccional sobre la tabla `relation` tratada como no dirigida, cargada en memoria. Sin ninguna llamada a la red. `a == b` → `[a]`; sin conexión → `None`.

- [ ] **Step 1: Pruebas que fallan** (portar las de la PoC al almacén)

```python
def test_path_uses_reverse_edges(self):     # 1→2→4→6→7 y 8→7 (8 solo enlaza hacia 7) → find_path(1,8) == [1,2,4,6,7,8]
def test_path_to_artist_without_related(self):  # 6→9 y 9 sin relacionadas → [1,2,4,6,9]
def test_path_same_and_disconnected(self):  # (1,1) → [1]; 1 y un aislado → None
def test_path_is_shortest(self):            # dos caminos de 4 y 6 pasos → el de 4
```

- [ ] **Step 2:** pruebas → FAIL.
- [ ] **Step 3:** implementar.
- [ ] **Step 4:** pruebas → PASS.
- [ ] **Step 5:** commit `feat(fase1): relacionadas y caminos sin red`.

---

### Task 8: El servidor usa la base de datos

**Files:**
- Modify: `poc/server.py` (sustituye `cached`, `get_json`, `mb_genres`, `deezer_genre`, `artist`, `related`, `resolve`, `search`, `find_path` por `Store`/`Ingestor`/`graph`; mantiene `profile()`, `playlists()` y `Handler`)
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: todo lo anterior.
- Produces: mismas rutas y formas JSON que hoy, con ids internos:

| Ruta | Respuesta | Implementación |
|---|---|---|
| `/api/search?q=` | `[{id, name, fans, picture}]` | `Ingestor.search` |
| `/api/artist/{id}` | ficha (forma de `Store.artist`) | `ensure_full` + `Store.artist`; 404 si el id no existe |
| `/api/resolve?name=` | `{id, name, fans}` o `null` | `resolve_name` + `Store.artist` |
| `/api/related/{id}` | `[{id, name, fans}]` | `ensure_related` + `Store.artist(...)["related"]` |
| `/api/path?from=&to=` | `[{id, name}]` o `null` | `graph.find_path`; si devuelve `None` y algún extremo tiene nivel < 1, `ensure_related` de los dos y reintentar una vez |
| `/api/playlists`, `/api/profile` | sin cambios | sin cambios |

- `server.make_app(store, ingestor) -> type[Handler]` para poder probarlo con fakes; `__main__` abre `data/weave.db` con los clientes reales.

- [ ] **Step 1: Pruebas que fallan** (servidor en hilo, puerto 0, fakes)

```python
def test_artist_endpoint_returns_full_and_known_shape(self):  # GET /api/artist/{id} → level 2 y claves de la PoC
def test_unknown_artist_is_404(self):
def test_search_returns_internal_ids_without_duplicates(self):  # dos fichas Deezer «B.B. King» con mismo MBID → un resultado
def test_path_endpoint_offline(self):                       # BD con cadena precargada y fakes que fallan si se llaman → camino con nombres
```

- [ ] **Step 2:** pruebas → FAIL.
- [ ] **Step 3:** implementar.
- [ ] **Step 4:** todas las pruebas del proyecto → PASS.
- [ ] **Step 5: Criterios de «hecho» de la fase (manual, con el servidor real en http://localhost:8766, Ctrl+F5):**
  1. Cargar «Mercurio» desde «Mis listas» → la pila se vacía en segundos (el ritmo de la animación), no en minutos.
  2. Buscar «B.B. King» → un solo resultado; desplegar relacionadas de Muddy Waters → B.B. King no aparece duplicado.
  3. Desconectar la red (o arrancar con los clientes sustituidos por unos que lanzan error) → «De → a» Marea → Michael Jackson devuelve un camino.
  4. El resto de la tabla de comportamientos de `ROADMAP.md` sigue igual (búsqueda, doble clic con límite de 5, quitar, filtro de género, sonidos).
- [ ] **Step 6:** actualizar `ROADMAP.md` (Fase 1 → hecha, con la fecha) y commit `feat(fase1): el servidor lee de la base de datos`.
