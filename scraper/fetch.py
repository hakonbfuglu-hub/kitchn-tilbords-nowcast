"""Høflig henting av offentlige sider: robots.txt, pause, nye forsøk."""

from __future__ import annotations

import fnmatch
import random
import time
from collections import Counter
from urllib.parse import urlparse

import requests

from . import config


def _robots_rules(txt: str) -> list[str]:
    """Disallow-mønstre for User-agent: * (med * som jokertegn)."""
    rules, active = [], False
    for line in txt.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        k, v = (s.strip() for s in line.split(":", 1))
        k = k.lower()
        if k == "user-agent":
            active = v == "*"
        elif k == "disallow" and active and v:
            rules.append(v)
    return rules


def robots_allows(rules: list[str], url: str) -> bool:
    u = urlparse(url)
    target = u.path + (("?" + u.query) if u.query else "")
    for r in rules:
        pat = r if r.startswith(("/", "*")) else "/" + r
        if "*" in pat:
            if fnmatch.fnmatchcase(target, pat.rstrip("$") + ("" if pat.endswith("$") else "*")):
                return False
        elif target.startswith(pat):
            return False
    return True


class Fetcher:
    def __init__(self, base: str, delay: float = config.DELAY_S):
        self.base = base.rstrip("/")
        self.delay = delay
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": config.USER_AGENT,
                               "Accept-Language": "nb-NO,nb;q=0.9,no;q=0.8"})
        self.status = Counter()
        self.n_requests = 0
        self.bytes = 0
        self._last = 0.0
        try:
            r = self.s.get(self.base + "/robots.txt", timeout=30)
            self.robots_txt = r.text if r.ok else ""
        except requests.RequestException as e:
            print(f"[hent] robots.txt kunne ikke leses: {e}")
            self.robots_txt = ""
        self.rules = _robots_rules(self.robots_txt)

    def allowed(self, url: str) -> bool:
        return robots_allows(self.rules, url)

    def _wait(self):
        gap = self.delay + random.uniform(0, self.delay * 0.5)
        dt = time.time() - self._last
        if dt < gap:
            time.sleep(gap - dt)
        self._last = time.time()

    def get(self, url: str, tries: int = 4, timeout: int = 90) -> str | None:
        if not url.startswith("http"):
            url = self.base + url
        if not self.allowed(url):
            print(f"[hent] robots.txt sier nei: {url}")
            self.status["robots"] += 1
            return None
        for i in range(1, tries + 1):
            self._wait()
            self.n_requests += 1
            try:
                r = self.s.get(url, timeout=timeout)
            except requests.RequestException as e:
                self.status["nettverksfeil"] += 1
                print(f"[hent] {url} forsøk {i}: {e}")
                time.sleep(5 * i)
                continue
            self.status[r.status_code] += 1
            if r.status_code == 200:
                r.encoding = r.encoding or "utf-8"
                self.bytes += len(r.content)
                return r.text
            if r.status_code in (429, 500, 502, 503, 504):
                wait = 15 * i + random.uniform(0, 5)
                print(f"[hent] {url} -> {r.status_code}, venter {wait:.0f}s")
                time.sleep(wait)
                continue
            print(f"[hent] {url} -> {r.status_code}")
            return None
        return None
