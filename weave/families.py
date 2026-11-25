"""Familias de género: una sola definición (families.json, editable) para el servidor y la página."""
import json
import re
from pathlib import Path

from .text import norm

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


# Etiquetas de Last.fm que no son géneros
NON_GENRES = {"seen live", "favorites", "favourite", "spanish", "español", "british", "american", "usa", "uk",
              "female vocalists", "male vocalists", "80s", "90s", "00s", "70s", "60s", "love", "beautiful", "awesome"}


def clean_tags(tags, artist_name) -> list[tuple[str, int]]:
    """Deja solo etiquetas que son géneros reconocibles: fuera las de poco peso, el propio nombre y las genéricas."""
    out = []
    for tag, weight in tags:
        t = tag.lower().strip()
        if weight < 10 or t in NON_GENRES or norm(t) == norm(artist_name) or family_of(t) == OTHER:
            continue
        out.append((t, weight))
    return out[:5]
