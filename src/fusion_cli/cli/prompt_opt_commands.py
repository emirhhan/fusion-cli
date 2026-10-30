"""`fusion prompt-opt` — istem önerisi üret, onaylayıp uygula, geri al (döngünün 2.-3. halkası).

`calistir` kümede ölçer, AYRI kümede doğrular ve ÖNERİ kaydeder; istem dosyasını değiştirmez.
`uygula` öneriyi dosyaya yazar, `geri-al` sürümden geri döner.
"""

from __future__ import annotations

import asyncio
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from ..config.loader import load_config
from ..core.clock import SystemClock
from ..core.errors import EvalError
from ..ui import theme
from .cleanup import with_web_cleanup
from .dongu_ortak import (
    DEFAULT_PROMPT,
    EXIT_MEASUREMENT_STOPPED,
    LoopPaths,
    error_console,
    fail,
    iso_time,
    loop_paths,
    require_dev_tools,
)

if TYPE_CHECKING:
    # Yalnız tip için: `evals` ve `prompt_opt` çalışma anında tembel yüklenir.
    from prompt_opt.additive import SnippetProvider
    from prompt_opt.campaign import RoundResult, RoundSetup
    from prompt_opt.evaluator import ExecutorFactory
    from prompt_opt.targets import PromptTarget

    from ..config.models import Config

prompt_opt_app = typer.Typer(
    no_args_is_help=True, help="İstem önerileri: ölç, ayrı kümede doğrula, onaylayıp uygula."
)
console = Console()


@prompt_opt_app.command("calistir")
def run_round_command(
    suite: Annotated[str, typer.Option("--kume", help="Optimizasyon kümesi (ad).")],
    heldout: Annotated[str, typer.Option("--ayri", help="AYRI tutulan doğrulama kümesi (ad).")],
    prompt: Annotated[
        str, typer.Option("--istem", help="Optimize edilecek istem.")
    ] = DEFAULT_PROMPT,
    variants: Annotated[int, typer.Option("--aday", min=1, help="Denenecek aday sayısı.")] = 3,
    repeat: Annotated[int, typer.Option("--tekrar", min=1, help="Her görev kaç kez koşulsun.")] = 1,
    min_tasks: Annotated[
        int, typer.Option("--en-az-gorev", min=1, help="Her kümede en az görev.")
    ] = 3,
) -> None:
    """Aday ek maddeler üret, kümede ölç, ayrı kümede doğrula, ÖNERİ olarak kaydet.

    GERÇEK MODEL ÇAĞRISI yapar (kota/ücret kullanıcıya aittir). İstem dosyasını değiştirmez.
    """
    require_dev_tools()
    from evals.kume import kume_coz
    from evals.loader import load_tasks
    from evals.runner import EvaluationUnavailableError, RateLimitedError
    from prompt_opt.campaign import RoundSetup, preflight
    from prompt_opt.targets import get_target

    paths = loop_paths()
    try:
        target = get_target(prompt)
        opt_tasks = load_tasks(_suite_file(suite, paths, kume_coz))
        held_tasks = load_tasks(_suite_file(heldout, paths, kume_coz))
        setup = RoundSetup(
            prompt=prompt,
            base_text=target.read(),
            suite=suite,
            heldout_suite=heldout,
            opt_tasks=opt_tasks,
            heldout_tasks=held_tasks,
            log_path=paths.log,
            now=SystemClock().now,
            timestamp=iso_time,
            variant_count=variants,
            min_tasks=min_tasks,
            max_chars=target.max_chars,
        )
        # Sağlayıcı kurulumundan ÖNCE: aşırı uyum ve boyut tavanı burada kesilir.
        result = preflight(setup) or asyncio.run(
            with_web_cleanup(_run_round(setup, paths, repeat=repeat))
        )
    except (RateLimitedError, EvaluationUnavailableError) as error:
        # Kota/erişim: agent'ın yeteneği ölçülmedi; "başarısız ölçüm" diye kaydedilmez.
        error_console.print(f"[{theme.WARN}]ÖLÇÜM DURDURULDU: {escape(str(error))}[/{theme.WARN}]")
        raise typer.Exit(EXIT_MEASUREMENT_STOPPED) from error
    except (EvalError, ValueError) as error:
        raise fail(str(error)) from error
    _print_round(result)


def _suite_file(name: str, paths: LoopPaths, resolve: Callable[..., Path]) -> Path:
    return resolve(name, kullanici_dizini=paths.suites, paketli_dizin=paths.bundled_suites)


async def _run_round(setup: RoundSetup, paths: LoopPaths, *, repeat: int) -> RoundResult:
    from prompt_opt.campaign import run_round
    from prompt_opt.evaluator import SuiteEvaluator
    from prompt_opt.proposals import ProposalStore
    from prompt_opt.targets import get_target

    config = load_config()
    factory = _executor_factory(config, get_target(setup.prompt))
    return await run_round(
        setup,
        provider=_snippet_provider(config),
        opt_evaluator=SuiteEvaluator(setup.opt_tasks, factory, repeat=repeat),
        heldout_evaluator=SuiteEvaluator(setup.heldout_tasks, factory, repeat=repeat),
        store=ProposalStore(paths.proposals),
    )


