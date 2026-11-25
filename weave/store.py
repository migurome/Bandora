"""Almacén de artistas: lecturas, escrituras e identidad. Una conexión compartida protegida por un cerrojo."""
import threading
from datetime import datetime, timezone

from .families import color_of, family_of_list, order_of
from .text import norm

SOURCE_ORDER = {"lastfm": 0, "musicbrainz": 1, "deezer": 2}  # prioridad de géneros


class Store:
    def __init__(self, conn):
        self.conn = conn
        self.lock = threading.RLock()  # la conexión se comparte entre los hilos del servidor

    def _write(self):
        """Contexto de escritura: cerrojo + transacción."""
        store = self

        class _Tx:
            def __enter__(self):
                store.lock.acquire()
                store.conn.execute("BEGIN IMMEDIATE")
                return store.conn

            def __exit__(self, exc, *_):
                try:
                    store.conn.execute("ROLLBACK" if exc else "COMMIT")
                finally:
                    store.lock.release()
        return _Tx()

    def _read(self, sql, args=()):
        with self.lock:
            return self.conn.execute(sql, args).fetchall()

    # ---------- escrituras ----------
    def upsert_deezer(self, deezer_id: int, name: str, fans: int = 0) -> int:
        with self._write() as c:
            row = c.execute("SELECT artist_id FROM source_id WHERE source='deezer' AND ext_id=?", (str(deezer_id),)).fetchone()
            if row:
                aid = row[0]
                c.execute("UPDATE artist SET fans=MAX(fans, ?) WHERE id=?", (fans or 0, aid))
            else:
                aid = c.execute("INSERT INTO artist (name, fans, updated_at) VALUES (?, ?, ?)",
                                (name, fans or 0, _now())).lastrowid
                c.execute("INSERT INTO source_id VALUES ('deezer', ?, ?)", (str(deezer_id), aid))
            c.execute("INSERT OR IGNORE INTO alias VALUES (?, ?, ?)", (aid, name, norm(name)))
            return aid

    def set_details(self, artist_id, *, picture=None, link=None, fans=None, country=None, preview=None, preview_title=None):
        with self._write() as c:
            c.execute("""UPDATE artist SET picture=COALESCE(?, picture), link=COALESCE(?, link), fans=MAX(fans, COALESCE(?, 0)),
                         country=COALESCE(?, country), preview=COALESCE(?, preview), preview_title=COALESCE(?, preview_title),
                         updated_at=? WHERE id=?""",
                      (picture, link, fans, country, preview, preview_title, _now(), artist_id))

    def set_genres(self, artist_id, genres, source: str):
        with self._write() as c:
            c.execute("DELETE FROM genre WHERE artist_id=? AND source=?", (artist_id, source))
            c.executemany("INSERT OR IGNORE INTO genre VALUES (?, ?, ?, ?)", [(artist_id, g, w, source) for g, w in genres])

    def set_related(self, artist_id, related_ids, source="deezer", weights=None):
        weights = weights or [None] * len(related_ids)
        with self._write() as c:
            c.execute("DELETE FROM relation WHERE a=? AND kind='similar' AND source=?", (artist_id, source))
            c.executemany("INSERT OR IGNORE INTO relation (a, b, kind, rank, source, weight) VALUES (?, ?, 'similar', ?, ?, ?)",
                          [(artist_id, b, rank, source, w) for rank, (b, w) in enumerate(zip(related_ids, weights)) if b != artist_id])
            c.execute("UPDATE artist SET level=MAX(level, 1) WHERE id=?", (artist_id,))

    def set_level(self, artist_id, level: int):
        with self._write() as c:
            c.execute("UPDATE artist SET level=MAX(level, ?) WHERE id=?", (level, artist_id))

    # ---------- identidad ----------
    # Reglas (aprendidas en la PoC): mismo (fuente, id) → mismo artista; mismo MBID → mismo artista;
    # mismo nombre normalizado sin MBIDs en conflicto → mismo artista; MBIDs distintos → artistas distintos.
    def merge(self, keep: int, drop: int) -> int:
        with self._write() as c:
            return _merge(c, keep, drop)

    def attach_mbid(self, artist_id: int, mbid: str) -> int:
        with self._write() as c:
            row = c.execute("SELECT id FROM artist WHERE mbid=?", (mbid,)).fetchone()
            if row and row[0] != artist_id:
                return _merge(c, row[0], artist_id)
            current = c.execute("SELECT mbid FROM artist WHERE id=?", (artist_id,)).fetchone()[0]
            if current is None:
                c.execute("UPDATE artist SET mbid=? WHERE id=?", (mbid, artist_id))
            return artist_id  # si ya tenía otro MBID no se toca: sería otro artista con el mismo id de Deezer

    def dedupe_by_name(self, artist_id: int) -> int:
        with self._write() as c:
            name, mbid = c.execute("SELECT name, mbid FROM artist WHERE id=?", (artist_id,)).fetchone()
            k = norm(name)
            if not k:
                return artist_id
            others = c.execute("""SELECT DISTINCT a.id, a.mbid FROM alias al JOIN artist a ON a.id = al.artist_id
                                  WHERE al.norm=? AND a.id<>?""", (k, artist_id)).fetchall()
            same = [o[0] for o in others if o[1] is None or mbid is None or o[1] == mbid]
            if not same:
                return artist_id
            ids = sorted(same + [artist_id])
            survivor = ids[0]
            for other in ids[1:]:
                mb = c.execute("SELECT mbid FROM artist WHERE id=?", (survivor,)).fetchone()[0]
                omb = c.execute("SELECT mbid FROM artist WHERE id=?", (other,)).fetchone()[0]
                if mb and omb and mb != omb:
                    continue  # dos candidatos con MBIDs distintos entre sí: homónimos
                _merge(c, survivor, other)
            return survivor

    # ---------- cola de rastreo ----------
    def enqueue(self, artist_id: int, target_level: int, hops: int) -> bool:
        """Encola o sube de objetivo; devuelve True si hay trabajo nuevo."""
        with self._write() as c:
            row = c.execute("SELECT target_level FROM crawl WHERE artist_id=?", (artist_id,)).fetchone()
            if row is None:
                c.execute("INSERT INTO crawl (artist_id, target_level, hops) VALUES (?, ?, ?)", (artist_id, target_level, hops))
                return True
            if row[0] < target_level:
                c.execute("""UPDATE crawl SET target_level=?, hops=MIN(hops, ?), state='pending', attempts=0, error=NULL
                             WHERE artist_id=?""", (target_level, hops, artist_id))
                return True
            return False

    def next_crawl(self, skip=()):
        """Siguiente pendiente: primero los más cercanos a la semilla, luego los menos intentados y los más populares."""
        rows = self._read("""SELECT c.artist_id, c.target_level, c.hops FROM crawl c JOIN artist a ON a.id = c.artist_id
                             WHERE c.state='pending' ORDER BY c.hops, c.attempts, a.fans DESC LIMIT ?""", (len(skip) + 1,))
        return next((tuple(r) for r in rows if r[0] not in skip), None)

    def crawl_done(self, artist_id: int):
        with self._write() as c:
            c.execute("UPDATE crawl SET state='done', error=NULL WHERE artist_id=?", (artist_id,))

    def crawl_failed(self, artist_id: int, error: str, max_attempts=3):
        with self._write() as c:
            c.execute("""UPDATE crawl SET attempts=attempts+1, error=?,
                         state=CASE WHEN attempts+1 >= ? THEN 'error' ELSE 'pending' END WHERE artist_id=?""",
                      (error[:500], max_attempts, artist_id))

    def counts(self) -> dict:
        levels = dict(self._read("SELECT level, COUNT(*) FROM artist GROUP BY level"))
        states = dict(self._read("SELECT state, COUNT(*) FROM crawl GROUP BY state"))
        return {"levels": levels, "crawl": states}

    def mark_lastfm(self, artist_id: int):
        with self._write() as c:
            c.execute("UPDATE artist SET lastfm_at=? WHERE id=?", (_now(), artist_id))

    def pending_lastfm(self, limit: int) -> list[int]:
        """Artistas completos aún sin pasar por Last.fm, los más populares primero."""
        return [r[0] for r in self._read("SELECT id FROM artist WHERE level >= 2 AND lastfm_at IS NULL ORDER BY fans DESC, id LIMIT ?",
                                         (limit,))]

    # ---------- lecturas ----------
    def by_source(self, source: str, ext_id) -> int | None:
        rows = self._read("SELECT artist_id FROM source_id WHERE source=? AND ext_id=?", (source, str(ext_id)))
        return rows[0][0] if rows else None

    def ext_id(self, artist_id: int, source: str) -> str | None:
        rows = self._read("SELECT ext_id FROM source_id WHERE artist_id=? AND source=? ORDER BY rowid LIMIT 1", (artist_id, source))
        return rows[0][0] if rows else None

    def edges(self, artist_id=None) -> list[tuple[int, int]]:
        """Relaciones de parecido (a, b): todas, o solo las que salen de artist_id en orden de parecido."""
        if artist_id is None:
            return [tuple(r) for r in self._read("SELECT a, b FROM relation WHERE kind='similar'")]
        return [tuple(r) for r in self._read("SELECT a, b FROM relation WHERE kind='similar' AND a=? ORDER BY rank", (artist_id,))]

    def by_alias(self, k: str) -> int | None:
        """Artista cuyo alias normalizado es exactamente k (el de más fans si hay varios)."""
        rows = self._read("""SELECT a.id FROM alias al JOIN artist a ON a.id = al.artist_id WHERE al.norm=?
                             ORDER BY a.fans DESC LIMIT 1""", (k,))
        return rows[0][0] if rows else None

    def artist(self, artist_id) -> dict | None:
        rows = self._read("SELECT * FROM artist WHERE id=?", (artist_id,))
        if not rows:
            return None
        a = rows[0]
        genres = self._read("SELECT name, weight, source FROM genre WHERE artist_id=?", (artist_id,))
        genres = [g["name"] for g in sorted(genres, key=lambda g: (SOURCE_ORDER.get(g["source"], 9), -(g["weight"] or 0)))]
        # Orden combinado: Last.fm aporta su parecido (0-1) y Deezer su posición; quien está en las dos sube
        related = self._read("""SELECT r.b AS id, x.name, x.fans FROM relation r JOIN artist x ON x.id = r.b
                                WHERE r.a=? AND r.kind='similar' GROUP BY r.b
                                ORDER BY SUM(CASE r.source WHEN 'lastfm' THEN 0.6 * COALESCE(r.weight, 0)
                                                           WHEN 'deezer' THEN 0.4 * (1 - COALESCE(r.rank, 25) / 25.0)
                                                           ELSE 0 END) DESC, r.b""", (artist_id,))
        genres = _dedupe(genres) or ["sin género"]
        fam = family_of_list(genres)
        return {"id": a["id"], "name": a["name"], "fans": a["fans"], "picture": a["picture"], "link": a["link"],
                "family": fam, "color": color_of(fam), "familyOrder": order_of(fam),
                "genres": genres, "country": a["country"], "preview": a["preview"],
                "previewTitle": a["preview_title"], "related": [dict(r) for r in _dedupe_rows(related)], "level": a["level"]}

    def search(self, text: str, limit=6) -> list[dict]:
        k = norm(text)
        if not k:
            return []
        rows = self._read("""SELECT DISTINCT a.id, a.name, a.fans, a.picture FROM alias al JOIN artist a ON a.id = al.artist_id
                             WHERE al.norm LIKE ? || '%' ORDER BY a.level = 2 DESC, a.fans DESC LIMIT ?""", (k, limit))
        return [dict(r) for r in rows]


