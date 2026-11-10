"""Mål per kjøring (daglig i nov-jan) og per uke, for hver butikk.

Samme definisjoner som Kid-trackeren der dataene finnes:
  1) Omsetning (indikatorer)
     varer, nye/utgåtte varer, andel på nettlager, prisindeks på samme varer
     NYTT her: lager i fysiske butikker per vare. Nedgang i lager på samme vare
     fra én kjøring til neste ≈ salg (minus påfyll), og fanges best daglig.
     (Anmeldelser per vare vises ikke på listesidene, så det målet mangler.)
  2) Kampanjetrykk
     andel av sortimentet med kampanje (etter type), snittrabatt mot ordinær pris
     for medlem og ikke-medlem.

Prislag:
  ordinaer  pris uten kampanje («Førpris», «Ikke medlem», «Etter kampanje», ellers pris)
  aapen     det en ikke-medlem betaler
  medlem    det et klubbmedlem betaler (laveste)
«3 for 2» og lignende ligger ikke i stykkprisen; de måles som andel av sortimentet.

Prisindeks = ujustert Jevons (geometrisk snitt) av prisendringen på samme vare.
Fast basis = hver vares snittpris i basisvinduet (før Black Week).
"""

from __future__ import annotations

import datetime as dt
import math
from pathlib import Path

import numpy as np
import pandas as pd

from . import config

LAYERS = ["ordinaer", "aapen", "medlem"]
REL_MIN, REL_MAX = 0.2, 5.0      # utenfor dette = tolkefeil, ikke prisendring

# kampanjetyper fra data-campaigns (Lindbak), med visningsnavn
CAMPAIGN_KEYS = {
    "kampanjevare": "kampanjevare",
    "klubbpris": "klubbpris",
    "3 for 2": "3for2",
    "black weeks": "black_weeks",
    "lagertømming": "lagertomming",
    "introduksjonspris": "introduksjonspris",
    "bra deal": "bra_deal",
}
_MULTIBUY = r"^\d\s*for\s*\d+\s*%?$"     # «3 for 2», «2 for 40%»
COLS = ["date", "iso_week", "product_id", "category", "name", "brand", "price",
        "price_ordinary", "price_open", "price_member", "price_before", "campaigns",
        "campaign_end", "web_stock", "store_units", "n_stores_stock", "is_new"]


def week_of(d: str) -> str:
    y, w, _ = dt.date.fromisoformat(d).isocalendar()
    return f"{y}-W{w:02d}"


def iso_quarter(d: str) -> str:
    x = dt.date.fromisoformat(d)
    return f"Q{(x.month - 1) // 3 + 1}/{str(x.year)[2:]}"


def jevons(rel: pd.Series) -> tuple[float, int]:
    rel = rel[(rel > REL_MIN) & (rel < REL_MAX)].dropna()
    if rel.empty:
        return np.nan, 0
    return float(np.exp(np.log(rel).mean())), int(rel.size)


def load(store: str, data_dir: Path | None = None) -> pd.DataFrame:
    d = (data_dir or config.DATA_DIR) / store / "varer"
    files = sorted(d.glob("*.csv.gz"))
    if not files:
        return pd.DataFrame(columns=COLS)
    frames = []
    for f in files:
        x = pd.read_csv(f, dtype={"product_id": str, "sku": str, "campaigns": str},
                        usecols=lambda c: c in COLS)
        frames.append(x)
    df = pd.concat(frames, ignore_index=True)
    return prepare(df)


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in ("price", "price_ordinary", "price_open", "price_member", "price_before",
              "store_units", "n_stores_stock"):
        df[c] = pd.to_numeric(df.get(c), errors="coerce")
    df = df[df["price"] > 0].copy()
    df["p_medlem"] = df["price_member"].fillna(df["price"])
    df["p_aapen"] = df["price_open"].fillna(df["price"])
    df["p_ordinaer"] = df[["price_ordinary", "p_aapen"]].max(axis=1)
    df["kat"] = df["category"].astype(str).str.strip("/").str.split("/").str[0]
    camps = df["campaigns"].fillna("").astype(str).str.lower()
    for k, col in CAMPAIGN_KEYS.items():
        df[f"k_{col}"] = camps.str.split(";").apply(lambda xs, k=k: k in xs)
    df["k_flerkjop"] = camps.str.split(";").apply(
        lambda xs: any(pd.Series(xs).str.match(_MULTIBUY)) if xs else False)
    df["k_rabatt_aapen"] = df["p_aapen"] < df["p_ordinaer"] - 0.5
    df["k_rabatt_medlem"] = df["p_medlem"] < df["p_ordinaer"] - 0.5
    df["k_noen"] = (df["k_rabatt_medlem"] | df["k_flerkjop"] | df["k_kampanjevare"]
                    | df["k_klubbpris"] | df["k_black_weeks"] | df["k_lagertomming"])
    df["rabatt_aapen"] = 1 - df["p_aapen"] / df["p_ordinaer"]
    df["rabatt_medlem"] = 1 - df["p_medlem"] / df["p_ordinaer"]
    web = df["web_stock"].astype(str).str.lower()
    df["paa_nettlager"] = web.map({"true": 1.0, "false": 0.0})
    return df


