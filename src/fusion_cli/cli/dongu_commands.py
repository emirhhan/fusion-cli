"""`fusion eval` ve `fusion prompt-opt` — kendini geliştirme döngüsü.

Döngü üç halkadır ve HER halkada son söz kullanıcıdadır:

1. `fusion eval taslak-uret`   gerçek konuşmadaki hatalardan eval görevi TASLAĞI çıkarır;
   `fusion eval taslaklar / kabul / sil` taslağı kullanıcı onaylar ya da atar.
2. `fusion prompt-opt calistir` kümede ölçer, AYRI kümede doğrular, ÖNERİ kaydeder;
   istem dosyasını değiştirmez.
3. `fusion prompt-opt uygula / geri-al` öneriyi uygular ya da sürümden geri döner.

Tüm veri `config.paths.loop_dir()` altında, kullanıcının makinesinde kalır. `evals` ve
`prompt_opt` depo kökündeki geliştirici araçlarıdır (pakete girmez); komutlar onları ilk
kullanımda tembel yükler ve bulunamazsa ne yapılacağını söyler.
"""

from __future__ import annotations

import sys
import tempfile
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from ..config.loader import load_config
from ..config.paths import loop_dir
from ..core.clock import SystemClock
from ..core.errors import EvalError
from ..ui import theme
from .cleanup import with_web_cleanup
from .repl.transcript_store import read_workspace_events

if TYPE_CHECKING:
    # Yalnız tip için: `evals` ve `prompt_opt` çalışma anında tembel yüklenir.
    from evals.taslak import Taslak
    from prompt_opt.additive import SnippetProvider
    from prompt_opt.campaign import RoundResult, RoundSetup
    from prompt_opt.evaluator import ExecutorFactory
    from prompt_opt.targets import PromptTarget

    from ..config.models import Config

eval_app = typer.Typer(
    no_args_is_help=True, help="Eval görevleri: gerçek hatalardan taslak üret, onayla."
)
prompt_opt_app = typer.Typer(
    no_args_is_help=True, help="İstem önerileri: ölç, ayrı kümede doğrula, onaylayıp uygula."
)
console = Console()
error_console = Console(stderr=True)

#: Varsayılan: son kaç günün konuşması taranır (haftalık çalıştırma için).
DEFAULT_SCAN_DAYS = 7
SECONDS_PER_DAY = 86_400
#: Listede gösterilen isteğin uzunluğu.
LIST_REQUEST_CHARS = 70
DEFAULT_SUITE = "kullanici"
DEFAULT_PROMPT = "system"
#: Çıkış kodları: ölçüm durdu (kota/erişim) ayrı, kullanıcı/yapılandırma hatası ayrı.
EXIT_FAILED = 1
EXIT_MEASUREMENT_STOPPED = 2

_TOOLS_MISSING = (
    "Bu komut depodaki geliştirici araçlarına (evals, prompt_opt) dayanır; kurulu pakette "
    "bulunmuyorlar. Depo kökünden çalıştır: .venv/bin/fusion ..."
)
_BUNDLED_SUITES = "evals/suite"


@dataclass(frozen=True, slots=True)
class LoopPaths:
    """Döngünün kullanıcıya özel dizinleri ve ölçüm izi dosyası."""

    drafts: Path
    suites: Path
    proposals: Path
    versions: Path
    log: Path
    bundled_suites: Path


def loop_paths() -> LoopPaths:
    root = loop_dir()
    repo = _repo_root()
    return LoopPaths(
        drafts=root / "taslak",
        suites=root / "kume",
        proposals=root / "oneriler",
        versions=root / "surumler",
        log=root / "kayit.jsonl",
        bundled_suites=(repo or Path()) / _BUNDLED_SUITES,
    )


def _repo_root() -> Path | None:
    """Kaynak deposunun kökü (`src/fusion_cli/cli/` üç seviye yukarı); kurulu pakette yok."""
    root = Path(__file__).resolve().parents[3]
    return root if (root / "evals" / "__init__.py").is_file() else None


def _require_dev_tools() -> None:
    """`evals` ve `prompt_opt` içe aktarılabilir olsun; değilse depo kökünü yola ekle."""
    try:
        import evals  # noqa: F401
        import prompt_opt  # noqa: F401

        return
    except ImportError:
        pass
    root = _repo_root()
    if root is None or not (root / "prompt_opt" / "__init__.py").is_file():
        error_console.print(f"[{theme.WARN}]{escape(_TOOLS_MISSING)}[/{theme.WARN}]")
        raise typer.Exit(EXIT_FAILED)
    # Editable kurulum yalnız `src/`yi yola koyar; araçlar depo kökünde durur.
    sys.path.insert(0, str(root))


