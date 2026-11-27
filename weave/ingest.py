"""Ingesta: completa artistas bajo demanda desde Deezer y MusicBrainz; semilla, rastreo reanudable y CLI."""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from .families import clean_tags
from .sources import SourceError
from .text import norm

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "weave.db"
KEY_PATH = ROOT / "data" / "lastfm_key.txt"  # fuera de git; sin ella no se usa Last.fm
# Contacto que exige la política de Wikimedia; lo escribe el usuario (fuera de git). Sin él, Wikidata nos limita.
CONTACT_PATH = ROOT / "data" / "wikidata_contact.txt"
EXPORT_DIR = ROOT / "resources" / "Spotify Account Data"
POC_CACHE = ROOT / "poc" / "cache"

FULL, RELATED = 2, 1


class Ingestor:
    def __init__(self, store, deezer, mb, lastfm=None, wikidata=None):
        self.store, self.dz, self.mb, self.lastfm, self.wikidata = store, deezer, mb, lastfm, wikidata

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
        self.enrich_lastfm(artist_id)
        self.enrich_wikidata(artist_id)
        artist_id = self.store.dedupe_by_name(artist_id)
        self.store.set_level(artist_id, FULL)
        return artist_id

    def enrich_lastfm(self, artist_id: int) -> bool:
        """Géneros de Last.fm (filtrados) y sus parecidos como relaciones con peso.
        Devuelve False si Last.fm no está o falla: el artista queda pendiente para otro relleno."""
        if not self.lastfm:
            return False
        name = self.store.artist(artist_id)["name"]
        try:
            tags, similar = self.lastfm.top_tags(name), self.lastfm.similar(name)
        except Exception:  # noqa: BLE001 - sin Last.fm se queda con MusicBrainz/Deezer
            return False
        genres = clean_tags(tags, name)
        if genres:
            self.store.set_genres(artist_id, genres, "lastfm")
        ids, weights = [], []
        for i, s in enumerate(sorted(similar, key=lambda s: -s["match"])):
            aid = self.store.by_alias(norm(s["name"]))
            if aid is None and i < 10:  # solo los más parecidos merecen una búsqueda en Deezer
                try:
                    aid = self.resolve_name(s["name"])
                except (SourceError, OSError):
                    aid = None
            if aid and aid != artist_id and aid not in ids:
                ids.append(aid); weights.append(s["match"])
        if ids:
            self.store.set_related(artist_id, ids, "lastfm", weights)
        self.store.mark_lastfm(artist_id)
        return True

    def enrich_wikidata(self, artist_id: int) -> bool:
        """Sinergias de Wikidata (miembros compartidos, influencias) como relaciones simétricas.
        Devuelve False si Wikidata no está o falla: el artista queda pendiente para otro relleno."""
        if not self.wikidata:
            return False
        mbid = self.store.mbid(artist_id)
        if not mbid:  # Wikidata se consulta por MBID: si falta, se busca en MusicBrainz
            try:
                found = self.mb.lookup(self.store.artist(artist_id)["name"])
            except Exception:  # noqa: BLE001 - MusicBrainz caído: se reintenta en otro relleno
                return False
            if found:
                artist_id = self.store.attach_mbid(artist_id, found["mbid"])
                mbid = self.store.mbid(artist_id)
        if not mbid:
            self.store.mark_wikidata(artist_id)  # sin MBID no hay nada que preguntar
            return True
        try:
            synergies = self.wikidata.synergies(mbid)
        except Exception:  # noqa: BLE001 - Wikidata caído o con límite
            return False
        pairs, searched = {"member": [], "influence": []}, 0
        for syn in synergies:
            other = self.store.by_mbid(syn["mbid"])
            for name in syn.get("names", [syn["name"]]):  # primero el nombre artístico, luego el civil
                if other:
                    break
                other = self.store.by_alias(norm(name))
                if other is None and searched < 5:  # solo unas pocas búsquedas en Deezer por artista
                    searched += 1
                    try:
                        other = self.resolve_name(name)
                    except (SourceError, OSError):
                        other = None
            if other and other != artist_id:
                pairs[syn["kind"]].append((artist_id, other))
        self.store.drop_relations(artist_id, "wikidata")  # al repetir, lo de la vez anterior se sustituye
        for kind, ps in pairs.items():
            if ps:
                self.store.add_relations(ps, kind, "wikidata")
        self.store.mark_wikidata(artist_id)
        return True

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
        hits = [a for a in self.dz.search(name) if norm(a["name"]) == k and a.get("albums", 1) > 0]  # fichas vacías no
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


