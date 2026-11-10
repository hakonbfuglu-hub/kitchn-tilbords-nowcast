"""python -m scraper kartlegg              hent et utvalg rå sider til rapport/probe"""

import argparse
import sys


def main(argv=None):
    ap = argparse.ArgumentParser(prog="scraper")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("kartlegg")
    a = ap.parse_args(argv)

    if a.cmd == "kartlegg":
        from . import probe
        print(probe.run().read_text(encoding="utf-8"))
        return 0


if __name__ == "__main__":
    sys.exit(main())
