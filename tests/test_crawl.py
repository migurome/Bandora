import json
import tempfile
import unittest
from pathlib import Path

from tests.fakes import FakeDeezer, FakeLastFm, FakeWikidata
from tests.test_ingest import world
from weave.ingest import crawl, enrich_pending, import_poc_cache, seed, spotify_artists


def crawl_rows(store):
    return store.conn.execute("SELECT artist_id, state, attempts, error FROM crawl").fetchall()


class CrawlTest(unittest.TestCase):
    def test_spotify_artists_order_and_dedupe(self):
        d = Path(tempfile.mkdtemp())
        (d / "StreamingHistory_music_0.json").write_text(json.dumps([
            {"artistName": "Robe", "msPlayed": 663 * 60000}, {"artistName": "Marea", "msPlayed": 674 * 60000}]), encoding="utf-8")
        (d / "Playlist1.json").write_text(json.dumps({"playlists": [{"items": [
            {"track": {"artistName": "Platero Y Tu"}}, {"track": {"artistName": "Platero y tú"}}, {"episode": {}}]}]}), encoding="utf-8")
        (d / "YourLibrary.json").write_text(json.dumps({"tracks": [{"artist": "Robe"}]}), encoding="utf-8")
        self.assertEqual(spotify_artists(d), ["Marea", "Robe", "Platero Y Tu"])

    def test_seed_is_idempotent(self):
        store, dz, mb, ing = world()
        self.assertEqual(seed(ing, ["Marea", "Extremoduro", "Nadie Existe"]), 2)
        seed(ing, ["Marea", "Extremoduro"])
        self.assertEqual(len(crawl_rows(store)), 2)

    def test_crawl_promotes_neighbours(self):
        store, dz, mb, ing = world()
        seed(ing, ["Marea"])
        r = crawl(ing)
        marea = store.by_source("deezer", 9148)
        self.assertEqual(store.artist(marea)["level"], 2)
        self.assertTrue(all(store.artist(x["id"])["level"] >= 1 for x in store.artist(marea)["related"]))
        self.assertEqual((r["pending"], r["errors"]), (0, 0))
        self.assertEqual(r["done"], 7)  # Marea + sus 6 relacionadas

    def test_crawl_resumes_after_failure(self):
        store, dz, mb, ing = world()
        seed(ing, ["Marea", "Extremoduro"])
        dz.fail_ids = {4163}
        crawl(ing, limit=2)
        dz.fail_ids = set()
        r = crawl(ing)
        self.assertEqual((r["pending"], r["errors"]), (0, 0))
        self.assertEqual(store.artist(store.by_source("deezer", 4163))["level"], 2)
        n_artists = store.conn.execute("SELECT COUNT(*) FROM artist").fetchone()[0]
        n_ids = store.conn.execute("SELECT COUNT(DISTINCT ext_id) FROM source_id").fetchone()[0]
        self.assertEqual(n_artists, n_ids)  # sin artistas duplicados

    def test_crawl_records_errors(self):
        store, dz, mb, ing = world()
        seed(ing, ["Marea"])
        dz.fail_ids = {9148}
        for _ in range(3):
            crawl(ing)
        (aid, state, attempts, error), = crawl_rows(store)
        self.assertEqual((state, attempts), ("error", 3))
        self.assertIn("fallo simulado", error)

    def test_import_poc_cache_offline(self):
        d = Path(tempfile.mkdtemp())
        (d / "artist_9148.json").write_text(json.dumps({
            "id": 9148, "name": "Marea", "picture": "m.jpg", "fans": 53022, "link": "L", "genres": ["rock"], "country": "ES",
            "preview": "p.mp3", "previewTitle": "Corazon de mimbre", "related": [{"id": 4163, "name": "Extremoduro", "fans": 110115}]}),
            encoding="utf-8")
        (d / "related_4163.json").write_text(json.dumps({"related": [{"id": 9148, "name": "Marea", "fans": 53022}]}), encoding="utf-8")
        (d / "resolve_plateroytu.json").write_text(json.dumps({"hit": {"id": 6135, "name": "Platero y tú", "fans": 37384}}), encoding="utf-8")
        (d / "resolve_nadie.json").write_text(json.dumps({"hit": None}), encoding="utf-8")
        store, dz, mb, ing = world()
        self.assertEqual(import_poc_cache(store, d), 3)  # el resolve sin coincidencia no aporta nada
        marea, ext = store.by_source("deezer", 9148), store.by_source("deezer", 4163)
        self.assertEqual((store.artist(marea)["level"], store.artist(marea)["genres"]), (2, ["rock"]))
        self.assertEqual(store.artist(ext)["level"], 1)
        self.assertEqual(store.by_alias("plateroytu"), store.by_source("deezer", 6135))
        self.assertEqual(sum(dz.calls.values()) + sum(mb.calls.values()), 0)

    def test_enrich_command_is_resumable(self):
        store, dz, mb, ing = world(FakeLastFm({}))
        a = store.upsert_deezer(9148, "Marea", 10); b = store.upsert_deezer(4163, "Extremoduro", 5)
        store.set_level(a, 2); store.set_level(b, 2)
        self.assertEqual(enrich_pending(ing, limit=1), 1)
        self.assertEqual(store.pending_lastfm(10), [b])
        self.assertEqual(enrich_pending(ing), 1)
        self.assertEqual(store.pending_lastfm(10), [])

    def test_enrich_failure_is_retried_later(self):
        class Broken:
            def top_tags(self, name): raise OSError("sin red")
            def similar(self, name, limit=30): raise OSError("sin red")
        store, dz, mb, ing = world(Broken())
        a = store.upsert_deezer(9148, "Marea", 10)
        store.set_level(a, 2)
        enrich_pending(ing)  # termina (no se queda en bucle) …
        self.assertEqual(store.pending_lastfm(10), [a])  # … y el artista sigue pendiente para otro intento

    def test_enrich_stops_after_repeated_failures(self):
        wd = FakeWikidata({}); wd.fail = True
        store, dz, mb, ing = world(wikidata=wd)
        for i in range(10):
            a = store.upsert_deezer(1000 + i, f"Banda {i}", 10); store.attach_mbid(a, f"mb-{i}"); store.set_level(a, 2)
        enrich_pending(ing, which="wikidata")
        self.assertEqual(wd.calls["synergies"], 3)  # no sigue martilleando una fuente que falla

    def test_wikidata_failure_keeps_pending(self):
        wd = FakeWikidata({}); wd.fail = True
        store, dz, mb, ing = world(wikidata=wd)
        a = store.upsert_deezer(4163, "Extremoduro", 10)
        store.attach_mbid(a, "mb-ext"); store.set_level(a, 2)
        enrich_pending(ing, which="wikidata")
        self.assertEqual(store.pending_wikidata(10), [a])
