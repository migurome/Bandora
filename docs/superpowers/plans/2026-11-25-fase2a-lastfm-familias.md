# Fase 2a · Last.fm y familias — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Los colores y las 5 relacionadas que se despliegan salen de géneros y similitudes de Last.fm, con familias revisadas (Clásica / Bandas sonoras, Folk / Cantautor) definidas en un único sitio.

**Architecture:** La clasificación en familias pasa del JavaScript al servidor (`weave/families.py` + `weave/families.json`, editable); la API de artista devuelve `family`, `color` y `familyOrder`. Last.fm entra como tercera fuente (`LastFm` en `weave/sources.py`): sus etiquetas, filtradas, tienen prioridad como géneros, y su `getsimilar` se guarda como relaciones con peso. El orden de las relacionadas combina Last.fm y Deezer.

**Tech Stack:** Python 3.12 stdlib, SQLite, HTML + D3 (sin cambios de dependencias).

**Spec:** `ROADMAP.md` → «Fase 2 · Géneros y relaciones de calidad», partida con el usuario el 25/11/2026: 2a = Last.fm + familias + relaciones combinadas + relleno de la BD; 2b = Wikidata (fuera de este plan).

## Global Constraints

- Solo librería estándar. Pruebas: `python -m unittest discover -s tests -t . -v`; interfaz: `python -I tools/smoke.py` con el servidor arrancado.
- Clave de Last.fm en `data/lastfm_key.txt` (fuera de git). Sin el archivo, todo funciona sin Last.fm.
- Last.fm: `https://ws.audioscrobbler.com/2.0/`, `format=json`, `autocorrect=1`; ritmo ≥ 0,25 s entre peticiones; uso no comercial.
- Familias (orden fijo = orden de la leyenda, colores pastel):
  1 Metal `#f5a9c8` · 2 Hip hop `#f3c6a5` · 3 Electrónica `#9de3d0` · 4 Latina / Flamenco `#f5a3a3` ·
  5 Soul / Funk / Jazz / Blues `#c9bbf6` · 6 Clásica / Bandas sonoras `#f6e3a1` · 7 Folk / Cantautor `#d9c3a5` ·
  8 Pop `#b5e3a1` · 9 Rock `#a3c9f5` · Otros `#c0c6cf`.
- La interfaz no cambia de comportamiento (tabla de `ROADMAP.md`); la prueba de humo sigue pasando (Marea en Rock = `#a3c9f5`).
- Castellano en comentarios y mensajes; commit por tarea en la rama `fase-2a`.

## Review Focus

1. **Artista que Last.fm no conoce** (error 6) → sin géneros ni similares de Last.fm, se usan MusicBrainz/Deezer; nada falla. → Tarea 3, `test_lastfm_unknown_artist_returns_empty`.
2. **Artista cuyas etiquetas no son géneros** («spanish», «seen live», su propio nombre) → no se guardan; se cae a MusicBrainz/Deezer. → Tarea 3, `test_clean_tags_drops_non_genres`.
3. **Similar de Last.fm que Deezer no encuentra** → se omite, no rompe la ingesta. → Tarea 4, `test_lastfm_similar_unresolved_is_skipped`.
4. **Sin archivo de clave** → `open_default` funciona y la app no usa Last.fm. → Tarea 4, `test_open_without_lastfm_key`.
5. **Base de datos existente (esquema 1)** → se migra a 2 sin perder datos. → Tarea 2, `test_migrates_v1_database`.

---

### Task 1: Familias en el servidor

**Files:**
- Create: `weave/families.json`, `weave/families.py`
- Modify: `weave/store.py` (`Store.artist` añade claves)
- Test: `tests/test_families.py`, `tests/test_store.py`

**Interfaces:**
- Produces:
  - `families.json`: lista ordenada de `{"name", "color", "pattern"}` (regex en minúsculas) + entrada final `{"name": "Otros", "color": "#c0c6cf"}`; además `"rock_first": "rock$|rock and roll|rock urbano"` (lo que acaba en rock es Rock antes que su prefijo).
  - `family_of(genre: str) -> str`; `family_of_list(genres: list[str]) -> str` (primera familia distinta de Otros; si no hay, Otros); `color_of(family: str) -> str`; `order_of(family: str) -> int` (índice en la lista; Otros el último).
  - `Store.artist(...)` añade `family`, `color`, `familyOrder` (a partir de `family_of_list(genres)`).

- [ ] **Step 1: Pruebas que fallan**

```python
CASES = {"hard rock": "Rock", "rock urbano": "Rock", "folk rock": "Rock", "blues rock": "Rock", "dance-pop": "Pop",
         "neoclassical metal": "Metal", "baroque": "Clásica / Bandas sonoras", "soundtrack": "Clásica / Bandas sonoras",
         "film score": "Clásica / Bandas sonoras", "post-punk": "Rock", "singer-songwriter": "Folk / Cantautor",
         "cantautor": "Folk / Cantautor", "country": "Folk / Cantautor", "flamenco": "Latina / Flamenco",
         "r&b": "Soul / Funk / Jazz / Blues", "synth-pop": "Electrónica", "trap latino": "Hip hop", "sin género": "Otros"}
def test_family_of_cases(self): ...            # todos los CASES
def test_family_of_list_skips_otros(self):     # ["spanish", "rock"] → "Rock"; ["spanish"] → "Otros"
def test_colors_and_order(self):               # color_of("Rock") == "#a3c9f5"; order_of("Metal") == 0; order_of("Otros") == 9
def test_artist_has_family_fields(self):       # (test_store) set_genres([("spanish",9),("hard rock",5)], "lastfm") → family "Rock", color "#a3c9f5"
```

