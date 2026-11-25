"""Prueba de concepto (desechable): servidor local que hace de proxy a Deezer + MusicBrainz con caché en disco.
Uso: python -I poc/server.py  ->  http://localhost:8766
"""
import json
import re
import threading
import time
import unicodedata
import urllib.parse
import urllib.request
from collections import Counter
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).parent
CACHE = HERE / "cache"
SPOTIFY = HERE.parent / "resources" / "Spotify Account Data"
UA = "ExploraMusica/0.1 (prueba local)"
CACHE.mkdir(exist_ok=True)

# Ritmo por servicio: MusicBrainz exige ≤1 petición/s; Deezer admite ~50 cada 5 s
_pace = {True: [threading.Lock(), 0.0, 1.1], False: [threading.Lock(), 0.0, 0.12]}


def get_json(url, musicbrainz=False):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(4):
        p = _pace[musicbrainz]
        with p[0]:
            wait = p[2] - (time.time() - p[1])
            if wait > 0:
                time.sleep(wait)
            p[1] = time.time()
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                data = json.load(r)
            if isinstance(data, dict) and data.get("error", {}).get("code") == 4 and attempt < 3:
                time.sleep(5)  # cuota de Deezer superada: esperar y reintentar
                continue
            return data
        except urllib.error.HTTPError as e:
            if e.code != 503 or attempt == 3:  # 503 = límite de ritmo: esperar y reintentar
                raise
            time.sleep(2 * (attempt + 1))


def cached(key, fn):
    f = CACHE / (re.sub(r"[^\w-]", "_", key) + ".json")
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    data = fn()
    if data.pop("_partial", False):  # respuesta incompleta (p. ej. MusicBrainz caído): no se guarda, se reintenta luego
        return data
    f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def norm(s):
    """Clave de comparación: sin tildes, mayúsculas ni signos ("Platero Y Tu" == "Platero y tú")."""
    s = unicodedata.normalize("NFKD", s.lower()).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "", s)


def mb_genres(name):
    """Géneros de MusicBrainz por nombre exacto; [] si no hay coincidencia fiable."""
    q = urllib.parse.quote(f'artist:"{name}"')
    res = get_json(f"https://musicbrainz.org/ws/2/artist/?query={q}&fmt=json&limit=3", True)
    cands = [a for a in res.get("artists", []) if a.get("score", 0) >= 95]
    # Primero nombre idéntico (Leño ≠ Leno); si no, igual sin tildes
    hit = next((a for a in cands if a["name"].lower() == name.lower()), None) or \
          next((a for a in cands if norm(a["name"]) == norm(name)), None)
    if not hit:
        return [], None
    d = get_json(f"https://musicbrainz.org/ws/2/artist/{hit['id']}?inc=genres&fmt=json", True)
    # Géneros oficiales; si no hay, etiquetas de usuarios (p. ej. «rock urbano»)
    gs = sorted(d.get("genres") or hit.get("tags", []), key=lambda g: -g["count"])
    return [g["name"] for g in gs[:3]], hit.get("country")


def deezer_genre(artist_id):
    albums = get_json(f"https://api.deezer.com/artist/{artist_id}/albums?limit=1").get("data", [])
    if not albums:
        return []
    g = get_json(f"https://api.deezer.com/album/{albums[0]['id']}").get("genres", {}).get("data", [])
    return [x["name"].lower() for x in g[:2]]


def artist(artist_id):
    def fetch():
        a = get_json(f"https://api.deezer.com/artist/{artist_id}")
        if "error" in a:
            raise ValueError(a["error"])
        related = get_json(f"https://api.deezer.com/artist/{artist_id}/related?limit=25").get("data", [])
        top = get_json(f"https://api.deezer.com/artist/{artist_id}/top?limit=1").get("data", [])
        partial = False
        try:
            genres, country = mb_genres(a["name"])
        except Exception as e:
            print(f"MusicBrainz falló para {a['name']}: {e}", flush=True)
            genres, country, partial = [], None, True
        if not genres:
            genres = deezer_genre(artist_id)
        return {
            "id": a["id"], "name": a["name"], "picture": a.get("picture_medium"), "fans": a.get("nb_fan", 0),
            "link": a.get("link"), "genres": genres or ["sin género"], "country": country,
            "preview": top[0]["preview"] if top else None, "previewTitle": top[0]["title"] if top else None,
            "_partial": partial,
            "related": [{"id": r["id"], "name": r["name"], "fans": r.get("nb_fan", 0)} for r in related],
        }
    return cached(f"artist_{artist_id}", fetch)


def related(artist_id):
    """Relacionadas de Deezer (sin MusicBrainz, para cargar listas grandes deprisa)."""
    f = CACHE / f"artist_{artist_id}.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))["related"]
    return cached(f"related_{artist_id}", lambda: {"related": [
        {"id": r["id"], "name": r["name"], "fans": r.get("nb_fan", 0)}
        for r in get_json(f"https://api.deezer.com/artist/{artist_id}/related?limit=25").get("data", [])]})["related"]


def resolve(name):
    """Artista de Deezer cuyo nombre normalizado coincide (el de más fans); None si no hay."""
    def fetch():
        res = get_json("https://api.deezer.com/search/artist?limit=10&q=" + urllib.parse.quote(name)).get("data", [])
        hits = [a for a in res if norm(a["name"]) == norm(name)]
        a = max(hits, key=lambda a: a.get("nb_fan", 0)) if hits else None
        return {"hit": a and {"id": a["id"], "name": a["name"], "fans": a.get("nb_fan", 0)}}
    return cached("resolve_" + (norm(name) or "x"), fetch)["hit"]


