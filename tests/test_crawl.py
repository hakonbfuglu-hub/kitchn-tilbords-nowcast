"""Innsamling mot en falsk butikk bygd av ekte produktfliser."""

import gzip
import re
from collections import Counter
from pathlib import Path

import pandas as pd
import pytest
from bs4 import BeautifulSoup

from scraper import config, crawl

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def tiles():
    with gzip.open(FIX / "kitchn_bakeutstyr_s1.html.gz", "rt", encoding="utf-8") as fh:
        s = BeautifulSoup(fh.read(), "lxml")
    return [str(li) for li in s.select("div#products li.product")]


def page(tiles, shown, total, kids=(), header_tiles=()):
    links = "".join(f'<a href="{k}">{k}</a>' for k in kids)
    return (f"<html><body><header><ul id='products'>{''.join(header_tiles)}</ul></header>"
            f"<nav>{links}</nav><div id='products'><p>{total} produkter</p>"
            f"<p>Viser {shown} av {total} produkter</p><ul>{''.join(tiles)}</ul></div>"
            f"</body></html>")


class FakeFetcher:
    def __init__(self, pages):
        self.pages, self.n_requests, self.bytes, self.status = pages, 0, 0, Counter()
        self.asked = []

    def get(self, path):
        self.n_requests += 1
        self.asked.append(path)
        html = self.pages.get(path)
        self.status[200 if html else 404] += 1
        return html


@pytest.fixture
def site(tiles, tmp_path, monkeypatch):
    t = tiles
    home = ("<html><body><nav>"
            "<a href='/kjokken/a/'>A</a><a href='/kjokken/b/'>B</a>"
            "<a href='/kampanje/blackfriday/'>Black Weeks -50%</a></nav>"
            "<a href='/kampanje/blackfriday/'>Black Weeks opptil -50%</a></body></html>")
    pages = {
        "/": home,
        "/kjokken/": page(t[:3], 3, 12),
        # A: 5 varer, side 1 viser 3, side 2 viser alle
        "/kjokken/a/": page(t[:3], 3, 5, header_tiles=t[10:12]),
        "/kjokken/a/?page=2": page(t[:5], 5, 5),
        # B: 7 varer, for stor for én side -> underkategorier
        "/kjokken/b/": page(t[5:8], 3, 7, kids=["/kjokken/b/x/", "/kjokken/b/y/"]),
        "/kjokken/b/x/": page(t[5:8], 3, 4),
        "/kjokken/b/x/?page=2": page(t[5:9], 4, 4),
        "/kjokken/b/y/": page(t[9:12], 3, 3),
        "/kampanje/": page(t[:3], 3, 40),
        "/kampanje/blackfriday/": page(t[:2], 2, 2),
    }
    fake = FakeFetcher(pages)
    monkeypatch.setattr(crawl, "Fetcher", lambda base: fake)
    monkeypatch.setattr(crawl, "DATA", tmp_path / "data")
    monkeypatch.setattr(crawl, "RAW", tmp_path / "raw")
    monkeypatch.setattr(config, "PAGE_SIZE", 3)
    monkeypatch.setattr(config, "MAX_CARDS_PER_REQUEST", 5)
    monkeypatch.setattr(config, "MIN_CATEGORIES", 1)
    monkeypatch.setattr(config, "HEALTH_MIN_PRODUCTS", 5)
    return fake, tmp_path


def test_full_run(site):
    fake, tmp = site
    h = crawl.run("kitchn")
    d = tmp / "data" / "kitchn"
    df = pd.read_csv(next((d / "varer").glob("*.csv.gz")), dtype={"product_id": str})
    assert len(df) == 12 and df["product_id"].is_unique
    assert set(df.loc[df["category"] == "/kjokken/b/", "product_id"]) == set(
        df["product_id"].iloc[5:12])
    assert "/kjokken/a/?page=2" in fake.asked          # siste side direkte
    assert "/kjokken/b/?page=3" not in fake.asked      # stor kategori deles opp
    assert "_stores" not in df.columns
    cats = pd.read_csv(next((d / "kategorier").glob("*.csv")))
    assert cats.set_index("category").loc["/kjokken/b/", "method"] == "underkategorier"
    butikker = pd.read_csv(next((d / "butikker").glob("*.csv")))
    assert butikker["units"].sum() == df["store_units"].sum()
    lager = pd.read_csv(next((d / "lager").glob("*.csv.gz")), dtype={"product_id": str})
    assert lager["units"].sum() == df["store_units"].sum() and (lager["units"] > 0).all()
    kp = pd.read_csv(next((d / "kampanjesider").glob("*.csv")))
    assert set(kp["page"]) == {"/kampanje/", "/kampanje/blackfriday/"}
    assert h["status"] == "OK", h["problemer"]
    assert list((tmp / "raw" / "kitchn").glob("*/*.html.gz"))


def test_health_flags_missing(site, monkeypatch):
    fake, _ = site
    fake.pages["/kjokken/a/?page=2"] = None            # siste side feiler
    h = crawl.run("kitchn")
    assert h["status"] == "FEIL"
    assert any("/kjokken/a/" in p for p in h["problemer"])