- [ ] **Step 2:** pruebas → FAIL.
- [ ] **Step 3:** implementar (regex compiladas una vez al cargar el JSON; `ost` como palabra completa `\bost\b` para no casar con «post-»).
- [ ] **Step 4:** pruebas → PASS.
- [ ] **Step 5:** commit `feat(fase2a): familias de género en el servidor`.

---

### Task 2: Esquema 2, relaciones con peso y orden combinado

**Files:**
- Modify: `weave/db.py`, `weave/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Produces:
  - Esquema 2: `relation.weight REAL` y `artist.lastfm_at TEXT`; `connect()` migra una BD de esquema 1 con `ALTER TABLE` y deja `meta.schema_version = '2'`.
  - `Store.set_related(artist_id, related_ids, source="deezer", weights=None)` (`weights` paralela a `related_ids`; `None` = sin peso).
  - `Store.artist(...)["related"]` ordenado por puntuación combinada, una entrada por artista:
    `score = Σ por fuente: lastfm → 0.6 × weight; deezer → 0.4 × (1 − rank / 25)`; empate → menor id.
  - `SOURCE_ORDER = {"lastfm": 0, "musicbrainz": 1, "deezer": 2}` para el orden de géneros.
  - `Store.mark_lastfm(artist_id)`; `Store.pending_lastfm(limit) -> list[int]` (nivel 2 y `lastfm_at` nulo, por fans descendente).

- [ ] **Step 1: Pruebas que fallan**

```python
def test_migrates_v1_database(self):          # BD creada con el SQL de esquema 1 y un artista → connect() → schema_version '2', artista intacto, columnas nuevas presentes
def test_related_combined_order(self):        # deezer [x, y, z]; lastfm [z (0.9), y (0.2)] → orden [z, x, y]
def test_related_lastfm_only(self):           # sin deezer, lastfm [y (0.3), x (0.8)] → [x, y]
def test_genres_prefer_lastfm(self):          # musicbrainz rock, lastfm rock urbano → genres[0] == "rock urbano"
def test_pending_lastfm(self):                # 2 artistas nivel 2, uno marcado → pending == [el otro]
```

- [ ] **Step 2:** pruebas → FAIL.
- [ ] **Step 3:** implementar (orden combinado en SQL con `GROUP BY b`).
- [ ] **Step 4:** todas las pruebas → PASS (las de orden por `rank` existentes siguen valiendo: solo Deezer conserva su orden).
- [ ] **Step 5:** commit `feat(fase2a): esquema 2, relaciones con peso y orden combinado`.

---

### Task 3: Cliente de Last.fm y limpieza de etiquetas

**Files:**
- Modify: `weave/http.py` (constante `LASTFM = "lastfm"`), `weave/sources.py`, `weave/families.py`, `tests/fakes.py`
- Test: `tests/test_sources.py`, `tests/test_families.py`

**Interfaces:**
- Produces:
  - `LastFm(fetcher, key)`: `top_tags(name) -> list[tuple[str, int]]` (`artist.gettoptags`) y `similar(name, limit=30) -> list[{"name", "match": float}]` (`artist.getsimilar`). Error 6 (no existe) → `[]`; otros errores → `SourceError`.
  - `clean_tags(tags, artist_name) -> list[tuple[str, int]]` en `families.py`: minúsculas; fuera las de peso < 10; fuera la igual (por `norm`) al nombre del artista; fuera `NON_GENRES` = {seen live, favorites, favourite, spanish, español, british, american, usa, uk, female vocalists, male vocalists, 80s, 90s, 00s, 70s, 60s, love, beautiful, awesome}; se conservan solo las que `family_of` clasifica (≠ Otros); máximo 5.
  - `FakeLastFm(data)` en `tests/fakes.py` con `data = {nombre: {"tags": [...], "similar": [...]}}` y contador de llamadas.

- [ ] **Step 1: Pruebas que fallan**

```python
def test_lastfm_top_tags_shape(self):              # {"toptags":{"tag":[{"name":"Rock Urbano","count":100}]}} → [("Rock Urbano", 100)]
def test_lastfm_similar_shape(self):               # {"similarartists":{"artist":[{"name":"La Fuga","match":"1"}]}} → [{"name":"La Fuga","match":1.0}]
def test_lastfm_unknown_artist_returns_empty(self):  # {"error":6,"message":"The artist you supplied could not be found"} → [] en ambos
def test_lastfm_other_error_raises(self):          # {"error":29,...} → SourceError
def test_clean_tags_drops_non_genres(self):        # Marea: [("rock",100),("Spanish Rock",82),("Rock Urbano",35),("spanish",23),("marea",5)] → [("rock",100),("spanish rock",82),("rock urbano",35)]
```

- [ ] **Step 2:** pruebas → FAIL.
- [ ] **Step 3:** implementar.
- [ ] **Step 4:** pruebas → PASS.
- [ ] **Step 5:** commit `feat(fase2a): cliente de Last.fm y limpieza de etiquetas`.

---

### Task 4: Ingesta con Last.fm y relleno de la BD

**Files:**
- Modify: `weave/ingest.py`
- Test: `tests/test_ingest.py`, `tests/test_crawl.py`

**Interfaces:**
- Consumes: Tareas 1–3.
- Produces:
  - `Ingestor(store, deezer, mb, lastfm=None)`.
  - `Ingestor.enrich_lastfm(artist_id) -> None`: si hay `lastfm`, guarda `clean_tags(top_tags)` como géneros `"lastfm"` y las similares como relaciones `"lastfm"` con peso `match`. Cada similar se resuelve con `store.by_alias(norm(name))`; si no está en la BD, solo las 10 primeras por `match` se buscan con `resolve_name` (Deezer); las que no se resuelven se omiten. Termina con `store.mark_lastfm`. Errores de Last.fm → no rompen nada.
  - `ensure_full` llama a `enrich_lastfm` antes de `dedupe_by_name`.
  - `open_default()` lee `data/lastfm_key.txt` si existe (`LastFm(f, clave)`; ritmo `LASTFM: 0.25`), si no `lastfm=None`.
  - CLI: `python -m weave.ingest lastfm [--limit N]` → `enrich_lastfm` sobre `store.pending_lastfm()`, con progreso; reanudable gracias a `lastfm_at`.

- [ ] **Step 1: Pruebas que fallan** (con `FakeLastFm`)

```python
def test_full_ingest_uses_lastfm_genres_and_similar(self):  # Marea: tags rock urbano; similar La Fuga 1.0 (en BD), Extremoduro 0.97 → genres[0]=="rock urbano", family "Rock", related empieza por La Fuga
def test_lastfm_similar_unresolved_is_skipped(self):       # similar "Nadie Existe" (Deezer no lo encuentra) → no aparece y no lanza
def test_lastfm_failure_does_not_break_ingest(self):        # FakeLastFm que lanza OSError → nivel 2 con géneros de MB/Deezer
def test_open_without_lastfm_key(self):                      # open_default con ruta de clave inexistente (parámetro) → ingestor.lastfm is None
def test_enrich_command_is_resumable(self):                  # 2 artistas nivel 2; enrich de 1 (limit=1) → pending_lastfm == [el otro]
```

- [ ] **Step 2:** pruebas → FAIL.
- [ ] **Step 3:** implementar (`open_default(key_path=DATA / "lastfm_key.txt")` para poder probarlo).
- [ ] **Step 4:** pruebas → PASS.
- [ ] **Step 5:** commit `feat(fase2a): ingesta con Last.fm y comando de relleno`.

---

### Task 5: La página usa las familias del servidor

**Files:**
- Modify: `weave/static/index.html`, `tools/smoke.js`

**Interfaces:**
- Consumes: `family`, `color`, `familyOrder` de `/api/artist/{id}` (Tarea 1).
- Produces: el nodo guarda `genre = full.family`, `color = full.color`, `order = full.familyOrder`; desaparecen `FAMILIES`, `family()` y la tabla de colores del JavaScript; leyenda y anclas de agrupación ordenadas por `order`.

- [ ] **Step 1:** añadir a `tools/smoke.js` la comprobación `ok('familia del servidor', nodes[0].genre === 'Rock' && nodes[0].color === '#a3c9f5')` tras añadir Marea, y ejecutar `python -I tools/smoke.py` → MAL en esa línea.
- [ ] **Step 2:** implementar el cambio en la página.
- [ ] **Step 3:** `python -I tools/smoke.py` → todo ok (18 comprobaciones).
- [ ] **Step 4:** commit `feat(fase2a): la página usa las familias del servidor`.

---

### Task 6: Relleno real y criterios de «hecho»

**Files:**
- Modify: `ROADMAP.md`

- [ ] **Step 1:** `python -m weave.ingest lastfm` sobre la BD real (en segundo plano; ~800 artistas completos a ≤4 peticiones/s).
- [ ] **Step 2: Comprobaciones** (servidor real):
  1. `/api/artist/{Leño}` → `family == "Rock"`.
  2. Antonio Vivaldi y Hans Zimmer → `family == "Clásica / Bandas sonoras"`.
  3. `/api/artist/{Marea}` → las dos primeras relacionadas son La Fuga y Extremoduro (en cualquier orden).
  4. Pruebas unitarias y prueba de humo en verde.
- [ ] **Step 3:** `ROADMAP.md`: Fase 2a hecha con fecha y resultados; Fase 2b (Wikidata) como siguiente. Commit `docs: fase 2a hecha`.
