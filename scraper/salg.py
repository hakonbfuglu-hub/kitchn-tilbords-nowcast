"""SIDEPROSJEKT: salgsanslag fra butikklager. Skrus av med config.SALGSANSLAG = False.

Produktflisene viser antall enheter per vare i hver fysiske butikk. Når lageret
av samme vare i samme butikk faller fra én kjøring til neste, regnes fallet som
solgt. Påfyll i samme periode skjuler salg, så tallet er et NEDRE anslag og
skal brukes som indeks (utvikling over tid, Black Week mot ukene før), ikke som
omsetning.

Regler
- Regnes per vare og butikk. Varer som ikke finnes i begge kjøringene telles ikke.
- «Butikker» med mer enn SENTRALLAGER_FAKTOR x median enheter regnes som
  sentrallager (Kitchn: én ID med ca. 1 mill. enheter). Holdes utenfor butikk-
  salget og vises for seg (ut av lageret = netthandel + forsendelser til butikk).
- Salgsdag: kjøringen ca. kl. 04 norsk tid dekker butikkdagen før.
- Kroner: fallet x pris ved forrige kjøring (medlem og ikke-medlem), inkl. og eks. mva.

Fem kontroller avgjør om anslaget er salg eller støy (se kontroller()):
  1 søndag nær null  2 ukemønster  3 stabil fordeling  4 Black Week-løft  5 nivå
"""

from __future__ import annotations

import datetime as dt
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from . import config, indeks

OSLO = ZoneInfo("Europe/Oslo")
OUT = Path(__file__).resolve().parents[1] / "rapport" / "salgsanslag"
UKEDAG = "man tir ons tor fre lør søn".split()


# --------------------------------------------------------------------------
# Lasting
# --------------------------------------------------------------------------

@lru_cache(maxsize=4)          # hvert døgn brukes i to intervaller
def _varer(store: str, date: str) -> pd.DataFrame | None:
    f = config.DATA_DIR / store / "varer" / f"{date}.csv.gz"
    if not f.exists():
        return None
    cols = indeks.COLS + ["crawled_utc", "web_stock_low", "subcategory"]
    x = pd.read_csv(f, dtype={"product_id": str, "campaigns": str}, usecols=lambda c: c in cols)
    p = indeks.prepare(x)
    p["subkat"] = p["category"].astype(str).str.strip("/")
    return p.drop_duplicates("product_id").set_index("product_id")


@lru_cache(maxsize=4)
def _lager(store: str, date: str) -> pd.DataFrame | None:
    f = config.DATA_DIR / store / "lager" / f"{date}.csv.gz"
    return pd.read_csv(f, dtype={"product_id": str}) if f.exists() else None


