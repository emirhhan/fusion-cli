"""Kabul koşucusunun komut satırı: ön-kontrol → paralel koşular → rapor."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from evals.kabul.areas import AREA_MODULES, load_area
from evals.kabul.engine_options import selected_engine
from evals.kabul.preflight import run_preflight
from evals.kabul.report import render_text, write_report
from evals.kabul.runner import Job, RunnerOptions, run_all

#: Varsayılan eşzamanlı koşu sayısı: 8 GB RAM'li makinede WordPress + Playwright +
#: çekirdek süreçleri için ölçülmüş güvenli üst sınır değil, tutucu başlangıç.
DEFAULT_PARALLEL = 3
#: Koşular arası başlangıç aralığı: öğretmenin plan istekleri üst üste binmesin.
DEFAULT_STAGGER_S = 300.0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m evals.kabul")
    parser.add_argument("--alan", action="append", choices=sorted(AREA_MODULES), default=[])
    parser.add_argument("--tekrar", type=int, default=1)
    parser.add_argument("--paralel", type=int, default=DEFAULT_PARALLEL)
    parser.add_argument("--aralik", type=float, default=DEFAULT_STAGGER_S)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--engine-source", type=Path, default=None)
    parser.add_argument("--engine-manifest", type=Path, default=None)
    parser.add_argument("--cikti", type=Path, required=True)
    parser.add_argument("--onkontrolu-atla", action="store_true")
    return parser


def main() -> None:
    args = _parser().parse_args()
    secenekler = RunnerOptions(
        args.paralel, args.aralik, args.config, args.engine_source, args.engine_manifest
    )
    adlar = args.alan or sorted(AREA_MODULES)
    alanlar = [load_area(ad) for ad in adlar]
    cikti = args.cikti.expanduser().resolve()
    selected_engine(secenekler.engine_source, secenekler.engine_manifest, cikti)
    cikti.mkdir(parents=True, exist_ok=True)
    on_kontrol = None
    if not args.onkontrolu_atla:
        on_kontrol = (
            run_preflight(
                alanlar,
                cikti,
                args.config,
                engine_source=args.engine_source,
                engine_manifest=args.engine_manifest,
            )
            if args.engine_source is not None
            else run_preflight(alanlar, cikti, args.config)
        )
        if not on_kontrol.passed:
            write_report(cikti / "rapor.json", [], on_kontrol)
            sys.stderr.write(f"Ön-kontrol geçmedi, koşu başlamadı: {on_kontrol.failures()}\n")
            raise SystemExit(2)
    isler = [
        Job(area=alan, attempt=tekrar, workdir=cikti / f"{alan.name}-{tekrar}")
        for tekrar in range(1, args.tekrar + 1)
        for alan in alanlar
    ]
    kayitlar = asyncio.run(run_all(isler, secenekler))
    write_report(cikti / "rapor.json", kayitlar, on_kontrol)
    sys.stdout.write(render_text(kayitlar) + "\n")
