"""Excel, graf og kort sammendrag per butikk.

  rapport/<butikk>_tracker.xlsx   Sammendrag, Dag, Uke, Kategorier, Kampanjefasetter,
                                  Butikker, Varer (siste kjøring), Forklaring
  rapport/<butikk>_utvikling.png  kampanjeandel, rabatt, prisindeks, sortiment
  rapport/SISTE.md                begge butikker, siste kjøring
  rapport/drive_ukesrapport.csv   kompakt tabell for ukesrapporten i Google Disk
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from . import config, indeks  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "rapport"

PCT = {"andel_", "snittrabatt", "lagervektet_rabatt", "nye_mot_eksisterende"}

FORKLARING = [
    ("Varer", "Antall unike varer funnet på kategorisidene (alle varer, også de som ikke er på nettlager)."),
    ("Nye / utgåtte varer", "Varer som er kommet til / forsvunnet siden forrige kjøring (Dag) eller forrige uke (Uke)."),
    ("Andel på nettlager", "Andel varer merket «På nettlager» / «Få igjen på nettlager»."),
    ("Andel med kampanje", "Varer med lavere pris enn ordinær for medlem, eller merket kampanjevare, klubbpris, 3 for 2, Black Weeks eller lagertømming."),
    ("Andel kampanjevare / klubbpris / 3for2 / black_weeks / lagertomming / bra_deal", "Butikkens egne kampanjemerker på varen. Flerkjøp = «3 for 2», «2 for 40%» o.l."),
    ("Andel rabatt medlem ekskl. lagertømming", "Varer med lavere medlemspris enn ordinær, uten lagertømming (Kitchn merker lagertømming med kampanjeslutt 2030, altså varig nedsatt)."),
    ("Snittrabatt ikke-medlem / medlem", "Snitt over alle varer av 1 − pris / ordinær pris. Ordinær = «Førpris», «Ikke medlem» eller «Etter kampanje» når de vises."),
    ("Lagervektet rabatt medlem", "Som over, vektet med enheter på lager i butikk (hvor mye av hylla som er på tilbud)."),
    ("Prisindeks", "Jevons (geometrisk snitt) av pris mot vareens snittpris i basisvinduet " + " til ".join(config.BASE_WINDOW) + ". Kjedeindeks = lenket fra kjøring til kjøring."),
    ("Nye mot eksisterende", "Log-forskjell i ordinær pris for nye varer mot eksisterende i samme kategori samme dag (−0,05 ≈ 5 % billigere)."),
    ("Mangler mot Kid", "Anmeldelser per vare vises ikke på listesidene, så «nye anmeldelser» finnes ikke her. Salgsanslag fra butikklager er et eget sideprosjekt: se rapport/salgsanslag/."),
]


def _fmt(ws, df: pd.DataFrame, r0: int = 1):
    from openpyxl.styles import Font
    for j, c in enumerate(df.columns, start=1):
        cell = ws.cell(row=r0, column=j)
        cell.font = Font(bold=True)
        w = max(10, min(40, len(str(c)) + 2))
        ws.column_dimensions[cell.column_letter].width = w
        if any(str(c).startswith(p) for p in PCT):
            for i in range(r0 + 1, r0 + 1 + len(df)):
                ws.cell(row=i, column=j).number_format = "0.0%"
        elif str(c).startswith(("prisindeks", "kjedeindeks")):
            for i in range(r0 + 1, r0 + 1 + len(df)):
                ws.cell(row=i, column=j).number_format = "0.0"
        elif str(c).startswith(("varer", "nye_varer", "utgaatte")):
            for i in range(r0 + 1, r0 + 1 + len(df)):
                ws.cell(row=i, column=j).number_format = "#,##0"
    ws.freeze_panes = ws.cell(row=r0 + 1, column=3)


def _chart(day: pd.DataFrame, path: Path, title: str):
    a = day[day["gruppe"] == "ALLE"].sort_values("date")
    if a.empty:
        return
    x = pd.to_datetime(a["date"])
    fig, ax = plt.subplots(2, 2, figsize=(11, 6.5), sharex=True)
    ax[0, 0].plot(x, 100 * a["andel_med_kampanje"], marker="o", label="med kampanje")
    ax[0, 0].plot(x, 100 * a["andel_rabatt_medlem"], marker=".", label="rabatt medlem")
    ax[0, 0].plot(x, 100 * a["andel_black_weeks"], marker=".", label="Black Weeks-merket")
    ax[0, 0].set_title("Andel av sortimentet, %")
    ax[0, 1].plot(x, 100 * a["snittrabatt_medlem"], marker="o", label="medlem")
    ax[0, 1].plot(x, 100 * a["snittrabatt_ikke_medlem"], marker=".", label="ikke-medlem")
    ax[0, 1].plot(x, 100 * a["lagervektet_rabatt_medlem"], marker=".", label="medlem, lagervektet")
    ax[0, 1].set_title("Snittrabatt mot ordinær pris, %")
    for L, lab in (("ordinaer", "ordinær"), ("aapen", "ikke-medlem"), ("medlem", "medlem")):
        if f"prisindeks_{L}" in a:
            ax[1, 0].plot(x, a[f"prisindeks_{L}"], marker=".", label=lab)
    ax[1, 0].axhline(100, color="grey", lw=0.8)
    ax[1, 0].set_title("Prisindeks samme varer (basis = 100)")
    ax[1, 1].plot(x, a["varer"], marker="o", color="#4c72b0")
    ax[1, 1].set_title("Antall varer")
    for k in ax.flat:
        k.grid(alpha=0.3)
        if k.get_legend_handles_labels()[0]:
            k.legend(fontsize=8)
    fig.suptitle(title)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def _store_report(store: str) -> dict | None:
    cfg = config.STORES[store]
    df = indeks.load(store)
    if df.empty:
        return None
    day = indeks.daily(df)
    wk = indeks.weekly(df, day)
    latest = df["date"].max()
    snap = df[df["date"] == latest]
    alle = day[day["gruppe"] == "ALLE"].copy()
    kats = day[(day["date"] == latest) & (day["gruppe"] != "ALLE")]
    fac = indeks.campaign_facets(store)
    bdir = config.DATA_DIR / store / "butikker"
    bfiles = sorted(bdir.glob("*.csv"))
    butikker = (pd.concat([pd.read_csv(f) for f in bfiles]) if bfiles else pd.DataFrame())
    if not butikker.empty:
        butikker = butikker.pivot_table(index="store_id", columns="date", values="units",
                                        aggfunc="sum").reset_index()
    kp_files = sorted((config.DATA_DIR / store / "kampanjesider").glob("*.csv"))
    kp = pd.concat([pd.read_csv(f) for f in kp_files if f.stat().st_size > 5]) if kp_files else pd.DataFrame()

    OUT.mkdir(exist_ok=True)
    xl = OUT / f"{store}_tracker.xlsx"
    with pd.ExcelWriter(xl, engine="openpyxl") as w:
        summ = alle.drop(columns=["gruppe"]).set_index("date").T.reset_index().rename(
            columns={"index": "mål"})
        summ.to_excel(w, sheet_name="Sammendrag", index=False)
        alle.to_excel(w, sheet_name="Dag", index=False)
        wk.to_excel(w, sheet_name="Uke", index=False)
        kats.to_excel(w, sheet_name="Kategorier", index=False)
        if not fac.empty:
            fac.to_excel(w, sheet_name="Kampanjefasetter", index=False)
        if not kp.empty:
            kp.to_excel(w, sheet_name="Kampanjesider", index=False)
        if not butikker.empty:
            butikker.to_excel(w, sheet_name="Butikker", index=False)
        cols = ["product_id", "category", "brand", "name", "price", "price_ordinary",
                "price_open", "price_member", "rabatt_medlem", "campaigns", "campaign_end",
                "web_stock", "n_stores_stock", "store_units"]
        snap[[c for c in cols if c in snap]].sort_values(["category", "brand"]).to_excel(
            w, sheet_name="Varer", index=False)
        pd.DataFrame(FORKLARING, columns=["Mål", "Forklaring"]).to_excel(w, sheet_name="Forklaring", index=False)
        for name, d in (("Dag", alle), ("Uke", wk), ("Kategorier", kats)):
            _fmt(w.sheets[name], d)
        ws = w.sheets["Sammendrag"]
        ws.column_dimensions["A"].width = 34
        for i, m in enumerate(summ["mål"], start=2):
            fmt = ("0.0%" if any(str(m).startswith(p) for p in PCT) else
                   "0.0" if str(m).startswith(("prisindeks", "kjedeindeks")) else "#,##0")
            for j in range(2, summ.shape[1] + 1):
                ws.cell(row=i, column=j).number_format = fmt
        w.sheets["Forklaring"].column_dimensions["A"].width = 38
        w.sheets["Forklaring"].column_dimensions["B"].width = 120
    _chart(day, OUT / f"{store}_utvikling.png", f"{cfg['navn']}: kampanjetrykk, pris og sortiment")

    last = alle.iloc[-1]
    prev = alle.iloc[-2] if len(alle) > 1 else None
    return {"store": store, "navn": cfg["navn"], "dato": latest, "last": last, "prev": prev,
            "kjoringer": len(alle), "wk": wk}


def _p(v) -> str:
    return "–" if v is None or (isinstance(v, float) and np.isnan(v)) else f"{100 * v:.1f} %".replace(".", ",")


def _n(v) -> str:
    return "–" if v is None or (isinstance(v, float) and np.isnan(v)) else f"{v:,.0f}".replace(",", " ")


def _i(v) -> str:
    return "–" if v is None or (isinstance(v, float) and np.isnan(v)) else f"{v:.1f}".replace(".", ",")


def build() -> dict:
    res = [r for r in (_store_report(s) for s in config.STORES) if r]
    if not res:
        return {"sammendrag": "ingen data"}
    lines = ["# Kitchn og Tilbords: siste kjøring", ""]
    rows = []
    for r in res:
        L, P = r["last"], r["prev"]
        lines += [
            f"## {r['navn']} ({r['dato']}, {r['kjoringer']} kjøringer)", "",
            f"![{r['navn']}]({r['store']}_utvikling.png)", "",
            "| Mål | Siste | Forrige |", "|---|---:|---:|",
            f"| Varer | {_n(L['varer'])} | {_n(P['varer']) if P is not None else '–'} |",
            f"| Andel med kampanje | {_p(L['andel_med_kampanje'])} | {_p(P['andel_med_kampanje']) if P is not None else '–'} |",
            f"| Andel Black Weeks-merket | {_p(L['andel_black_weeks'])} | {_p(P['andel_black_weeks']) if P is not None else '–'} |",
            f"| Snittrabatt medlem | {_p(L['snittrabatt_medlem'])} | {_p(P['snittrabatt_medlem']) if P is not None else '–'} |",
            f"| Snittrabatt ikke-medlem | {_p(L['snittrabatt_ikke_medlem'])} | {_p(P['snittrabatt_ikke_medlem']) if P is not None else '–'} |",
            f"| Prisindeks medlem (basis 100) | {_i(L.get('prisindeks_medlem'))} | {_i(P.get('prisindeks_medlem')) if P is not None else '–'} |",
            f"| Andel på nettlager | {_p(L['andel_paa_nettlager'])} | {_p(P['andel_paa_nettlager']) if P is not None else '–'} |",
            "",
        ]
        rows.append({"butikk": r["navn"], "dato": r["dato"], **{k: L.get(k) for k in (
            "varer", "nye_varer", "utgaatte_varer", "andel_med_kampanje", "andel_kampanjevare",
            "andel_klubbpris", "andel_3for2", "andel_flerkjop", "andel_rabatt_medlem_ekskl_lagertomming", "andel_black_weeks", "andel_lagertomming",
            "snittrabatt_medlem", "snittrabatt_ikke_medlem", "lagervektet_rabatt_medlem",
            "prisindeks_ordinaer", "prisindeks_aapen", "prisindeks_medlem",
            "andel_paa_nettlager")}})
    lines += ["Full rapport: `rapport/kitchn_tracker.xlsx` og `rapport/tilbords_tracker.xlsx`. "
              "Forklaring av målene står i arket «Forklaring».", ""]
    (OUT / "SISTE.md").write_text("\n".join(lines), encoding="utf-8")
    pd.DataFrame(rows).to_csv(OUT / "drive_ukesrapport.csv", index=False)
    return {"sammendrag": "\n".join(lines)}
