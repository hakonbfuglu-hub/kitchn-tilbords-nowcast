"""Mål på et lite, konstruert datasett med kjente svar."""

import pandas as pd
import pytest

from scraper import config, indeks


def frame(date, rows):
    df = pd.DataFrame(rows, columns=["product_id", "price", "price_ordinary", "price_open",
                                     "price_member", "campaigns", "store_units"])
    return df.assign(date=date, iso_week=indeks.week_of(date), category="/kjokken/x/",
                     name="v", brand="b", price_before=None, campaign_end=None,
                     web_stock=True, n_stores_stock=1, is_new=False)


@pytest.fixture
def df(monkeypatch):
    monkeypatch.setattr(config, "BASE_WINDOW", ("2026-11-10", "2026-11-10"))
    a = frame("2026-11-10", [
        ("1", 100, 100, 100, 100, "fullprisvare", 10),
        ("2", 50, 100, 50, 50, "kampanjevare", 20),
        ("3", 60, 120, 120, 60, "klubbpris;kampanjevare", 5),
        ("4", 80, 80, 80, 80, "3 for 2", 0),
    ])
    b = frame("2026-11-11", [
        ("1", 80, 100, 80, 80, "black weeks;kampanjevare", 7),     # -20 %, solgt 3
        ("2", 50, 100, 50, 50, "kampanjevare", 25),                 # påfyll +5
        ("3", 60, 120, 120, 60, "klubbpris;kampanjevare", 4),       # solgt 1
        ("5", 40, 40, 40, 40, "nyhet", 9),                          # ny vare
    ])
    return indeks.prepare(pd.concat([a, b], ignore_index=True))


def test_snapshot(df):
    s = indeks.snapshot_metrics(df).set_index(["date", "gruppe"])
    a = s.loc[("2026-11-10", "ALLE")]
    assert a["varer"] == 4
    assert a["andel_med_kampanje"] == pytest.approx(0.75)        # 2, 3 og 3 for 2
    assert a["andel_rabatt_medlem"] == pytest.approx(0.5)
    assert a["andel_rabatt_ikke_medlem"] == pytest.approx(0.25)  # klubbpris gjelder ikke
    assert a["snittrabatt_medlem"] == pytest.approx((0 + .5 + .5 + 0) / 4)
    assert a["andel_flerkjop"] == pytest.approx(0.25)


def test_flows(df):
    f = indeks.flows(df).set_index("gruppe").loc["ALLE"]
    assert f["nye_varer"] == 1 and f["utgaatte_varer"] == 1


def test_price_index(df):
    p = indeks.price_indices(df).set_index(["date", "gruppe"]).loc[("2026-11-11", "ALLE")]
    # samme varer: 1 (0,8), 2 (1,0), 3 (1,0) -> geometrisk snitt
    assert p["prisindeks_medlem"] == pytest.approx(100 * 0.8 ** (1 / 3))
    assert p["prisindeks_ordinaer"] == pytest.approx(100)
    assert p["n_medlem"] == 3


def test_report_builds(df, tmp_path, monkeypatch):
    from scraper import rapport
    d = tmp_path / "data" / "kitchn" / "varer"
    d.mkdir(parents=True)
    raw = df[[c for c in indeks.COLS if c in df]]
    for day, g in raw.groupby("date"):
        g.to_csv(d / f"{day}.csv.gz", index=False)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "STORES", {"kitchn": config.STORES["kitchn"]})
    monkeypatch.setattr(rapport, "OUT", tmp_path / "rapport")
    r = rapport.build()
    assert "Kitchn" in r["sammendrag"]
    x = pd.read_excel(tmp_path / "rapport" / "kitchn_tracker.xlsx", sheet_name=None, engine="openpyxl")
    assert {"Sammendrag", "Dag", "Uke", "Varer", "Forklaring"} <= set(x)
    assert len(x["Varer"]) == 4