def _groups(df: pd.DataFrame):
    yield "ALLE", df
    for k, g in df.groupby("kat"):
        yield k, g


def snapshot_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """Nivåmål per kjøring og gruppe."""
    rows = []
    for d, day in df.groupby("date"):
        for grp, g in _groups(day):
            n = len(g)
            w = g["store_units"].fillna(0)
            row = {"date": d, "gruppe": grp, "varer": n,
                   "andel_paa_nettlager": g["paa_nettlager"].mean(),
                   "andel_med_kampanje": g["k_noen"].mean(),
                   "andel_rabatt_ikke_medlem": g["k_rabatt_aapen"].mean(),
                   "andel_rabatt_medlem": g["k_rabatt_medlem"].mean(),
                   "snittrabatt_ikke_medlem": g["rabatt_aapen"].mean(),
                   "snittrabatt_medlem": g["rabatt_medlem"].mean(),
                   "snittrabatt_kampanjevarer_medlem": g.loc[g["k_rabatt_medlem"], "rabatt_medlem"].mean(),
                   "lagervektet_rabatt_medlem": (np.average(g["rabatt_medlem"], weights=w)
                                                 if w.sum() > 0 else np.nan),
                   "butikklager_enheter": w.sum(),
                   "butikklager_kr_ordinaer": (w * g["p_ordinaer"]).sum()}
            for col in list(CAMPAIGN_KEYS.values()) + ["flerkjop"]:
                row[f"andel_{col}"] = g[f"k_{col}"].mean()
            row["andel_rabatt_medlem_ekskl_lagertomming"] = (g["k_rabatt_medlem"] & ~g["k_lagertomming"]).mean()
            rows.append(row)
    return pd.DataFrame(rows)


def flows(df: pd.DataFrame, key: str = "date") -> pd.DataFrame:
    """Endring mellom påfølgende kjøringer (eller uker): nye/utgåtte varer og
    lagernedgang i butikk på samme vare. lager_nedgang = sum av nedgang på varer
    der lageret falt (≈ solgte enheter; påfyll trekker ned). netto = nedgang - økning."""
    rows = []
    snaps = {k: g.drop_duplicates("product_id").set_index("product_id")
             for k, g in df.groupby(key)}
    keys = sorted(snaps)
    for i in range(1, len(keys)):
        a, b = snaps[keys[i - 1]], snaps[keys[i]]
        both = a.index.intersection(b.index)
        days = ((dt.date.fromisoformat(b["date"].iloc[0]) - dt.date.fromisoformat(a["date"].iloc[0])).days
                if key == "date" else 7)
        du = (b.loc[both, "store_units"] - a.loc[both, "store_units"]).dropna()
        kat = b.loc[du.index, "kat"]
        camp = b.loc[du.index, "k_noen"]
        price = a.loc[du.index, "p_medlem"]
        for grp, mask in [("ALLE", pd.Series(True, index=du.index))] + \
                         [(k, kat == k) for k in sorted(kat.unique())]:
            d = du[mask]
            cur, prev = set(b.index[b["kat"] == grp]) if grp != "ALLE" else set(b.index), \
                set(a.index[a["kat"] == grp]) if grp != "ALLE" else set(a.index)
            fall = (-d.clip(upper=0))
            rows.append({
                key: keys[i], "gruppe": grp, "dager": days,
                "nye_varer": len(cur - prev), "utgaatte_varer": len(prev - cur),
                "lager_nedgang": fall.sum(),
                "lager_okning": d.clip(lower=0).sum(),
                "lager_netto": d.sum(),
                "lager_nedgang_per_dag": fall.sum() / days if days else np.nan,
                "lager_nedgang_kr_medlem": (fall * price[mask]).sum(),
                "lager_nedgang_kampanjevarer": fall[camp[mask]].sum(),
                "lager_nedgang_fullpris": fall[~camp[mask]].sum(),
                "varer_med_nedgang": int((d < 0).sum()),
            })
    return pd.DataFrame(rows)


def base_dates(df: pd.DataFrame) -> list[str]:
    lo, hi = config.BASE_WINDOW
    ds = sorted(df["date"].unique())
    inside = [d for d in ds if lo <= d <= hi]
    return inside or ds[:1]


