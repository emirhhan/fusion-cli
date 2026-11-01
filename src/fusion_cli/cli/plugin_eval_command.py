"""`fusion plugin eval [hedef]` (Claude Code 2.1.287 `claude plugin eval`, #380).

Her vaka için `runs` kez (varsayılan 3, `--runs`) ayrı bir `fusion agent` alt süreci, geçici
çalışma klasöründe ve vakanın `allowed_tools`/`max_turns`/`timeout_seconds` sınırlarıyla koşar
(`-j` ile eşzamanlı; koşu düzeni `tools/plugin_eval_run.py`). Eklenti çözüldüyse varsayılan
`--ablation with-without`: eklentili kol `--plugin-dir` ile (kurulu hedefte kurulu kopya),
eklentisiz kol eklenti dışlanarak koşar ve puan farkı raporlanır. `llm`/`baseline`
değerlendiricileri yargıç alt süreciyle puanlanır (`SCORE: <0..1>`, `--judge-model`). MCP
sunucuları `--mocks record` (varsayılan) ile `<eval>/mocks/`'taki sahtelerle değişir
(`tools/plugin_eval_mocks.py`). Sonuç `<eklenti>/<eval>/results/<zaman>/aggregate-result.json` ve
`report.html` (`--output-dir`, `--report`); `--json [yol]` tam sonucu basar ya da yazar; herhangi
bir vaka `--threshold`'un (varsayılan 1.0) altındaysa çıkış 1, `--max-cost-usd` aşılınca çıkış 2.
Güvenilmeyen eklenti klasöründe ilk koşu onay ister (`--trust-plugin` CI için). Claude'un raporu
claude.ai'de yayımlaması Fusion'da yoktur (`--publish-report` hata, `--no-publish` etkisiz).
`eval init` için bkz. `plugin_eval_init.py`.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import typer

from ..config.plugin_store import load_state, plugin_folder, plugins_dir
from ..core.plugins import PluginError
from ..tools import plugin_eval_run as run
from ..tools.plugin_eval import EvalCase, Judge, eval_dir, load_cases
from ..tools.plugin_eval_run import (
    EXCLUDE_ENV,
    EvalOptions,
    RunSpec,
    Target,
    parse_trace,
    run_agent,
)
from .plugin_commands import app

__all__ = ["EXCLUDE_ENV", "RunSpec", "Target", "parse_trace", "run_agent", "run_suite"]

TRUST_FILE = "eval-trusted.json"
ERR_PUBLISH = "Rapor yayımlama claude.ai hesabı gerektirir; Fusion'da yok (--report <yol> kullan)."
ERR_NO_CASES = "Eval vakası bulunamadı: {path}"
ERR_TARGET = "Eval hedefi çözülemedi: {target}"
ERR_CONCURRENCY = "--concurrency must be an integer from 1 to 8"
ERR_SCAFFOLD_BOTH = "--scaffold and --no-scaffold cannot be used together"
ERR_UNTRUSTED = (
    "Bu eklenti klasörüne eval için henüz güvenilmedi ({path}). Eklentinin kodunu ve eval "
    "paketini kendin çalıştırırdın diyorsan --trust-plugin ver."
)
CONFIRM_TRUST = (
    "Eval eklentinin kodunu senin kullanıcınla çalıştırır. Bu eklentiye güveniyor musun?"
)
NOTE_SCAFFOLD = (
    "Note: --scaffold runs each case's scaffold_script as you. Only use it on case files you "
    "(or your org) authored."
)
NOTE_COST = "Maliyet tavanı (--max-cost-usd {ceiling}) aşıldı; kısmi sonuç yazıldı."


def resolve_target(target: str) -> Target | None:
    path = Path(target or ".").expanduser()
    if path.is_dir():
        root = path.resolve()
        manifest = root / ".claude-plugin" / "plugin.json"
        if manifest.is_file() or (root / "SKILL.md").is_file():
            try:
                name = str(json.loads(manifest.read_text("utf-8")).get("name") or root.name)
            except (OSError, ValueError):
                name = root.name
            return Target(root, name, installed=False)
        return None
    from ..tools.plugin_toggle import find_record

    try:
        record = find_record(load_state(), target)
    except PluginError:
        return None
    return Target(plugin_folder(record), record.name, installed=True)


def judge_subprocess(prompt: str, model: str = "") -> float:
    return run.judge_command(prompt, model)[0]


def run_suite(
    cases: tuple[EvalCase, ...],
    target: Target | None,
    *,
    runner: run.Runner,
    judge: Judge,
    runs: int = 0,
    ablation: bool = True,
    options: EvalOptions | None = None,
) -> dict[str, object]:
    return run.run_suite(
        cases, target, runner=runner, judge=judge, runs=runs, ablation=ablation, options=options
    )


def _number(value: object) -> float:
    return float(value) if isinstance(value, int | float) else 0.0


def with_scores(result: dict[str, object]) -> list[float]:
    """Her vakanın eklentili kol puanı (eşik denetimi)."""
    cases = result.get("cases")
    found: list[float] = []
    for row in cases if isinstance(cases, list) else []:
        arm = row.get("with") if isinstance(row, dict) else None
        found.append(_number(arm.get("score")) if isinstance(arm, dict) else 0.0)
    return found


def _trusted(root: Path, trust: bool) -> None:
    path = plugins_dir() / TRUST_FILE
    try:
        known = set(json.loads(path.read_text("utf-8")))
    except (OSError, ValueError, TypeError):
        known = set()
    if str(root) in known:
        return
    if not trust and not (sys.stdin.isatty() and typer.confirm(CONFIRM_TRUST, default=False)):
        raise PluginError(ERR_UNTRUSTED.format(path=root))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(known | {str(root)})), "utf-8")


def _summary(result: dict[str, object]) -> str:
    lines = []
    for row in result["cases"]:  # type: ignore[attr-defined]
        text = f"{row['name']}  with {row['with']['score']:.2f}"
        if "without" in row:
            text += f"  without {row['without']['score']:.2f}  Δ {row['delta']:+.2f}"
        lines.append(text)
    return "\n".join(lines)


def _declared_servers(target: Target | None) -> tuple[str, ...]:
    if target is None:
        return ()
    from ..config.plugin_eval_env import server_key
    from ..config.plugin_layout import mcp_servers
    from ..config.plugin_scan import scan_plugin

    try:
        return tuple(server_key(s.name) for s in mcp_servers(scan_plugin(target.root, target.name)))
    except (PluginError, OSError):
        return ()


def _options(
    folder: Path, resolved: Target | None, flags: dict[str, object]
) -> tuple[EvalOptions, tuple[str, ...]]:
    from ..tools.plugin_eval_mocks import load_mocks, mock_env, mock_notes

    concurrency = int(flags["concurrency"])  # type: ignore[call-overload]
    if not 1 <= concurrency <= run.MAX_CONCURRENCY:
        raise PluginError(ERR_CONCURRENCY)
    if flags["scaffold"] and flags["no_scaffold"]:
        raise PluginError(ERR_SCAFFOLD_BOTH)
    mode = str(flags["mocks"] or "record")
    allow_real = bool(flags["allow_real_servers"])
    mocks = load_mocks(folder) if mode != "off" else {}
    notes = mock_notes(_declared_servers(resolved), mocks, mode=mode, allow_real=allow_real)
    ceiling = flags["max_cost_usd"]
    options = EvalOptions(
        concurrency=concurrency,
        max_cost_usd=float(ceiling) if isinstance(ceiling, int | float) else None,
        allow_tools=tuple(str(t) for t in flags["allow_tools"]),  # type: ignore[attr-defined]
        model=str(flags["model"] or ""),
        judge_model=str(flags["judge_model"] or ""),
        scaffold=bool(flags["scaffold"]),
        keep_temp=bool(flags["keep_temp"]),
        mock_env=mock_env(mode, mocks, allow_real=allow_real),
        plugin_grants=run.skill_grants(resolved.root) if resolved else (),
    )
    if options.scaffold:
        notes = (NOTE_SCAFFOLD, *notes)
    return options, notes


def _scaffold_notes(
    cases: tuple[EvalCase, ...], options: EvalOptions, explicit_off: bool
) -> list[str]:
    if options.scaffold or explicit_off:
        return []
    return [run.NOTE_SCAFFOLD_SKIPPED.format(case=c.name) for c in cases if c.scaffold_script]


def _write_outputs(
    result: dict[str, object],
    cases: tuple[EvalCase, ...],
    out: Path,
    *,
    json_file: str,
    report: str,
    threshold: float,
) -> str:
    from ..tools.plugin_eval_report import render_report, write_report

    out.mkdir(parents=True, exist_ok=True)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    (out / "aggregate-result.json").write_text(text + "\n", "utf-8")
    if json_file:
        Path(json_file).write_text(text + "\n", "utf-8")
    html = render_report(result, cases, threshold=threshold)
    write_report(Path(report) if report else out / "report.html", html)
    return text


def _init(name: str, eval_dir_name: str, bare: bool, interactive: bool) -> None:
    from .plugin_eval_init import run_init

    try:
        text = run_init(
            Path.cwd(), name, eval_dir_name=eval_dir_name, bare=bare, interactive=interactive
        )
    except PluginError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error
    if text:
        typer.echo(text)


def _json_target(as_json: bool, target: str, name: str, json_file: str) -> tuple[str, str]:
    """Claude `--json [yol]`: `--json`'dan sonra gelen `.json` adı hedef değil çıktı dosyasıdır."""
    if as_json and not json_file and target.endswith(".json") and not Path(target).is_dir():
        return name, target
    return target, json_file


