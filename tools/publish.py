"""Publica la app en GitHub Pages: exporta los datos y sube weave/static/ a la rama gh-pages del remoto indicado.
La versión sale de `const VERSION` en index.html: «v0.3.10» es oficial y va a la raíz (las betas publicadas se
conservan); «b0.3.11» es beta y va a su carpeta (…/weave-bands/b0.3.11/) sin tocar lo demás. Desde la app,
«/version b0.3.11» lleva a ella. La rama se rehace en cada publicación, sin historial. La app no lleva claves ni datos personales:
solo la red de artistas exportada (data/weave.json).
Uso:  python -I tools/publish.py <remoto>    p. ej.  python -I tools/publish.py https://github.com/<usuario>/weave-bands.git
Después, en GitHub: Settings → Pages → rama gh-pages. La app queda en https://<usuario>.github.io/<repositorio>/
"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "weave" / "static"


def files_to_publish(static: Path) -> list[Path]:
    """Todo lo de la app salvo las páginas temporales de las pruebas (_smoke, _pwa, _shot…)."""
    return [p.relative_to(static) for p in sorted(static.rglob("*")) if p.is_file() and not p.name.startswith("_")]


def app_version(page: str) -> str:
    m = re.search(r"const VERSION = '([vb]\d[^']*)'", page)
    if not m:
        raise ValueError("index.html: VERSION debe empezar por v (oficial) o b (beta)")
    return m.group(1)


def target_dir(version: str) -> str:
    return version if version.startswith("b") else ""


def keep_from_old(old: list[str], version: str) -> list[str]:
    """Lo publicado antes que sigue: con una oficial, las carpetas de las betas; con una beta, todo menos su carpeta."""
    beta = re.compile(r"^b\d[^/]*/")
    if version.startswith("b"):
        return [p for p in old if not p.startswith(version + "/")]
    return [p for p in old if beta.match(p)]


def git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True)


def main(remote: str) -> int:
    sys.path.insert(0, str(ROOT))
    from weave import export
    export.main()
    version = app_version((STATIC / "index.html").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="weave-pages-") as tmp:
        prev, out = Path(tmp) / "prev", Path(tmp) / "out"
        clone = subprocess.run(["git", "clone", "-q", "--depth", "1", "-b", "gh-pages", remote, str(prev)])
        old = [] if clone.returncode else [p.relative_to(prev).as_posix() for p in prev.rglob("*")
                                           if p.is_file() and ".git" not in p.relative_to(prev).parts]
        for rel in keep_from_old(old, version):
            (out / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(prev / rel, out / rel)
        dest = out / target_dir(version)
        for rel in files_to_publish(STATIC):
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(STATIC / rel, dest / rel)
        (out / ".nojekyll").write_text("")  # que GitHub sirva los archivos tal cual
        git("init", "-q", "-b", "gh-pages", cwd=out)
        git("add", "-A", cwd=out)
        # firma genérica: el repositorio de Pages es público y no debe llevar el correo del usuario
        git("-c", "user.name=Weave bands", "-c", "user.email=weave-bands@users.noreply.github.com",
            "commit", "-q", "-m", f"Publicar Weave bands {version}", cwd=out)
        git("push", "-q", "--force", remote, "gh-pages", cwd=out)
    print(f"Publicada {version} en la rama gh-pages de {remote}" + (f" (carpeta {version}/)" if target_dir(version) else ""))
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
