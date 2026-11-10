"""Tolking av listesider på kitchn.no og tilbords.no (Lindbak, nov. 2026).

Hver vare er et <li class="product"> inne i <div id="products"> med data-
attributter (id, SKU, merke, kampanjer, kategori, pris, lager per butikk) og
en priseske:
  data-type="1"  «Førpris X» + pris          åpen kampanje
                 «Etter kampanje X» + pris   introduksjonspris (X = senere pris)
  data-type="2"  «Ikke medlem X» + pris      klubbpris (pris = medlemspris)
  data-type="4"  bare pris                   ordinær pris
NB: Toppen av siden har også en liste («Populære varer», <ul id="products">)
som ikke hører til kategorien. Den hoppes over.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup

from . import config

NUM = r"(\d{1,3}(?:[\s  .]\d{3})+(?:,\d{1,2})?|\d+(?:,\d{1,2})?)"
_PRICE = re.compile(NUM + r"\s*(?:,-|kr\b)?")
_TOTAL = re.compile(r"Viser\s+(\d[\d\s ]*)\s+av\s+(\d[\d\s ]*)\s+produkter")
_COUNT = re.compile(r"(\d[\d\s ]*)\s+produkter\b")
_FACET = re.compile(r"^(.*\S)\s*\((\d+)\)$")


def to_float(s: str | None) -> float | None:
    if not s:
        return None
    m = _PRICE.search(s)
    if not m:
        return None
    v = re.sub(r"[\s  .]", "", m.group(1)).replace(",", ".")
    try:
        return float(v)
    except ValueError:
        return None


def _txt(node) -> str:
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)) if node else ""


def _path(href: str | None) -> str | None:
    if not href:
        return None
    p = urlparse(href).path
    return "/" + "/".join(s for s in p.split("/") if s) + "/"


def _dec(v: str | None) -> str:
    return unquote(v or "").strip()


def _stores(raw: str | None) -> tuple[int | None, int | None, list]:
    """data-stores = [[butikk-id, antall], ...] -> (butikker med lager, sum enheter, liste)."""
    if not raw:
        return None, None, []
    try:
        lst = json.loads(raw)
    except ValueError:
        return None, None, []
    pairs = [(int(a), int(b)) for a, b in lst if b is not None]
    return sum(1 for _, q in pairs if q > 0), sum(q for _, q in pairs if q > 0), pairs


def _campaign_end(s: str) -> str | None:
    m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", s)
    if not m:
        return None
    try:
        return dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
    except ValueError:
        return None


def parse_card(li) -> dict:
    a = li.attrs
    link = li.select_one("a.product-text") or li.find("a", href=True)
    path = _path(link.get("href")) if link else None
    brand = _txt(li.select_one("h3.brand")) or None
    model = _txt(li.select_one("h3.model")) or (link.get("title") if link else None)

    pw = li.select_one(".priceWrapper")
    ptype = pw.get("data-type") if pw else None
    tag = to_float(_txt(pw.select_one(".priceTag"))) if pw else None
    small_lab, small_val = None, None
    if pw:
        for p in pw.find_all("p"):
            if "priceTag" in (p.get("class") or []):
                continue
            t = _txt(p)
            if t:
                small_val = to_float(t)
                small_lab = re.sub(r"\s*" + NUM + r".*$", "", t).strip() or None
                break

    # Prislag: ordinær (uten kampanje), åpen (ikke-medlem), medlem
    price = tag
    before = nonmember = after = None
    lab = (small_lab or "").lower()
    if small_val is not None and lab.startswith("førpris"):
        before = small_val
    elif small_val is not None and lab.startswith("ikke medlem"):
        nonmember = small_val
    elif small_val is not None and lab.startswith("etter kampanje"):
        after = small_val
    elif small_val is not None and ptype == "1":
        before = small_val
    elif small_val is not None and ptype == "2":
        nonmember = small_val
    if before is not None and price is not None and before <= price:
        before = None
    if nonmember is not None and price is not None and nonmember <= price:
        nonmember = None
    price_open = nonmember if nonmember is not None else price      # ikke-medlem
    price_member = price                                             # laveste
    price_ordinary = before or nonmember or after or price

    tags = [_txt(t) for t in li.select(".product-tag")]
    tags = [t for t in tags if t]
    camps = [c.strip() for c in _dec(a.get("data-campaigns")).split(",") if c.strip()]
    flat = _txt(li)
    m = re.search(r"(?<![\w-])-\s?(\d{1,2})\s*%", flat)
    disc = float(m.group(1)) if m else None
    end = None
    ce = li.select_one(".campaign-end")
    if ce:
        end = _campaign_end(_txt(ce))
    elif "Kampanjeslutt" in flat:
        end = _campaign_end(flat.split("Kampanjeslutt", 1)[1][:30])

    stock_txt = " | ".join(_txt(s) for s in li.select(".info-stock span"))
    m = re.search(r"Finnes i (\d+) butikk", stock_txt)
    n_store_txt = int(m.group(1)) if m else None
    if re.search(r"Ikke på nettlager|Utsolgt på nett", stock_txt):
        web = False
    elif re.search(r"på nettlager", stock_txt, re.I):
        web = True
    else:
        web = None
    low = bool(re.search(r"Få (igjen )?på nettlager|Få igjen", stock_txt))
    n_st, units, pairs = _stores(a.get("data-stores"))

    segs = (path or "").strip("/").split("/")
    return {
        "product_id": a.get("data-product-id") or a.get("id"),
        "sku": a.get("data-product-sku"),
        "article_id": a.get("data-article-id"),
        "path": path,
        "subcategory": "/".join(segs[:-1]) if len(segs) > 1 else None,
        "category_path": _dec(a.get("data-path")) or None,
        "product_type": _dec(a.get("data-producttype")) or None,
        "brand": brand,
        "brand_key": _dec(a.get("data-brand")) or None,
        "series": _dec(a.get("data-series")) or None,
        "color": _dec(a.get("data-color")) or None,
        "name": model,
        "price": price,
        "price_ordinary": price_ordinary,
        "price_open": price_open,
        "price_member": price_member,
        "price_before": before,
        "price_nonmember": nonmember,
        "price_after_intro": after,
        "data_price": to_float(a.get("data-price")),
        "price_type": ptype,
        "price_label": small_lab,
        "discount_pct": disc,
        "campaign_end": end,
        "campaigns": ";".join(camps) or None,
        "tags": ";".join(tags) or None,
        "is_new": "nyhet" in camps or "Nyhet" in tags,
        "web_stock": web,
        "web_assortment": (a["data-net-stock"] == "true") if "data-net-stock" in a else None,
        "web_stock_low": low,
        "can_ship_to_store": "Kan sendes til butikk" in stock_txt,
        "stock_text": stock_txt or None,
        "n_stores_text": n_store_txt,
        "n_stores_stock": n_st,
        "store_units": units,
        "_stores": pairs,
    }


def parse_listing(html: str) -> tuple[list[dict], dict]:
    """(varer, meta) fra én kategoriside. meta: total, vist, fasetter, underkategorier."""
    soup = BeautifulSoup(html, "lxml")
    box = soup.select_one("div#products")
    lis = box.select("li.product") if box else []
    cards, seen = [], set()
    for li in lis:
        c = parse_card(li)
        if not c["product_id"] or c["product_id"] in seen:
            continue
        seen.add(c["product_id"])
        c["rank"] = len(cards) + 1
        cards.append(c)
    return cards, page_meta(soup)


def page_meta(soup) -> dict:
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    shown = total = None
    m = _TOTAL.search(text)
    if m:
        shown = int(re.sub(r"\D", "", m.group(1)))
        total = int(re.sub(r"\D", "", m.group(2)))
    else:
        m = _COUNT.search(text)
        if m:
            total = int(re.sub(r"\D", "", m.group(1)))
    facets = []
    for d in soup.select("div.facet-container[id]"):
        fid = d["id"].removeprefix("facet-")
        title = _txt(d.find(recursive=False)) or fid
        for lab in d.find_all("label"):
            mm = _FACET.match(_txt(lab))
            if mm:
                facets.append({"facet": fid, "facet_title": title,
                               "value": mm.group(1), "count": int(mm.group(2))})
    return {"shown": shown, "total": total, "facets": facets,
            "children": child_categories(soup)}


def child_categories(soup) -> list[str]:
    """Underkategorier fra kategorimenyen (JSON på kitchn.no, lenker på tilbords.no)."""
    out = set()
    tag = soup.find("script", id="nav-children-data")
    if tag and tag.string:
        try:
            for lst in json.loads(tag.string).values():
                for c in lst:
                    if c.get("Url"):
                        out.add(_path(c["Url"]))
        except ValueError:
            pass
    for a in soup.find_all("a", href=True):
        if a.find_parent("li", class_="product"):
            continue
        p = _path(a["href"])
        if p and p.strip("/").split("/")[0] in config.FALLBACK_CATEGORIES:
            out.add(p)
    return sorted(out)


def category_links(html: str) -> list[str]:
    """Kategorier på nivå 2 (f.eks. /kjokken/bakeutstyr/) fra menyen på forsiden."""
    soup = BeautifulSoup(html, "lxml")
    out = set()
    for p in child_categories(soup):
        segs = p.strip("/").split("/")
        if len(segs) >= 2:
            out.add("/" + "/".join(segs[:2]) + "/")
    return sorted(out)


def sitemap_paths(xml: str) -> list[str]:
    return [_path(u) for u in re.findall(r"<loc>\s*([^<]+?)\s*</loc>", xml)]


def homepage_banners(html: str) -> list[dict]:
    """Kampanjelenker på forsiden (tekst med %, «3 for 2», Black, Klubb, Salg)."""
    soup = BeautifulSoup(html, "lxml")
    rx = re.compile(r"\d+\s*%|3 for 2|Black|Klubb|Medlem|Salg|Tilbud|Kupp|Lagertømming|kampanje",
                    re.I)
    out, seen = [], set()
    for a in soup.find_all("a", href=True):
        if a.find_parent("li", class_="product") or a.find_parent(["nav", "header", "footer"]):
            continue
        t = _txt(a)
        if not t or not rx.search(t + " " + a["href"]):
            continue
        key = (t[:150], a["href"])
        if key in seen:
            continue
        seen.add(key)
        pct = [float(x) for x in re.findall(r"(\d{1,2})\s*%", t)]
        out.append({"text": t[:200], "href": _path(a["href"]) or a["href"],
                    "pct_max": max(pct) if pct else None})
    return out
