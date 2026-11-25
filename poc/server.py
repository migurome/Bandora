"""Servidor local de Weave: API sobre la base de datos de artistas (weave/) + la página de la prueba de concepto.
Uso: python -I poc/server.py  ->  http://localhost:8766
Los ids que ve la página son ids internos de la BD; lo que falta se completa bajo demanda y se guarda.
"""
import json
import re
import sys
import urllib.parse
from collections import Counter
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))  # con python -I la raíz del proyecto no está en la ruta

from weave import graph  # noqa: E402
from weave.ingest import EXPORT_DIR, open_default  # noqa: E402
from weave.text import norm  # noqa: E402


def profile(export_dir=EXPORT_DIR):
    """Huella: minutos por artista (historial) + nº de canciones en playlists y en «Me gusta»."""
    minutes, songs = Counter(), Counter()
    for f in export_dir.glob("StreamingHistory_music_*.json"):
        for r in json.loads(f.read_text(encoding="utf-8")):
            minutes[r["artistName"]] += r["msPlayed"] / 60000
    for p in json.loads((export_dir / "Playlist1.json").read_text(encoding="utf-8"))["playlists"]:
        for i in p["items"]:
            if i.get("track"):
                songs[i["track"]["artistName"]] += 1
    for t in json.loads((export_dir / "YourLibrary.json").read_text(encoding="utf-8"))["tracks"]:
        songs[t["artist"]] += 1
    names = set(minutes) | set(songs)
    return {norm(n): {"name": n, "min": round(minutes[n]), "songs": songs[n]} for n in names if norm(n)}


def playlists(prof, export_dir=EXPORT_DIR):
    """«Mi top» (tus 40 artistas más escuchados) y tus playlists con sus artistas, de más a menos."""
    top = sorted(prof.values(), key=lambda p: -p["min"])[:40]
    out = [{"name": "Mi top", "tracks": len(top), "artists": [[p["name"], p["min"]] for p in top], "top": True}]
    for p in json.loads((export_dir / "Playlist1.json").read_text(encoding="utf-8"))["playlists"]:
        c = Counter(i["track"]["artistName"] for i in p["items"] if i.get("track"))
        out.append({"name": p["name"], "tracks": len(p["items"]), "artists": c.most_common()})
    return out[:1] + sorted(out[1:], key=lambda p: -p["tracks"])


def make_app(store, ingestor, profile, playlists):
    """Clase de handler ligada a un almacén y un ingestor (así las pruebas usan fuentes falsas)."""

    def artist_view(aid):
        if store.artist(aid) is None:
            return None
        aid = ingestor.ensure_full(aid)
        ingestor.refresh_preview(aid)
        return store.artist(aid)

    def path(a, b):
        ids = graph.find_path(store, a, b)
        if ids is None and any((store.artist(x) or {}).get("level", 0) < 1 for x in (a, b)):
            for x in (a, b):  # algún extremo aún sin relacionadas: se completan y se reintenta una vez
                ingestor.ensure_related(x)
            ids = graph.find_path(store, a, b)
        return ids and [{"id": i, "name": store.artist(i)["name"]} for i in ids]

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
                    return self.send_json(ingestor.search(qs.get("q", [""])[0][:100])[:6])
                if m := re.fullmatch(r"/api/artist/(\d+)", u.path):
                    a = artist_view(int(m.group(1)))
                    return self.send_json(a) if a else self.send_json({"error": "artista desconocido"}, 404)
                if u.path == "/api/resolve":
                    aid = ingestor.resolve_name(qs.get("name", [""])[0][:200])
                    a = aid and store.artist(aid)
                    return self.send_json(a and {"id": a["id"], "name": a["name"], "fans": a["fans"]})
                if m := re.fullmatch(r"/api/related/(\d+)", u.path):
                    aid = int(m.group(1))
                    if store.artist(aid) is None:
                        return self.send_json({"error": "artista desconocido"}, 404)
                    return self.send_json(store.artist(ingestor.ensure_related(aid))["related"])
                if u.path == "/api/path":
                    return self.send_json(path(int(qs["from"][0]), int(qs["to"][0])))
                if u.path == "/api/profile":
                    return self.send_json(profile)
                if u.path == "/api/playlists":
                    return self.send_json(playlists)
            except Exception as e:  # la página muestra el error en vez de quedarse colgada
                return self.send_json({"error": f"{type(e).__name__}: {e}"}, 502)
            return super().do_GET()

        def log_message(self, fmt, *args):
            if "/api/" in str(args[0] if args else ""):
                print(fmt % args)

    return Handler


if __name__ == "__main__":
    store, ingestor = open_default()
    prof = profile()
    print(f"Huella cargada: {len(prof)} artistas. Abre http://localhost:8766", flush=True)
    ThreadingHTTPServer.allow_reuse_address = False  # en Windows, True deja compartir el puerto con otro servidor
    ThreadingHTTPServer(("127.0.0.1", 8766), make_app(store, ingestor, prof, playlists(prof))).serve_forever()