@app.command("eval")
def eval_command(
    target: str = typer.Argument("", help="Eklenti yolu, adı ya da ad@pazar (varsayılan: .)"),
    name: str = typer.Argument("", help="`eval init [ad]` vaka adı."),
    eval_dir_name: str = typer.Option(
        "", "--eval-dir", help="Vakaların klasörü (varsayılan evals/)."
    ),
    case: str = typer.Option("", "--case", help="Vaka adı glob süzgeci."),
    tag: list[str] = typer.Option([], "--tag", help="Etiket süzgeci (tekrarlanabilir)."),  # noqa: B008
    runs: int = typer.Option(0, "--runs", help="Vaka başına koşu (varsayılan case.runs ?? 3)."),
    ablation: str = typer.Option("", "--ablation", help="none | with-without"),
    threshold: float = typer.Option(1.0, "--threshold", help="Bu puanın altındaki vaka çıkış 1."),
    as_json: bool = typer.Option(
        False, "--json", help="Tam sonucu JSON bas (--json <yol>.json yazar)."
    ),
    json_file: str = typer.Option("", "--json-file", help="Tam sonucu bu .json dosyasına yaz."),
    output_dir: str = typer.Option("", "--output-dir", help="aggregate-result.json klasörü."),
    report: str = typer.Option("", "--report", help="HTML raporunu bu yola yaz."),
    trust_plugin: bool = typer.Option(False, "--trust-plugin", help="İlk koşu güven onayını geç."),
    concurrency: int = typer.Option(
        1, "--concurrency", "-j", help="Aynı anda en çok n koşu (1-8)."
    ),
    max_cost_usd: float | None = typer.Option(
        None, "--max-cost-usd", help="Maliyet tavanı; aşılınca kısmi sonuç ve çıkış 2."
    ),
    allow_tools: list[str] = typer.Option(  # noqa: B008
        [], "--allow-tools", help="Kapılı araç izni (Bash, Write, Edit, WebFetch, mcp__*)."
    ),
    model: str = typer.Option("", "--model", help="Tüm vakaların modeli."),
    judge_model: str = typer.Option("", "--judge-model", help="llm değerlendirici modeli."),
    scaffold: bool = typer.Option(
        False, "--scaffold", help="Vakanın scaffold_script'ini çalıştır."
    ),
    no_scaffold: bool = typer.Option(False, "--no-scaffold", help="scaffold_script'i açıkça atla."),
    keep_temp: bool = typer.Option(False, "--keep-temp", help="Çalışma klasörlerini silme."),
    mocks: str = typer.Option("record", "--mocks", help="MCP sahte sunucuları: record | off."),
    allow_real_servers: bool = typer.Option(
        False,
        "--allow-real-servers",
        help="Sahtesi olmayan gerçek eklenti MCP sunucularını başlat.",
    ),
    bare: bool = typer.Option(False, "--bare", help="eval init: boş şablon yaz."),
    interactive: bool = typer.Option(False, "--interactive", "-i", help="eval init: görüşme."),
    publish_report: bool = typer.Option(
        False, "--publish-report", help="claude.ai'de yayımla (yok)."
    ),
    no_publish: bool = typer.Option(False, "--no-publish", help="Raporu yerel tut (zaten öyle)."),
) -> None:
    """Eklentinin eval vakalarını koştur ve puanla (Claude `plugin eval`)."""
    del no_publish
    if target == "init":
        _init(name, eval_dir_name, bare, interactive)
        return
    target, json_file = _json_target(as_json, target, name, json_file)
    flags: dict[str, object] = {
        "concurrency": concurrency,
        "max_cost_usd": max_cost_usd,
        "allow_tools": allow_tools,
        "model": model,
        "judge_model": judge_model,
        "scaffold": scaffold,
        "no_scaffold": no_scaffold,
        "keep_temp": keep_temp,
        "mocks": mocks,
        "allow_real_servers": allow_real_servers,
    }
    try:
        if publish_report:
            raise PluginError(ERR_PUBLISH)
        resolved = resolve_target(target)
        if resolved is None and target:
            raise PluginError(ERR_TARGET.format(target=target))
        root = resolved.root if resolved else Path.cwd()
        folder = eval_dir(root, eval_dir_name)
        cases = load_cases(folder, case_glob=case, tags=tag)
        if not cases:
            raise PluginError(ERR_NO_CASES.format(path=folder))
        options, notes = _options(folder, resolved, flags)
        _trusted(root, trust_plugin)
        warnings = run.tool_warnings(cases, options)
        for note in (*notes, *_scaffold_notes(cases, options, no_scaffold), *warnings):
            typer.echo(note, err=True)
        chosen = options.judge_model
        judge = judge_subprocess if not chosen else (lambda p: judge_subprocess(p, chosen))
        result = run_suite(
            cases,
            resolved,
            runner=run_agent,
            judge=judge,
            runs=runs,
            ablation=ablation != "none" and resolved is not None,
            options=options,
        )
    except PluginError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error
    out = Path(output_dir) if output_dir else folder / "results" / time.strftime("%Y%m%dT%H%M%S")
    text = _write_outputs(
        result, cases, out, json_file=json_file, report=report, threshold=threshold
    )
    typer.echo(text if as_json and not json_file else _summary(result))
    if result.get("aborted"):
        typer.echo(NOTE_COST.format(ceiling=max_cost_usd), err=True)
        raise typer.Exit(2)
    if any(score < threshold for score in with_scores(result)):
        raise typer.Exit(1)
