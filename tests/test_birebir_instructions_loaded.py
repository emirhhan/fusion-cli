"""`InstructionsLoaded` kancası (Claude Code #169; code.claude.com/docs/en/hooks)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from fusion_cli.core.hooks.events import CLAUDE_ONLY_EVENTS, HookEvent, parse_event
from fusion_cli.engines.agent import instructions_hook


class _Hooks:
    def __init__(self) -> None:
        self.calls: list[tuple[HookEvent, tuple[str, ...], dict[str, object]]] = []

    async def emit(self, event, *, subjects=(), fields=None):  # type: ignore[no-untyped-def]
        self.calls.append((event, subjects, dict(fields or {})))


def test_olay_taninir_ve_claude_only_degil() -> None:
    assert parse_event("InstructionsLoaded") is HookEvent.INSTRUCTIONS_LOADED
    assert "InstructionsLoaded" not in CLAUDE_ONLY_EVENTS


def test_dosya_basina_oturumda_bir_kez_claude_alanlariyla(tmp_path: Path) -> None:
    hooks = _Hooks()
    files = [
        SimpleNamespace(path=tmp_path / "CLAUDE.md", layer="proje"),
        SimpleNamespace(path=tmp_path / "ek.md", layer="import"),
        SimpleNamespace(path=tmp_path / "ev" / "CLAUDE.md", layer="kullanici"),
    ]

    async def run() -> None:
        instructions_hook.notify(hooks, instructions_hook.startup_events(files))
        instructions_hook.notify(hooks, instructions_hook.startup_events(files))  # ikinci tur
        await asyncio.sleep(0)

    asyncio.run(run())

    assert len(hooks.calls) == 3
    event, subjects, fields = hooks.calls[0]
    assert event is HookEvent.INSTRUCTIONS_LOADED and subjects == ("session_start",)
    assert fields == {
        "file_path": str(tmp_path / "CLAUDE.md"),
        "memory_type": "Project",
        "load_reason": "session_start",
    }
    assert hooks.calls[1][2]["load_reason"] == "include"
    assert hooks.calls[2][2]["memory_type"] == "User"


def test_ic_ice_yukleme_tetik_dosyasini_tasir(tmp_path: Path) -> None:
    hooks = _Hooks()
    event = instructions_hook.payload(
        str(tmp_path / "pkg" / "CLAUDE.md"),
        "proje",
        "nested_traversal",
        trigger_file_path=str(tmp_path / "pkg" / "a.py"),
    )

    async def run() -> None:
        instructions_hook.notify(hooks, [event])
        await asyncio.sleep(0)

    asyncio.run(run())

    assert hooks.calls[0][1] == ("nested_traversal",)
    assert hooks.calls[0][2]["trigger_file_path"] == str(tmp_path / "pkg" / "a.py")


def test_kural_dosyalari_oturum_basi_ve_glob_eslesmesiyle_bildirilir(tmp_path: Path) -> None:
    """#169: `.claude/rules` — paths'siz kural session_start, paths'li path_glob_match + globs."""
    from fusion_cli.engines.agent.instruction_rules import RuleFile

    genel = RuleFile(".claude/rules/genel.md", tmp_path / "genel.md", (), False)
    tsx = RuleFile(".claude/rules/tsx.md", tmp_path / "tsx.md", ("src/**/*.tsx",), False)
    kisisel = RuleFile("~/.claude/rules/k.md", tmp_path / "k.md", (), True)

    startup = instructions_hook.rule_startup_events([genel, tsx, kisisel])
    assert [item["file_path"] for item in startup] == [str(genel.path), str(kisisel.path)]
    assert {item["memory_type"] for item in startup} == {"Project", "User"}

    event = instructions_hook.nested_event(tmp_path, tsx.label, "src/App.tsx", [genel, tsx])
    assert event["load_reason"] == "path_glob_match" and event["globs"] == ["src/**/*.tsx"]
    assert event["trigger_file_path"] == "src/App.tsx"
    alt = instructions_hook.nested_event(tmp_path, "paket/CLAUDE.md", "paket/a.py", [tsx])
    assert alt["load_reason"] == "nested_traversal"
    assert alt["file_path"] == str(tmp_path / "paket" / "CLAUDE.md")
