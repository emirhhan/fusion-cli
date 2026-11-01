"""`InstructionsLoaded` kancası (#90): talimat dosyası bağlama girince bir kez çalışır."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

from fusion_cli.config.hooks import parse_hooks_block
from fusion_cli.core.hooks.events import CLAUDE_ONLY_EVENTS, HookEvent, HookSet
from fusion_cli.engines.agent.hook_instructions import (
    memory_type,
    nested_instructions,
    session_instructions,
)
from fusion_cli.engines.agent.instruction_layers import load_instruction_layers
from fusion_cli.engines.agent.instruction_rules import discover_rules
from fusion_cli.engines.hooks.session import HookSession


def _deps(tmp_path: Path, matcher: str = ""):
    log = tmp_path / "kayit.jsonl"
    script = tmp_path / "kanca.py"
    script.write_text(
        "import sys\n"
        f"open(r'{log}', 'a').write(sys.stdin.read().strip() + '\\n')\n"
        "print('{\"continue\": false}')\n",
        encoding="utf-8",
    )
    commands, skipped = parse_hooks_block(
        {
            "InstructionsLoaded": [
                {
                    "matcher": matcher,
                    "hooks": [{"type": "command", "command": f"{sys.executable} {script}"}],
                }
            ]
        },
        source="kullanici",
        path=Path("settings.json"),
    )
    assert not skipped
    project = tmp_path / "proje"
    home = tmp_path / "ev"
    project.mkdir()
    home.mkdir()
    session = HookSession(root=project, loader=lambda: HookSet(commands))
    deps = SimpleNamespace(
        hooks=session,
        home=home,
        tool_context=SimpleNamespace(root=project),
        config=SimpleNamespace(runtime=SimpleNamespace(instruction_merge=True)),
    )
    return deps, log


def _records(log: Path) -> list[dict]:
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines() if line]


async def _drain(session: HookSession) -> None:
    while session._background:
        await asyncio.gather(*list(session._background))


def test_olay_artik_tetikleniyor():
    assert "InstructionsLoaded" not in CLAUDE_ONLY_EVENTS
    assert HookEvent.INSTRUCTIONS_LOADED.value == "InstructionsLoaded"


def test_memory_type_claude_kapsamlari(tmp_path):
    home = tmp_path / "ev"
    home.mkdir()
    assert memory_type(home / ".claude" / "CLAUDE.md", home) == "User"
    assert memory_type(tmp_path / "p" / "CLAUDE.local.md", home) == "Local"
    assert memory_type(tmp_path / "p" / "CLAUDE.md", home) == "Project"


def test_oturum_basi_dosyalar_bir_kez_bildirilir(tmp_path):
    deps, log = _deps(tmp_path)
    root = deps.tool_context.root
    (root / "CLAUDE.md").write_text("kural\n@ek.md\n", encoding="utf-8")
    (root / "ek.md").write_text("ek kural\n", encoding="utf-8")
    (root / "CLAUDE.local.md").write_text("yerel\n", encoding="utf-8")
    rules = root / ".claude" / "rules"
    rules.mkdir(parents=True)
    (rules / "genel.md").write_text("genel kural\n", encoding="utf-8")
    load = load_instruction_layers(root, deps.home)

    async def run() -> None:
        session_instructions(deps, load)
        await _drain(deps.hooks)
        session_instructions(deps, load)  # ikinci kök tur: yeniden bildirilmez
        await _drain(deps.hooks)

    asyncio.run(run())
    got = {Path(r["file_path"]).name: r for r in _records(log)}
    assert set(got) == {"CLAUDE.md", "ek.md", "CLAUDE.local.md", "genel.md"}
    assert got["CLAUDE.md"]["load_reason"] == "session_start"
    assert got["CLAUDE.md"]["memory_type"] == "Project"
    assert got["CLAUDE.local.md"]["memory_type"] == "Local"
    assert got["ek.md"]["load_reason"] == "include"
    assert got["ek.md"]["parent_file_path"].endswith("CLAUDE.md")
    assert got["CLAUDE.md"]["hook_event_name"] == "InstructionsLoaded"
    assert len(_records(log)) == 4


def test_sikistirma_sonrasi_compact_nedeni(tmp_path):
    deps, log = _deps(tmp_path, matcher="compact")
    root = deps.tool_context.root
    (root / "CLAUDE.md").write_text("kural\n", encoding="utf-8")
    load = load_instruction_layers(root, deps.home)

    async def run() -> None:
        session_instructions(deps, load)  # session_start: eşleştirici uymaz
        await _drain(deps.hooks)
        await deps.hooks.compacted()
        session_instructions(deps, load)
        await _drain(deps.hooks)

    asyncio.run(run())
    records = _records(log)
    assert [r["load_reason"] for r in records] == ["compact"]


def test_ic_ice_ve_kural_tembel_yuklemesi(tmp_path):
    deps, log = _deps(tmp_path)
    root = deps.tool_context.root
    rules_dir = root / ".claude" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "api.md").write_text("---\npaths:\n  - src/**\n---\napi kuralı\n", "utf-8")
    rules = discover_rules(root, deps.home)
    label = next(rule.label for rule in rules if rule.is_scoped)
    trigger = root / "src" / "a.py"

    async def run() -> None:
        nested_instructions(deps, root, ("src/CLAUDE.md", label), rules, trigger)
        await _drain(deps.hooks)

    asyncio.run(run())
    got = {Path(r["file_path"]).name: r for r in _records(log)}
    assert got["CLAUDE.md"]["load_reason"] == "nested_traversal"
    assert got["CLAUDE.md"]["trigger_file_path"] == str(trigger)
    assert got["api.md"]["load_reason"] == "path_glob_match"
    assert got["api.md"]["globs"] == ["src/**"]


def test_kanca_yoksa_hicbir_sey_calismaz(tmp_path):
    deps, log = _deps(tmp_path)
    deps.hooks = HookSession(root=deps.tool_context.root, loader=lambda: HookSet(()))
    (deps.tool_context.root / "CLAUDE.md").write_text("kural\n", encoding="utf-8")
    load = load_instruction_layers(deps.tool_context.root, deps.home)
    session_instructions(deps, load)  # döngü yok, kanca yok: sessizce geçer
    assert not log.exists()
