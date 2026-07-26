"""`python -m evals` — değerlendirme setini koştur ve iki çalıştırmayı karşılaştır.

Bu bir GELİŞTİRİCİ aracıdır (ürünün `fusion` komutuna dahil değil): depo kökünden
çalıştırılır. Gerçek koşu modeli çağırır (ağ/anahtar gerekir); karşılaştırma tümüyle
yereldir.

Kullanım:
    python -m evals run evals/suite/starter.yaml --out rapor.json
    python -m evals compare eski.json yeni.json
"""

from __future__ import annotations

import argparse
import asyncio
import tempfile
from pathlib import Path

from evals.agent_runner import FusionAgentRunner
from evals.compare import compare_reports
from evals.executor import AgentTaskExecutor
from evals.loader import load_tasks
from evals.metrics import RunReport
from evals.report import read_report, write_report
from evals.runner import run_suite
from fusion_cli.config.loader import load_config
from fusion_cli.core.clock import SystemClock


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="evals", description="fusion-cli değerlendirme aracı")
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="Seti koştur ve metrik topla")
    run_parser.add_argument("suite", type=Path, help="Görev seti (YAML) yolu")
    run_parser.add_argument("--out", type=Path, default=None, help="Raporun yazılacağı JSON")
    run_parser.add_argument(
        "--seed", type=Path, default=None, help="Her görev dizinine kopyalanacak tohum dizini"
    )
    run_parser.add_argument(
        "--workspace", type=Path, default=None, help="Çalışma dizinlerinin kökü (varsayılan: tmp)"
    )
    run_parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="Her görevi N kez koştur ve geçme oranını raporla (varsayılan 1). "
        "Tek koşu gürültülüdür; bir ayarın etkisini ölçmek için 3-5 önerilir.",
    )

    compare_parser = sub.add_parser("compare", help="İki raporu karşılaştır")
    compare_parser.add_argument("baseline", type=Path, help="Eski (temel) rapor JSON")
    compare_parser.add_argument("candidate", type=Path, help="Yeni (aday) rapor JSON")

    args = parser.parse_args(argv)
    if args.command == "run":
        return _run(args)
    return _compare(args)


def _run(args: argparse.Namespace) -> int:
    tasks = load_tasks(args.suite)
    workspace_root = args.workspace or Path(tempfile.mkdtemp(prefix="fusion-eval-"))
    workspace_root.mkdir(parents=True, exist_ok=True)

    executor = AgentTaskExecutor(
        FusionAgentRunner(load_config()),
        workspace_root=workspace_root,
        clock=SystemClock(),
        seed_dir=args.seed,
    )
    tekrar = f" × {args.repeat} tekrar" if args.repeat > 1 else ""
    print(f"{len(tasks)} görev{tekrar} koşturuluyor (çalışma dizini: {workspace_root})…")
    report = asyncio.run(run_suite(tasks, executor, repeat=args.repeat))

    _print_summary(report)
    if args.out is not None:
        write_report(report, args.out)
        print(f"\nRapor yazıldı: {args.out}")
    return 0


def _compare(args: argparse.Namespace) -> int:
    baseline = read_report(args.baseline)
    candidate = read_report(args.candidate)
    comparison = compare_reports(baseline, candidate)

    print("Metrik karşılaştırması (eski → yeni):")
    for metric in comparison.metrics:
        arrow = "▲" if metric.delta > 0 else ("▼" if metric.delta < 0 else "=")
        print(
            f"  {metric.name:<28} {metric.baseline:.3f} → {metric.candidate:.3f} "
            f"({metric.delta:+.3f}) {arrow}"
        )
    print(f"\nGerileyen görevler: {', '.join(comparison.regressions) or '(yok)'}")
    print(f"İyileşen görevler:  {', '.join(comparison.improvements) or '(yok)'}")
    return 0


def _print_summary(report: RunReport) -> None:
    print("\nÖzet:")
    print(f"  görev sayısı           : {report.task_count}")
    print(f"  başarı oranı           : {report.task_success_rate:.3f}")
    print(f"  ilk denemede başarı    : {report.first_attempt_success_rate:.3f}")
    print(f"  toplam yeniden deneme  : {report.total_retries}")
    print(f"  ort. model çağrısı     : {report.mean_model_calls:.2f}")
    print(f"  ort. süre (sn)         : {report.mean_duration_seconds:.2f}")

    kararsiz = [item for item in report.results if not item.kararli]
    if kararsiz:
        # Kararsız görev bir ayarın etkisini ölçerken gürültü kaynağıdır; sessizce
        # ortalamaya karışmasın, adıyla yazılsın.
        print("\n  KARARSIZ görevler (her koşuda aynı sonucu vermiyor):")
        for item in kararsiz:
            print(f"    {item.task_id:<32} {item.passes}/{item.runs} geçti")


if __name__ == "__main__":
    raise SystemExit(main())
