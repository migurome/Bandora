"""Clientes de Deezer y MusicBrainz: llamadas y parseo a estructuras simples."""
import urllib.parse

from .http import DEEZER, MUSICBRAINZ
from .text import norm

DZ = "https://api.deezer.com"
MB = "https://musicbrainz.org/ws/2"


class SourceError(Exception):
    pass


class Deezer:
    def __init__(self, fetcher):
        self.f = fetcher

    def _get(self, path):
        data = self.f.get_json(DZ + path, DEEZER)
        if isinstance(data, dict) and "error" in data:
            raise SourceError(f"Deezer {path}: {data['error']}")
        return data

    def artist(self, id) -> dict:
        a = self._get(f"/artist/{id}")
        return {"id": a["id"], "name": a["name"], "fans": a.get("nb_fan", 0), "picture": a.get("picture_medium"),
                "link": a.get("link")}

    def related(self, id, limit=25) -> list[dict]:
        return [{"id": r["id"], "name": r["name"], "fans": r.get("nb_fan", 0)}
                for r in self._get(f"/artist/{id}/related?limit={limit}").get("data", [])]

    def top(self, id) -> dict | None:
        t = self._get(f"/artist/{id}/top?limit=1").get("data", [])
        return {"title": t[0]["title"], "preview": t[0].get("preview")} if t else None

    def top_tracks(self, id, limit=10) -> list[dict]:
        """Canciones más escuchadas con preview de 30 s (las que no tienen preview se descartan)."""
        return [{"title": t["title"], "preview": t["preview"]}
                for t in self._get(f"/artist/{id}/top?limit={limit}").get("data", []) if t.get("preview")]

    def album_genres(self, id) -> list[str]:
        albums = self._get(f"/artist/{id}/albums?limit=1").get("data", [])
        if not albums:
            return []
        g = self._get(f"/album/{albums[0]['id']}").get("genres", {}).get("data", [])
        return [x["name"].lower() for x in g[:2]]

    def search(self, q, limit=10) -> list[dict]:
        res = self._get(f"/search/artist?limit={limit}&q=" + urllib.parse.quote(q)).get("data", [])
        return [{"id": a["id"], "name": a["name"], "fans": a.get("nb_fan", 0), "picture": a.get("picture_small")} for a in res]


class MusicBrainz:
    def __init__(self, fetcher):
        self.f = fetcher

    def lookup(self, name) -> dict | None:
        q = urllib.parse.quote(f'artist:"{name}"')
        res = self.f.get_json(f"{MB}/artist/?query={q}&fmt=json&limit=3", MUSICBRAINZ)
        cands = [a for a in res.get("artists", []) if a.get("score", 0) >= 95]
        # Primero nombre idéntico (Leño ≠ Leno); si no, igual sin tildes ni signos
        hit = next((a for a in cands if a["name"].lower() == name.lower()), None) or \
            next((a for a in cands if norm(a["name"]) == norm(name)), None)
        if not hit:
            return None
        d = self.f.get_json(f"{MB}/artist/{urllib.parse.quote(hit['id'])}?inc=genres&fmt=json", MUSICBRAINZ)
        # Géneros oficiales; si no hay, etiquetas de usuarios (p. ej. «rock urbano»)
        gs = sorted(d.get("genres") or hit.get("tags", []), key=lambda g: -g.get("count", 0))
        return {"mbid": hit["id"], "country": hit.get("country"), "genres": [(g["name"], g.get("count", 0)) for g in gs[:3]]}
