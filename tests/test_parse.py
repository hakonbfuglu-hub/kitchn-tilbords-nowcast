"""Tolking av ekte listesider (nedkortet utdrag, nov. 2026)."""

import gzip
from pathlib import Path

import pytest

from scraper.parse import parse_listing, to_float

FIX = Path(__file__).parent / "fixtures"


def load(name):
    with gzip.open(FIX / f"{name}.html.gz", "rt", encoding="utf-8") as fh:
        return parse_listing(fh.read())


@pytest.fixture(scope="module")
def kitchn():
    return load("kitchn_bakeutstyr_s1")


@pytest.fixture(scope="module")
def tilbords():
    return load("tilbords_bakeutstyr_s1")


def by_id(cards):
    return {c["product_id"]: c for c in cards}


def test_to_float():
    assert to_float("2 749,-") == 2749
    assert to_float("Førpris 1 899,-") == 1899
    assert to_float(" 77,-") == 77
    assert to_float("499,90 kr") == 499.9
    assert to_float(None) is None


def test_skips_header_list_and_reads_total(kitchn):
    cards, meta = kitchn
    assert len(cards) == 13                      # «Populære varer» i toppen er ikke med
    assert meta["total"] == 1435 and meta["shown"] == 80
    assert all(c["path"].startswith("/kjokken/bakeutstyr/") for c in cards)


def test_kitchn_open_campaign(kitchn):
    c = by_id(kitchn[0])["86170"]
    assert c["price_type"] == "1"
    assert (c["price"], c["price_ordinary"], c["price_open"], c["price_member"]) == (77, 129, 77, 77)
    assert c["discount_pct"] == 40
    assert c["campaign_end"] == "2026-11-30"
    assert c["campaigns"] == "kampanjevare"
    assert c["brand"] == "Modern House" and c["sku"] == "610352"
    assert c["web_stock"] is True
    assert c["n_stores_stock"] == c["n_stores_text"] == 146
    assert c["store_units"] == 1590


def test_kitchn_club_price(kitchn):
    c = by_id(kitchn[0])["59485"]
    assert c["price_type"] == "2"
    assert c["price_open"] == 959 and c["price_member"] == 575 and c["price_ordinary"] == 959
    assert "klubbpris" in c["campaigns"] and c["tags"] == "Klubbpris"


def test_kitchn_regular_and_out_of_stock(kitchn):
    cards = by_id(kitchn[0])
    r = cards["438321"]
    assert r["price_type"] == "4" and r["price"] == r["price_ordinary"] == 599
    assert r["price_before"] is None and r["campaign_end"] is None
    o = cards["246939"]
    assert o["web_stock"] is False and o["store_units"] == 0


def test_facets(kitchn):
    f = {(x["facet"], x["value"]): x["count"] for x in kitchn[1]["facets"]}
    assert f[("campaigns", "Kampanjevare")] == 368
    assert f[("campaigns", "Black Weeks")] == 25
    assert f[("categories", "Bakeboller")] == 208
    assert ("ratings", "5") in f


def test_children(kitchn, tilbords):
    for _, meta in (kitchn, tilbords):
        kids = [c for c in meta["children"] if c.startswith("/kjokken/bakeutstyr/")
                and c.count("/") == 4]
        assert "/kjokken/bakeutstyr/bakeboller/" in kids and len(kids) >= 20


def test_tilbords_same_layout(tilbords):
    cards, meta = tilbords
    assert len(cards) == 12 and meta["total"] == 1474
    c = by_id(cards)
    assert c["61719"]["price_open"] == 899 and c["61719"]["price_member"] == 450
    assert c["94929"]["price_ordinary"] == 199 and c["94929"]["price"] == 119
    assert c["94929"]["web_stock"] is False and c["94929"]["n_stores_stock"] == 55
    assert all(x["price"] for x in cards)
