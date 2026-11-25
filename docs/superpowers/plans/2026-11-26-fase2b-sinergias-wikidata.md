# Fase 2b · Sinergias de Wikidata — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Las bandas que comparten miembros (o se influyen) quedan conectadas aunque no «suenen» parecidas, y la línea de unión muestra el motivo con su color, sin texto.

**Architecture:** Wikidata entra como cuarta fuente (`Wikidata` en `weave/sources.py`), consultada por SPARQL con el MBID del artista. Sus resultados se guardan en `relation` con `kind = 'member' | 'influence'` y `source = 'wikidata'`, en los dos sentidos. El orden de las relacionadas suma un plus a estas relaciones, y la API indica el motivo de cada una (`kind`). La página colorea la línea según el motivo.

**Tech Stack:** Python 3.12 stdlib, SQLite, HTML + D3.

**Spec:** `ROADMAP.md` → «Fase 2b · Sinergias de Wikidata».

## Global Constraints

- Solo librería estándar. Pruebas: `python -m unittest discover -s tests -t . -v`; interfaz: `python -I tools/smoke.py`.
- Wikidata: `https://query.wikidata.org/sparql`, `format=json`, ritmo ≥ 1,0 s entre peticiones, User-Agent `Weave/0.1 (proyecto personal local)` (sin datos personales).
- Consulta de sinergias (por MBID, propiedad P434): miembros compartidos (P527 «tiene parte» y P463 «miembro de», en ambos sentidos) e influencias (P737, en ambos sentidos); solo resultados con MBID; máximo 60 filas.
- Motivos y colores de línea: `member` = `#c9bbf6`, grosor 2,5; `influence` = `#9de3d0`, grosor 2; parecido (`similar`) sin cambios; camino dorado sin cambios (tiene prioridad).
- Orden de relacionadas: a la puntuación de la fase 2a se suma +0,5 si hay relación `member` y +0,3 si hay `influence`.
- No se reintroduce texto en la interfaz; los motivos se explican solo en la leyenda (`/label on`).
- Castellano; commit por tarea en `fase-2b`.

## Review Focus

1. **Artista sin MBID** → se busca en MusicBrainz y, si no aparece, se marca como hecho sin relaciones. → Tarea 3, `test_wikidata_without_mbid_looks_it_up`.
2. **Otro artista de Wikidata que no está en la BD ni se encuentra en Deezer** (personas con nombre real, como «Roberto Iniesta») → se omite. → Tarea 3, `test_unresolved_synergy_is_skipped`.
3. **Wikidata caído o con límite (HTTP 429/5xx)** → el artista queda pendiente para otro relleno. → Tarea 3, `test_wikidata_failure_keeps_pending`.
4. **Relación en un solo sentido**: si Extremoduro comparte miembro con Platero, al abrir Platero también aparece Extremoduro, aunque Platero no se haya rellenado. → Tarea 2, `test_member_relations_are_symmetric`.
5. **BD de esquema 2** → migra a 3 sin perder datos. → Tarea 2, `test_migrates_v2_database`.

---

### Task 1: Cliente de Wikidata

**Files:** Modify `weave/http.py` (`WIKIDATA = "wikidata"`), `weave/sources.py`, `tests/fakes.py`. Test: `tests/test_sources.py`.

**Interfaces — Produces:**
- `Wikidata(fetcher).synergies(mbid) -> list[{"mbid", "name", "kind"}]`: filas de la consulta SPARQL de Global Constraints; un elemento por MBID (si sale como `member` y como `influence`, gana `member`); sin el propio MBID.
- `FakeWikidata(data)` con `data = {mbid: [{"mbid", "name", "kind"}]}`, contador de llamadas y `fail = False` (si es `True`, lanza `OSError`).

- [ ] **Step 1: Pruebas que fallan**

```python
def test_wikidata_synergies_shape(self):        # bindings con otherMbid/otherLabel/kind → [{"mbid","name","kind"}]; la URL lleva el MBID y format=json
def test_wikidata_member_wins_over_influence(self):  # mismo MBID como influence y member → una fila, kind "member"
def test_wikidata_skips_self(self):              # fila con el propio MBID → fuera
```

- [ ] **Step 2:** FAIL. **Step 3:** implementar. **Step 4:** PASS. **Step 5:** commit `feat(fase2b): cliente de Wikidata`.

---

### Task 2: Esquema 3 y relaciones con motivo

**Files:** Modify `weave/db.py`, `weave/store.py`. Test: `tests/test_store.py`.

**Interfaces — Produces:**
- Esquema 3: `artist.wikidata_at TEXT`; migración desde 2 y desde 1; `schema_version = '3'`.
- `Store.by_mbid(mbid) -> int | None`; `Store.mbid(artist_id) -> str | None`.
- `Store.add_relations(pairs: list[tuple[int, int]], kind: str, source: str)`: inserta cada par **en los dos sentidos** (`INSERT OR IGNORE`, sin `a == b`).
- `Store.mark_wikidata(artist_id)`; `Store.pending_wikidata(limit) -> list[int]` (nivel 2, `wikidata_at` nulo, por fans).
- `Store.artist(...)["related"]`: ahora incluye todas las clases de relación; cada elemento lleva `"kind"`: `"member"` si hay alguna `member`, si no `"influence"` si hay alguna, si no `"similar"`. Puntuación: la de 2a + 0,5 (`member`) + 0,3 (`influence`).