def _fail(message: str) -> typer.Exit:
    error_console.print(f"[{theme.WARN}]{escape(message)}[/{theme.WARN}]")
    return typer.Exit(EXIT_FAILED)


def _iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=UTC).isoformat(timespec="seconds")


# --------------------------------------------------------------------------- #
# fusion eval
# --------------------------------------------------------------------------- #


@eval_app.command("taslak-uret")
def draft_generate(
    project: Annotated[
        Path | None, typer.Option("--proje", help="Proje kökü (varsayılan: bulunduğun dizin).")
    ] = None,
    days: Annotated[
        int, typer.Option("--gun", min=1, help="Son kaç günün konuşması.")
    ] = DEFAULT_SCAN_DAYS,
    limit: Annotated[int, typer.Option("--maks", min=1, help="En çok kaç taslak yazılsın.")] = 50,
) -> None:
    """Konuşma günlüğündeki düzeltme/geri alma/tekrar/başarısız turlardan taslak üret."""
    _require_dev_tools()
    from evals.dongu_kaydi import OLAY_TASLAK_URETILDI, kayit_ekle
    from evals.kume import kabul_edilen_kimlikler
    from evals.taslak import taslak_uret
    from evals.taslak_deposu import TaslakDeposu

    paths = loop_paths()
    root = (project or Path.cwd()).expanduser().resolve()
    now = SystemClock().now()
    records = read_workspace_events(load_config().memory_dir, root)
    found = taslak_uret(
        records,
        kok=root,
        ev=Path.home(),
        simdi=now,
        sonra=now - days * SECONDS_PER_DAY,
        maks=limit,
    )
    written = TaslakDeposu(paths.drafts).kaydet(found, atla=kabul_edilen_kimlikler(paths.suites))
    kinds = Counter(taslak.kaynak.value for taslak in written)
    kayit_ekle(
        paths.log,
        OLAY_TASLAK_URETILDI,
        {"bulunan": len(found), "yeni": len(written), "kaynaklar": dict(kinds), "gun": days},
        simdi=now,
    )
    console.print(
        f"{len(records)} kayıt tarandı: {len(found)} taslak bulundu, {len(written)} yeni yazıldı."
    )
    if written:
        console.print("Görmek için: fusion eval taslaklar")


@eval_app.command("taslaklar")
def drafts_show(
    draft_id: Annotated[str, typer.Argument(help="Verilirse o taslağın ayrıntısı.")] = "",
) -> None:
    """Onay bekleyen taslakları listele (ya da birinin ayrıntısını göster)."""
    _require_dev_tools()
    from evals.taslak_deposu import TaslakDeposu

    store = TaslakDeposu(loop_paths().drafts)
    try:
        if draft_id:
            _print_draft_detail(store.oku(draft_id))
            return
        drafts = store.listele()
    except EvalError as error:
        raise _fail(str(error)) from error
    if not drafts:
        console.print("Onay bekleyen taslak yok. Üretmek için: fusion eval taslak-uret")
        return
    table = Table(title="Eval görev taslakları (onay bekliyor)")
    for column in ("kimlik", "kaynak", "ölçüt", "istek"):
        table.add_column(column)
    for draft in drafts:
        table.add_row(
            draft.id,
            draft.kaynak.value,
            draft.olcut.kind.value if draft.olcut else "[yok]",
            escape(draft.request[:LIST_REQUEST_CHARS].replace("\n", " ")),
        )
    console.print(table)
    console.print("Kabul: fusion eval kabul <kimlik>   ·   Atma: fusion eval sil <kimlik>")


def _print_draft_detail(draft: Taslak) -> None:
    console.print(f"[bold]{escape(draft.id)}[/bold]  ({draft.kaynak.value})")
    console.print(escape(draft.request))
    for satir in draft.kanit:
        console.print(f"[{theme.DIM}]- {escape(satir)}[/{theme.DIM}]")
    ozet = draft.olcut.kind.value if draft.olcut else "yok"
    console.print(f"ölçüt: {ozet} ({escape(draft.olcut_notu)})")


