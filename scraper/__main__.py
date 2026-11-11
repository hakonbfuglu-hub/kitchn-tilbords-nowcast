"""python -m scraper innsamling [--butikk kitchn|tilbords]   samle inn alle varer og priser
python -m scraper rapport                                 lag Excel, graf og sammendrag
python -m scraper salgsanslag                             sideprosjekt: salgsanslag fra butikklager
python -m scraper lagersjekk                              sideprosjekt: lager i noen kategorier nå
python -m scraper kartlegg                                hent et utvalg rå sider til rapport/probe
python -m scraper test-side BUTIKK STI                    hent én side og vis hva som tolkes"""

import argparse
import sys

from . import config


def main(argv=None):
    ap = argparse.ArgumentParser(prog="scraper")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("innsamling")
    c.add_argument("--butikk", choices=list(config.STORES), action="append",
                   help="bare denne butikken (kan gjentas); standard: alle")
    c.add_argument("--uten-raa", action="store_true", help="ikke lagre rå sider")
    sub.add_parser("rapport")
    sub.add_parser("kartlegg")
    sub.add_parser("salgsanslag")
    sub.add_parser("lagersjekk")
    t = sub.add_parser("test-side")
    t.add_argument("butikk", choices=list(config.STORES))
    t.add_argument("sti", nargs="?", default="/kjokken/bakeutstyr/")
    a = ap.parse_args(argv)

    if a.cmd == "innsamling":
        from . import crawl
        hs = []
        for s in a.butikk or list(config.STORES):
            try:
                h = crawl.run(s, raw=not a.uten_raa)
            except Exception as e:                       # én butikk skal ikke stoppe den andre
                print(f"[{s}] FEILET: {e!r}")
                h = {"butikk": s, "dato": crawl.today(), "uke": crawl.iso_week(),
                     "status": "FEIL", "problemer": [f"krasj: {e!r}"], "varer": 0,
                     "varer_forrige": None, "oppgitt_toppkategorier": None,
                     "andel_med_pris": 0, "andel_kampanjevare": None,
                     "andel_paa_nettlager": None, "butikkenheter": 0, "fysiske_butikker": 0,
                     "forside_bannere": 0, "kampanjesider": 0, "foresporsler": 0, "mb": 0,
                     "http_status": {}, "minutter": 0, "kategorier": []}
            hs.append(h)
            print(f"\n[{s}] {h['status']}: {h['varer']} varer "
                  f"(oppgitt {h['oppgitt_toppkategorier']}), {h['foresporsler']} forespørsler, "
                  f"{h['mb']} MB, {h['minutter']} min")
            for p in h["problemer"]:
                print("  PROBLEM:", p)
        crawl.write_health(hs)
        return 0 if all(h["status"] == "OK" for h in hs) else 1
    if a.cmd == "rapport":
        from . import rapport
        r = rapport.build()
        print(r.get("sammendrag", "ingen data"))
        return 0
    if a.cmd == "salgsanslag":
        from . import salg
        txt = salg.build()
        print(txt or "ingen salgsanslag (skrudd av eller for lite data)")
        return 0
    if a.cmd == "lagersjekk":
        if not config.SALGSANSLAG:
            print("Salgsanslag er skrudd av.")
            return 0
        from . import crawl
        for s in config.STORES:
            crawl.lagersjekk(s)
        return 0
    if a.cmd == "kartlegg":
        from . import probe
        print(probe.run().read_text(encoding="utf-8"))
        return 0
    if a.cmd == "test-side":
        from .fetch import Fetcher
        from .parse import parse_listing
        html = Fetcher(config.STORES[a.butikk]["base"]).get(a.sti)
        if not html:
            print("Fikk ikke hentet siden.")
            return 1
        cards, meta = parse_listing(html)
        print({k: v for k, v in meta.items() if k != "facets"}, len(meta["facets"]), "fasetter")
        for x in cards[:10]:
            print(x["product_id"], x["price_type"], x["price"], x["price_ordinary"],
                  x["price_member"], x["campaigns"], x["campaign_end"], "|", x["name"])
        print(f"{len(cards)} varer")
        return 0


if __name__ == "__main__":
    sys.exit(main())
