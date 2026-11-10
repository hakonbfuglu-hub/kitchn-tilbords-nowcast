"""Innsamling for én butikk: finn kategorier, hent alle varer, lagre filer for
dagen og skriv en helsesjekk.

Lindbak viser 80 varer per side, og ?page=N viser varene 1..N*80. For hver
kategori henter vi derfor side 1 (total og fasetter) og deretter siste side
direkte, som inneholder alle varene. Store kategorier deles i underkategorier.
Én fullstendig innsamling er ca. 70 forespørsler per butikk.

Filer per kjøring (dato = ÅÅÅÅ-MM-DD, UTC):
  data/<butikk>/varer/<dato>.csv.gz        én rad per vare (pris, kampanje, lager)
  data/<butikk>/kategorier/<dato>.csv      per kategori: oppgitt antall, funnet
  data/<butikk>/fasetter/<dato>.csv.gz     filtertellinger per kategori (kampanjer,
                                           merker, kundeanmeldelser ...)
  data/<butikk>/kampanjesider/<dato>.csv   antall varer på kampanjesidene
  data/<butikk>/forside/<dato>.csv         kampanjetekster på forsiden
  data/<butikk>/butikker/<dato>.csv        per fysisk butikk: varer og enheter på lager
  raw/<butikk>/<dato>/*.html.gz            rå sider (lastes opp som artefakt, ikke i git)
"""

from __future__ import annotations

import datetime as dt
import gzip
import json
import math
import re
import time
from collections import defaultdict
from pathlib import Path

import pandas as pd
from . import config
from .fetch import Fetcher
from .parse import category_links, homepage_banners, parse_listing

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
REPORT = ROOT / "rapport"
RAW = ROOT / "raw"


def today() -> str:
    return dt.datetime.now(dt.timezone.utc).date().isoformat()


def iso_week(d: str | None = None) -> str:
    day = dt.date.fromisoformat(d) if d else dt.datetime.now(dt.timezone.utc).date()
    y, w, _ = day.isocalendar()
    return f"{y}-W{w:02d}"


class Run:
    def __init__(self, store: str, raw: bool = True):
        self.store = store
        self.cfg = config.STORES[store]
        self.f = Fetcher(self.cfg["base"])
        self.date = today()
        self.raw_dir = RAW / store / self.date if raw else None
        if self.raw_dir:
            self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.store_stock: dict[int, list[int]] = defaultdict(lambda: [0, 0])
        self.n_store_cards = 0

    def get(self, path: str) -> str | None:
        html = self.f.get(path)
        if html is not None and self.raw_dir:
            slug = re.sub(r"[^a-z0-9]+", "_", path.lower()).strip("_") or "forside"
            with gzip.open(self.raw_dir / f"{slug}.html.gz", "wt", encoding="utf-8") as fh:
                fh.write(html)
        return html

    def listing(self, path: str, page: int | None = None):
        url = path if not page or page == 1 else f"{path}?page={page}"
        html = self.get(url)
        if html is None:
            return None, None
        cards, meta = parse_listing(html)
        return cards, meta


def _crawl_category(r: Run, path: str, deadline: float, depth: int = 2):
    """Alle varer i en kategori. Gir (varer, kategori-rader, fasett-rader)."""
    cards, meta = r.listing(path)
    if cards is None:
        return [], [{"category": path, "depth": depth, "site_total": None, "found": 0,
                     "requests": 1, "method": "feil"}], []
    total = meta["total"] or len(cards)
    facets = [{**x, "category": path} for x in meta["facets"]]
    method, req = "side1", 1
    if total > len(cards) and time.time() < deadline:
        last = math.ceil(total / config.PAGE_SIZE)
        kids = [c for c in meta["children"]
                if c.startswith(path) and c.strip("/").count("/") == path.strip("/").count("/") + 1]
        if total <= config.MAX_CARDS_PER_REQUEST or not kids:
            more, _ = r.listing(path, last)
            req += 1
            if more is not None and len(more) >= len(cards):
                cards, method = more, f"side{last}"
        if len(cards) < 0.95 * total and kids:
            # del opp i underkategorier
            seen = {c["product_id"]: c for c in cards}
            sub_rows, sub_facets = [], []
            for k in kids:
                if time.time() > deadline:
                    break
                kc, kr, kf = _crawl_category(r, k, deadline, depth + 1)
                for c in kc:
                    seen.setdefault(c["product_id"], c)
                sub_rows += kr
                sub_facets += kf
            cards, method = list(seen.values()), "underkategorier"
            row = {"category": path, "depth": depth, "site_total": total, "found": len(cards),
                   "requests": req, "method": method}
            return cards, [row] + sub_rows, facets + sub_facets
    row = {"category": path, "depth": depth, "site_total": total, "found": len(cards),
           "requests": req, "method": method}
    return cards, [row], facets