- [ ] **Step 1: Pruebas que fallan**

```python
def test_migrates_v2_database(self):            # BD con esquema 2 → '3', datos intactos, columna wikidata_at
def test_member_relations_are_symmetric(self):  # add_relations([(a, b)], "member", "wikidata") → artist(b)["related"] contiene a con kind "member"
def test_member_boosts_order(self):              # deezer [x, y] para a; member (a, y) → orden [y, x]; kinds ["member", "similar"]
def test_by_mbid_and_pending_wikidata(self):     # attach_mbid → by_mbid; 2 de nivel 2, uno marcado → pending == [el otro]
```

- [ ] **Step 2:** FAIL. **Step 3:** implementar. **Step 4:** PASS (las pruebas existentes siguen valiendo; las que comparan `related` exacto se adaptan a la clave nueva `kind`). **Step 5:** commit `feat(fase2b): esquema 3 y relaciones con motivo`.

---

### Task 3: Ingesta con Wikidata y relleno

**Files:** Modify `weave/ingest.py`. Test: `tests/test_ingest.py`, `tests/test_crawl.py`.

**Interfaces — Consumes:** Tareas 1–2. **Produces:**
- `Ingestor(store, deezer, mb, lastfm=None, wikidata=None)`.
- `Ingestor.enrich_wikidata(artist_id) -> bool`: MBID del artista (si falta, `mb.lookup(name)` + `attach_mbid`; si aun así no hay, marca y devuelve `True`); `wikidata.synergies(mbid)`; cada uno se resuelve con `by_mbid` → `by_alias(norm(name))` → `resolve_name` (solo los 5 primeros sin resolver); `add_relations` por motivo; `mark_wikidata`. Si Wikidata falla → `False` sin marcar.
- `ensure_full` llama a `enrich_wikidata` después de `enrich_lastfm`.
- `open_default` crea `Wikidata(f)` con ritmo `WIKIDATA: 1.0`.
- El bucle de relleno se generaliza: `enrich_pending(ingestor, which="lastfm" | "wikidata", limit=None, on_progress=None)`; CLI `python -m weave.ingest wikidata [--limit N]`.

- [ ] **Step 1: Pruebas que fallan**

```python
def test_full_ingest_adds_member_relations(self):   # FakeWikidata: Extremoduro (mb-ext) ↔ Platero (mb-pla) member → related de Extremoduro incluye Platero con kind "member"
def test_wikidata_without_mbid_looks_it_up(self):    # sin MBID; FakeMusicBrainz lo da → se consulta Wikidata con ese MBID
def test_unresolved_synergy_is_skipped(self):        # sinergia «Roberto Iniesta» no resoluble → no aparece, no lanza
def test_wikidata_failure_keeps_pending(self):       # fail=True → enrich_pending(which="wikidata") termina y el artista sigue en pending_wikidata
```

- [ ] **Step 2:** FAIL. **Step 3:** implementar. **Step 4:** PASS. **Step 5:** commit `feat(fase2b): ingesta con Wikidata y relleno`.

---

### Task 4: La línea muestra el motivo

**Files:** Modify `weave/static/index.html`, `tools/smoke.js`.

**Interfaces — Consumes:** `related[].kind` (Tarea 2).

- Al desplegar, cada enlace guarda `kind`; clase `link member` / `link influence` con los colores de Global Constraints. El camino (dorado) manda sobre el motivo.
- Con `/label on`, la leyenda añade dos muestras de línea: «miembros» y «influencia».

- [ ] **Step 1:** en `tools/smoke.js`, tras desplegar Marea: `ok('motivo en la línea', links.every(l => ['similar', 'member', 'influence'].includes(l.kind)))` → MAL (aún no existe `kind`).
- [ ] **Step 2:** implementar. **Step 3:** `python -I tools/smoke.py` → todo ok. **Step 4:** commit `feat(fase2b): la línea muestra el motivo de la relación`.

---

### Task 5: Relleno real y criterios de «hecho»

- [ ] **Step 1:** `python -m weave.ingest wikidata` sobre la BD real (en segundo plano; completa también los MBID que faltan).
- [ ] **Step 2: Comprobaciones:**
  1. Las relacionadas de Extremoduro incluyen Platero y Tú y Extrechinato y Tú con motivo `member`.
  2. Al menos una relación `member` une dos bandas que no estaban relacionadas por parecido (contar en la BD).
  3. Unitarias y humo en verde.
- [ ] **Step 3:** `ROADMAP.md` (2b hecha, tabla de comportamiento con los colores de motivo) y `README.md`; commit `docs: fase 2b hecha`.
