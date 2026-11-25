"""Clientes de Deezer y MusicBrainz: llamadas y parseo a estructuras simples."""
import urllib.parse

from .http import DEEZER, LASTFM, MUSICBRAINZ, WIKIDATA
from .text import norm

DZ = "https://api.deezer.com"
MB = "https://musicbrainz.org/ws/2"
LFM = "https://ws.audioscrobbler.com/2.0/"
WD = "https://query.wikidata.org/sparql"


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


class LastFm:
    """Géneros votados por oyentes (etiquetas con peso) y artistas parecidos con nota de 0 a 1."""

    def __init__(self, fetcher, key):
        self.f, self.key = fetcher, key

    def _get(self, method, name, **extra):
        q = urllib.parse.urlencode({"method": method, "artist": name, "api_key": self.key, "format": "json",
                                    "autocorrect": 1, **extra})
        data = self.f.get_json(f"{LFM}?{q}", LASTFM)
        if isinstance(data, dict) and "error" in data:
            if data["error"] == 6:  # el artista no existe en Last.fm: no es un fallo
                return None
            raise SourceError(f"Last.fm {method}: {data.get('message')}")
        return data

    def top_tags(self, name) -> list[tuple[str, int]]:
        d = self._get("artist.gettoptags", name)
        return [(t["name"], int(t.get("count", 0))) for t in (d or {}).get("toptags", {}).get("tag", [])]

    def similar(self, name, limit=30) -> list[dict]:
        d = self._get("artist.getsimilar", name, limit=limit)
        return [{"name": a["name"], "match": float(a.get("match", 0))} for a in (d or {}).get("similarartists", {}).get("artist", [])]


# Sinergias por MBID (P434): miembros compartidos (P527 «tiene parte», P463 «miembro de») e influencias (P737)
SYNERGY_QUERY = """SELECT DISTINCT ?otherMbid ?otherLabel ?kind WHERE {{
  ?band wdt:P434 "{mbid}" .
  {{ ?band wdt:P527 ?m . ?m wdt:P463 ?other . BIND("member" AS ?kind) }}
  UNION {{ ?m wdt:P463 ?band . ?m wdt:P463 ?other . BIND("member" AS ?kind) }}
  UNION {{ ?band wdt:P527 ?other . BIND("member" AS ?kind) }}
  UNION {{ ?other wdt:P463 ?band . BIND("member" AS ?kind) }}
  UNION {{ ?band wdt:P737 ?other . BIND("influence" AS ?kind) }}
  UNION {{ ?other wdt:P737 ?band . BIND("influence" AS ?kind) }}
  FILTER(?other != ?band)
  ?other wdt:P434 ?otherMbid .
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "es,en". }}
}} LIMIT 60"""


class Wikidata:
    def __init__(self, fetcher):
        self.f = fetcher

    def synergies(self, mbid) -> list[dict]:
        q = urllib.parse.urlencode({"query": SYNERGY_QUERY.format(mbid=mbid.replace('"', "")), "format": "json"})
        rows = self.f.get_json(f"{WD}?{q}", WIKIDATA).get("results", {}).get("bindings", [])
        out = {}
        for r in rows:
            other, kind = r["otherMbid"]["value"], r["kind"]["value"]
            if other == mbid:
                continue
            if other not in out or kind == "member":  # si sale por los dos motivos, gana «miembro»
                out[other] = {"mbid": other, "name": r["otherLabel"]["value"], "kind": kind}
        return list(out.values())