def price_indices(df: pd.DataFrame, key: str = "date") -> pd.DataFrame:
    bd = base_dates(df)
    b = df[df["date"].isin(bd)]
    out = []
    for grp, g in _groups(df):
        bg = b if grp == "ALLE" else b[b["kat"] == grp]
        bp = {L: np.exp(np.log(bg[f"p_{L}"]).groupby(bg["product_id"]).mean()) for L in LAYERS}
        lvl, prev = {L: 100.0 for L in LAYERS}, None
        for k, cur in g.groupby(key):
            cur = cur.sort_values("date").drop_duplicates("product_id", keep="last").set_index("product_id")
            row = {key: k, "gruppe": grp}
            for L in LAYERS:
                both = cur.index.intersection(bp[L].index)
                r, n = jevons(cur.loc[both, f"p_{L}"] / bp[L].loc[both])
                row[f"prisindeks_{L}"] = 100 * r if not math.isnan(r) else np.nan
                row[f"n_{L}"] = n
                if prev is not None:
                    both = cur.index.intersection(prev.index)
                    r, _ = jevons(cur.loc[both, f"p_{L}"] / prev.loc[both, f"p_{L}"])
                    if not math.isnan(r):
                        lvl[L] *= r
                row[f"kjedeindeks_{L}"] = lvl[L]
            out.append(row)
            prev = cur
    return pd.DataFrame(out)


def entry_vs_existing(df: pd.DataFrame) -> pd.DataFrame:
    """Nye varer mot eksisterende av samme underkategori samme dag (log-forskjell i
    ordinær pris). −0,05 ≈ 5 % billigere enn det som allerede står på hylla."""
    first = df.groupby("product_id")["date"].transform("min")
    d = df.assign(ny=(df["date"] == first) & (df["date"] > df["date"].min()))
    rows = []
    for day, g in d.groupby("date"):
        new = g[g["ny"]]
        if new.empty:
            continue
        lp = np.log(g["p_ordinaer"])
        cell = g["category"]
        mean_old = lp[~g["ny"]].groupby(cell[~g["ny"]]).mean()
        diff = (lp[g["ny"]] - cell[g["ny"]].map(mean_old)).dropna()
        rows.append({"date": day, "gruppe": "ALLE", "nye_mot_eksisterende": diff.mean(),
                     "n_nye_sammenlignet": len(diff)})
    return pd.DataFrame(rows)


def daily(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    k = ["date", "gruppe"]
    w = snapshot_metrics(df)
    for part in (flows(df), price_indices(df), entry_vs_existing(df)):
        if len(part.columns) > 2:
            w = w.merge(part, on=k, how="left")
    w.insert(1, "iso_week", w["date"].map(week_of))
    w.insert(2, "ukedag", w["date"].map(lambda d: "man tir ons tor fre lør søn".split()[
        dt.date.fromisoformat(d).weekday()]))
    return w.sort_values(["gruppe", "date"]).reset_index(drop=True)


def weekly(df: pd.DataFrame, day: pd.DataFrame) -> pd.DataFrame:
    """Uke: nivåer fra første kjøring i uken (mandag når den finnes, som Kid),
    lagernedgang summert over alle kjøringer i uken."""
    if df.empty:
        return pd.DataFrame()
    first = df.groupby("iso_week")["date"].transform("min")
    snap = df[df["date"] == first]
    k = ["iso_week", "gruppe"]
    lv = snapshot_metrics(snap).rename(columns={"date": "maaledag"})
    lv["iso_week"] = lv["maaledag"].map(week_of)
    fl = flows(snap.assign(_w=snap["iso_week"]), key="_w").rename(columns={"_w": "iso_week"})
    pi = price_indices(snap.assign(_w=snap["iso_week"]), key="_w").rename(columns={"_w": "iso_week"})
    w = lv
    if len(fl.columns) > 2:
        w = w.merge(fl[["iso_week", "gruppe", "nye_varer", "utgaatte_varer"]], on=k, how="left")
    if len(pi.columns) > 2:
        w = w.merge(pi, on=k, how="left")
    if "lager_nedgang" in day:
        s = (day.groupby(k)[["lager_nedgang", "lager_netto", "lager_nedgang_kr_medlem",
                             "lager_nedgang_kampanjevarer", "lager_nedgang_fullpris", "dager"]]
             .sum(min_count=1).reset_index().rename(columns={"dager": "dager_med_lagerdata"}))
        w = w.merge(s, on=k, how="left")
    w.insert(2, "kvartal", w["maaledag"].map(iso_quarter))
    return w.sort_values(["gruppe", "iso_week"]).reset_index(drop=True)


def campaign_facets(store: str, data_dir: Path | None = None) -> pd.DataFrame:
    """Kampanjefasetter på toppkategoriene (sidens egne tellinger)."""
    d = (data_dir or config.DATA_DIR) / store / "fasetter"
    files = sorted(d.glob("*.csv.gz"))
    if not files:
        return pd.DataFrame()
    f = pd.concat([pd.read_csv(x) for x in files], ignore_index=True)
    f = f[(f["facet"] == "campaigns") & (f["category"].str.count("/") == 2)]
    return f.pivot_table(index=["date", "value"], columns="category", values="count",
                         aggfunc="sum").reset_index()