def open_default(db_path=DB_PATH, key_path=KEY_PATH, contact_path=CONTACT_PATH):
    from .db import connect
    from .http import DEEZER, LASTFM, MUSICBRAINZ, WIKIDATA, Fetcher
    from .sources import Deezer, LastFm, MusicBrainz, Wikidata
    from .store import Store
    contact = Path(contact_path).read_text(encoding="utf-8").strip() if Path(contact_path).exists() else ""
    agents = {WIKIDATA: f"Weave/0.1 (proyecto personal; {contact})"} if contact else {}
    f = Fetcher({MUSICBRAINZ: 1.1, DEEZER: 0.12, LASTFM: 0.25, WIKIDATA: 1.0}, user_agents=agents)
    store = Store(connect(db_path))
    key = Path(key_path).read_text(encoding="utf-8").strip() if Path(key_path).exists() else ""
    return store, Ingestor(store, Deezer(f), MusicBrainz(f), LastFm(f, key) if key else None, Wikidata(f))


def enrich_pending(ingestor, limit=None, on_progress=None, which="lastfm") -> int:
    """Pasa por Last.fm o Wikidata los artistas completos que aún no lo tienen (reanudable: lastfm_at / wikidata_at)."""
    pending = ingestor.store.pending_lastfm if which == "lastfm" else ingestor.store.pending_wikidata
    enrich = ingestor.enrich_lastfm if which == "lastfm" else ingestor.enrich_wikidata
    done, tried, failures = 0, set(), 0
    while limit is None or done < limit:
        # los que fallan en esta pasada se saltan sin marcar: quedan pendientes para el próximo relleno
        nxt = next((a for a in pending(len(tried) + 1) if a not in tried), None)
        if nxt is None:
            break
        tried.add(nxt)
        if enrich(nxt):
            done, failures = done + 1, 0
            if on_progress:
                on_progress(done, nxt)
        else:
            failures += 1
            if failures >= 3:  # la fuente no responde (o nos limita): se para en vez de insistir
                break
    return done


def prune(ingestor, max_fans=100, on_progress=None) -> int:
    """Borra las fichas vacías de Deezer (0 álbumes: sin canciones ni relacionadas) que se colaron antes del filtro
    de resolve_name. Solo pregunta por las pequeñas: una ficha vacía no junta más de un puñado de fans."""
    rows = ingestor.store.conn.execute("""SELECT a.id, s.ext_id FROM artist a JOIN source_id s ON s.artist_id = a.id
                                          AND s.source = 'deezer' WHERE COALESCE(a.fans, 0) <= ?""", (max_fans,)).fetchall()
    gone = 0
    for i, (aid, ext) in enumerate(rows, 1):
        try:
            empty = ingestor.dz.artist(int(ext)).get("albums", 1) == 0
        except (SourceError, OSError):
            continue  # sin respuesta no se borra nada
        if empty:
            ingestor.store.delete(aid)
            gone += 1
        if on_progress:
            on_progress(i, len(rows), gone)
    return gone


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
    lf = sub.add_parser("lastfm", help="completa con Last.fm los artistas que aún no lo tienen (reanudable)")
    lf.add_argument("--limit", type=int)
    wd = sub.add_parser("wikidata", help="añade las sinergias de Wikidata (miembros, influencias); reanudable")
    wd.add_argument("--limit", type=int)
    sub.add_parser("prune", help="borra las fichas vacías de Deezer (0 álbumes) que haya en la base")
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
    elif args.cmd == "lastfm":
        if not ing.lastfm:
            print(f"Falta la clave de Last.fm en {KEY_PATH}")
        else:
            try:
                n = enrich_pending(ing, args.limit, lambda d, aid: print(f"{chr(13)}completados con Last.fm: {d}", end="", flush=True))
                print(f"{chr(10)}Fin: {n} artistas.")
            except KeyboardInterrupt:
                print(chr(10) + "Interrumpido. Relanza «lastfm» para continuar.")
    elif args.cmd == "wikidata":
        try:
            n = enrich_pending(ing, args.limit, lambda d, aid: print(f"{chr(13)}completados con Wikidata: {d}", end="", flush=True),
                               which="wikidata")
            print(f"{chr(10)}Fin: {n} artistas.")
        except KeyboardInterrupt:
            print(chr(10) + "Interrumpido. Relanza «wikidata» para continuar.")
    elif args.cmd == "prune":
        try:
            n = prune(ing, on_progress=lambda i, t, g: print(f"{chr(13)}revisadas {i}/{t} · borradas {g}", end="", flush=True))
            print(f"{chr(10)}Fin: {n} fichas vacías borradas.")
        except KeyboardInterrupt:
            print(chr(10) + "Interrumpido. Relanza «prune» para continuar.")
    _status(store)


if __name__ == "__main__":
    main()