def _par(store: str, date: str, v: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    """Lager per vare og butikk. Fra før lagringen startet (10.-11. nov) finnes bare
    sum per vare; da brukes den som én «butikk» (-1) og metoden merkes grov."""
    x = _lager(store, date)
    if x is not None:
        return x, "vare x butikk"
    s = v["store_units"].fillna(0)
    return (pd.DataFrame({"product_id": s.index, "store_id": -1, "units": s.values}),
            "sum per vare (grov)")


def dates(store: str) -> list[str]:
    return sorted(p.name[:10] for p in (config.DATA_DIR / store / "varer").glob("*.csv.gz"))


def central_stores(store: str) -> set[int]:
    files = sorted((config.DATA_DIR / store / "butikker").glob("*.csv"))
    out = set()
    for f in files[-5:]:
        b = pd.read_csv(f)
        if len(b) > 3:
            med = b["units"].median()
            out |= set(b.loc[b["units"] > config.SENTRALLAGER_FAKTOR * med, "store_id"].astype(int))
    return out


def sales_day(end_utc: str) -> tuple[str, float]:
    """(salgsdag, timer siden forrige) – salgsdag = dagen før en nattkjøring."""
    t = dt.datetime.fromisoformat(end_utc).astimezone(OSLO)
    day = t.date() - dt.timedelta(days=1) if t.hour < 10 else t.date()
    return day.isoformat(), 0.0


# --------------------------------------------------------------------------
# Intervaller
# --------------------------------------------------------------------------

def interval(store: str, da: str, db: str, central: set[int]) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    va, vb = _varer(store, da), _varer(store, db)
    pa, ma = _par(store, da, va)
    pb, mb = _par(store, db, vb)
    grov = "grov" in ma or "grov" in mb
    if grov:     # samme nivå på begge sider
        pa = pd.DataFrame({"product_id": va.index, "store_id": -1, "units": va["store_units"].fillna(0).values})
        pb = pd.DataFrame({"product_id": vb.index, "store_id": -1, "units": vb["store_units"].fillna(0).values})
    both = va.index.intersection(vb.index)
    m = pa.merge(pb, on=["product_id", "store_id"], how="outer", suffixes=("_a", "_b")).fillna(
        {"units_a": 0, "units_b": 0})
    m = m[m["product_id"].isin(both)]
    m["d"] = m["units_b"] - m["units_a"]
    m["sentral"] = m["store_id"].isin(central)
    a = va.loc[both]
    m = m.join(a[["p_medlem", "p_aapen", "k_noen", "kat", "subkat"]], on="product_id")
    m["solgt"] = (-m["d"]).clip(lower=0)
    m["paafyll"] = m["d"].clip(lower=0)
    st = m[~m["sentral"]]
    ce = m[m["sentral"]]

    t_a = dt.datetime.fromisoformat(str(va["crawled_utc"].iloc[0]))
    t_b = dt.datetime.fromisoformat(str(vb["crawled_utc"].iloc[0]))
    hours = (t_b - t_a).total_seconds() / 3600
    sday, _ = sales_day(str(vb["crawled_utc"].iloc[0]))
    wa = va.loc[both, "web_stock"].astype(str).str.lower()
    wb = vb.loc[both, "web_stock"].astype(str).str.lower()
    kr_m = (st["solgt"] * st["p_medlem"]).sum()
    row = {
        "fra": da, "til": db, "salgsdag": sday,
        "ukedag": UKEDAG[dt.date.fromisoformat(sday).weekday()],
        "timer": round(hours, 1),
        "hel_dag": 20 <= hours <= 28,
        "metode": "sum per vare (grov)" if grov else "vare x butikk",
        "par_sammenlignet": len(st),
        "andel_par_endret": float((st["d"] != 0).mean()) if len(st) else np.nan,
        "solgt_enheter": st["solgt"].sum(),
        "paafyll_enheter": st["paafyll"].sum(),
        "solgt_kr_medlem_inkl_mva": kr_m,
        "solgt_kr_ikke_medlem_inkl_mva": (st["solgt"] * st["p_aapen"]).sum(),
        "solgt_kr_medlem_eks_mva": kr_m / config.MVA,
        "solgt_enheter_kampanje": st.loc[st["k_noen"], "solgt"].sum(),
        "solgt_enheter_fullpris": st.loc[~st["k_noen"], "solgt"].sum(),
        "andel_salg_kampanjevarer": (st.loc[st["k_noen"], "solgt"].sum() / st["solgt"].sum()
                                     if st["solgt"].sum() else np.nan),
        "andel_sortiment_kampanje": float(a["k_noen"].mean()),
        "sentrallager_ut_enheter": ce["solgt"].sum() if not grov else np.nan,
        "sentrallager_inn_enheter": ce["paafyll"].sum() if not grov else np.nan,
        "sentrallager_ut_kr_medlem": (ce["solgt"] * ce["p_medlem"]).sum() if not grov else np.nan,
        "nett_gikk_tom": int(((wa == "true") & (wb == "false")).sum()),
        "nett_kom_tilbake": int(((wa == "false") & (wb == "true")).sum()),
        "andel_faa_paa_nettlager": float(vb["web_stock_low"].astype(str).str.lower().eq("true").mean()),
    }
    kat = (st.groupby("subkat")[["solgt"]].sum()
           .assign(solgt_kr=st.assign(k=st["solgt"] * st["p_medlem"]).groupby("subkat")["k"].sum())
           .reset_index().assign(salgsdag=sday, metode=row["metode"]))
    bt = (st.groupby("store_id")[["solgt", "paafyll"]].sum().reset_index()
          .assign(salgsdag=sday, metode=row["metode"]))
    return row, kat, bt


def build_store(store: str):
    _varer.cache_clear()
    _lager.cache_clear()
    ds = dates(store)
    central = central_stores(store)
    rows, kats, bts = [], [], []
    for da, db in zip(ds, ds[1:]):
        r, k, b = interval(store, da, db, central)
        rows.append(r)
        kats.append(k)
        bts.append(b)
    dag = pd.DataFrame(rows)
    kat = pd.concat(kats, ignore_index=True) if kats else pd.DataFrame()
    bt = pd.concat(bts, ignore_index=True) if bts else pd.DataFrame()
    return dag, kat, bt, central


# --------------------------------------------------------------------------
# Lagersjekk: hvor ofte oppdateres lageret?
# --------------------------------------------------------------------------

def update_frequency(store: str) -> pd.DataFrame:
    d = config.DATA_DIR / store / "lagersjekk"
    files = sorted(d.glob("*.csv.gz"))
    if not files:
        return pd.DataFrame()
    snaps = [pd.read_csv(f, dtype={"product_id": str}) for f in files]
    ids = set(snaps[0]["product_id"])
    # nattkjøringene for de samme varene
    for day in dates(store):
        f = config.DATA_DIR / store / "lager" / f"{day}.csv.gz"
        v = config.DATA_DIR / store / "varer" / f"{day}.csv.gz"
        if f.exists() and v.exists():
            t = pd.read_csv(v, usecols=["crawled_utc"], nrows=1)["crawled_utc"].iloc[0]
            x = pd.read_csv(f, dtype={"product_id": str})
            snaps.append(x[x["product_id"].isin(ids)].assign(crawled_utc=t))
    snaps.sort(key=lambda s: s["crawled_utc"].iloc[0])
    rows = []
    for a, b in zip(snaps, snaps[1:]):
        keep = set(a["product_id"]) & set(b["product_id"])
        m = a[a["product_id"].isin(keep)].merge(b[b["product_id"].isin(keep)],
                                                on=["product_id", "store_id"], how="outer",
                                                suffixes=("_a", "_b")).fillna({"units_a": 0, "units_b": 0})
        d = m["units_b"] - m["units_a"]
        ta = dt.datetime.fromisoformat(a["crawled_utc"].iloc[0]).astimezone(OSLO)
        tb = dt.datetime.fromisoformat(b["crawled_utc"].iloc[0]).astimezone(OSLO)
        rows.append({"fra": f"{ta:%d.%m %H:%M}", "til": f"{tb:%d.%m %H:%M}",
                     "timer": round((tb - ta).total_seconds() / 3600, 1),
                     "andel_par_endret": float((d != 0).mean()) if len(d) else np.nan,
                     "solgt_enheter": float((-d).clip(lower=0).sum()),
                     "paafyll_enheter": float(d.clip(lower=0).sum())})
    return pd.DataFrame(rows)


def update_verdict(fq: pd.DataFrame) -> str:
    if fq.empty:
        return "VENTER: lagersjekk kjøres 12.-18. november"
    day = fq[(fq["timer"] < 6)]
    if day.empty:
        return "VENTER: ingen målinger på dagtid ennå"
    if day["solgt_enheter"].sum() > 0 and (day["andel_par_endret"] > 0).mean() >= 0.5:
        return "Løpende: lageret endrer seg i løpet av dagen"
    return "Én gang i døgnet (ingen endring på dagtid): nattkjøringen fanger hele dagen"


# --------------------------------------------------------------------------
# Fem kontroller
# --------------------------------------------------------------------------

def _between(s: pd.Series, lo: str, hi: str) -> pd.Series:
    return (s >= lo) & (s <= hi)


def kontroller(store: str, dag: pd.DataFrame, kat: pd.DataFrame, bt: pd.DataFrame) -> list[dict]:
    out = []
    ok = dag[(dag["hel_dag"]) & (dag["metode"] == "vare x butikk")] if len(dag) else dag
    base = ok[_between(ok["salgsdag"], *config.BASELINE)] if len(ok) else ok

    # 1 Søndag
    sun = ok[ok["ukedag"] == "søn"] if len(ok) else ok
    week = ok[ok["ukedag"].isin(UKEDAG[:6])] if len(ok) else ok
    if len(sun) and len(week) >= 3:
        r = sun["solgt_enheter"].mean() / week["solgt_enheter"].median()
        mon = ok[ok["ukedag"] == "man"]
        lag = len(mon) and mon["solgt_enheter"].mean() / week["solgt_enheter"].median() < 0.25
        st = "OK" if r < 0.25 else "FEIL"
        txt = f"søndag = {r:.0%} av en vanlig dag"
        if st == "FEIL" and lag:
            txt += "; mandag er lav i stedet: lageret ser ut til å oppdateres én dag på etterskudd"
        out.append({"kontroll": "1 Søndag nær null", "status": st, "verdi": txt,
                    "krav": "søndag < 25 % av median hverdag"})
    else:
        out.append({"kontroll": "1 Søndag nær null", "status": "VENTER", "verdi": "trenger en hel søndag og tre hverdager",
                    "krav": "søndag < 25 % av median hverdag"})

    # 2 Ukemønster
    days = set(base["ukedag"]) if len(base) else set()
    if days >= set(UKEDAG[:6]):
        avg = base.groupby("ukedag")["solgt_enheter"].mean()
        top2 = set(avg.drop("søn", errors="ignore").nlargest(2).index)
        early = avg.reindex(["man", "tir", "ons"]).mean()
        late = avg.reindex(["tor", "fre", "lør"]).mean()
        st = "OK" if "lør" in top2 and early < late else "FEIL"
        out.append({"kontroll": "2 Ukemønster", "status": st,
                    "verdi": f"største dager: {', '.join(sorted(top2))}; man-ons {early:,.0f} mot tor-lør {late:,.0f} enheter",
                    "krav": "lørdag blant de to største; man-ons lavere enn tor-lør"})
    else:
        out.append({"kontroll": "2 Ukemønster", "status": "VENTER", "verdi": f"har {len(days)} av 6 ukedager før Black Week",
                    "krav": "lørdag blant de to største; man-ons lavere enn tor-lør"})

    # 3 Stabilitet: fordeling på kategorier og butikker, første mot andre halvdel av basisperioden
    bd = sorted(base["salgsdag"]) if len(base) else []
    if len(bd) >= 8:
        h1, h2 = set(bd[: len(bd) // 2]), set(bd[len(bd) // 2:])

        def corr(df, key):
            x = df[df["metode"] == "vare x butikk"]
            s1 = x[x["salgsdag"].isin(h1)].groupby(key)["solgt"].sum()
            s2 = x[x["salgsdag"].isin(h2)].groupby(key)["solgt"].sum()
            j = pd.concat([s1 / s1.sum(), s2 / s2.sum()], axis=1).fillna(0)
            return float(j.corr().iloc[0, 1]) if len(j) >= 3 else float("nan")
        ck, cb = corr(kat, "subkat"), corr(bt, "store_id")
        st = "OK" if all(np.isnan(c) or c >= lim for c, lim in ((ck, 0.85), (cb, 0.8))) else "FEIL"
        out.append({"kontroll": "3 Stabil fordeling", "status": st,
                    "verdi": f"korrelasjon kategorier {ck:.2f}, butikker {cb:.2f}",
                    "krav": "kategorier ≥ 0,85 og butikker ≥ 0,80 (første mot andre halvdel før Black Week)"})
    else:
        out.append({"kontroll": "3 Stabil fordeling", "status": "VENTER",
                    "verdi": f"har {len(bd)} av 8 hele dager før Black Week",
                    "krav": "kategorier ≥ 0,85 og butikker ≥ 0,80"})

    # 4 Black Week-løft
    bw = ok[_between(ok["salgsdag"], *config.BLACK_WEEK)] if len(ok) else ok
    if len(bw) >= 3 and len(base) >= 5:
        lift = bw["solgt_enheter"].mean() / base["solgt_enheter"].mean()
        lk = bw["solgt_enheter_kampanje"].mean() / max(base["solgt_enheter_kampanje"].mean(), 1)
        lf = bw["solgt_enheter_fullpris"].mean() / max(base["solgt_enheter_fullpris"].mean(), 1)
        st = "OK" if lift > 1.3 and lk > lf else "FEIL"
        out.append({"kontroll": "4 Black Week-løft", "status": st,
                    "verdi": f"totalt x{lift:.2f}; kampanjevarer x{lk:.2f}, fullpris x{lf:.2f}",
                    "krav": "totalt > 1,3x ukene før, og større løft på kampanjevarer enn fullpris"})
    else:
        out.append({"kontroll": "4 Black Week-løft", "status": "VENTER",
                    "verdi": f"{len(bw)} dager i Black Week ({' til '.join(config.BLACK_WEEK)})",
                    "krav": "totalt > 1,3x ukene før, og større løft på kampanjevarer enn fullpris"})

    # 5 Nivå mot årsregnskap
    ref = config.REFERANSE_OMSETNING_MNOK.get(store)
    if ref and len(base) >= 5:
        r = base["solgt_kr_medlem_eks_mva"].mean() * 365 / (ref * 1e6)
        st = "OK" if 0.2 <= r <= 1.5 else "FEIL"
        out.append({"kontroll": "5 Nivå", "status": st,
                    "verdi": f"anslaget x 365 = {r:.0%} av årsomsetningen i butikk",
                    "krav": "20-150 % (nedre anslag; november er ikke en snittmåned)"})
    else:
        out.append({"kontroll": "5 Nivå", "status": "VENTER",
                    "verdi": "mangler årsomsetning i config.REFERANSE_OMSETNING_MNOK" if not ref
                    else "trenger 5 hele dager før Black Week",
                    "krav": "20-150 % av årsomsetning i butikk"})
    return out


def verdict(checks: list[dict]) -> str:
    s = {c["kontroll"][0]: c["status"] for c in checks}
    core = [s.get(k) for k in "123"]
    if core.count("FEIL") >= 2 or (s.get("4") == "FEIL" and "FEIL" in core):
        return "STØY: anbefaler å skru av (config.SALGSANSLAG = False)"
    if all(x == "OK" for x in core):
        return "BRUKBART: kontroll 1-3 bestått" + (" og Black Week-løftet synlig" if s.get("4") == "OK" else "")
    if "VENTER" in core:
        return f"FOR TIDLIG: avgjøres innen {config.VURDERINGSDATO}"
    return "USIKKERT: én av kontroll 1-3 feiler"


# --------------------------------------------------------------------------
# Rapport
# --------------------------------------------------------------------------

def _fmt_n(v):
    return "–" if v is None or (isinstance(v, float) and np.isnan(v)) else f"{v:,.0f}".replace(",", " ")


def _chart(res: dict, path: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, len(res), figsize=(6 * len(res), 3.8), squeeze=False)
    for ax, (store, r) in zip(axes[0], res.items()):
        d = r["dag"]
        if d.empty:
            continue
        x = pd.to_datetime(d["salgsdag"])
        col = ["#c44e52" if u == "søn" else ("#4c72b0" if h else "#bbbbbb")
               for u, h in zip(d["ukedag"], d["hel_dag"])]
        ax.bar(x, d["solgt_kr_medlem_inkl_mva"] / 1e6, color=col)
        ax.set_title(f"{config.STORES[store]['navn']}: salgsanslag butikk, mill. kr inkl. mva\n"
                     "(rød = søndag, grå = ikke hel dag)", fontsize=9)
        ax.grid(alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def build() -> str | None:
    if not config.SALGSANSLAG:
        print("Salgsanslag er skrudd av (config.SALGSANSLAG = False).")
        return None
    OUT.mkdir(parents=True, exist_ok=True)
    res = {}
    for store in config.STORES:
        if len(dates(store)) < 2:
            continue
        dag, kat, bt, central = build_store(store)
        fq = update_frequency(store)
        res[store] = {"dag": dag, "kat": kat, "bt": bt, "central": central, "fq": fq,
                      "checks": kontroller(store, dag, kat, bt)}
    if not res:
        return None
    lines = ["# Salgsanslag fra butikklager (sideprosjekt)", "",
             "Nedre anslag på salg i fysiske butikker: fall i lager per vare og butikk fra én "
             "nattkjøring til neste. Påfyll skjuler salg, så bruk tallene som indeks. Holdes utenfor "
             "hovedrapporten. Skrus av med `SALGSANSLAG = False` i `scraper/config.py`.", "",
             "![Salgsanslag](salgsanslag.png)", ""]
    for store, r in res.items():
        d = r["dag"]
        lines += [f"## {config.STORES[store]['navn']}", "",
                  f"**Vurdering: {verdict(r['checks'])}**", "",
                  "| Kontroll | Status | Resultat | Krav |", "|---|---|---|---|"]
        lines += [f"| {c['kontroll']} | {c['status']} | {c['verdi']} | {c['krav']} |" for c in r["checks"]]
        lines += ["", f"Oppdatering av lagertall: {update_verdict(r['fq'])}", "",
                  f"Sentrallager holdt utenfor: {', '.join(map(str, sorted(r['central']))) or 'ingen'}", "",
                  "| Salgsdag | Dag | Timer | Solgt, enheter | Mill. kr (medlem, inkl. mva) | Påfyll | "
                  "Andel salg kampanje | Sentrallager ut | Nett: gikk tom / tilbake | Metode |",
                  "|---|---|---:|---:|---:|---:|---:|---:|---|---|"]
        for _, x in d.tail(21).iterrows():
            lines.append(
                f"| {x['salgsdag']} | {x['ukedag']} | {x['timer']} | {_fmt_n(x['solgt_enheter'])} | "
                f"{x['solgt_kr_medlem_inkl_mva'] / 1e6:.2f} | {_fmt_n(x['paafyll_enheter'])} | "
                f"{(x['andel_salg_kampanjevarer'] if pd.notna(x['andel_salg_kampanjevarer']) else 0):.0%} | "
                f"{_fmt_n(x['sentrallager_ut_enheter'])} | {x['nett_gikk_tom']} / {x['nett_kom_tilbake']} | "
                f"{x['metode']} |")
        lines.append("")
    (OUT / "SALGSANSLAG.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    _chart(res, OUT / "salgsanslag.png")
    with pd.ExcelWriter(OUT / "salgsanslag.xlsx", engine="openpyxl") as w:
        for store, r in res.items():
            n = config.STORES[store]["navn"]
            pd.DataFrame(r["checks"]).to_excel(w, sheet_name=f"{n} kontroller", index=False)
            r["dag"].to_excel(w, sheet_name=f"{n} dag", index=False)
            if not r["kat"].empty:
                r["kat"].pivot_table(index="subkat", columns="salgsdag", values="solgt",
                                     aggfunc="sum").reset_index().to_excel(
                    w, sheet_name=f"{n} kategori", index=False)
            if not r["bt"].empty:
                r["bt"].pivot_table(index="store_id", columns="salgsdag", values="solgt",
                                    aggfunc="sum").reset_index().to_excel(
                    w, sheet_name=f"{n} butikk", index=False)
            if not r["fq"].empty:
                r["fq"].to_excel(w, sheet_name=f"{n} lagersjekk", index=False)
    return "\n".join(lines)
