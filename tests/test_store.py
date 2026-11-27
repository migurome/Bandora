import os
import tempfile
import threading
import unittest

from weave.db import connect
from weave.store import Store

API_KEYS = {"id", "name", "fans", "picture", "link", "genres", "country", "preview", "previewTitle", "related", "level",
            "family", "color", "familyOrder"}


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
        self.assertEqual(a["related"][1], {"id": ext, "name": "Extremoduro", "fans": 110115, "kind": "similar"})
        self.assertEqual((a["genres"], a["country"], a["previewTitle"], a["level"]), (["rock"], "ES", "Corazón de mimbre", 1))
        self.assertIsNone(self.s.artist(99999))

    def test_genres_prefer_musicbrainz(self):
        a = self.s.upsert_deezer(9148, "Marea")
        self.s.set_genres(a, [("alternativo", 1)], "deezer")
        self.s.set_genres(a, [("rock", 3)], "musicbrainz")
        self.assertEqual(self.s.artist(a)["genres"][0], "rock")
        b = self.s.upsert_deezer(1, "Nadie")
        self.assertEqual(self.s.artist(b)["genres"], ["sin género"])

    def test_artist_has_family_fields(self):
        a = self.s.upsert_deezer(9148, "Marea")
        self.s.set_genres(a, [("spanish", 9), ("hard rock", 5)], "musicbrainz")
        r = self.s.artist(a)
        self.assertEqual((r["family"], r["color"], r["familyOrder"]), ("Rock", "#a3c9f5", 8))

    def test_migrates_v1_database(self):
        import sqlite3
        path = os.path.join(tempfile.mkdtemp(), "v1.db")
        old = sqlite3.connect(path)
        old.executescript("""CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE artist (id INTEGER PRIMARY KEY, name TEXT NOT NULL, mbid TEXT UNIQUE, country TEXT, fans INTEGER DEFAULT 0,
              picture TEXT, link TEXT, preview TEXT, preview_title TEXT, level INTEGER NOT NULL DEFAULT 0, updated_at TEXT);
            CREATE TABLE relation (a INTEGER NOT NULL, b INTEGER NOT NULL, kind TEXT NOT NULL DEFAULT 'similar', rank INTEGER,
              source TEXT NOT NULL, PRIMARY KEY (a, b, kind, source), CHECK (a <> b));
            INSERT INTO meta VALUES ('schema_version', '1');
            INSERT INTO artist (id, name, fans, level) VALUES (1, 'Marea', 53022, 2);""")
        old.commit(); old.close()
        conn = connect(path)
        self.assertEqual(conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0], "4")  # siempre migra a la última versión
        self.assertEqual(conn.execute("SELECT name, fans, level FROM artist").fetchone()[:], ("Marea", 53022, 2))
        self.assertIn("weight", [r[1] for r in conn.execute("PRAGMA table_info(relation)")])
        self.assertIn("lastfm_at", [r[1] for r in conn.execute("PRAGMA table_info(artist)")])
        conn.close()

    def test_renormalize_merges_conjunction_twins(self):
        from weave.store import renormalize
        a = self.s.upsert_deezer(307450, "Fito y Fitipaldis", 170576)
        b = self.s.upsert_deezer(7225, "Fito & Fitipaldis", 42575)
        x = self.s.upsert_deezer(1, "Extremoduro", 1)
        n1 = self.s.upsert_deezer(2, "Nirvana", 9)
        n2 = self.s.upsert_deezer(3, "Nirvana", 1)  # homónimos de siempre: no se tocan
        self.s.set_related(x, [b])
        c = self.s.conn  # como estaban antes de unificar las conjunciones
        c.execute("UPDATE alias SET norm='fitoyfitipaldis' WHERE artist_id=?", (a,))
        renormalize(c)
        self.assertIsNone(self.s.artist(b))
        self.assertEqual(self.s.artist(a)["name"], "Fito y Fitipaldis")
        self.assertEqual([r["id"] for r in self.s.artist(x)["related"]], [a])
        self.assertEqual(self.s.by_source("deezer", "7225"), a)
        self.assertIsNotNone(self.s.artist(n1)); self.assertIsNotNone(self.s.artist(n2))

    def test_related_combined_order(self):
        a, x, y, z = (self.s.upsert_deezer(i, n) for i, n in [(1, "A"), (2, "X"), (3, "Y"), (4, "Z")])
        self.s.set_related(a, [x, y, z])
        self.s.set_related(a, [z, y], source="lastfm", weights=[0.9, 0.2])
        self.assertEqual([r["id"] for r in self.s.artist(a)["related"]], [z, y, x])  # y está en las dos fuentes: supera a x

    def test_related_skips_minor_variant_of_itself(self):
        # «Bruce Springsteen & The E Street Band» (1 fan) no es otro grupo: no gasta un hueco de los relacionados
        a = self.s.upsert_deezer(1, "Bruce Springsteen", 1_800_000)
        v = self.s.upsert_deezer(2, "Bruce Springsteen & The E Street Band", 1)
        band = self.s.upsert_deezer(3, "Tom Petty and the Heartbreakers", 235_000)
        tp = self.s.upsert_deezer(4, "Tom Petty", 118_000)  # el grupo de verdad, con peso propio, sí se queda
        x = self.s.upsert_deezer(5, "John Mellencamp", 900_000)
        self.s.set_related(a, [v, x], source="lastfm", weights=[1.0, 0.6])
        self.s.set_related(x, [v], source="lastfm", weights=[0.6])  # desde otro artista sí sale
        self.s.set_related(tp, [band])
        self.assertEqual([r["id"] for r in self.s.artist(a)["related"]], [x])
        self.assertEqual([r["id"] for r in self.s.artist(x)["related"]], [v])
        self.assertEqual([r["id"] for r in self.s.artist(tp)["related"]], [band])

    def test_related_lastfm_only(self):
        a, x, y = (self.s.upsert_deezer(i, n) for i, n in [(1, "A"), (2, "X"), (3, "Y")])
        self.s.set_related(a, [y, x], source="lastfm", weights=[0.3, 0.8])
        self.assertEqual([r["id"] for r in self.s.artist(a)["related"]], [x, y])

    def test_genres_prefer_lastfm(self):
        a = self.s.upsert_deezer(9148, "Marea")
        self.s.set_genres(a, [("rock", 3)], "musicbrainz")
        self.s.set_genres(a, [("rock urbano", 35)], "lastfm")
        self.assertEqual(self.s.artist(a)["genres"][0], "rock urbano")

    def test_pending_lastfm(self):
        a = self.s.upsert_deezer(1, "A", 10)
        b = self.s.upsert_deezer(2, "B", 5)
        self.s.set_level(a, 2); self.s.set_level(b, 2)
        self.s.mark_lastfm(a)
        self.assertEqual(self.s.pending_lastfm(10), [b])

    def test_migrates_v2_database(self):
        path = os.path.join(tempfile.mkdtemp(), "v2.db")
        c = connect(path)
        c.execute("ALTER TABLE artist DROP COLUMN wikidata_at")
        c.execute("UPDATE meta SET value='2' WHERE key='schema_version'")
        c.execute("INSERT INTO artist (id, name, level) VALUES (1, 'Marea', 2)")
        c.close()
        conn = connect(path)
        self.assertEqual(conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0], "4")
        self.assertIn("wikidata_at", [r[1] for r in conn.execute("PRAGMA table_info(artist)")])
        self.assertEqual(conn.execute("SELECT name FROM artist").fetchone()[0], "Marea")
        conn.close()

    def test_member_relations_are_symmetric(self):
        a, b = self.s.upsert_deezer(1, "Extremoduro"), self.s.upsert_deezer(2, "Platero y tú")
        self.s.add_relations([(a, b)], "member", "wikidata")
        self.assertEqual([(r["id"], r["kind"]) for r in self.s.artist(b)["related"]], [(a, "member")])
        self.assertEqual([(r["id"], r["kind"]) for r in self.s.artist(a)["related"]], [(b, "member")])

    def test_member_boosts_order(self):
        a, x, y = (self.s.upsert_deezer(i, n) for i, n in [(1, "A"), (2, "X"), (3, "Y")])
        self.s.set_related(a, [x, y])
        self.s.add_relations([(a, y)], "member", "wikidata")
        self.assertEqual([(r["id"], r["kind"]) for r in self.s.artist(a)["related"]], [(y, "member"), (x, "similar")])

    def test_by_mbid_and_pending_wikidata(self):
        a, b = self.s.upsert_deezer(1, "A", 10), self.s.upsert_deezer(2, "B", 5)
        self.s.attach_mbid(a, "mb-a")
        self.assertEqual((self.s.by_mbid("mb-a"), self.s.mbid(a), self.s.mbid(b)), (a, "mb-a", None))
        self.s.set_level(a, 2); self.s.set_level(b, 2)
        self.s.mark_wikidata(a)
        self.assertEqual(self.s.pending_wikidata(10), [b])

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
