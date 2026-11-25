import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from tests.test_ingest import world
from weave import server

API_KEYS = {"id", "name", "fans", "picture", "link", "genres", "country", "preview", "previewTitle", "related", "level",
            "family", "color", "familyOrder"}


class Offline:
    """Fuente que falla si se usa: demuestra que la respuesta sale solo de la BD."""

    def __getattr__(self, name):
        def boom(*a, **kw):
            raise AssertionError(f"se intentó usar la red: {name}")
        return boom


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.store, self.dz, self.mb, self.ing = world()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.make_app(self.store, self.ing))
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=10) as r:
            return json.load(r)

    def test_artist_endpoint_returns_full_and_known_shape(self):
        aid = self.store.upsert_deezer(9148, "Marea")
        a = self.get(f"/api/artist/{aid}")
        self.assertEqual(set(a), API_KEYS)
        self.assertEqual((a["level"], a["genres"][0]), (2, "rock"))

    def test_unknown_artist_is_404(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.get("/api/artist/99999")
        self.assertEqual(cm.exception.code, 404)

    def test_search_returns_internal_ids_without_duplicates(self):
        res = self.get("/api/search?q=b.b.%20king")
        self.assertEqual([r["name"] for r in res], ["B.B. King"])
        self.assertEqual(self.store.by_source("deezer", 3614), res[0]["id"])  # id interno, no el de Deezer

    def test_top_tracks_endpoint(self):
        self.dz.artists[9148]["tracks"] = [{"title": "Corazón de mimbre", "preview": "a.mp3"},
                                           {"title": "La luna me sabe a poco", "preview": "b.mp3"}]
        aid = self.store.upsert_deezer(9148, "Marea")
        self.assertEqual([t["title"] for t in self.get(f"/api/top/{aid}")], ["Corazón de mimbre", "La luna me sabe a poco"])

    def test_top_tracks_unknown_artist_is_404(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.get("/api/top/99999")
        self.assertEqual(cm.exception.code, 404)

    def test_page_is_served(self):
        with urllib.request.urlopen(self.base + "/", timeout=10) as r:
            self.assertIn("<title>Weave</title>", r.read().decode("utf-8"))

    def test_path_endpoint_offline(self):
        ids = {n: self.store.upsert_deezer(n, name) for n, name in
               [(1, "Marea"), (2, "Extremoduro"), (3, "Fito y Fitipaldis"), (4, "Michael Jackson")]}
        self.store.set_related(ids[1], [ids[2]])
        self.store.set_related(ids[2], [ids[3]])
        self.store.set_related(ids[4], [ids[3]])  # solo hacia atrás
        self.ing.dz = self.ing.mb = Offline()
        path = self.get(f"/api/path?from={ids[1]}&to={ids[4]}")
        self.assertEqual([p["name"] for p in path], ["Marea", "Extremoduro", "Fito y Fitipaldis", "Michael Jackson"])
