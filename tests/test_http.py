import io
import json
import unittest
import urllib.error

from weave.http import DEEZER, MUSICBRAINZ, Fetcher


class FakeClock:
    def __init__(self):
        self.t = 1000.0
        self.sleeps = []

    def now(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s


def opener_returning(*responses, seen=None):
    """Opener falso: cada elemento es un dict/list (respuesta 200) o un int (código de error HTTP)."""
    queue = list(responses)

    def opener(req, timeout=None):
        if seen is not None:
            seen.append(req)
        r = queue.pop(0)
        if isinstance(r, int):
            raise urllib.error.HTTPError(req.full_url, r, "error", {}, None)
        return io.BytesIO(json.dumps(r).encode())
    return opener


def fetcher(clock, opener):
    return Fetcher({MUSICBRAINZ: 1.1, DEEZER: 0.12}, sleep=clock.sleep, opener=opener, clock=clock.now)


class FetcherTest(unittest.TestCase):
    def test_paces_per_service(self):
        c = FakeClock()
        f = fetcher(c, opener_returning({}, {}, {}))
        f.get_json("http://mb/1", MUSICBRAINZ)
        c.t += 0.3  # pasan 0,3 s
        f.get_json("http://mb/2", MUSICBRAINZ)
        self.assertAlmostEqual(sum(c.sleeps), 0.8, places=6)
        f.get_json("http://dz/1", DEEZER)  # otro servicio: no espera por MusicBrainz
        self.assertAlmostEqual(sum(c.sleeps), 0.8, places=6)

    def test_retries_503_then_succeeds(self):
        c = FakeClock()
        f = fetcher(c, opener_returning(503, 503, {"ok": 1}))
        self.assertEqual(f.get_json("http://mb/x", MUSICBRAINZ), {"ok": 1})
        self.assertIn(2, c.sleeps)
        self.assertIn(4, c.sleeps)

    def test_retries_deezer_quota_error(self):
        c = FakeClock()
        f = fetcher(c, opener_returning({"error": {"code": 4}}, {"data": []}))
        self.assertEqual(f.get_json("http://dz/x", DEEZER), {"data": []})
        self.assertEqual(c.sleeps.count(5), 1)

    def test_gives_up_after_4_attempts(self):
        c = FakeClock()
        f = fetcher(c, opener_returning(503, 503, 503, 503))
        with self.assertRaises(urllib.error.HTTPError):
            f.get_json("http://mb/x", MUSICBRAINZ)

    def test_sends_user_agent(self):
        seen = []
        f = fetcher(FakeClock(), opener_returning({}, seen=seen))
        f.get_json("http://dz/x", DEEZER)
        self.assertEqual(seen[0].get_header("User-agent"), "Weave/0.1 (prueba local)")
