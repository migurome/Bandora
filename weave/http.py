"""GET de JSON con ritmo por servicio y reintentos ante los límites de cada API."""
import json
import threading
import time
import urllib.error
import urllib.request

DEEZER = "deezer"
MUSICBRAINZ = "musicbrainz"
LASTFM = "lastfm"
WIKIDATA = "wikidata"
UA = "Weave/0.1 (prueba local)"
ATTEMPTS = 4


class Fetcher:
    def __init__(self, min_interval: dict, sleep=time.sleep, opener=urllib.request.urlopen, clock=time.monotonic,
                 user_agents=None):
        self.min_interval = min_interval
        self.sleep, self.opener, self.clock = sleep, opener, clock
        self.user_agents = user_agents or {}  # identificación propia por servicio (Wikidata pide un contacto)
        self._locks = {s: threading.Lock() for s in min_interval}
        self._last = {s: None for s in min_interval}

    def _pace(self, service):
        with self._locks[service]:
            last = self._last[service]
            if last is not None:
                wait = self.min_interval[service] - (self.clock() - last)
                if wait > 0:
                    self.sleep(wait)
            self._last[service] = self.clock()

    def get_json(self, url: str, service: str):
        req = urllib.request.Request(url, headers={"User-Agent": self.user_agents.get(service, UA)})
        for attempt in range(ATTEMPTS):
            self._pace(service)
            try:
                with self.opener(req, timeout=15) as r:
                    data = json.load(r)
            except urllib.error.HTTPError as e:
                if e.code not in (429, 503) or attempt == ATTEMPTS - 1:
                    raise
                # 429/503 = límite de ritmo: esperar lo que pida el servidor (máx. 60 s) o cada vez más
                after = (e.headers or {}).get("Retry-After")
                self.sleep(min(int(after), 60) if after and str(after).isdigit() else 2 * (attempt + 1))
                continue
            if isinstance(data, dict) and isinstance(data.get("error"), dict) and data["error"].get("code") == 4 \
                    and attempt < ATTEMPTS - 1:
                self.sleep(5)  # cuota de Deezer superada
                continue
            return data
