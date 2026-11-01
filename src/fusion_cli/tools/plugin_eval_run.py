"""`plugin eval` koşu düzeni: alt süreç komutu, araç izni, eşzamanlılık, maliyet tavanı (#380).

Claude Code 2.1.287 `claude plugin eval` seçenekleri: `-j/--concurrency <1-8>` (sonuç sırası vaka
sırasıdır), `--max-cost-usd` (tavan her koşu başlamadan denetlenir; aşılınca kalan koşular
başlamaz, kısmi sonuç ve çıkış 2; tavanı aşan koşunun ücretli `llm`/`baseline` değerlendiricileri
atlanır), `--allow-tools` (kapılı araçlar — Bash, Write, Edit, NotebookEdit, WebFetch — yalnız
operatör izniyle ya da eklentili kolda eklenti becerisinin `allowed-tools` ön maddesiyle açılır;
`Tool(desen:*)` biçiminde desen Fusion'da araç ailesinin tamamına uygulanır), `--model` (tüm
vakalar; vaka `model:` alanından önce gelir), `--judge-model` (yargıç; varsayılan yapılandırma),
`--scaffold` (vakanın `scaffold_script`'ini çalışma klasöründe bash ile çalıştırır; varsayılan
kapalı), `--keep-temp` (çalışma klasörlerini silmez).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .plugin_eval import EvalCase, Judge, RunTrace, score_run
from .plugin_eval_mocks import LOG_ENV, read_log

GATED = ("Bash", "Write", "Edit", "NotebookEdit", "WebFetch")
EXCLUDE_ENV = "FUSION_EVAL_EXCLUDE_PLUGINS"
MAX_CONCURRENCY = 8
NOTE_SCAFFOLD_SKIPPED = (
    'Case "{case}": its scaffold_script is not run without --scaffold (author-supplied bash that '
    "runs as you - pass it only for suites you trust); the case runs against an unstaged workspace"
)


@dataclass(frozen=True, slots=True)
class EvalOptions:
    concurrency: int = 1
    max_cost_usd: float | None = None
    allow_tools: tuple[str, ...] = ()
    model: str = ""
    judge_model: str = ""
    scaffold: bool = False
    keep_temp: bool = False
    mock_env: Mapping[str, str] = field(default_factory=dict)
    plugin_grants: tuple[str, ...] = ()


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
    options: EvalOptions = field(default_factory=EvalOptions)
    log: Path | None = None


Runner = Callable[[RunSpec], RunTrace]


def fusion_command() -> list[str]:
    exe = shutil.which("fusion")
    return [exe] if exe else [sys.executable, "-c", "from fusion_cli.cli.app import main; main()"]


def _base(tool: str) -> str:
    return tool.split("(", 1)[0].strip()


def skill_grants(root: Path) -> tuple[str, ...]:
    """Eklenti becerilerinin `allowed-tools` ön maddesindeki araç adları (eklentili kol izni)."""
    found: set[str] = set()
    for path in sorted(root.rglob("SKILL.md")):
        text = path.read_text("utf-8", errors="replace")
        if not text.startswith("---"):
            continue
        head = text[3:].partition("\n---")[0]
        try:
            data = yaml.safe_load(head) or {}
        except yaml.YAMLError:
            continue
        raw = data.get("allowed-tools") if isinstance(data, dict) else None
        items = raw.split(",") if isinstance(raw, str) else raw if isinstance(raw, list) else []
        found |= {_base(str(item)) for item in items if str(item).strip()}
    return tuple(sorted(found))


def denied_tools(spec: RunSpec) -> tuple[str, ...]:
    granted = {_base(t) for t in spec.options.allow_tools}
    if spec.arm == "with":
        granted |= set(spec.options.plugin_grants)
    return tuple(tool for tool in GATED if tool not in granted)


_WRITERS = frozenset({"Write", "Edit", "Bash", "NotebookEdit"})
WARN_TOOLS = (
    "⚠ case {case} cannot pass with the granted tools: a file grader needs Write, Edit or Bash "
    "(allowed_tools, the skill's allowed-tools or --allow-tools)"
)


def _needs_file(case: EvalCase) -> bool:
    for grader in case.graders:
        if grader.type == "file_exists" and grader.fields.get("exists") is not False:
            return True
        if grader.type == "regex" and grader.fields.get("target") == "files":
            return str(grader.fields.get("match") or "contains") == "contains"
    return False


def tool_warnings(cases: tuple[EvalCase, ...], options: EvalOptions) -> tuple[str, ...]:
    """Dosya değerlendiricisi olup dosya yazabilecek araç izni olmayan vakalar (Claude ⚠)."""
    granted = {_base(t) for t in (*options.allow_tools, *options.plugin_grants)}
    return tuple(
        WARN_TOOLS.format(case=case.name)
        for case in cases
        if _needs_file(case)
        and not (_WRITERS & granted & ({_base(t) for t in case.allowed_tools} or _WRITERS))
    )


def child_command(spec: RunSpec) -> list[str]:
    case = spec.case
    args = fusion_command()
    if spec.arm == "with" and spec.target is not None and not spec.target.installed:
        args += ["--plugin-dir", str(spec.target.root)]
    args += ["agent", case.prompt, "--output-format", "stream-json", "--no-memory"]
    args += ["--max-turns", str(case.max_turns)]
    if case.allowed_tools:
        args += ["--allowed-tools", ",".join(case.allowed_tools)]
    denied = denied_tools(spec)
    if denied:
        args += ["--disallowed-tools", ",".join(denied)]
    if case.append_system_prompt:
        args += ["--append-system-prompt", case.append_system_prompt]
    return args


def child_env(spec: RunSpec) -> dict[str, str]:
    from ..config.plugin_eval_env import MODEL_ENV

    env = {**os.environ, **spec.case.env, **spec.options.mock_env}
    model = spec.options.model or spec.case.model
    if model:
        env[MODEL_ENV] = model
    if spec.log is not None:
        env[LOG_ENV] = str(spec.log)
    if spec.arm == "without" and spec.target is not None:
        env[EXCLUDE_ENV] = spec.target.name
    return env


def parse_trace(output: str, workdir: Path) -> RunTrace:
    tools: list[tuple[str, dict[str, object]]] = []
    last = ""
    cost = 0.0
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
        elif event.get("type") == "result":
            last = last or str(event.get("sonuc") or "")
            cost = max(cost, result_cost(event))
    return RunTrace(last, tuple(tools), workdir, output, cost)


def result_cost(event: Mapping[str, object]) -> float:
    usage = event.get("kullanim")
    value = usage.get("maliyet_usd") if isinstance(usage, dict) else None
    return float(value) if isinstance(value, int | float) else 0.0


def run_agent(spec: RunSpec) -> RunTrace:
    """Bir koşuyu alt süreçte yürüt ve olay satırlarından izi çıkar."""
    try:
        done = subprocess.run(
            child_command(spec),
            cwd=spec.workdir,
            env=child_env(spec),
            capture_output=True,
            text=True,
            timeout=spec.case.timeout_seconds,
            stdin=subprocess.DEVNULL,
            check=False,
        )
        output = done.stdout
    except subprocess.TimeoutExpired as error:
        output = error.stdout if isinstance(error.stdout, str) else ""
    return parse_trace(output, spec.workdir)


def judge_command(prompt: str, model: str = "") -> tuple[float, float]:
    """Yargıç alt süreci: (puan, maliyet)."""
    from ..config.plugin_eval_env import MODEL_ENV
    from .plugin_eval import parse_score

    env = {**os.environ, **({MODEL_ENV: model} if model else {})}
    argv = [*fusion_command(), "agent", prompt, "--output-format", "json", "--no-memory"]
    try:
        done = subprocess.run(
            [*argv, "--max-turns", "1"],
            capture_output=True,
            text=True,
            timeout=300,
            stdin=subprocess.DEVNULL,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return 0.0, 0.0
    last = done.stdout.strip().splitlines()[-1] if done.stdout.strip() else ""
    try:
        event = json.loads(last)
    except ValueError:
        return parse_score(last), 0.0
    if not isinstance(event, dict):
        return 0.0, 0.0
    return parse_score(str(event.get("sonuc") or "")), result_cost(event)


def scaffold(case: EvalCase, workdir: Path) -> None:
    script = case.scaffold_script
    path = case.folder / script
    argv = ["bash", str(path)] if path.is_file() else ["bash", "-c", script]
    subprocess.run(argv, cwd=workdir, check=False, timeout=case.timeout_seconds)


class _Budget:
    def __init__(self, ceiling: float | None) -> None:
        self.ceiling = ceiling
        self.spent = 0.0
        self.hit = False
        self._lock = threading.Lock()

    def may_start(self) -> bool:
        with self._lock:
            if self.ceiling is not None and self.spent >= self.ceiling:
                self.hit = True
            return not self.hit

    def add(self, cost: float) -> bool:
        """Maliyeti ekle; tavan aşıldıysa True."""
        with self._lock:
            self.spent += cost
            return self.ceiling is not None and self.spent >= self.ceiling


@dataclass(frozen=True, slots=True)
class _Job:
    case: EvalCase
    arm: str
    index: int


def _one(job: _Job, target: Target | None, ctx: _SuiteContext) -> dict[str, object] | None:
    if not ctx.budget.may_start():
        return None
    folder = Path(tempfile.mkdtemp(prefix="fusion-eval-"))
    log = Path(tempfile.mkdtemp(prefix="fusion-eval-log-")) / "mock-calls.jsonl"
    try:
        if job.case.scaffold_script and ctx.options.scaffold:
            scaffold(job.case, folder)
        spec = RunSpec(job.case, job.arm, target, folder, ctx.options, log)
        trace = ctx.runner(spec)
        breached = ctx.budget.add(trace.cost_usd)
        judge = ctx.judge if not breached else (lambda _p: 0.0)
        result = score_run(job.case, trace, judge, arm=job.arm, ablation=ctx.ablation)
        calls = read_log(log)
        aborts = [str(a) for row in calls for a in _items(row.get("abort"))]
        if aborts:
            result = {**result, "score": 0.0, "aborted": aborts}
        return {**result, "costUsd": trace.cost_usd, "mockCalls": calls, "paidSkipped": breached}
    finally:
        if not ctx.options.keep_temp:
            shutil.rmtree(folder, ignore_errors=True)
        shutil.rmtree(log.parent, ignore_errors=True)


@dataclass(frozen=True, slots=True)
class _SuiteContext:
    runner: Runner
    judge: Judge
    options: EvalOptions
    budget: _Budget
    ablation: bool


def _items(value: object) -> list[object]:
    return list(value) if isinstance(value, list) else []


def _number(value: object) -> float:
    return float(value) if isinstance(value, int | float) else 0.0


def run_suite(
    cases: tuple[EvalCase, ...],
    target: Target | None,
    *,
    runner: Runner,
    judge: Judge,
    runs: int = 0,
    ablation: bool = True,
    options: EvalOptions | None = None,
) -> dict[str, object]:
    opts = options or EvalOptions()
    arms = ("with", "without") if ablation and target is not None else ("with",)
    budget = _Budget(opts.max_cost_usd)
    ctx = _SuiteContext(runner, judge, opts, budget, len(arms) == 2)
    jobs = [_Job(case, arm, i) for case in cases for arm in arms for i in range(runs or case.runs)]
    workers = max(1, min(MAX_CONCURRENCY, opts.concurrency))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        done = list(pool.map(lambda job: _one(job, target, ctx), jobs))
    rows = _rows(cases, arms, list(zip(jobs, done, strict=True)))
    return {
        "plugin": target.name if target else "",
        "ablation": "with-without" if len(arms) == 2 else "none",
        "costUsd": round(budget.spent, 6),
        "suite": {"plugins": [{"name": target.name, "root": str(target.root)}] if target else []},
        "aborted": budget.hit,
        "cases": rows,
    }


def _rows(
    cases: tuple[EvalCase, ...],
    arms: tuple[str, ...],
    done: list[tuple[_Job, dict[str, object] | None]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for case in cases:
        row: dict[str, object] = {"name": case.name}
        means: dict[str, float] = {}
        for arm in arms:
            results = [r for job, r in done if job.case is case and job.arm == arm and r]
            means[arm] = (
                sum(_number(r.get("score")) for r in results) / len(results) if results else 0.0
            )
            row[arm] = {"score": means[arm], "runs": results}
        if len(arms) == 2:
            row["delta"] = means["with"] - means["without"]
        rows.append(row)
    return rows