def _merge(c, keep: int, drop: int) -> int:
    """Funde drop en keep dentro de la transacción abierta en c."""
    if keep == drop:
        return keep
    k = c.execute("SELECT * FROM artist WHERE id=?", (keep,)).fetchone()
    d = c.execute("SELECT * FROM artist WHERE id=?", (drop,)).fetchone()
    if k is None or d is None:
        return keep
    c.execute("UPDATE source_id SET artist_id=? WHERE artist_id=?", (keep, drop))
    c.execute("INSERT OR IGNORE INTO alias SELECT ?, name, norm FROM alias WHERE artist_id=?", (keep, drop))
    c.execute("INSERT OR IGNORE INTO genre SELECT ?, name, weight, source FROM genre WHERE artist_id=?", (keep, drop))
    # relaciones: se reescribe drop→keep en ambos extremos, sin duplicar y sin crear a == b
    c.execute("""INSERT OR IGNORE INTO relation (a, b, kind, rank, source, weight)
                 SELECT CASE WHEN a=:d THEN :k ELSE a END, CASE WHEN b=:d THEN :k ELSE b END, kind, rank, source, weight
                 FROM relation WHERE (a=:d OR b=:d)
                   AND (CASE WHEN a=:d THEN :k ELSE a END) <> (CASE WHEN b=:d THEN :k ELSE b END)""", {"d": drop, "k": keep})
    c.execute("UPDATE OR IGNORE crawl SET artist_id=? WHERE artist_id=?", (keep, drop))
    c.execute("DELETE FROM artist WHERE id=?", (drop,))  # en cascada: lo que quedaba de drop
    best = d if (d["fans"] or 0) > (k["fans"] or 0) else k
    c.execute("""UPDATE artist SET name=?, mbid=COALESCE(mbid, ?), fans=?, level=?, country=COALESCE(country, ?),
                 picture=COALESCE(picture, ?), link=COALESCE(link, ?), preview=COALESCE(preview, ?),
                 preview_title=COALESCE(preview_title, ?) WHERE id=?""",
              (best["name"], d["mbid"], max(k["fans"] or 0, d["fans"] or 0), max(k["level"], d["level"]),
               d["country"], d["picture"], d["link"], d["preview"], d["preview_title"], keep))
    return keep


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _dedupe(xs):
    seen = set()
    return [x for x in xs if not (x in seen or seen.add(x))]


def _dedupe_rows(rows):
    seen = set()
    return [r for r in rows if not (r["id"] in seen or seen.add(r["id"]))]
