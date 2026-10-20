from __future__ import annotations

import argparse
from pathlib import Path

from .depo import UrunDeposu


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="stokapp")
    parser.add_argument("--depo", default="urunler.json")
    alt = parser.add_subparsers(dest="komut", required=True)
    alt.add_parser("listele")
    args = parser.parse_args(argv)
    depo = UrunDeposu(Path(args.depo))
    if args.komut == "listele":
        for urun in depo.hepsi().values():
            print(f"{urun.sku}\t{urun.ad}\t{urun.fiyat:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