def _campaign_pages(r: Run, banners: list[dict]) -> list[dict]:
    paths = ["/kampanje/"] + sorted({b["href"] for b in banners
                                     if str(b["href"]).startswith("/kampanje/")} - {"/kampanje/"})
    out = []
    for p in paths[:12]:
        cards, meta = r.listing(p)
        if cards is None:
            continue
        camp = defaultdict(int)
        for c in cards:
            for x in (c["campaigns"] or "").split(";"):
                if x:
                    camp[x] += 1
        out.append({"page": p, "site_total": meta["total"], "cards_page1": len(cards),
                    "campaigns_page1": json.dumps(dict(camp), ensure_ascii=False)})
    return out


def run(store: str, raw: bool = True, campaign_pages: bool = True) -> dict:
    t0 = time.time()
    deadline = t0 + 60 * config.MAX_RUNTIME_MIN / len(config.STORES)
    r = Run(store, raw=raw)
    home = r.get("/")
    banners = homepage_banners(home) if home else []
    cats = category_links(home) if home else []
    if len(cats) < config.MIN_CATEGORIES:
        print(f"[{store}] fant bare {len(cats)} kategorier i menyen, bruker toppnivå")
        cats = [f"/{c}/" for c in config.FALLBACK_CATEGORIES]
    print(f"[{store}] {r.date}: {len(cats)} kategorier")

    # Toppnivå: totalt antall og fasetter (kampanjer, merker, anmeldelser)
    top_rows, facet_rows = [], []
    for t in config.FALLBACK_CATEGORIES:
        cards, meta = r.listing(f"/{t}/")
        if meta:
            top_rows.append({"category": f"/{t}/", "depth": 1, "site_total": meta["total"],
                             "found": None, "requests": 1, "method": "topp"})
            facet_rows += [{**x, "category": f"/{t}/"} for x in meta["facets"]]

    products: dict[str, dict] = {}
    cat_rows = []
    for c in cats:
        cards, rows, facets = _crawl_category(r, c, deadline)
        for x in cards:
            if x["product_id"] not in products:
                products[x["product_id"]] = {**x, "category": c}
        cat_rows += rows
        facet_rows += facets
        print(f"[{store}] {c:42s} {rows[0]['found']:6d} av {rows[0]['site_total']} "
              f"({rows[0]['method']})")
        if time.time() > deadline:
            print(f"[{store}] tidsgrense nådd, avslutter tidlig")
            break

    camp_rows = _campaign_pages(r, banners) if campaign_pages else []

    # lager per fysisk butikk (summeres over varene; lagres ikke per vare)
    for x in products.values():
        for sid, q in x.pop("_stores", []):
            if q > 0:
                r.store_stock[sid][0] += 1
                r.store_stock[sid][1] += q

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    df = pd.DataFrame(list(products.values()))
    if not df.empty:
        df.insert(0, "date", r.date)
        df.insert(1, "iso_week", iso_week(r.date))
        df.insert(2, "crawled_utc", now)
    d = DATA / store
    for sub in ("varer", "kategorier", "fasetter", "kampanjesider", "forside", "butikker"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    if len(df):
        df.to_csv(d / "varer" / f"{r.date}.csv.gz", index=False)
    pd.DataFrame(top_rows + cat_rows).assign(date=r.date).to_csv(
        d / "kategorier" / f"{r.date}.csv", index=False)
    pd.DataFrame(facet_rows).assign(date=r.date).to_csv(
        d / "fasetter" / f"{r.date}.csv.gz", index=False)
    pd.DataFrame(camp_rows).assign(date=r.date).to_csv(
        d / "kampanjesider" / f"{r.date}.csv", index=False)
    pd.DataFrame(banners).assign(date=r.date).to_csv(
        d / "forside" / f"{r.date}.csv", index=False)
    pd.DataFrame([{"store_id": k, "n_products": v[0], "units": v[1]}
                  for k, v in sorted(r.store_stock.items())]).assign(date=r.date).to_csv(
        d / "butikker" / f"{r.date}.csv", index=False)

    h = check_health(store, df, top_rows, cat_rows, r, time.time() - t0, len(banners), len(camp_rows))
    return h


def _previous_count(store: str, date: str) -> int | None:
    files = sorted(p for p in (DATA / store / "varer").glob("*.csv.gz") if p.name[:10] < date)
    if not files:
        return None
    return len(pd.read_csv(files[-1], usecols=["product_id"]))


def check_health(store, df, top_rows, cat_rows, r: Run, secs, n_banners, n_camp) -> dict:
    n = len(df)
    share = (lambda c: float(df[c].notna().mean()) if n and c in df else 0.0)
    site_total = sum(x["site_total"] or 0 for x in top_rows)
    prev = _previous_count(store, r.date)
    problems = []
    if n < config.HEALTH_MIN_PRODUCTS:
        problems.append(f"bare {n} varer (minst {config.HEALTH_MIN_PRODUCTS} ventet)")
    if n and share("price") < config.HEALTH_MIN_PRICE_SHARE:
        problems.append(f"pris funnet for bare {share('price'):.0%} av varene")
    if prev and n < (1 - config.HEALTH_MAX_DROP_VS_LAST) * prev:
        problems.append(f"{n} varer mot {prev} forrige kjøring")
    if site_total and n < 0.9 * site_total:
        problems.append(f"{n} varer funnet, toppkategoriene oppgir {site_total}")
    gaps = [x["category"] for x in cat_rows
            if x["depth"] == 2 and x["site_total"] and x["found"] < 0.9 * x["site_total"]]
    if gaps:
        problems.append("under 90 % av oppgitt antall i: " + ", ".join(gaps))
    h = {
        "butikk": store, "dato": r.date, "uke": iso_week(r.date),
        "status": "OK" if not problems else "FEIL", "problemer": problems,
        "varer": n, "varer_forrige": prev, "oppgitt_toppkategorier": site_total,
        "andel_med_pris": round(share("price"), 3),
        "andel_kampanjevare": (round(float(df["campaigns"].fillna("").str.contains("kampanjevare").mean()), 3)
                               if n else None),
        "andel_paa_nettlager": (round(float((df["web_stock"] == True).mean()), 3) if n else None),  # noqa: E712
        "butikkenheter": int(df["store_units"].fillna(0).sum()) if n else 0,
        "fysiske_butikker": len(r.store_stock),
        "forside_bannere": n_banners, "kampanjesider": n_camp,
        "foresporsler": r.f.n_requests, "mb": round(r.f.bytes / 1e6, 1),
        "http_status": {str(k): v for k, v in dict(r.f.status).items()},
        "minutter": round(secs / 60, 1),
        "kategorier": [x for x in top_rows + cat_rows if x["depth"] <= 2],
    }
    return h


def write_health(hs: list[dict]):
    REPORT.mkdir(exist_ok=True)
    (REPORT / "helse.json").write_text(json.dumps(hs, indent=2, ensure_ascii=False, default=str),
                                       encoding="utf-8")
    lines = []
    for h in hs:
        lines += [f"# Helsesjekk {config.STORES[h['butikk']]['navn']} {h['dato']}: {h['status']}", ""]
        if h["problemer"]:
            lines += ["**Problemer:**", *[f"- {p}" for p in h["problemer"]], ""]
        lines += [
            f"- Varer: {h['varer']} (forrige kjøring: {h['varer_forrige']}); "
            f"toppkategoriene oppgir {h['oppgitt_toppkategorier']}",
            f"- Med pris: {h['andel_med_pris']:.0%}, kampanjevare: {(h['andel_kampanjevare'] or 0):.0%}, "
            f"på nettlager: {(h['andel_paa_nettlager'] or 0):.0%}",
            f"- Lager i butikk: {h['butikkenheter']:,} enheter i {h['fysiske_butikker']} butikker".replace(",", " "),
            f"- Forsidebannere: {h['forside_bannere']}, kampanjesider: {h['kampanjesider']}",
            f"- Forespørsler: {h['foresporsler']}, {h['mb']} MB, {h['minutter']} min, HTTP: {h['http_status']}",
            "", "| Kategori | Funnet | Oppgitt | Metode |", "|---|---:|---:|---|",
        ]
        for x in h["kategorier"]:
            lines.append(f"| {x['category']} | {x['found'] if x['found'] is not None else ''} | "
                         f"{x['site_total']} | {x['method']} |")
        lines.append("")
    (REPORT / "helse.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
