"""Servidor local de Weave: la página (weave/static) y una API mínima sobre la base de datos de artistas.
Uso: python -m weave.server  ->  http://localhost:8766
Los ids que ve la página son ids internos de la BD; lo que falta se completa bajo demanda y se guarda.
"""
import json
import re
import socket
import threading
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import graph
from .ingest import open_default

STATIC = Path(__file__).resolve().parent / "static"
PORT = 8766


def make_app(store, ingestor):
    """Clase de handler ligada a un almacén y un ingestor (así las pruebas usan fuentes falsas)."""

    def path(a, b):
        ids = graph.find_path(store, a, b)
        if ids is None and any((store.artist(x) or {}).get("level", 0) < 1 for x in (a, b)):
            for x in (a, b):  # algún extremo aún sin relacionadas: se completan y se reintenta una vez
                ingestor.ensure_related(x)
            ids = graph.find_path(store, a, b)
        return ids and [{"id": i, "name": store.artist(i)["name"]} for i in ids]

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(STATIC), **kw)

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
                if m := re.fullmatch(r"/api/(artist|top)/(\d+)", u.path):
                    aid = int(m.group(2))
                    if store.artist(aid) is None:
                        return self.send_json({"error": "artista desconocido"}, 404)
                    if m.group(1) == "top":
                        return self.send_json(ingestor.top_tracks(aid))
                    return self.send_json(store.artist(ingestor.ensure_full(aid)))
                if u.path == "/api/path":
                    return self.send_json(path(int(qs["from"][0]), int(qs["to"][0])))
            except Exception as e:  # la página muestra el error en vez de quedarse colgada
                return self.send_json({"error": f"{type(e).__name__}: {e}"}, 502)
            return super().do_GET()

        def log_message(self, fmt, *args):
            if "/api/" in str(args[0] if args else ""):
                print(fmt % args)

    return Handler


class _Server6(ThreadingHTTPServer):
    address_family = socket.AF_INET6


def main():
    store, ingestor = open_default()
    app = make_app(store, ingestor)
    ThreadingHTTPServer.allow_reuse_address = False  # en Windows, True deja compartir el puerto con otro servidor
    # «localhost» en Windows prueba antes ::1 que 127.0.0.1: escuchar en las dos evita ~2 s de espera por petición
    servers = [ThreadingHTTPServer(("127.0.0.1", PORT), app)]
    try:
        servers.append(_Server6(("::1", PORT), app))
    except OSError:
        pass  # sin IPv6 local: basta con IPv4
    for s in servers[1:]:
        threading.Thread(target=s.serve_forever, daemon=True).start()
    print(f"Weave en http://localhost:{PORT}", flush=True)
    servers[0].serve_forever()


if __name__ == "__main__":
    main()
