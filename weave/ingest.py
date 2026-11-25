"""Ingesta: completa artistas bajo demanda desde Deezer y MusicBrainz; semilla, rastreo reanudable y CLI."""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from .sources import SourceError
from .text import norm

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "weave.db"
EXPORT_DIR = ROOT / "resources" / "Spotify Account Data"
POC_CACHE = ROOT / "poc" / "cache"

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

    def top_tracks(self, artist_id: int) -> list[dict]:
        """Canciones con preview, siempre en vivo: las URLs de preview de Deezer caducan."""
        return self.dz.top_tracks(self._deezer_id(artist_id))

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


# ---------- semilla, rastreo e importación ----------
def spotify_artists(export_dir: Path) -> list[str]:
    """Tus artistas (historial, playlists, «Me gusta»), únicos por nombre normalizado, de más a menos escuchados."""
    minutes, songs, first = Counter(), Counter(), {}

    def see(name):
        k = norm(name)
        if k:
            first.setdefault(k, name)
        return k

    for f in sorted(export_dir.glob("StreamingHistory_music_*.json")):
        for r in json.loads(f.read_text(encoding="utf-8")):
            minutes[see(r["artistName"])] += r["msPlayed"]
    pl = export_dir / "Playlist1.json"
    if pl.exists():
        for p in json.loads(pl.read_text(encoding="utf-8"))["playlists"]:
            for i in p["items"]:
                if i.get("track"):
                    songs[see(i["track"]["artistName"])] += 1
    lib = export_dir / "YourLibrary.json"
    if lib.exists():
        for t in json.loads(lib.read_text(encoding="utf-8"))["tracks"]:
            songs[see(t["artist"])] += 1
    return [first[k] for k in sorted(first, key=lambda k: (-minutes[k], -songs[k]))]


def seed(ingestor, names, on_progress=None) -> int:
    n = 0
    for i, name in enumerate(names):
        try:
            aid = ingestor.resolve_name(name)
        except (SourceError, OSError):
            aid = None
        if aid and ingestor.store.enqueue(aid, FULL, 0):
            n += 1
        if on_progress:
            on_progress(i + 1, len(names), name)
    return n


def crawl(ingestor, limit=None, on_progress=None) -> dict:
    store, done, errors, tried = ingestor.store, 0, 0, set()
    while limit is None or len(tried) < limit:
        nxt = store.next_crawl(tried)
        if nxt is None:
            break
        aid, target, hops = nxt
        tried.add(aid)
        try:
            new = ingestor.ensure_full(aid) if target >= FULL else ingestor.ensure_related(aid)
            store.crawl_done(aid)
            store.crawl_done(new)  # si se fusionó con otro, su fila de la cola pudo pasar al superviviente
            tried.add(new)
            if hops == 0:  # vecinos de la semilla: solo relacionadas, para poder trazar caminos sin red
                for r in store.artist(new)["related"]:
                    store.enqueue(r["id"], RELATED, 1)
            done += 1
        except Exception as e:  # noqa: BLE001 - un artista roto no debe parar el rastreo
            store.crawl_failed(aid, f"{type(e).__name__}: {e}")
            errors += 1
        if on_progress:
            on_progress(done, errors, aid)
    return {"done": done, "errors": errors, "pending": store.counts()["crawl"].get("pending", 0)}


def import_poc_cache(store, cache_dir: Path) -> int:
    """Convierte la caché de la prueba de concepto sin tocar la red. Devuelve cuántos archivos aprovechó."""
    used = 0
    for f in sorted(cache_dir.glob("artist_*.json")):
        a = json.loads(f.read_text(encoding="utf-8"))
        aid = store.upsert_deezer(a["id"], a["name"], a.get("fans", 0))
        store.set_details(aid, picture=a.get("picture"), link=a.get("link"), fans=a.get("fans"), country=a.get("country"),
                          preview=a.get("preview"), preview_title=a.get("previewTitle"))
        genres = [g for g in a.get("genres", []) if g != "sin género"]
        # la PoC no guardaba la fuente del género: con país, casi siempre venía de MusicBrainz
        store.set_genres(aid, [(g, len(genres) - i) for i, g in enumerate(genres)], "musicbrainz" if a.get("country") else "deezer")
        store.set_related(aid, [store.upsert_deezer(r["id"], r["name"], r.get("fans", 0)) for r in a.get("related", [])])
        store.set_level(aid, FULL)
        used += 1
    for f in sorted(cache_dir.glob("resolve_*.json")):
        hit = json.loads(f.read_text(encoding="utf-8")).get("hit")
        if hit:
            store.upsert_deezer(hit["id"], hit["name"], hit.get("fans", 0))
            used += 1
    for f in sorted(cache_dir.glob("related_*.json")):
        aid = store.by_source("deezer", f.stem.split("_", 1)[1])
        if aid is None:
            continue  # sin nombre no se puede crear el artista; ya aparecerá por otra vía
        rel = json.loads(f.read_text(encoding="utf-8"))["related"]
        store.set_related(aid, [store.upsert_deezer(r["id"], r["name"], r.get("fans", 0)) for r in rel])
        used += 1
    return used


def open_default():
    from .db import connect
    from .http import DEEZER, MUSICBRAINZ, Fetcher
    from .sources import Deezer, MusicBrainz
    from .store import Store
    f = Fetcher({MUSICBRAINZ: 1.1, DEEZER: 0.12})
    store = Store(connect(DB_PATH))
    return store, Ingestor(store, Deezer(f), MusicBrainz(f))


def _status(store):
    k = store.counts()
    lv = k["levels"]
    print(f"Artistas: {sum(lv.values())} · completos {lv.get(2, 0)} · con relacionadas {lv.get(1, 0)} · solo nombre {lv.get(0, 0)}")
    print(f"Cola: {k['crawl'] or 'vacía'}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m weave.ingest", description="Base de datos de artistas de Weave")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("import-poc", help="importa poc/cache sin usar la red")
    sub.add_parser("seed", help="encola tus artistas del export de Spotify")
    c = sub.add_parser("crawl", help="completa la cola (reanudable; Ctrl+C para parar)")
    c.add_argument("--limit", type=int)
    sub.add_parser("status", help="artistas por nivel y estado de la cola")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # la consola de Windows usa cp1252 por defecto
    store, ing = open_default()
    if args.cmd == "import-poc":
        print(f"Importados {import_poc_cache(store, POC_CACHE)} archivos de la caché de la prueba.")
    elif args.cmd == "seed":
        names = spotify_artists(EXPORT_DIR)

        def progress(i, total, name):
            if i % 25 == 0 or i == total:
                print(f"\r{i}/{total} {name[:40]:40}", end="", flush=True)
        print(f"\n{seed(ing, names, progress)} artistas encolados de {len(names)} de tu export.")
    elif args.cmd == "crawl":
        try:
            r = crawl(ing, args.limit, lambda d, e, aid: print(f"\rcompletados {d} · errores {e}", end="", flush=True))
            print(f"\nFin: {r}")
        except KeyboardInterrupt:  # lo ya guardado se queda; el artista a medias se repite al relanzar
            print("\nInterrumpido. Relanza «crawl» para continuar.")
    _status(store)


if __name__ == "__main__":
    main()