def _snippet_provider(config: Config) -> SnippetProvider:
    """Ek madde öneren GERÇEK model sağlayıcısı (testte değiştirilir)."""
    from prompt_opt.model_provider import ModelSnippetProvider

    from ..providers.factory import build_provider
    from ..providers.web_registry import web_registry_for

    runtime = config.runtime
    provider = build_provider(
        config.judge,
        publisher=None,
        retry_delays_s=runtime.retry_delays_s,
        background=True,
        web_sessions=web_registry_for(config),
    )
    return ModelSnippetProvider(
        provider,
        temperature=runtime.judge_temperature,
        max_tokens=runtime.judge_max_tokens,
        timeout_s=runtime.judge_timeout_s,
    )


def _executor_factory(config: Config, target: PromptTarget) -> ExecutorFactory:
    """Aday istemle gerçek agent koşturan yürütücü fabrikası (testte değiştirilir)."""
    from evals.profiles import EvalProfile, build_runner
    from prompt_opt.evaluator import agent_executor_factory

    return agent_executor_factory(
        build_runner(EvalProfile.FUSION_FULL, config),
        target,
        workspace_root=Path(tempfile.mkdtemp(prefix="fusion-prompt-opt-")),
        clock=SystemClock(),
    )


def _print_round(result: RoundResult) -> None:
    def fmt(value: float | None) -> str:
        return "-" if value is None else f"{value:.2f}"

    console.print(f"Sonuç: [bold]{result.outcome}[/bold] — {escape(result.detail)}")
    console.print(f"  optimizasyon kümesi: {fmt(result.opt_base)} → {fmt(result.opt_candidate)}")
    console.print(
        f"  ayrı küme          : {fmt(result.heldout_base)} → {fmt(result.heldout_candidate)}"
    )
    if result.proposal is not None:
        console.print(f"Öneri kaydedildi: {result.proposal.id}")
        console.print(
            "İncele: fusion prompt-opt oneriler  ·  Uygula: fusion prompt-opt uygula <kimlik>"
        )


@prompt_opt_app.command("oneriler")
def proposals_show(
    proposal_id: Annotated[
        str, typer.Argument(help="Verilirse o önerinin ayrıntısı (eklenen metin).")
    ] = "",
) -> None:
    """Kayıtlı istem önerilerini listele (ya da birinin eklediği metni göster)."""
    require_dev_tools()
    from prompt_opt.proposals import ProposalStore

    store = ProposalStore(loop_paths().proposals)
    try:
        if proposal_id:
            proposal = store.get(proposal_id)
            console.print(
                f"[bold]{escape(proposal.id)}[/bold]  {proposal.prompt}  ({proposal.status})"
            )
            console.print(f"[{theme.DIM}]Eklenen metin:[/{theme.DIM}]\n{escape(proposal.addition)}")
            return
        proposals = store.list()
    except EvalError as error:
        raise fail(str(error)) from error
    if not proposals:
        console.print(
            "Kayıtlı öneri yok. Üretmek için: fusion prompt-opt calistir --kume X --ayri Y"
        )
        return
    table = Table(title="İstem önerileri")
    for column in ("kimlik", "istem", "durum", "opt (temel→aday)", "ayrı (temel→aday)"):
        table.add_column(column)
    for item in proposals:
        table.add_row(
            item.id,
            item.prompt,
            item.status,
            f"{item.opt_base:.2f} → {item.opt_candidate:.2f}",
            f"{item.heldout_base:.2f} → {item.heldout_candidate:.2f}",
        )
    console.print(table)


@prompt_opt_app.command("uygula")
def proposal_apply(
    proposal_id: Annotated[str, typer.Argument(help="`oneriler` kimliği")],
) -> None:
    """Öneriyi istem dosyasına uygula (orijinal sürüm olarak saklanır)."""
    require_dev_tools()
    from prompt_opt.apply import apply_proposal
    from prompt_opt.proposals import ProposalStore
    from prompt_opt.versioning import PromptStore

    paths = loop_paths()
    try:
        change = apply_proposal(
            proposal_id,
            proposals=ProposalStore(paths.proposals),
            versions=PromptStore(paths.versions),
            log_path=paths.log,
            now=SystemClock().now,
        )
    except (EvalError, ValueError) as error:
        raise fail(str(error)) from error
    console.print(f"Uygulandı: {change.prompt} sürüm {change.version}.")
    console.print("İstem bütçesi ve davranış testlerini koş: make test")
    console.print(f"Geri almak için: fusion prompt-opt geri-al {change.prompt}")


@prompt_opt_app.command("geri-al")
def proposal_rollback(
    prompt: Annotated[str, typer.Argument(help="Geri alınacak istem adı.")] = DEFAULT_PROMPT,
    version: Annotated[
        int, typer.Option("--surum", help="Dönülecek sürüm (varsayılan: son uygulamadan önce).")
    ] = 0,
) -> None:
    """İstemi uygulamadan önceki sürüme döndür (geçmiş silinmez)."""
    require_dev_tools()
    from prompt_opt.apply import rollback_prompt
    from prompt_opt.proposals import ProposalStore
    from prompt_opt.versioning import PromptStore

    paths = loop_paths()
    try:
        change = rollback_prompt(
            prompt,
            proposals=ProposalStore(paths.proposals),
            versions=PromptStore(paths.versions),
            log_path=paths.log,
            now=SystemClock().now,
            version=version or None,
        )
    except (EvalError, ValueError) as error:
        raise fail(str(error)) from error
    console.print(f"Geri alındı: {change.prompt} sürüm {change.version} olarak yayımlandı.")
