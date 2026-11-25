"""Fuentes falsas en memoria, con la misma interfaz que weave.sources."""
from collections import Counter

from weave.sources import SourceError
from weave.text import norm


class FakeDeezer:
    """artists: {id: {"name", "fans", "related": [ids], "top": {...}|None, "genres": [...]}}"""

    def __init__(self, artists):
        self.artists = artists
        self.calls = Counter()
        self.fail_ids = set()

    def _a(self, id, method):
        self.calls[method] += 1
        if id in self.fail_ids or id not in self.artists:
            raise SourceError(f"fallo simulado en {method}({id})")
        return self.artists[id]

    def artist(self, id):
        a = self._a(id, "artist")
        return {"id": id, "name": a["name"], "fans": a.get("fans", 0), "picture": f"pic{id}", "link": f"https://deezer/{id}"}

    def related(self, id, limit=25):
        a = self._a(id, "related")
        return [{"id": r, "name": self.artists[r]["name"], "fans": self.artists[r].get("fans", 0)} for r in a.get("related", [])][:limit]

    def top(self, id):
        return self._a(id, "top").get("top")

    def album_genres(self, id):
        return self._a(id, "album_genres").get("genres", [])

    def search(self, q, limit=10):
        self.calls["search"] += 1
        k = norm(q)
        return [{"id": i, "name": a["name"], "fans": a.get("fans", 0), "picture": None}
                for i, a in self.artists.items() if k and k in norm(a["name"])][:limit]


class FakeMusicBrainz:
    """data: {nombre: {"mbid", "country", "genres": [(g, peso)]}}"""

    def __init__(self, data):
        self.data = data
        self.calls = Counter()

    def lookup(self, name):
        self.calls["lookup"] += 1
        return self.data.get(name)
