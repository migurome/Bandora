"""Comprueba la PWA en un Edge sin ventana y en tiempo real: que el service worker se registra y guarda
lo necesario para funcionar sin conexión. (Con --virtual-time-budget el service worker no llega a arrancar,
por eso esto no va en smoke.py.)
Uso (con el servidor arrancado: python -m weave.server):  python -I tools/pwa.py
"""
import json
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROBE = ROOT / "weave" / "static" / "_pwa.html"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PORT = 9333  # depuración remota de Edge
NEEDED = ["/", "/index.html", "/data.js", "/manifest.json", "/d3.min.js", "/weave-icon.svg", "/icon-192.png", "/icon-512.png",
          "/data/weave.json"]

PAGE = """<!doctype html><title>inicio</title><script>
const NEEDED = """ + json.dumps(NEEDED) + """;
(async () => {
  try {
    await navigator.serviceWorker.register('sw.js');
    await navigator.serviceWorker.ready;
    await new Promise(r => setTimeout(r, 1500));
    const name = (await caches.keys()).find(k => k.startsWith('weave-bands-app'));
    const keys = name ? (await (await caches.open(name)).keys()).map(q => q.url.replace(location.origin, '')) : [];
    const missing = NEEDED.filter(u => !keys.includes(u));
    document.title = !name ? 'FALTA caché' : missing.length ? 'FALTA ' + missing.join(' ') : 'GUARDADO';
  } catch (e) { document.title = 'ERR ' + e.message; }
})();
</script>"""


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    PROBE.write_text(PAGE, encoding="utf-8")
    profile = tempfile.mkdtemp(prefix="weave-pwa-")  # perfil limpio: sin service worker de otras pruebas
    edge = subprocess.Popen([EDGE, "--headless=new", "--disable-gpu", f"--user-data-dir={profile}",
                             f"--remote-debugging-port={PORT}", "http://localhost:8766/_pwa.html"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    title = ""
    try:
        for _ in range(30):
            time.sleep(1)
            try:
                targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list", timeout=2))
            except OSError:
                continue
            title = next((t["title"] for t in targets if t["type"] == "page" and "_pwa.html" in t["url"]), "")
            if title.startswith(("GUARDADO", "FALTA", "ERR")):
                break
    finally:
        edge.kill()
        PROBE.unlink(missing_ok=True)
        time.sleep(1)
        shutil.rmtree(profile, ignore_errors=True)
    if title == "GUARDADO":
        print("ok service worker registrado y guarda todo para usarla sin conexión")
        return 0
    print("MAL service worker:", title or "sin respuesta")
    return 1


if __name__ == "__main__":
    sys.exit(main())
