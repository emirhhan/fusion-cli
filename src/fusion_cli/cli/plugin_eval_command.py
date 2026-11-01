"""`fusion plugin eval [hedef]` (Claude Code 2.1.287 `claude plugin eval`, #380).

Her vaka için `runs` kez (varsayılan 3, `--runs`) ayrı bir `fusion agent` alt süreci, geçici
çalışma klasöründe ve vakanın `allowed_tools`/`max_turns`/`timeout_seconds` sınırlarıyla koşar.
Eklenti çözüldüyse varsayılan `--ablation with-without`: eklentili kol `--plugin-dir` ile (kurulu
hedefte kurulu kopya), eklentisiz kol eklenti dışlanarak koşar ve puan farkı raporlanır.
`llm`/`baseline` değerlendiricileri yargıç alt süreciyle puanlanır (`SCORE: <0..1>`).
Sonuç `<eklenti>/<eval>/results/<zaman>/aggregate-result.json`'a yazılır (`--output-dir`);
`--json [yol]` tam sonucu basar ya da yazar; herhangi bir vaka `--threshold`'un (varsayılan 1.0)
altındaysa çıkış 1. Güvenilmeyen eklenti klasöründe ilk koşu onay ister (`--trust-plugin` CI
için). Claude'un claude.ai'de rapor yayımlaması Fusion'da yoktur (`--publish-report` hata,
`--no-publish` etkisiz); MCP sahte sunucu kaydı (`--mocks record`) yoktur.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import typer

from ..config.plugin_store import load_state, plugin_folder, plugins_dir
from ..core.plugins import PluginError
from ..tools.plugin_eval import (
    EvalCase,
    Judge,
    RunTrace,
    eval_dir,
    load_cases,
    parse_score,
    score_run,
)
from .plugin_commands import app

EXCLUDE_ENV = "FUSION_EVAL_EXCLUDE_PLUGINS"
TRUST_FILE = "eval-trusted.json"
ERR_PUBLISH = "Rapor yayımlama claude.ai hesabı gerektirir; Fusion'da yok (--report <yol> kullan)."
ERR_NO_CASES = "Eval vakası bulunamadı: {path}"
ERR_TARGET = "Eval hedefi çözülemedi: {target}"
ERR_UNTRUSTED = (
    "Bu eklenti klasörüne eval için henüz güvenilmedi ({path}). Eklentinin kodunu ve eval "
    "paketini kendin çalıştırırdın diyorsan --trust-plugin ver."
)
CONFIRM_TRUST = (
    "Eval eklentinin kodunu senin kullanıcınla çalıştırır. Bu eklentiye güveniyor musun?"
)


@dataclass(frozen=True, slots=True)
class Target:
    root: Path
    name: str
    installed: bool


@dataclass(frozen=True, slots=True)
class RunSpec:
    case: EvalCase
    arm: str
    target: Target | None
    workdir: Path


Runner = Callable[[RunSpec], RunTrace]


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


def _fusion() -> list[str]:
    exe = shutil.which("fusion")
    return [exe] if exe else [sys.executable, "-c", "from fusion_cli.cli.app import main; main()"]


def _command(spec: RunSpec) -> list[str]:
    case = spec.case
    args = _fusion()
    if spec.arm == "with" and spec.target is not None and not spec.target.installed:
        args += ["--plugin-dir", str(spec.target.root)]
    args += ["agent", case.prompt, "--output-format", "stream-json", "--no-memory"]
    args += ["--max-turns", str(case.max_turns)]
    if case.allowed_tools:
        args += ["--allowed-tools", ",".join(case.allowed_tools)]
    if case.append_system_prompt:
        args += ["--append-system-prompt", case.append_system_prompt]
    return args


def run_agent(spec: RunSpec) -> RunTrace:
    """Bir koşuyu alt süreçte yürüt ve olay satırlarından izi çıkar."""
    env = {**os.environ, **spec.case.env}
    if spec.arm == "without" and spec.target is not None:
        env[EXCLUDE_ENV] = spec.target.name
    try:
        done = subprocess.run(
            _command(spec),
            cwd=spec.workdir,
            env=env,
            capture_output=True,
            text=True,
            timeout=spec.case.timeout_seconds,
            stdin=subprocess.DEVNULL,
        )
        output = done.stdout
    except subprocess.TimeoutExpired as error:
        output = error.stdout if isinstance(error.stdout, str) else ""
    return parse_trace(output, spec.workdir)


def parse_trace(output: str, workdir: Path) -> RunTrace:
    tools: list[tuple[str, dict[str, object]]] = []
    last = ""
    for line in output.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("event") == "ToolExecuted":
            raw = event.get("args")
            args: dict[str, object] = dict(raw) if isinstance(raw, dict) else {}
            tools.append((str(event.get("name")), args))
        elif event.get("event") == "TurnAnswered":
            last = str(event.get("text") or "")
        elif event.get("type") == "result" and not last:
            last = str(event.get("sonuc") or "")
    return RunTrace(last, tuple(tools), workdir, output)


def judge_subprocess(prompt: str) -> float:
    try:
        done = subprocess.run(
            [
                *_fusion(),
                "agent",
                prompt,
                "--output-format",
                "json",
                "--no-memory",
                "--max-turns",
                "1",
            ],
            capture_output=True,
            text=True,
            timeout=300,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        return 0.0
    text = done.stdout.strip().splitlines()[-1] if done.stdout.strip() else ""
    with contextlib.suppress(ValueError, AttributeError):
        text = str(json.loads(text).get("sonuc") or "")
    return parse_score(text)


def run_suite(
    cases: tuple[EvalCase, ...],
    target: Target | None,
    *,
    runner: Runner,
    judge: Judge,
    runs: int = 0,
    ablation: bool = True,
) -> dict[str, object]:
    arms = ("with", "without") if ablation and target is not None else ("with",)
    rows: list[dict[str, object]] = []
    for case in cases:
        row: dict[str, object] = {"name": case.name}
        means: dict[str, float] = {}
        for arm in arms:
            results: list[dict[str, object]] = []
            for _ in range(runs or case.runs):
                with tempfile.TemporaryDirectory(prefix="fusion-eval-") as folder:
                    trace = runner(RunSpec(case, arm, target, Path(folder)))
                    results.append(score_run(case, trace, judge, arm=arm, ablation=len(arms) == 2))
            means[arm] = sum(_number(r.get("score")) for r in results) / len(results)
            row[arm] = {"score": means[arm], "runs": results}
        if len(arms) == 2:
            row["delta"] = means["with"] - means["without"]
        rows.append(row)
    return {
        "plugin": target.name if target else "",
        "ablation": "with-without" if len(arms) == 2 else "none",
        "cases": rows,
    }


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


@app.command("eval")
def eval_command(
    target: str = typer.Argument("", help="Eklenti yolu, adı ya da ad@pazar (varsayılan: .)"),
    eval_dir_name: str = typer.Option(
        "", "--eval-dir", help="Vakaların klasörü (varsayılan evals/)."
    ),
    case: str = typer.Option("", "--case", help="Vaka adı glob süzgeci."),
    tag: list[str] = typer.Option([], "--tag", help="Etiket süzgeci (tekrarlanabilir)."),  # noqa: B008
    runs: int = typer.Option(0, "--runs", help="Vaka başına koşu (varsayılan case.runs ?? 3)."),
    ablation: str = typer.Option("", "--ablation", help="none | with-without"),
    threshold: float = typer.Option(1.0, "--threshold", help="Bu puanın altındaki vaka çıkış 1."),
    as_json: bool = typer.Option(False, "--json", help="Tam sonucu JSON olarak bas."),
    json_file: str = typer.Option("", "--json-file", help="Tam sonucu bu .json dosyasına yaz."),
    output_dir: str = typer.Option("", "--output-dir", help="aggregate-result.json klasörü."),
    trust_plugin: bool = typer.Option(False, "--trust-plugin", help="İlk koşu güven onayını geç."),
    publish_report: bool = typer.Option(
        False, "--publish-report", help="claude.ai'de yayımla (yok)."
    ),
    no_publish: bool = typer.Option(False, "--no-publish", help="Raporu yerel tut (zaten öyle)."),
) -> None:
    """Eklentinin eval vakalarını koştur ve puanla (Claude `plugin eval`)."""
    del no_publish
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
        _trusted(root, trust_plugin)
        with_without = ablation != "none" and resolved is not None
        result = run_suite(
            cases,
            resolved,
            runner=run_agent,
            judge=judge_subprocess,
            runs=runs,
            ablation=with_without,
        )
    except PluginError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error
    out = Path(output_dir) if output_dir else folder / "results" / time.strftime("%Y%m%dT%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    (out / "aggregate-result.json").write_text(text + "\n", "utf-8")
    if json_file:
        Path(json_file).write_text(text + "\n", "utf-8")
    if as_json:
        typer.echo(text)
    else:
        typer.echo(_summary(result))
    if any(score < threshold for score in with_scores(result)):
        raise typer.Exit(1)
