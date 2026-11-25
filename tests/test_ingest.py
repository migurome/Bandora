import unittest

from tests.fakes import FakeDeezer, FakeMusicBrainz
from weave.db import connect
from weave.ingest import Ingestor
from weave.store import Store


def world():
    dz = FakeDeezer({
        9148: {"name": "Marea", "fans": 53022, "related": [4163, 6135, 1, 2, 3, 4],
               "top": {"title": "Corazón de mimbre", "preview": "p.mp3"}, "genres": ["alternativo", "rock"]},
        4163: {"name": "Extremoduro", "fans": 110115, "related": [9148]},
        6135: {"name": "Platero y tú", "fans": 37384, "related": [4163]},
        1: {"name": "Sinkope"}, 2: {"name": "Reincidentes"}, 3: {"name": "La Fuga"}, 4: {"name": "Los Suaves"},
        3614: {"name": "B.B. King", "fans": 1707660, "related": []},
        54984: {"name": "B.B.King", "fans": 22864, "related": []},
    })
    mb = FakeMusicBrainz({
        "Marea": {"mbid": "mb-marea", "country": "ES", "genres": [("rock", 3)]},
        "B.B. King": {"mbid": "mb-bb", "country": "US", "genres": [("blues", 5)]},
        "B.B.King": {"mbid": "mb-bb", "country": "US", "genres": [("blues", 5)]},
    })
    store = Store(connect(":memory:"))
    return store, dz, mb, Ingestor(store, dz, mb)


class IngestTest(unittest.TestCase):
    def test_full_ingest_sets_level_genres_related(self):
        store, dz, mb, ing = world()
        aid = ing.ensure_full(store.upsert_deezer(9148, "Marea"))
        a = store.artist(aid)
        self.assertEqual(a["level"], 2)
        self.assertEqual(a["genres"][0], "rock")
        self.assertEqual([r["name"] for r in a["related"]],
                         ["Extremoduro", "Platero y tú", "Sinkope", "Reincidentes", "La Fuga", "Los Suaves"])
        self.assertEqual((a["preview"], a["previewTitle"], a["country"]), ("p.mp3", "Corazón de mimbre", "ES"))

    def test_full_ingest_is_cached(self):
        store, dz, mb, ing = world()
        aid = ing.ensure_full(store.upsert_deezer(9148, "Marea"))
        before = (dict(dz.calls), dict(mb.calls))
        self.assertEqual(ing.ensure_full(aid), aid)
        self.assertEqual((dict(dz.calls), dict(mb.calls)), before)

    def test_full_ingest_without_musicbrainz_match_uses_deezer_genres(self):
        store, dz, mb, ing = world()
        del mb.data["Marea"]
        aid = ing.ensure_full(store.upsert_deezer(9148, "Marea"))
        self.assertEqual(store.artist(aid)["genres"], ["alternativo", "rock"])

    def test_full_ingest_survives_musicbrainz_failure(self):
        store, dz, mb, ing = world()
        mb.lookup = lambda name: (_ for _ in ()).throw(OSError("MusicBrainz caído"))
        aid = ing.ensure_full(store.upsert_deezer(9148, "Marea"))
        self.assertEqual((store.artist(aid)["level"], store.artist(aid)["genres"]), (2, ["alternativo", "rock"]))

    def test_two_deezer_ids_same_artist_become_one(self):
        store, dz, mb, ing = world()
        a = ing.ensure_full(store.upsert_deezer(3614, "B.B. King", 1707660))
        b = ing.ensure_full(store.upsert_deezer(54984, "B.B.King", 22864))
        self.assertEqual(a, b)
        self.assertEqual(store.by_source("deezer", 54984), a)
        self.assertEqual(store.artist(a)["name"], "B.B. King")

    def test_resolve_name_matches_normalized(self):
        store, dz, mb, ing = world()
        aid = ing.resolve_name("Platero Y Tu")
        self.assertEqual(store.artist(aid)["name"], "Platero y tú")
        self.assertEqual(ing.resolve_name("Platero Y Tu"), aid)  # segunda vez sale de la BD
        self.assertEqual(dz.calls["search"], 1)
        self.assertIsNone(ing.resolve_name("Nadie Existe"))

    def test_related_only_skips_musicbrainz(self):
        store, dz, mb, ing = world()
        aid = ing.ensure_related(store.upsert_deezer(9148, "Marea"))
        self.assertEqual(mb.calls["lookup"], 0)
        self.assertEqual(store.artist(aid)["level"], 1)
        self.assertEqual(len(store.artist(aid)["related"]), 6)

    def test_search_returns_one_result_per_artist(self):
        store, dz, mb, ing = world()
        res = ing.search("b.b. king")
        self.assertEqual([r["name"] for r in res], ["B.B. King"])
        self.assertTrue(isinstance(res[0]["id"], int))
