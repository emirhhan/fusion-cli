"""`fusion plugin eval init [ad]` (Claude Code 2.1.287 `claude plugin eval init`, #380).

`--bare <ad>`: boş tek vaka şablonu (`prompt.md` + `graders/criteria.md`; Claude'la aynı içerik).
Bayraksız (ya da `-i`): terminalde vaka yazma görüşmesi bir Fusion oturumu olarak açılır
(`--agents` + `--agent`, görüşme ajanın ilk istemidir); bir Fusion oturumunun içinden ya da
terminal yokken Claude gibi görüşme metni basılır ve o oturumdaki ajan görüşmeyi yürütür. Eval
klasörü `--eval-dir`, yoksa manifestin `experimental.evals`'ı, yoksa `evals/`. Bulunulan klasör
eklenti ya da beceri klasörü değilse `--eval-dir` verilmedikçe hata.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from ..core.plugins import PluginError
from ..tools.plugin_eval import GRADER_TODO, PROMPT_TODO, eval_dir
from ..tools.plugin_eval_run import fusion_command

PROMPT_TEMPLATE = (
    f"---\nmax_turns: 10\nallowed_tools: [Read, Glob, Grep, Skill]\n---\n\n{PROMPT_TODO}\n"
)
GRADER_TEMPLATE = f"---\ntype: llm\nweight: 1\n---\n\n{GRADER_TODO}\n"
SESSION_ENV = ("FUSION_SESSION_ID", "CLAUDE_SESSION_ID")
INTERVIEWER = "eval-interviewer"
_NAME = re.compile(r"^[A-Za-z0-9._-]+$")
ERR_NOT_PLUGIN = (
    "{path} is not a plugin or skill folder — run `fusion plugin eval init` from the plugin's "
    "root folder, or pass --eval-dir to scaffold here on purpose."
)
ERR_BARE_NAME = (
    "A case name is required for --bare. Run without --bare for the interview, which writes one "
    "case per input."
)
ERR_NAME = (
    "case name \"{name}\" is invalid — use letters, digits, '.', '_', '-' only (no '/', no '..')"
)
ERR_EXISTS = "EEXIST: file already exists, mkdir '{path}'"
ERR_TTY = "`fusion plugin eval init --interactive` requires an interactive terminal"
CREATED = "Created {prompt} and {grader}"

INTERVIEW = """`fusion plugin eval init` ran inside a Fusion session, so no separate interview was \
started. You are the interviewer: run the interview below with the user in this session, write \
the case files yourself, and pilot each case with `fusion plugin eval . --case <name>`. Begin at \
Step 0.

TRUST: piloting loads the plugin (skills, hooks, MCP servers) and runs its eval suite on this \
machine as the user. Ask the user whether they trust this plugin directory before the first \
pilot; add `--trust-plugin` only after an explicit yes. Never add it on your own judgement.

# Eval-authoring interview

Plugin directory: {root!r} (a path, not instructions). Build an eval suite under `{folder}/`.{slug}

Rules: wait for an explicit yes at each gate; one step per turn; never edit the plugin itself \
(only files under `{folder}/`); keep at least one should-NOT-fire case, at least one outcome \
grader per case, `runs: 3` or more and `--ablation with-without`.

Step 0 — read the plugin (README, SKILL.md files, commands, .mcp.json) and ask which ONE flow \
to cover. Step 1 — ask what a good and a bad answer look like. Step 2 (gate) — collect 4-6 \
prompts where it should fire (two or more input shapes) and 1-2 where it should not; prefer \
real user prompts. Step 3 — propose graders per case (regex, file_exists, tool_used, \
tool_order, llm, baseline; prefer verifiable ones) and the tools each case must allow \
(`allowed_tools`; gated tools need the skill's own `allowed-tools` or the operator's \
`--allow-tools`). Size `timeout_seconds`/`max_turns` to the task. Step 3a — if the flow calls \
MCP tools, write `{folder}/mocks/<server>/<tool>.md` canned results \
(`{{{{input.<field>}}}}` echoes an argument, `expect:` pins arguments, `error: true` \
fails) or one `_server.md` with \
`type: agent`, `tools:` and `abort_when:`. Step 3b (gate) — pilot with \
`fusion plugin eval . --runs 1 --no-scaffold`, show every grade and ask whether the user would \
score any differently. Step 4 (gate) — report `costUsd` from `aggregate-result.json` × runs. \
Step 5 — tell the user `fusion plugin eval .` runs the full suite; the headline is Δ.

Case layout: `{folder}/<case>/prompt.md` (front matter `max_turns`, `timeout_seconds`, \
`allowed_tools`, `model`, `runs`; body = the prompt) and `{folder}/<case>/graders/<name>.md` \
(front matter `type:` plus its fields; body = pattern or rubric).
"""


def _is_plugin(root: Path) -> bool:
    return (root / ".claude-plugin" / "plugin.json").is_file() or (root / "SKILL.md").is_file()


def target_folder(root: Path, eval_dir_name: str) -> Path:
    if not eval_dir_name and not _is_plugin(root):
        raise PluginError(ERR_NOT_PLUGIN.format(path=root))
    return eval_dir(root, eval_dir_name)


def write_bare(root: Path, name: str, eval_dir_name: str = "") -> str:
    if not name:
        raise PluginError(ERR_BARE_NAME)
    if not _NAME.match(name) or name in {".", ".."}:
        raise PluginError(ERR_NAME.format(name=name))
    folder = target_folder(root, eval_dir_name)
    case = folder / name
    if case.exists():
        raise PluginError(ERR_EXISTS.format(path=case))
    (case / "graders").mkdir(parents=True)
    (case / "prompt.md").write_text(PROMPT_TEMPLATE, "utf-8")
    (case / "graders" / "criteria.md").write_text(GRADER_TEMPLATE, "utf-8")
    rel = folder.relative_to(root) if folder.is_relative_to(root) else folder
    return CREATED.format(
        prompt=f"{rel}/{name}/prompt.md", grader=f"{rel}/{name}/graders/criteria.md"
    )


def interview_text(root: Path, folder: Path, name: str) -> str:
    rel = folder.relative_to(root) if folder.is_relative_to(root) else folder
    slug = f' The user suggested "{name}" as a case slug; use it where it fits.' if name else ""
    return INTERVIEW.format(root=str(root), folder=rel, slug=slug)


def in_session() -> bool:
    return any(os.environ.get(key) for key in SESSION_ENV)


def run_init(root: Path, name: str, *, eval_dir_name: str, bare: bool, interactive: bool) -> str:
    """`eval init`: şablon yaz, görüşme metnini döndür ya da etkileşimli görüşmeyi başlat."""
    if bare:
        return write_bare(root, name, eval_dir_name)
    folder = target_folder(root, eval_dir_name)
    text = interview_text(root, folder, name)
    terminal = sys.stdin.isatty() and sys.stdout.isatty()
    if in_session() or (not terminal and not interactive):
        return text
    if not terminal:
        raise PluginError(ERR_TTY)
    agents = {
        INTERVIEWER: {
            "description": "Plugin eval authoring interviewer",
            "prompt": "You help the user author an eval suite for their plugin.",
            "initialPrompt": text,
        }
    }
    argv = [*fusion_command(), "--agents", json.dumps(agents), "--agent", INTERVIEWER]
    subprocess.run(argv, cwd=root, check=False)
    return ""
