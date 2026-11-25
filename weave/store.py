"""Almacén de artistas: lecturas, escrituras e identidad. Una conexión compartida protegida por un cerrojo."""
import threading
from datetime import datetime, timezone

from .text import norm

SOURCE_ORDER = {"musicbrainz": 0, "deezer": 1}


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

    def set_related(self, artist_id, related_ids, source="deezer"):
        with self._write() as c:
            c.execute("DELETE FROM relation WHERE a=? AND kind='similar' AND source=?", (artist_id, source))
            c.executemany("INSERT OR IGNORE INTO relation VALUES (?, ?, 'similar', ?, ?)",
                          [(artist_id, b, rank, source) for rank, b in enumerate(related_ids) if b != artist_id])
            c.execute("UPDATE artist SET level=MAX(level, 1) WHERE id=?", (artist_id,))

    def set_level(self, artist_id, level: int):
        with self._write() as c:
            c.execute("UPDATE artist SET level=MAX(level, ?) WHERE id=?", (level, artist_id))

    # ---------- lecturas ----------
    def by_source(self, source: str, ext_id) -> int | None:
        rows = self._read("SELECT artist_id FROM source_id WHERE source=? AND ext_id=?", (source, str(ext_id)))
        return rows[0][0] if rows else None

    def artist(self, artist_id) -> dict | None:
        rows = self._read("SELECT * FROM artist WHERE id=?", (artist_id,))
        if not rows:
            return None
        a = rows[0]
        genres = self._read("SELECT name, weight, source FROM genre WHERE artist_id=?", (artist_id,))
        genres = [g["name"] for g in sorted(genres, key=lambda g: (SOURCE_ORDER.get(g["source"], 9), -(g["weight"] or 0)))]
        related = self._read("""SELECT r.b AS id, x.name, x.fans FROM relation r JOIN artist x ON x.id = r.b
                                WHERE r.a=? AND r.kind='similar' ORDER BY r.rank""", (artist_id,))
        return {"id": a["id"], "name": a["name"], "fans": a["fans"], "picture": a["picture"], "link": a["link"],
                "genres": _dedupe(genres) or ["sin género"], "country": a["country"], "preview": a["preview"],
                "previewTitle": a["preview_title"], "related": [dict(r) for r in _dedupe_rows(related)], "level": a["level"]}

    def search(self, text: str, limit=6) -> list[dict]:
        k = norm(text)
        if not k:
            return []
        rows = self._read("""SELECT DISTINCT a.id, a.name, a.fans, a.picture FROM alias al JOIN artist a ON a.id = al.artist_id
                             WHERE al.norm LIKE ? || '%' ORDER BY a.level = 2 DESC, a.fans DESC LIMIT ?""", (k, limit))
        return [dict(r) for r in rows]


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _dedupe(xs):
    seen = set()
    return [x for x in xs if not (x in seen or seen.add(x))]


def _dedupe_rows(rows):
    seen = set()
    return [r for r in rows if not (r["id"] in seen or seen.add(r["id"]))]
