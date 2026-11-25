import unittest

from weave.sources import Deezer, LastFm, MusicBrainz, SourceError


class UrlFetcher:
    """Fetcher falso: devuelve el JSON de la primera clave contenida en la URL."""

    def __init__(self, routes):
        self.routes, self.urls = routes, []

    def get_json(self, url, service):
        self.urls.append(url)
        for k, v in self.routes.items():
            if k in url:
                return v
        raise AssertionError("URL no prevista: " + url)


class MusicBrainzTest(unittest.TestCase):
    def test_mb_prefers_exact_name(self):
        f = UrlFetcher({
            "ws/2/artist/?query": {"artists": [
                {"id": "mb-leno", "name": "Leno", "score": 100, "country": "BR", "tags": []},
                {"id": "mb-leño", "name": "Leño", "score": 100, "country": "ES", "tags": []}]},
            "ws/2/artist/mb-le%C3%B1o": {"genres": [{"name": "hard rock", "count": 2}]},
            "ws/2/artist/mb-leño": {"genres": [{"name": "hard rock", "count": 2}]},
        })
        r = MusicBrainz(f).lookup("Leño")
        self.assertEqual((r["mbid"], r["country"]), ("mb-leño", "ES"))

    def test_mb_falls_back_to_tags(self):
        f = UrlFetcher({
            "ws/2/artist/?query": {"artists": [{"id": "x", "name": "Leño", "score": 100, "country": "ES",
                                                "tags": [{"name": "hard rock", "count": 1}, {"name": "rock urbano", "count": 2}]}]},
            "ws/2/artist/x?": {"genres": []},
        })
        self.assertEqual(MusicBrainz(f).lookup("Leño")["genres"], [("rock urbano", 2), ("hard rock", 1)])

    def test_mb_no_match_below_95(self):
        f = UrlFetcher({"ws/2/artist/?query": {"artists": [{"id": "x", "name": "Marea", "score": 88}]}})
        self.assertIsNone(MusicBrainz(f).lookup("Marea"))


class DeezerTest(unittest.TestCase):
    def test_deezer_error_payload_raises(self):
        f = UrlFetcher({"/artist/1": {"error": {"type": "DataException", "message": "no data"}}})
        with self.assertRaises(SourceError):
            Deezer(f).artist(1)

    def test_deezer_related_shape(self):
        f = UrlFetcher({"/artist/9148/related": {"data": [
            {"id": 4163, "name": "Extremoduro", "nb_fan": 110115}, {"id": 6135, "name": "Platero y tú", "nb_fan": 37384}]}})
        self.assertEqual(Deezer(f).related(9148), [{"id": 4163, "name": "Extremoduro", "fans": 110115},
                                                   {"id": 6135, "name": "Platero y tú", "fans": 37384}])

    def test_deezer_top_tracks_skip_missing_preview(self):
        f = UrlFetcher({"/artist/9148/top": {"data": [
            {"title": "Corazón de mimbre", "preview": "a.mp3"}, {"title": "Sin preview", "preview": ""},
            {"title": "La luna me sabe a poco", "preview": "b.mp3"}]}})
        self.assertEqual(Deezer(f).top_tracks(9148), [{"title": "Corazón de mimbre", "preview": "a.mp3"},
                                                      {"title": "La luna me sabe a poco", "preview": "b.mp3"}])
        self.assertIn("limit=10", f.urls[0])

    def test_deezer_artist_top_and_genres(self):
        f = UrlFetcher({
            "/artist/9148/top": {"data": [{"title": "Corazón de mimbre", "preview": "p.mp3"}]},
            "/artist/9148/albums": {"data": [{"id": 55}]},
            "/album/55": {"genres": {"data": [{"name": "Alternativo"}, {"name": "Rock"}, {"name": "Pop"}]}},
            "/artist/9148": {"id": 9148, "name": "Marea", "nb_fan": 53022, "picture_medium": "m.jpg", "link": "L"},
        })
        d = Deezer(f)
        self.assertEqual(d.artist(9148), {"id": 9148, "name": "Marea", "fans": 53022, "picture": "m.jpg", "link": "L"})
        self.assertEqual(d.top(9148), {"title": "Corazón de mimbre", "preview": "p.mp3"})
        self.assertEqual(d.album_genres(9148), ["alternativo", "rock"])


class LastFmTest(unittest.TestCase):
    def test_lastfm_top_tags_shape(self):
        f = UrlFetcher({"artist.gettoptags": {"toptags": {"tag": [{"name": "Rock Urbano", "count": 100}, {"name": "rock", "count": 80}]}}})
        self.assertEqual(LastFm(f, "k").top_tags("Leño"), [("Rock Urbano", 100), ("rock", 80)])
        self.assertIn("api_key=k", f.urls[0])
        self.assertIn("autocorrect=1", f.urls[0])

    def test_lastfm_similar_shape(self):
        f = UrlFetcher({"artist.getsimilar": {"similarartists": {"artist": [{"name": "La Fuga", "match": "1"},
                                                                            {"name": "Extremoduro", "match": "0.97"}]}}})
        self.assertEqual(LastFm(f, "k").similar("Marea"), [{"name": "La Fuga", "match": 1.0}, {"name": "Extremoduro", "match": 0.97}])

    def test_lastfm_unknown_artist_returns_empty(self):
        f = UrlFetcher({"ws.audioscrobbler.com": {"error": 6, "message": "The artist you supplied could not be found"}})
        self.assertEqual(LastFm(f, "k").top_tags("Nadie"), [])
        self.assertEqual(LastFm(f, "k").similar("Nadie"), [])

    def test_lastfm_other_error_raises(self):
        f = UrlFetcher({"ws.audioscrobbler.com": {"error": 29, "message": "Rate limit exceeded"}})
        with self.assertRaises(SourceError):
            LastFm(f, "k").top_tags("Marea")