@eval_app.command("kabul")
def draft_accept(
    draft_id: Annotated[str, typer.Argument(help="`fusion eval taslaklar` kimliği")],
    suite: Annotated[
        str, typer.Option("--kume", help="Eklenecek kullanıcı kümesi.")
    ] = DEFAULT_SUITE,
    command: Annotated[str, typer.Option("--komut", help="Ölçüt: bu komut 0 dönmeli.")] = "",
    keyword: Annotated[
        str, typer.Option("--anahtar", help="Ölçüt: cevapta bu metin geçmeli.")
    ] = "",
    file: Annotated[str, typer.Option("--dosya", help="Ölçüt: bu dosya değişmeli.")] = "",
) -> None:
    """Taslağı onayla: görev kullanıcı kümesine eklenir, taslak kaldırılır."""
    _require_dev_tools()
    from evals.dongu_kaydi import OLAY_TASLAK_KABUL, kayit_ekle
    from evals.kume import SETUP_UYARISI, kume_dosyasi, olcut_olustur, taslagi_kabul_et
    from evals.taslak_deposu import TaslakDeposu

    paths = loop_paths()
    try:
        criterion = olcut_olustur(
            komut=command or None, anahtar=keyword or None, dosya=file or None
        )
        target = kume_dosyasi(suite, paths.suites)
        task = taslagi_kabul_et(TaslakDeposu(paths.drafts), draft_id, target, olcut=criterion)
    except EvalError as error:
        raise _fail(str(error)) from error
    kayit_ekle(
        paths.log,
        OLAY_TASLAK_KABUL,
        {"taslak": task.id, "kume": suite, "olcut": task.criterion.kind.value},
        simdi=SystemClock().now(),
    )
    console.print(f"Eklendi: {escape(task.id)} → {escape(str(target))}")
    console.print(f"[{theme.WARN}]{escape(SETUP_UYARISI)}[/{theme.WARN}]")


@eval_app.command("sil")
def draft_delete(
    draft_id: Annotated[str, typer.Argument(help="`fusion eval taslaklar` kimliği")],
) -> None:
    """Taslağı at; aynı hata günlükte durdukça bir daha önerilmez."""
    _require_dev_tools()
    from evals.dongu_kaydi import OLAY_TASLAK_SILINDI, kayit_ekle
    from evals.taslak_deposu import TaslakDeposu

    paths = loop_paths()
    try:
        TaslakDeposu(paths.drafts).kaldir(draft_id, reddet=True)
    except EvalError as error:
        raise _fail(str(error)) from error
    kayit_ekle(paths.log, OLAY_TASLAK_SILINDI, {"taslak": draft_id}, simdi=SystemClock().now())
    console.print(f"Silindi: {escape(draft_id)}")


# --------------------------------------------------------------------------- #
# fusion prompt-opt
# --------------------------------------------------------------------------- #


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
    _require_dev_tools()
    import asyncio

    from evals.kume import kume_coz
    from evals.loader import load_tasks
    from evals.runner import EvaluationUnavailableError, RateLimitedError
    from prompt_opt.campaign import RoundSetup, check_heldout
    from prompt_opt.targets import get_target

    paths = loop_paths()
    try:
        target = get_target(prompt)
        opt_tasks = load_tasks(_suite_file(suite, paths, kume_coz))
        held_tasks = load_tasks(_suite_file(heldout, paths, kume_coz))
        # Model çağrısı ya da sağlayıcı kurulumundan ÖNCE: aşırı uyum burada kesilir.
        check_heldout(opt_tasks, held_tasks, min_tasks=min_tasks)
        setup = RoundSetup(
            prompt=prompt,
            base_text=target.read(),
            suite=suite,
            heldout_suite=heldout,
            opt_tasks=opt_tasks,
            heldout_tasks=held_tasks,
            log_path=paths.log,
            now=SystemClock().now,
            timestamp=_iso,
            variant_count=variants,
            min_tasks=min_tasks,
        )
        result = asyncio.run(with_web_cleanup(_run_round(setup, paths, repeat=repeat)))
    except (RateLimitedError, EvaluationUnavailableError) as error:
        # Kota/erişim: agent'ın yeteneği ölçülmedi; "başarısız ölçüm" diye kaydedilmez.
        error_console.print(f"[{theme.WARN}]ÖLÇÜM DURDURULDU: {escape(str(error))}[/{theme.WARN}]")
        raise typer.Exit(EXIT_MEASUREMENT_STOPPED) from error
    except (EvalError, ValueError) as error:
        raise _fail(str(error)) from error
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
    _require_dev_tools()
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
        raise _fail(str(error)) from error
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
    _require_dev_tools()
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
        raise _fail(str(error)) from error
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
    _require_dev_tools()
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
        raise _fail(str(error)) from error
    console.print(f"Geri alındı: {change.prompt} sürüm {change.version} olarak yayımlandı.")
