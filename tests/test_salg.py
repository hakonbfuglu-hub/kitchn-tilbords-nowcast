"""Sideprosjekt salgsanslag: kjente svar på et konstruert datasett."""

import datetime as dt

import pandas as pd
import pytest

from scraper import config, salg


def write_day(root, store, day, stock, prices=None, camps=None):
    """stock: {(product, store_id): units}. Nattkjøring kl. 03:45 UTC dagen etter salgsdagen."""
    prods = sorted({p for p, _ in stock} | set(prices or {}))
    run = (dt.date.fromisoformat(day) + dt.timedelta(days=1)).isoformat()
    v = pd.DataFrame({
        "date": run, "iso_week": "x", "crawled_utc": f"{run}T03:45:00+00:00",
        "product_id": prods, "category": "/kjokken/a/", "name": "v", "brand": "b",
        "price": [(prices or {}).get(p, 100) for p in prods],
        "price_ordinary": 100, "price_open": [(prices or {}).get(p, 100) for p in prods],
        "price_member": [(prices or {}).get(p, 100) for p in prods], "price_before": None,
        "campaigns": [(camps or {}).get(p, "fullprisvare") for p in prods],
        "campaign_end": None, "web_stock": True, "web_stock_low": False,
        "store_units": [sum(u for (q, _), u in stock.items() if q == p) for p in prods],
        "n_stores_stock": 1, "is_new": False})
    for sub in ("varer", "lager", "butikker"):
        (root / store / sub).mkdir(parents=True, exist_ok=True)
    v.to_csv(root / store / "varer" / f"{run}.csv.gz", index=False)
    pd.DataFrame([(p, s, u) for (p, s), u in stock.items() if u > 0],
                 columns=["product_id", "store_id", "units"]).to_csv(
        root / store / "lager" / f"{run}.csv.gz", index=False)
    b = pd.DataFrame([(s, u) for (_, s), u in stock.items()], columns=["store_id", "units"])
    b.groupby("store_id")["units"].sum().reset_index().assign(n_products=1).to_csv(
        root / store / "butikker" / f"{run}.csv", index=False)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "STORES", {"kitchn": config.STORES["kitchn"]})
    monkeypatch.setattr(salg, "OUT", tmp_path / "out")
    monkeypatch.setattr(config, "BASELINE", ("2026-11-15", "2026-11-28"))
    monkeypatch.setattr(config, "BLACK_WEEK", ("2026-12-01", "2026-12-07"))
    return tmp_path


def test_interval_per_store_and_central(setup):
    root = setup
    # butikk 1 selger 3 av vare A; butikk 2 får påfyll 5 av A og selger 1 av B;
    # 9 er sentrallager (stort); vare C forsvinner (telles ikke)
    write_day(root, "kitchn", "2026-11-14", {("A", 1): 10, ("A", 2): 2, ("B", 2): 4,
                                             ("A", 9): 5000, ("C", 1): 7, ("B", 3): 10, ("B", 4): 10})
    write_day(root, "kitchn", "2026-11-15", {("A", 1): 7, ("A", 2): 7, ("B", 2): 3,
                                             ("A", 9): 4990, ("B", 3): 10, ("B", 4): 10},
              prices={"A": 50}, camps={"A": "kampanjevare"})
    dag, kat, bt, central = salg.build_store("kitchn")
    assert central == {9}
    r = dag.iloc[0]
    assert r["salgsdag"] == "2026-11-15" and r["ukedag"] == "søn" and r["hel_dag"]
    assert r["solgt_enheter"] == 4                       # 3 (A, butikk 1) + 1 (B)
    assert r["paafyll_enheter"] == 5                     # påfyll skjuler ikke salg i annen butikk
    assert r["solgt_kr_medlem_inkl_mva"] == 3 * 100 + 1 * 100   # pris ved forrige kjøring
    assert r["sentrallager_ut_enheter"] == 10
    assert r["metode"] == "vare x butikk"


def test_checks_pass_on_clean_pattern(setup):
    root = setup
    # 2 uker før «Black Week» med tydelig ukemønster og søndag = 0, så Black Week x2
    pattern = {"man": 10, "tir": 10, "ons": 12, "tor": 15, "fre": 20, "lør": 30, "søn": 0}
    stock = {("A", 1): 100000, ("B", 2): 100000, ("C", 3): 100000}
    day = dt.date(2026, 11, 14)
    write_day(root, "kitchn", day.isoformat(), stock)
    while day < dt.date(2026, 12, 7):
        day += dt.timedelta(days=1)
        n = pattern[salg.UKEDAG[day.weekday()]]
        if day >= dt.date(2026, 12, 1):
            n *= 2
        stock = {("A", 1): stock[("A", 1)] - n, ("B", 2): stock[("B", 2)] - n,
                 ("C", 3): stock[("C", 3)] - (2 * n if day >= dt.date(2026, 12, 1) else 0)}
        write_day(root, "kitchn", day.isoformat(), stock,
                  camps={"C": "kampanjevare;black weeks"})
    dag, kat, bt, central = salg.build_store("kitchn")
    checks = {c["kontroll"][0]: c for c in salg.kontroller("kitchn", dag, kat, bt)}
    assert checks["1"]["status"] == "OK"
    assert checks["2"]["status"] == "OK"
    assert checks["3"]["status"] == "OK"
    assert checks["4"]["status"] == "OK", checks["4"]["verdi"]
    assert salg.verdict(list(checks.values())).startswith("BRUKBART")
    txt = salg.build()
    assert "BRUKBART" in txt and (salg.OUT / "salgsanslag.xlsx").exists()


def test_checks_fail_on_noise(setup):
    import numpy as np
    root = setup
    rng = np.random.default_rng(0)
    stock = {(p, s): 100000 for p in "ABCDEF" for s in range(1, 6)}
    day = dt.date(2026, 11, 14)
    write_day(root, "kitchn", day.isoformat(), stock)
    while day < dt.date(2026, 11, 29):
        day += dt.timedelta(days=1)
        stock = {k: v + int(rng.integers(-40, 40)) for k, v in stock.items()}
        write_day(root, "kitchn", day.isoformat(), stock)
    dag, kat, bt, _ = salg.build_store("kitchn")
    checks = salg.kontroller("kitchn", dag, kat, bt)
    assert [c["status"] for c in checks[:3]].count("FEIL") >= 2
    assert salg.verdict(checks).startswith("STØY")


def test_switch_off(setup, monkeypatch):
    monkeypatch.setattr(config, "SALGSANSLAG", False)
    assert salg.build() is None