def find_path(a, b, max_expand=450, beam=15, fanout=15):
    """Camino de artistas relacionados entre a y b (ids de Deezer).
    Búsqueda bidireccional por capas sobre las relacionadas de Deezer (tratadas como no dirigidas);
    cada capa se recorta a las `beam` bandas con más fans, que son las que más conectan estilos."""
    if a == b:
        return [{"id": a, "name": None}]
    parents = ({a: None}, {b: None})
    frontier = ([a], [b])
    fans, names = {}, {}
    expanded = 0
    while (frontier[0] or frontier[1]) and expanded < max_expand:
        # se expande el lado con menos frente; si uno se agota (artista sin relacionadas), sigue el otro solo
        side = 0 if frontier[0] and (not frontier[1] or len(frontier[0]) <= len(frontier[1])) else 1
        mine_, other = parents[side], parents[1 - side]
        new = []
        for x in frontier[side]:
            expanded += 1
            for r in related(x)[:fanout]:
                fans[r["id"]] = r.get("fans", 0); names[r["id"]] = r["name"]
                if r["id"] in mine_:
                    continue
                mine_[r["id"]] = x
                if r["id"] in other:  # se tocan las dos búsquedas: reconstruir
                    m = r["id"]
                    left, node = [], m
                    while node is not None:
                        left.append(node); node = parents[0][node]
                    right, node = [], parents[1][m]
                    while node is not None:
                        right.append(node); node = parents[1][node]
                    return [{"id": i, "name": names.get(i)} for i in left[::-1] + right]
                new.append(r["id"])
            if expanded >= max_expand:
                break
        frontier = list(frontier)
        frontier[side] = sorted(new, key=lambda i: -fans.get(i, 0))[:beam]
        frontier = tuple(frontier)
    return None


def playlists():
    """«Mi top» (tus 40 artistas más escuchados) y tus playlists con sus artistas, de más a menos."""
    top = sorted(PROFILE.values(), key=lambda p: -p["min"])[:40]
    out = [{"name": "Mi top", "tracks": len(top), "artists": [[p["name"], p["min"]] for p in top], "top": True}]
    for p in json.loads((SPOTIFY / "Playlist1.json").read_text(encoding="utf-8"))["playlists"]:
        c = Counter(i["track"]["artistName"] for i in p["items"] if i.get("track"))
        out.append({"name": p["name"], "tracks": len(p["items"]), "artists": c.most_common()})
    return out[:1] + sorted(out[1:], key=lambda p: -p["tracks"])


def search(q):
    res = get_json("https://api.deezer.com/search/artist?limit=6&q=" + urllib.parse.quote(q))
    return [{"id": a["id"], "name": a["name"], "fans": a.get("nb_fan", 0), "picture": a.get("picture_small")}
            for a in res.get("data", [])]


def profile():
    """Huella: minutos por artista (historial) + nº de canciones en playlists y en «Me gusta»."""
    minutes, songs = Counter(), Counter()
    for f in SPOTIFY.glob("StreamingHistory_music_*.json"):
        for r in json.loads(f.read_text(encoding="utf-8")):
            minutes[r["artistName"]] += r["msPlayed"] / 60000
    for p in json.loads((SPOTIFY / "Playlist1.json").read_text(encoding="utf-8"))["playlists"]:
        for i in p["items"]:
            if i.get("track"):
                songs[i["track"]["artistName"]] += 1
    for t in json.loads((SPOTIFY / "YourLibrary.json").read_text(encoding="utf-8"))["tracks"]:
        songs[t["artist"]] += 1
    names = set(minutes) | set(songs)
    return {norm(n): {"name": n, "min": round(minutes[n]), "songs": songs[n]} for n in names if norm(n)}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(HERE), **kw)

    def send_json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(u.query)
        try:
            if u.path == "/api/search":
                return self.send_json(search(qs.get("q", [""])[0][:100]))
            if m := re.fullmatch(r"/api/artist/(\d+)", u.path):
                return self.send_json(artist(int(m.group(1))))
            if u.path == "/api/profile":
                return self.send_json(PROFILE)
            if u.path == "/api/playlists":
                return self.send_json(PLAYLISTS)
            if u.path == "/api/path":
                return self.send_json(find_path(int(qs["from"][0]), int(qs["to"][0])))
            if u.path == "/api/resolve":
                return self.send_json(resolve(qs.get("name", [""])[0][:200]))
            if m := re.fullmatch(r"/api/related/(\d+)", u.path):
                return self.send_json(related(int(m.group(1))))
        except Exception as e:  # la prueba muestra el error en el navegador en vez de colgarse
            return self.send_json({"error": str(e)}, 502)
        return super().do_GET()

    def log_message(self, fmt, *args):
        if "/api/" in str(args[0] if args else ""):
            print(fmt % args)


PROFILE = profile()
PLAYLISTS = playlists()

if __name__ == "__main__":
    assert norm("Platero Y Tu") == norm("Platero y tú") and norm("AC/DC") == "acdc"
    print(f"Huella cargada: {len(PROFILE)} artistas. Abre http://localhost:8766", flush=True)
    ThreadingHTTPServer.allow_reuse_address = False  # en Windows, True deja compartir el puerto con otro servidor
    ThreadingHTTPServer(("127.0.0.1", 8766), Handler).serve_forever()
