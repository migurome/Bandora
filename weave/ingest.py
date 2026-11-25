"""Ingesta: completa artistas bajo demanda desde Deezer y MusicBrainz."""
from .sources import SourceError
from .text import norm

FULL, RELATED = 2, 1


class Ingestor:
    def __init__(self, store, deezer, mb):
        self.store, self.dz, self.mb = store, deezer, mb

    def _deezer_id(self, artist_id):
        dz = self.store.ext_id(artist_id, "deezer")
        if dz is None:
            raise SourceError(f"el artista {artist_id} no tiene id de Deezer")
        return int(dz)

    def _save_related(self, artist_id, related):
        ids = [self.store.upsert_deezer(r["id"], r["name"], r.get("fans", 0)) for r in related]
        self.store.set_related(artist_id, ids)

    def ensure_related(self, artist_id: int) -> int:
        a = self.store.artist(artist_id)
        if a is None or a["level"] >= RELATED:
            return artist_id
        self._save_related(artist_id, self.dz.related(self._deezer_id(artist_id)))
        return artist_id

    def ensure_full(self, artist_id: int) -> int:
        a = self.store.artist(artist_id)
        if a is not None and a["level"] >= FULL:
            return artist_id
        dz = self._deezer_id(artist_id)
        info = self.dz.artist(dz)
        top = self.dz.top(dz)
        related = self.dz.related(dz)
        self.store.set_details(artist_id, picture=info["picture"], link=info["link"], fans=info["fans"],
                               preview=top and top["preview"], preview_title=top and top["title"])
        try:
            mb = self.mb.lookup(info["name"])
        except Exception:  # MusicBrainz caído o lento: se completa con los géneros de Deezer
            mb = None
        if mb:
            artist_id = self.store.attach_mbid(artist_id, mb["mbid"])
            self.store.set_details(artist_id, country=mb["country"])
            self.store.set_genres(artist_id, mb["genres"], "musicbrainz")
        if not mb or not mb["genres"]:
            try:
                genres = self.dz.album_genres(dz)
            except SourceError:
                genres = []
            self.store.set_genres(artist_id, [(g, len(genres) - i) for i, g in enumerate(genres)], "deezer")
        self._save_related(artist_id, related)
        artist_id = self.store.dedupe_by_name(artist_id)
        self.store.set_level(artist_id, FULL)
        return artist_id

    def resolve_name(self, name: str) -> int | None:
        k = norm(name)
        if not k:
            return None
        found = self.store.by_alias(k)
        if found:
            return found
        hits = [a for a in self.dz.search(name) if norm(a["name"]) == k]
        if not hits:
            return None
        best = max(hits, key=lambda a: a["fans"])
        return self.store.upsert_deezer(best["id"], best["name"], best["fans"])

    def search(self, text: str) -> list[dict]:
        try:
            live = self.dz.search(text)
        except (SourceError, OSError):
            return self.store.search(text)
        best = {}
        for r in live:  # un resultado por artista: por id interno y por nombre normalizado, el de más fans
            aid = self.store.upsert_deezer(r["id"], r["name"], r["fans"])
            k = norm(r["name"]) or f"id{aid}"
            row = {"id": aid, "name": r["name"], "fans": r["fans"], "picture": r.get("picture")}
            if k not in best or r["fans"] > best[k]["fans"]:
                best[k] = row
        seen, out = set(), []
        for row in best.values():  # orden de relevancia de Deezer
            if row["id"] not in seen:
                seen.add(row["id"]); out.append(row)
        return out
