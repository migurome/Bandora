"""Exporta la base de datos a un JSON estático que la app lee sin servidor (app de móvil sola).
Uso: python -m weave.export  ->  weave/static/data/weave.json
Formato:
  version     fecha de la exportación (la app vuelve a bajarlo si cambia)
  families    [{name, color, pattern}] y rockFirst: las reglas de weave/families.json, para los artistas en vivo
  artists     [[id, nombre, fans, foto, deezerId, índice de familia, género], ...]
              foto: hash de Deezer (32 hex) si es una foto de artista de Deezer; si no, la URL; o ""
  related     {"id": [otroId | [otroId, motivo], ...]} todas, en el orden en que se despliegan;
              un número solo es «parecido»; motivo 1 influencia, 2 miembros
"""
import json
import re
import time
from collections import defaultdict
from pathlib import Path

from .families import _DATA as FAMILIES_JSON, family_of_list
from .store import KINDS, SOURCE_ORDER, Store, _dedupe

OUT = Path(__file__).resolve().parent / "static" / "data" / "weave.json"
PIC = re.compile(r"/images/artist/([0-9a-f]{32})/")


def build(store: Store) -> dict:
    con = store.conn
    names = [f["name"] for f in FAMILIES_JSON["families"]]
    genres = defaultdict(list)
    for aid, name, weight, source in con.execute("SELECT artist_id, name, weight, source FROM genre"):
        genres[aid].append((SOURCE_ORDER.get(source, 9), -(weight or 0), name))
    deezer = {}
    for aid, ext in con.execute("SELECT artist_id, ext_id FROM source_id WHERE source='deezer'"):
        deezer.setdefault(aid, int(ext))
    related = {}
    for (aid,) in con.execute("SELECT DISTINCT a FROM relation").fetchall():
        a = store.artist(aid)
        if a is None:  # borrado mientras se exporta (p. ej. con «prune» en marcha)
            continue
        rel = a["related"]
        related[str(aid)] = [[r["id"], k] if (k := KINDS.index(r["kind"])) else r["id"] for r in rel]
    # solo los que se pueden alcanzar desplegando: con relacionadas o dentro de alguna lista
    keep = {int(a) for a in related} | {x if isinstance(x, int) else x[0] for rel in related.values() for x in rel}
    artists = []
    for aid, name, fans, picture in con.execute("SELECT id, name, fans, picture FROM artist ORDER BY id"):
        if aid not in keep:
            continue
        gs = _dedupe([g for *_, g in sorted(genres[aid])]) or ["sin género"]
        m = PIC.search(picture or "")
        artists.append([aid, name, fans or 0, m.group(1) if m else (picture or ""), deezer.get(aid, 0),
                        names.index(family_of_list(gs)), gs[0]])
    return {"version": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "families": [{"name": f["name"], "color": f["color"], "pattern": f.get("pattern", "")} for f in FAMILIES_JSON["families"]],
            "rockFirst": FAMILIES_JSON["rock_first"], "artists": artists, "related": related}


def main():
    from .db import connect
    from .ingest import DB_PATH
    out = build(Store(connect(DB_PATH)))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{OUT}: {len(out['artists'])} artistas, {len(out['related'])} con relacionadas, {OUT.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
