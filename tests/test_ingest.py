import unittest

from tests.fakes import FakeDeezer, FakeLastFm, FakeMusicBrainz, FakeWikidata
from weave.db import connect
from weave.ingest import Ingestor
from weave.store import Store


def world(lastfm=None, wikidata=None):
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
        "Extremoduro": {"mbid": "mb-ext", "country": "ES", "genres": [("rock", 5)]},
    })
    store = Store(connect(":memory:"))
    return store, dz, mb, Ingestor(store, dz, mb, lastfm, wikidata)


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


MAREA_LFM = {"Marea": {"tags": [("Rock Urbano", 35), ("spanish", 20)],
                       "similar": [{"name": "La Fuga", "match": 1.0}, {"name": "Extremoduro", "match": 0.97},
                                   {"name": "Nadie Existe", "match": 0.9}]}}


class LastFmIngestTest(unittest.TestCase):
    def test_full_ingest_uses_lastfm_genres_and_similar(self):
        store, dz, mb, ing = world(FakeLastFm(MAREA_LFM))
        a = store.artist(ing.ensure_full(store.upsert_deezer(9148, "Marea")))
        self.assertEqual((a["genres"][0], a["family"]), ("rock urbano", "Rock"))
        self.assertEqual({r["name"] for r in a["related"][:2]}, {"La Fuga", "Extremoduro"})

    def test_lastfm_similar_unresolved_is_skipped(self):
        store, dz, mb, ing = world(FakeLastFm(MAREA_LFM))
        a = store.artist(ing.ensure_full(store.upsert_deezer(9148, "Marea")))
        self.assertNotIn("Nadie Existe", [r["name"] for r in a["related"]])

    def test_lastfm_failure_does_not_break_ingest(self):
        class Broken:
            def top_tags(self, name): raise OSError("Last.fm caído")
            def similar(self, name, limit=30): raise OSError("Last.fm caído")
        store, dz, mb, ing = world(Broken())
        a = store.artist(ing.ensure_full(store.upsert_deezer(9148, "Marea")))
        self.assertEqual((a["level"], a["genres"][0]), (2, "rock"))

    def test_open_without_lastfm_key(self):
        import os, tempfile
        from weave.ingest import open_default
        d = tempfile.mkdtemp()
        store, ing = open_default(db_path=os.path.join(d, "w.db"), key_path=os.path.join(d, "no_existe.txt"))
        self.assertIsNone(ing.lastfm)
        store.conn.close()


class WikidataIngestTest(unittest.TestCase):
    def test_full_ingest_adds_member_relations(self):
        wd = FakeWikidata({"mb-ext": [{"mbid": "mb-pla", "name": "Platero y Tú", "kind": "member"}]})
        store, dz, mb, ing = world(wikidata=wd)
        a = store.artist(ing.ensure_full(store.upsert_deezer(4163, "Extremoduro")))
        self.assertIn(("Platero y tú", "member"), [(r["name"], r["kind"]) for r in a["related"]])

    def test_wikidata_without_mbid_looks_it_up(self):
        wd = FakeWikidata({"mb-marea": [{"mbid": "mb-ext", "name": "Extremoduro", "kind": "member"}]})
        store, dz, mb, ing = world(wikidata=wd)
        marea = store.upsert_deezer(9148, "Marea"); store.set_level(marea, 2)
        self.assertTrue(ing.enrich_wikidata(marea))
        self.assertEqual(store.mbid(marea), "mb-marea")
        self.assertIn(("Extremoduro", "member"), [(r["name"], r["kind"]) for r in store.artist(marea)["related"]])

    def test_stage_name_with_music_wins(self):
        syn = {"mbid": "mb-ia", "name": "Iñaki Antón", "names": ["Uoho", "Iñaki Antón"], "kind": "member"}
        store, dz, mb, ing = world(wikidata=FakeWikidata({"mb-ext": [syn]}))
        dz.artists[6640568] = {"name": "IÑAKI ANTON", "fans": 148, "albums": 0}
        dz.artists[165369147] = {"name": "UOHO", "fans": 243, "albums": 9}
        a = store.artist(ing.ensure_full(store.upsert_deezer(4163, "Extremoduro")))
        self.assertIn("UOHO", [r["name"] for r in a["related"]])
        self.assertNotIn("IÑAKI ANTON", [r["name"] for r in a["related"]])

    def test_artist_without_albums_is_not_linked(self):
        syn = {"mbid": "mb-ia", "name": "Iñaki Antón", "names": ["Iñaki Antón"], "kind": "member"}
        store, dz, mb, ing = world(wikidata=FakeWikidata({"mb-ext": [syn]}))
        dz.artists[6640568] = {"name": "IÑAKI ANTON", "fans": 148, "albums": 0}
        a = store.artist(ing.ensure_full(store.upsert_deezer(4163, "Extremoduro")))
        self.assertNotIn("IÑAKI ANTON", [r["name"] for r in a["related"]])

    def test_wikidata_again_replaces_old_links(self):
        syn = {"mbid": "mb-ia", "name": "Iñaki Antón", "names": ["Uoho", "Iñaki Antón"], "kind": "member"}
        store, dz, mb, ing = world(wikidata=FakeWikidata({"mb-ext": [syn]}))
        dz.artists[165369147] = {"name": "UOHO", "fans": 243, "albums": 9}
        ext, old = store.upsert_deezer(4163, "Extremoduro"), store.upsert_deezer(6640568, "IÑAKI ANTON")
        store.attach_mbid(ext, "mb-ext")
        store.add_relations([(ext, old)], "member", "wikidata")  # lo que dejó la versión anterior
        self.assertTrue(ing.enrich_wikidata(ext))
        names = [r["name"] for r in store.artist(ext)["related"]]
        self.assertIn("UOHO", names); self.assertNotIn("IÑAKI ANTON", names)

    def test_unresolved_synergy_is_skipped(self):
        wd = FakeWikidata({"mb-ext": [{"mbid": "mb-robe", "name": "Roberto Iniesta", "kind": "member"}]})
        store, dz, mb, ing = world(wikidata=wd)
        a = store.artist(ing.ensure_full(store.upsert_deezer(4163, "Extremoduro")))
        self.assertNotIn("Roberto Iniesta", [r["name"] for r in a["related"]])
