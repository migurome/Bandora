"""Familias de género: una sola definición (families.json, editable) para el servidor y la página."""
import json
import re
from pathlib import Path

_DATA = json.loads((Path(__file__).with_name("families.json")).read_text(encoding="utf-8"))
_ROCK_FIRST = re.compile(_DATA["rock_first"])
FAMILIES = [(f["name"], f["color"], re.compile(f["pattern"]) if f.get("pattern") else None) for f in _DATA["families"]]
OTHER = FAMILIES[-1][0]
_COLOR = {name: color for name, color, _ in FAMILIES}
_ORDER = {name: i for i, (name, _, _) in enumerate(FAMILIES)}


def family_of(genre: str) -> str:
    g = genre.lower()
    if _ROCK_FIRST.search(g):  # «blues rock», «folk rock», «hard rock»… son rock antes que su prefijo
        return "Rock"
    return next((name for name, _, rx in FAMILIES if rx and rx.search(g)), OTHER)


def family_of_list(genres: list[str]) -> str:
    """Primera familia reconocible de la lista (así «spanish» no tapa a «rock»)."""
    return next((f for f in map(family_of, genres) if f != OTHER), OTHER)


def color_of(family: str) -> str:
    return _COLOR.get(family, _COLOR[OTHER])


def order_of(family: str) -> int:
    return _ORDER.get(family, _ORDER[OTHER])
