"""Prueba de humo de la interfaz en un Edge sin ventana: recorre los flujos principales y lista ok/MAL.
Uso (con el servidor arrancado: python -m weave.server):  python -I tools/smoke.py
Usa la red (Deezer) para lo que no esté en la base de datos; el camino Marea → Michael Jackson puede tardar.
"""
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "weave" / "static" / "index.html"
TEMP = ROOT / "weave" / "static" / "_smoke.html"
EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
URL = "http://localhost:8766"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        urllib.request.urlopen(URL, timeout=5)
    except OSError:
        print(f"El servidor no responde en {URL}: arráncalo con  python -m weave.server")
        return 2
    page = PAGE.read_text(encoding="utf-8")
    # la prueba sustituye al arranque final (render y service worker, que con tiempo virtual no arranca)
    cut = page.rindex("render();\n")
    end = page.index("</script>", cut)
    TEMP.write_text(page[:cut] + (Path(__file__).parent / "smoke.js").read_text(encoding="utf-8") + "\n" + page[end:],
                    encoding="utf-8")
    try:
        out = subprocess.run([str(EDGE), "--headless=new", "--disable-gpu", "--autoplay-policy=no-user-gesture-required",
                              "--virtual-time-budget=120000", "--dump-dom", f"{URL}/{TEMP.name}"],
                             capture_output=True, timeout=300).stdout.decode("utf-8", "replace")
    finally:
        TEMP.unlink(missing_ok=True)
    m = re.search(r"<title>(.*?)</title>", out, re.S)
    lines = [x.strip() for x in (m.group(1) if m else "sin resultado").split("|")]
    print("\n".join(lines))
    return 0 if lines and all(x.startswith("ok ") for x in lines) else 1


if __name__ == "__main__":
    sys.exit(main())
