"""Publica la app en GitHub Pages: exporta los datos y sube weave/static/ a la rama gh-pages del remoto indicado.
La rama se rehace en cada publicación (solo interesa la última versión). La app no lleva claves ni datos personales:
solo la red de artistas exportada (data/weave.json).
Uso:  python -I tools/publish.py <remoto>    p. ej.  python -I tools/publish.py https://github.com/<usuario>/weave-bands.git
Después, en GitHub: Settings → Pages → rama gh-pages. La app queda en https://<usuario>.github.io/<repositorio>/
"""
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


def git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True)


def main(remote: str) -> int:
    sys.path.insert(0, str(ROOT))
    from weave import export
    export.main()
    with tempfile.TemporaryDirectory(prefix="weave-pages-") as tmp:
        out = Path(tmp)
        for rel in files_to_publish(STATIC):
            (out / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(STATIC / rel, out / rel)
        (out / ".nojekyll").write_text("")  # que GitHub sirva los archivos tal cual
        git("init", "-q", "-b", "gh-pages", cwd=out)
        git("add", "-A", cwd=out)
        # firma genérica: el repositorio de Pages es público y no debe llevar el correo del usuario
        git("-c", "user.name=Weave bands", "-c", "user.email=weave-bands@users.noreply.github.com",
            "commit", "-q", "-m", "Publicar Weave bands", cwd=out)
        git("push", "-q", "--force", remote, "gh-pages", cwd=out)
    print(f"Publicado en la rama gh-pages de {remote}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
