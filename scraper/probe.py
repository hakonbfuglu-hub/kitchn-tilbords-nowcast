"""Kartlegging: henter et lite utvalg sider fra hver butikk og lagrer dem rått i
rapport/probe/<butikk>/, med en oppsummering (probe.md) av hva som ble funnet.
Brukes for å skrive og justere tolkingen når sidene endres."""

from __future__ import annotations

import gzip
import math
import re
from pathlib import Path

from . import config
from .fetch import Fetcher

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "rapport" / "probe"

_TOTAL = re.compile(r"Viser\s+(\d[\d\s ]*)\s+av\s+(\d[\d\s ]*)\s+produkter")
_HREF = re.compile(r'href="(/[a-z0-9\-]+/[^"?#]+/)"')


def _save(d: Path, name: str, txt: str):
    if len(txt) > 400_000:
        with gzip.open(d / (name + ".gz"), "wt", encoding="utf-8") as fh:
            fh.write(txt)
    else:
        (d / name).write_text(txt, encoding="utf-8")


def _summ(txt: str | None) -> str:
    if txt is None:
        return "IKKE HENTET"
    m = _TOTAL.search(txt)
    hrefs = {h for h in _HREF.findall(txt) if h.count("/") >= 4}
    js = []
    for k in ("__NEXT_DATA__", "application/ld+json", "application/json", "window.",
              "data-product", "ng-app", "Vue", "knockout", "data-bind", "{{"):
        if k in txt:
            js.append(k)
    return (f"{len(txt):,} tegn; viser={m.group(0) if m else '-'}; "
            f"produktlenker(>=3 ledd)={len(hrefs)}; "
            f"Førpris={txt.count('Førpris')}; Klubbpris={txt.count('Klubbpris')}; "
            f"Kampanjeslutt={txt.count('Kampanjeslutt')}; tegn: {', '.join(js)}")


def _total(txt: str | None) -> int | None:
    m = _TOTAL.search(txt or "")
    return int(re.sub(r"\D", "", m.group(2))) if m else None


def run() -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    lines = ["# Kartlegging", ""]
    for key, st in config.STORES.items():
        d = OUT / key
        d.mkdir(parents=True, exist_ok=True)
        f = Fetcher(st["base"])
        (d / "robots.txt").write_text(f.robots_txt, encoding="utf-8")
        lines += [f"## {st['navn']} ({st['base']})", "",
                  f"- robots-regler: {f.rules}"]
        pages = [
            ("sitemap_index.xml", "/sitemap_index.xml/"),
            ("sitemapsplit_1.xml", "/sitemapsplit.xml?page=1"),
            ("forside.html", "/"),
            ("topp_kjokken_s1.html", "/kjokken/"),
            ("topp_kjokken_kampanjevare.html", "/kjokken/?campaigns=kampanjevare"),
            ("kat_bakeutstyr_s1.html", "/kjokken/bakeutstyr/"),
            ("kat_bakeutstyr_s2.html", "/kjokken/bakeutstyr/?page=2"),
            ("kat_bakeutstyr_pagesize.html", "/kjokken/bakeutstyr/?pageSize=200"),
            ("kat_bakeutstyr_kakering.html", "/kjokken/bakeutstyr/kakering/"),
            ("kampanje.html", "/kampanje/"),
            ("kampanje_blackfriday.html",
             "/kampanje/blackfriday/" if key == "kitchn" else "/kampanje/black-friday/"),
            ("vare.html",
             "/kjokken/gryter-og-panner/stekepanner/"
             "woll-eco-logic-qxr-stekepanne-28-cm-avtagbart-trehandtak/"),
        ]
        got = {}
        for name, path in pages:
            txt = f.get(path)
            got[name] = txt
            if txt is not None:
                _save(d, name, txt)
            lines.append(f"- `{path}` -> {_summ(txt)}")
        # Siste side i én forespørsel: inneholder den alle varene?
        tot = _total(got.get("kat_bakeutstyr_s1.html"))
        if tot:
            last = math.ceil(tot / config.PAGE_SIZE)
            path = f"/kjokken/bakeutstyr/?page={last}"
            txt = f.get(path)
            if txt is not None:
                _save(d, "kat_bakeutstyr_siste.html", txt)
            lines.append(f"- `{path}` (oppgitt {tot}) -> {_summ(txt)}")
        lines += [f"- forespørsler: {f.n_requests}, HTTP: {dict(f.status)}, "
                  f"bytes: {f.bytes:,}", ""]
    p = OUT / "probe.md"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p
