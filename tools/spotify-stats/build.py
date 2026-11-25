"""Genera web/index.html a partir del export de Spotify en resources/Spotify Account Data.
Uso: python -I tools/spotify-stats/build.py
Omite a propósito Payments, UserAddress, Identifiers y nombres de seguidores (datos personales).
"""
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote_plus

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent  # raíz del proyecto
DATA = ROOT / "resources" / "Spotify Account Data"
OUT = ROOT / "web" / "index.html"


def load(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def last_sunday(year, month):
    d = datetime(year, month, 31)
    return d - timedelta(days=(d.weekday() + 1) % 7)


def local(end_time):
    """UTC -> hora peninsular española (regla UE: CEST entre el último domingo de marzo y de octubre, 01:00 UTC)."""
    t = datetime.strptime(end_time, "%Y-%m-%d %H:%M")
    summer = last_sunday(t.year, 3) + timedelta(hours=1) <= t < last_sunday(t.year, 10) + timedelta(hours=1)
    return t + timedelta(hours=2 if summer else 1)


def top(counter, n):
    return [[k, round(v / 60000)] for k, v in counter.most_common(n)]


def build():
    music = load("StreamingHistory_music_0.json")
    pods = load("StreamingHistory_podcast_0.json")

    artist_ms, track_ms, track_plays = Counter(), Counter(), Counter()
    month_ms = defaultdict(lambda: [0, 0])  # [música, podcast]
    heat = [[0] * 24 for _ in range(7)]  # [día semana][hora] en minutos
    day_ms = Counter()
    skips = 0
    for r in music:
        ms, t = r["msPlayed"], local(r["endTime"])
        artist_ms[r["artistName"]] += ms
        key = f'{r["trackName"]} — {r["artistName"]}'
        track_ms[key] += ms
        if ms >= 30000:  # Spotify cuenta una reproducción a partir de 30 s
            track_plays[key] += 1
        else:
            skips += 1
        month_ms[t.strftime("%Y-%m")][0] += ms
        heat[t.weekday()][t.hour] += ms / 60000
        day_ms[t.date().isoformat()] += ms

    pod_ms, ep_ms = Counter(), Counter()
    for r in pods:
        ms, t = r["msPlayed"], local(r["endTime"])
        pod_ms[r["podcastName"]] += ms
        ep_ms[f'{r["episodeName"]} — {r["podcastName"]}'] += ms
        month_ms[t.strftime("%Y-%m")][1] += ms

    best_day = day_ms.most_common(1)[0]
    music_total = sum(r["msPlayed"] for r in music)
    pod_total = sum(r["msPlayed"] for r in pods)

    playlists = load("Playlist1.json")["playlists"]
    pl_artists = Counter(i["track"]["artistName"] for p in playlists for i in p["items"] if i.get("track"))
    library = load("YourLibrary.json")
    lib_artists = Counter(t["artist"] for t in library["tracks"])

    searches = load("SearchQueries.json")
    # Las búsquedas guardan cada pulsación ("c", "cri"...): nos quedamos con las de 4+ letras.
    search_top = Counter(s["searchQuery"].strip().lower() for s in searches if len(s["searchQuery"].strip()) >= 4)

    wrapped = load("Wrapped2025.json")
    capsule = load("YourSoundCapsule.json")
    follow = load("Follow.json")

    d = {
        "range": [music[0]["endTime"][:10], music[-1]["endTime"][:10]],
        "kpi": {
            "musicH": round(music_total / 3.6e6),
            "podH": round(pod_total / 3.6e6),
            "streams": len(music),
            "artists": len(artist_ms),
            "tracks": len(track_ms),
            "skipPct": round(100 * skips / len(music)),
            "bestDay": [best_day[0], round(best_day[1] / 60000)],
            "podcasts": len(pod_ms),
        },
        "months": sorted([k, round(v[0] / 60000), round(v[1] / 60000)] for k, v in month_ms.items()),
        "heat": [[round(x) for x in row] for row in heat],
        "topArtists": top(artist_ms, 20),
        "topTracks": top(track_ms, 20),
        "topPlays": track_plays.most_common(15),
        "topPods": top(pod_ms, 12),
        "topEps": top(ep_ms, 10),
        "playlists": sorted(({"name": p["name"], "date": p["lastModifiedDate"], "collab": len(p.get("collaborators") or []),
                              "items": [song(i) for i in p["items"]]} for p in playlists), key=lambda x: -len(x["items"])),
        "plArtists": pl_artists.most_common(15),
        "library": {k: len(library[k]) for k in ("tracks", "albums", "artists", "shows", "episodes")},
        "libArtists": lib_artists.most_common(10),
        "searches": search_top.most_common(15),
        "social": [len(follow["userIsFollowing"]), len(follow["userIsFollowedBy"])],
        "wrapped": {
            "totalH": round(wrapped["yearlyMetrics"]["totalMsListened"] / 3.6e6),
            "uniqueArtists": wrapped["topArtists"]["numUniqueArtists"],
            "uniqueTracks": wrapped["topTracks"]["numUniqueTracks"],
            "genres": wrapped["topGenres"]["totalNumGenres"],
            "topPct": round(wrapped["topArtists"]["topNPercentileFan"] * 100, 1),
            "listeningAge": wrapped["listeningAge"]["listeningAge"],
            "night": round(wrapped["party"]["percentListenedNight"]),
            "trueCrimeMin": wrapped["party"]["numMinsPlayedTrueCrime"],
            "sportsMin": wrapped["party"]["numMinsPlayedSports"],
            "club": wrapped["clubs"]["userClub"].replace("_", " ").title(),
        },
        "capsule": [
            {"date": s["date"], "h": round(s["secondsPlayed"] / 3600, 1),
             "artists": [a["name"] for a in s["topArtists"][:5]],
             "tracks": [t["name"] for t in s["topTracks"][:5]]}
            for s in capsule["stats"]
        ],
        "highlights": [highlight(h) for h in capsule["highlights"]],
    }
    d["highlights"] = [h for h in d["highlights"] if h]

    html = (HERE / "template.html").read_text(encoding="utf-8")
    payload = json.dumps(d, ensure_ascii=False).replace("</", "<\\/")
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(html.replace("/*DATA*/null", payload), encoding="utf-8")
    return d


def song(item):
    """Elemento de playlist -> [título, artista, álbum, fecha añadida, url o ""]."""
    if t := item.get("track"):
        return [t["trackName"], t["artistName"], t["albumName"], item["addedDate"],
                "https://open.spotify.com/track/" + t["trackUri"].rsplit(":", 1)[-1]]
    if e := item.get("episode"):
        return [e["episodeName"], e["showName"], "Podcast", item["addedDate"],
                "https://open.spotify.com/episode/" + e["episodeUri"].rsplit(":", 1)[-1]]
    # Archivo local: spotify:local:artista:álbum:título:duración
    parts = [unquote_plus(x) for x in item["localTrack"]["uri"].split(":")[2:5]]
    return [parts[2], parts[0], parts[1] + " (archivo local)", item["addedDate"], ""]


def highlight(h):
    t = h["highlightType"]
    if t == "TIME_WELL_SPENT":
        x = h["timeWellSpentHighlight"]
        it = x["items"][0]
        return [h["date"], f'{x["dimension"].capitalize()} de la semana: {it["entity"]} ({round(it["secondsPlayed"] / 3600, 1)} h)']
    if t == "MILESTONE":
        x = h.get("milestoneHighlight") or h["multiEntityMilestoneHighlight"]
        who = x.get("entity") or ", ".join(x["entities"][:3])
        return [h["date"], f'Hito: {round(x["milestoneListeningSeconds"] / 3600, 1)} h escuchando {who}']
    if t == "FIRST_TO_DISCOVER":
        x = h["firstToDiscoverHighlight"]
        return [h["date"], f'Pionero: oyente nº {x["position"]} de «{x["entity"]}» en {x["country"]}']
    if t == "PROPORTION_LISTENING_ENTITY":
        x = h["proportionListeningHighlight"]
        return [h["date"], f'{x["entity"]} fue el {round(x["listeningPercentage"])} % de tu escucha']
    if t == "UNLIKE_COMBINATION":
        x = h["unlikeCombinationHighlight"]
        return [h["date"], f'Combinación improbable: «{x["firstEntity"]}» y «{x["secondEntity"]}»']
    if t == "STREAKS":
        x = h["streaksHighlight"]
        return [h["date"], f'Racha: {x["dayStreaks"]} días seguidos con {x["entity"]}']
    if t == "YOU_STAND_OUT":
        x = h["youStandOutHighlight"]
        return [h["date"], f'Destacas: {x["entity"]} {round(x["secondsPlayed"] / x["marketAvgSecondsPlayed"])}× más que la media en {x["country"]}']
    if t == "ON_REPEAT":
        x = h["onRepeatHighlight"]
        return [h["date"], f'En bucle: «{x["entity"]}» {x["streamCount"]} veces']
    if t == "MONTHLY_RECAP":
        x = h["monthlyRecapHighlight"]
        return [h["date"], f'Resumen del mes: {round(x["totalSecondsPlayed"] / 3600)} h · top: {", ".join(x["topArtists"][:3])}']
    return None


if __name__ == "__main__":
    d = build()
    # Autocomprobación mínima
    assert d["kpi"]["streams"] > 0 and len(d["heat"]) == 7 and all(len(r) == 24 for r in d["heat"])
    assert song({"localTrack": {"uri": "spotify:local:Vlood:Amine+Rami:Now+%28Extended+Mix%29:350"}, "addedDate": "x"})[:3] == ["Now (Extended Mix)", "Vlood", "Amine Rami (archivo local)"]
    assert sum(len(p["items"]) for p in d["playlists"]) == 1760
    assert local("2026-07-01 10:00").hour == 12 and local("2026-01-01 10:00").hour == 11
    assert last_sunday(2026, 3).day == 29 and last_sunday(2026, 10).day == 25
    assert abs(sum(m[1] for m in d["months"]) / 60 - d["kpi"]["musicH"]) < 2  # meses suman el total
    print("OK ->", OUT, "| KPIs:", d["kpi"])
