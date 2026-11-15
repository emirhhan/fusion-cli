"""`plugin eval` vaka biçimi ve puanlama (Claude Code 2.1.287 `claude plugin eval`, #380).

Vaka: `<eval klasörü>/**/case.yaml` ya da `prompt.md` + `graders/*.md`. Eval klasörü `--eval-dir`,
yoksa manifestin `experimental.evals` değeri, yoksa `evals/`. `prompt.md` gövdesi kullanıcı
istemidir; ön madde `schema_version, name, description, tags, plugins, runs, expected_outcome`
(üst) ve `model, max_turns, timeout_seconds, allowed_tools, append_system_prompt, env`
(execution) alır. Her `graders/<ad>.md` bir değerlendiricidir: ön maddede `type` (regex |
tool_order | tool_used | file_exists | llm | baseline), `weight`, `arm`; gövde `llm`/`baseline`
ölçütü, `regex` deseni. `init` şablonundaki "TODO: describe…" satırı kalmışsa vaka hatadır.

Puan: koşu puanı değerlendiricilerin ağırlıklı ortalamasıdır (0-1), vaka puanı koşuların
ortalaması. `with-without` ablasyonunda `arm: with-only` ve `tool_used: Skill` değerlendiricileri
puana girmez, "eklenti tetiklendi" göstergesidir; eklentisiz kolda atlanır.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path

import yaml

from ..core.plugins import PluginError

PROMPT_TODO = "TODO: describe what the agent should do"
GRADER_TODO = "TODO: describe what a successful response looks like"
GRADER_TYPES = ("regex", "tool_order", "tool_used", "file_exists", "llm", "baseline")
_TOP = {"schema_version", "name", "description", "tags", "plugins", "runs", "expected_outcome"}
_EXECUTION = {
    "model",
    "max_turns",
    "timeout_seconds",
    "allowed_tools",
    "artifact_publish",
    "growthbook_overrides",
    "append_system_prompt",
    "env",
    "scaffold_script",
}
ERR_KEY = '{path}: unknown frontmatter key "{key}" (expected one of: {keys})'
ERR_TYPE = (
    '{path}: frontmatter must include "type:" (regex | tool_order | tool_used | file_exists | '
    "llm | baseline)"
)
ERR_PROMPT = "{case}: execution.prompt is required (a prompt.md body, or execution.prompt)"
ERR_TEMPLATE = '{case}: the prompt is still the blank `init` template — replace the "{todo}" line'
ERR_GRADER_TEMPLATE = '{case}: grader "{name}" is still the blank `init` template'
ERR_NO_GRADER = "{case}: en az bir değerlendirici gerekli"
ERR_YAML = "{path}: geçersiz YAML: {error}"


@dataclass(frozen=True, slots=True)
class Grader:
    name: str
    type: str
    weight: float = 1.0
    arm: str = ""
    fields: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EvalCase:
    name: str
    folder: Path
    prompt: str
    graders: tuple[Grader, ...]
    tags: tuple[str, ...] = ()
    runs: int = 3
    max_turns: int = 10
    timeout_seconds: int = 300
    model: str = ""
    allowed_tools: tuple[str, ...] = ()
    append_system_prompt: str = ""
    env: Mapping[str, str] = field(default_factory=dict)
    scaffold_script: str = ""


@dataclass(frozen=True, slots=True)
class RunTrace:
    """Bir ajan koşusunun izi: son mesaj, araç çağrıları (Fusion adı, argüman), çalışma klasörü."""

    last_message: str
    tools: tuple[tuple[str, Mapping[str, object]], ...]
    workdir: Path
    trace_text: str = ""
    cost_usd: float = 0.0


Judge = Callable[[str], float]


def _split(text: str, path: Path) -> tuple[dict[str, object], str]:
    if not text.startswith("---"):
        return {}, text
    _, _, rest = text.partition("---")
    head, sep, body = rest.partition("\n---")
    if not sep:
        return {}, text
    try:
        loaded = yaml.safe_load(head) or {}
    except yaml.YAMLError as error:
        raise PluginError(ERR_YAML.format(path=path, error=error)) from error
    return (dict(loaded) if isinstance(loaded, dict) else {}), body.lstrip("\n")


def eval_dir(plugin_root: Path, override: str = "") -> Path:
    if override:
        return plugin_root / override
    try:
        manifest = json.loads((plugin_root / ".claude-plugin" / "plugin.json").read_text("utf-8"))
    except (OSError, ValueError):
        manifest = {}
    experimental = manifest.get("experimental") if isinstance(manifest, dict) else None
    name = experimental.get("evals") if isinstance(experimental, dict) else None
    return plugin_root / (name if isinstance(name, str) and name else "evals")


def _grader(name: str, raw: Mapping[str, object], body: str, path: Path) -> Grader:
    kind = raw.get("type")
    if kind not in GRADER_TYPES:
        raise PluginError(ERR_TYPE.format(path=path))
    fields = {k: v for k, v in raw.items() if k not in {"type", "weight", "arm", "name"}}
    if kind in {"llm", "baseline"} and body.strip() and "criteria" not in fields:
        fields["criteria"] = body.strip()
    if kind == "regex" and body.strip() and "pattern" not in fields:
        fields["pattern"] = body.strip()
    weight = raw.get("weight", 1)
    arm = raw.get("arm")
    return Grader(
        str(raw.get("name") or name),
        str(kind),
        float(weight) if isinstance(weight, int | float) else 1.0,
        arm if isinstance(arm, str) else "",
        fields,
    )


def _from_markdown(folder: Path) -> dict[str, object] | None:
    prompt_path = folder / "prompt.md"
    graders_dir = folder / "graders"
    if not prompt_path.is_file() and not graders_dir.is_dir():
        return None
    data: dict[str, object] = {"graders": []}
    if prompt_path.is_file():
        head, body = _split(prompt_path.read_text("utf-8"), prompt_path)
        for key, value in head.items():
            if key not in _TOP | _EXECUTION:
                keys = ", ".join(sorted(_TOP | _EXECUTION))
                raise PluginError(ERR_KEY.format(path=prompt_path.name, key=key, keys=keys))
            data[key] = value
        data["prompt"] = body.strip()
    graders: list[Grader] = []
    for path in sorted(graders_dir.glob("*.md")) if graders_dir.is_dir() else ():
        head, body = _split(path.read_text("utf-8"), path)
        if head:
            graders.append(_grader(path.stem, head, body, path))
    data["graders"] = graders
    return data


def _from_yaml(folder: Path) -> dict[str, object] | None:
    path = folder / "case.yaml"
    if not path.is_file():
        return None
    try:
        raw = yaml.safe_load(path.read_text("utf-8")) or {}
    except yaml.YAMLError as error:
        raise PluginError(ERR_YAML.format(path=path, error=error)) from error
    if not isinstance(raw, dict):
        raise PluginError(f"{path}: case.yaml must be a YAML object")
    execution = _dict(raw, "execution")
    graders = [
        _grader(str(g.get("name") or f"g{i}"), g, "", path)
        for i, g in enumerate(_list(raw, "graders"))
        if isinstance(g, dict)
    ]
    return {**raw, **execution, "graders": graders}


def _dict(data: Mapping[str, object], key: str) -> dict[str, object]:
    value = data.get(key)
    return {str(k): v for k, v in value.items()} if isinstance(value, dict) else {}


def _list(data: Mapping[str, object], key: str) -> list[object]:
    value = data.get(key)
    return list(value) if isinstance(value, list | tuple) else []


def _int(data: Mapping[str, object], key: str, default: int) -> int:
    value = data.get(key)
    return (
        value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else default
    )


def _case(folder: Path, data: Mapping[str, object]) -> EvalCase:
    name = str(data.get("name") or folder.name)
    prompt = str(data.get("prompt") or "").strip()
    if not prompt:
        raise PluginError(ERR_PROMPT.format(case=name))
    if PROMPT_TODO in prompt:
        raise PluginError(ERR_TEMPLATE.format(case=name, todo=PROMPT_TODO))
    graders = tuple(g for g in _list(data, "graders") if isinstance(g, Grader))
    if not graders:
        raise PluginError(ERR_NO_GRADER.format(case=name))
    for grader in graders:
        text = str(grader.fields.get("criteria") or grader.fields.get("pattern") or "")
        if GRADER_TODO in text:
            raise PluginError(ERR_GRADER_TEMPLATE.format(case=name, name=grader.name))
    env = _dict(data, "env")
    tools = _list(data, "allowed_tools")
    tags = _list(data, "tags")
    return EvalCase(
        name,
        folder,
        prompt,
        graders,
        tuple(str(t) for t in tags),
        _int(data, "runs", 3),
        _int(data, "max_turns", 10),
        _int(data, "timeout_seconds", 300),
        str(data.get("model") or ""),
        tuple(str(t) for t in tools),
        str(data.get("append_system_prompt") or ""),
        {str(k): str(v) for k, v in env.items()},
        str(data.get("scaffold_script") or ""),
    )


def load_cases(
    root: Path, *, case_glob: str = "", tags: Iterable[str] = ()
) -> tuple[EvalCase, ...]:
    """Eval klasöründeki vakalar (ad sırasıyla); filtreler `--case` ve `--tag`."""
    wanted = set(tags)
    found: list[EvalCase] = []
    folders = sorted({p.parent for p in root.rglob("*") if p.name in {"case.yaml", "prompt.md"}})
    for folder in folders:
        if "results" in folder.relative_to(root).parts:
            continue
        data = _from_yaml(folder) or _from_markdown(folder)
        if data is None:
            continue
        case = _case(folder, data)
        if case_glob and not fnmatch(case.name, case_glob):
            continue
        if wanted and not wanted & set(case.tags):
            continue
        found.append(case)
    return tuple(found)


# --- Puanlama ----------------------------------------------------------------- #


def is_with_only(grader: Grader) -> bool:
    return grader.arm == "with-only" or (
        grader.type == "tool_used" and str(grader.fields.get("tool")) == "Skill"
    )


def _fusion_names(tool: str) -> frozenset[str]:
    from .capabilities import CLAUDE_TOOL_MAP

    return CLAUDE_TOOL_MAP.get(tool.lower(), frozenset()) | {tool}


def _target(trace: RunTrace, name: object) -> str:
    if name == "trace":
        return trace.trace_text
    if name == "files":
        return "\n".join(str(p.relative_to(trace.workdir)) for p in trace.workdir.rglob("*"))
    return trace.last_message


def _regex(grader: Grader, trace: RunTrace) -> float:
    flags = str(grader.fields.get("flags") or "")
    compiled = re.compile(
        str(grader.fields.get("pattern") or ""),
        (re.I if "i" in flags else 0)
        | (re.M if "m" in flags else 0)
        | (re.S if "s" in flags else 0),
    )
    hits = len(compiled.findall(_target(trace, grader.fields.get("target"))))
    match = str(grader.fields.get("match") or "contains")
    if match == "not_contains":
        return 1.0 if hits == 0 else 0.0
    if match.startswith("count:"):
        return 1.0 if hits == int(match.removeprefix("count:")) else 0.0
    return 1.0 if hits else 0.0


def _calls(trace: RunTrace, tool: str, pattern: str = "") -> list[int]:
    names = _fusion_names(tool)
    regex = re.compile(pattern) if pattern else None
    return [
        index
        for index, (name, args) in enumerate(trace.tools)
        if name in names and (regex is None or regex.search(json.dumps(args, ensure_ascii=False)))
    ]


def _tool_used(grader: Grader, trace: RunTrace) -> float:
    count = len(
        _calls(trace, str(grader.fields.get("tool")), str(grader.fields.get("input_match") or ""))
    )
    low = grader.fields.get("min")
    high = grader.fields.get("max")
    low_ok = count >= (int(low) if isinstance(low, int) else 1)
    high_ok = not isinstance(high, int) or count <= high
    return 1.0 if low_ok and high_ok else 0.0


def _spec(raw: object) -> tuple[str, str]:
    if isinstance(raw, Mapping):
        return str(raw.get("tool")), str(raw.get("input_match") or "")
    return str(raw), ""


def _tool_order(grader: Grader, trace: RunTrace) -> float:
    before = _calls(trace, *_spec(grader.fields.get("before")))
    after = _calls(trace, *_spec(grader.fields.get("after")))
    return 1.0 if before and after and min(before) < min(after) else 0.0


def _file_exists(grader: Grader, trace: RunTrace) -> float:
    present = (trace.workdir / str(grader.fields.get("path"))).exists()
    wanted = grader.fields.get("exists") is not False
    return 1.0 if present == wanted else 0.0


def judge_prompt(grader: Grader, trace: RunTrace, case: EvalCase) -> str:
    focus = _target(trace, grader.fields.get("focus"))
    baseline = ""
    if grader.type == "baseline":
        path = case.folder / str(grader.fields.get("baseline_file"))
        baseline = path.read_text("utf-8") if path.is_file() else ""
        baseline = f"\n\n<baseline>\n{baseline}\n</baseline>"
    return (
        "You are grading an AI agent's response. Reply with a single line 'SCORE: <0..1>'.\n\n"
        f"<task>\n{case.prompt}\n</task>\n\n<criteria>\n{grader.fields.get('criteria')}\n"
        f"</criteria>{baseline}\n\n<response>\n{focus}\n</response>"
    )


def grade(grader: Grader, trace: RunTrace, case: EvalCase, judge: Judge) -> float:
    if grader.type == "regex":
        return _regex(grader, trace)
    if grader.type == "tool_used":
        return _tool_used(grader, trace)
    if grader.type == "tool_order":
        return _tool_order(grader, trace)
    if grader.type == "file_exists":
        return _file_exists(grader, trace)
    return max(0.0, min(1.0, judge(judge_prompt(grader, trace, case))))


def parse_score(text: str) -> float:
    match = re.search(r"SCORE:\s*([01](?:\.\d+)?)", text, re.I)
    if match:
        return float(match.group(1))
    lowered = text.strip().lower()
    return 1.0 if lowered.startswith(("pass", "yes")) else 0.0


def score_run(
    case: EvalCase, trace: RunTrace, judge: Judge, *, arm: str, ablation: bool
) -> dict[str, object]:
    """Tek koşunun değerlendirici sonuçları ve puanı."""
    rows: list[dict[str, object]] = []
    total = weight = 0.0
    for grader in case.graders:
        indicator = ablation and is_with_only(grader)
        if arm == "without" and indicator:
            continue
        value = grade(grader, trace, case, judge)
        rows.append(
            {"name": grader.name, "type": grader.type, "score": value, "scored": not indicator}
        )
        if not indicator:
            total += value * grader.weight
            weight += grader.weight
    return {"score": total / weight if weight else 0.0, "graders": rows}
