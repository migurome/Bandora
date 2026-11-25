import os
import tempfile
import threading
import unittest

from weave.db import connect
from weave.store import Store

API_KEYS = {"id", "name", "fans", "picture", "link", "genres", "country", "preview", "previewTitle", "related", "level"}


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.s = Store(connect(":memory:"))

    def test_upsert_is_idempotent(self):
        a = self.s.upsert_deezer(3614, "B.B. King", 1707660)
        b = self.s.upsert_deezer(3614, "B.B. King", 1707660)
        self.assertEqual(a, b)
        self.assertEqual(self.s.conn.execute("SELECT COUNT(*) FROM artist").fetchone()[0], 1)
        self.assertEqual(self.s.by_source("deezer", "3614"), a)

    def test_artist_shape_matches_poc_api(self):
        marea = self.s.upsert_deezer(9148, "Marea", 53022)
        ext = self.s.upsert_deezer(4163, "Extremoduro", 110115)
        plat = self.s.upsert_deezer(6135, "Platero y tú", 37384)
        self.s.set_details(marea, picture="p.jpg", link="https://deezer/9148", fans=53022, country="ES",
                           preview="pre.mp3", preview_title="Corazón de mimbre")
        self.s.set_genres(marea, [("rock", 3)], "musicbrainz")
        self.s.set_related(marea, [plat, ext])
        a = self.s.artist(marea)
        self.assertEqual(set(a), API_KEYS)
        self.assertEqual([r["name"] for r in a["related"]], ["Platero y tú", "Extremoduro"])
        self.assertEqual(a["related"][1], {"id": ext, "name": "Extremoduro", "fans": 110115})
        self.assertEqual((a["genres"], a["country"], a["previewTitle"], a["level"]), (["rock"], "ES", "Corazón de mimbre", 1))
        self.assertIsNone(self.s.artist(99999))

    def test_genres_prefer_musicbrainz(self):
        a = self.s.upsert_deezer(9148, "Marea")
        self.s.set_genres(a, [("alternativo", 1)], "deezer")
        self.s.set_genres(a, [("rock", 3)], "musicbrainz")
        self.assertEqual(self.s.artist(a)["genres"][0], "rock")
        b = self.s.upsert_deezer(1, "Nadie")
        self.assertEqual(self.s.artist(b)["genres"], ["sin género"])

    def test_level_never_decreases(self):
        a = self.s.upsert_deezer(9148, "Marea")
        self.s.set_level(a, 2)
        self.s.set_level(a, 1)
        self.assertEqual(self.s.artist(a)["level"], 2)

    def test_search_by_alias_prefix(self):
        p = self.s.upsert_deezer(6135, "Platero y tú")
        b = self.s.upsert_deezer(3614, "B.B. King")
        self.assertEqual([r["id"] for r in self.s.search("plat")], [p])
        self.assertEqual([r["id"] for r in self.s.search("b.b.k")], [b])

    def test_relation_rejects_self(self):
        a = self.s.upsert_deezer(1, "A")
        b = self.s.upsert_deezer(2, "B")
        self.s.set_related(a, [a, b])
        self.assertEqual([r["id"] for r in self.s.artist(a)["related"]], [b])

    def test_concurrent_writes_from_threads(self):
        d = tempfile.mkdtemp()
        path = os.path.join(d, "t.db")
        s = Store(connect(path))
        errors = []

        def work(t):
            try:
                for i in range(50):
                    s.upsert_deezer(t * 1000 + i, f"Banda {t}-{i}")
            except Exception as e:  # noqa: BLE001 - la prueba recoge cualquier fallo de concurrencia
                errors.append(e)

        threads = [threading.Thread(target=work, args=(t,)) for t in range(8)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()
        self.assertEqual(errors, [])
        self.assertEqual(s.conn.execute("SELECT COUNT(*) FROM artist").fetchone()[0], 400)
        s.conn.close()
