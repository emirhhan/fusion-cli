"""Beceri `hooks` alanı: çağrıda oturuma kaydedilir, oturum boyunca etkin (Claude Code #161)."""

from __future__ import annotations

from pathlib import Path

from fusion_cli.core.hooks.events import HookEvent, HookSet
from fusion_cli.engines.agent import skill_hooks
from fusion_cli.engines.hooks.session import HookSession
from fusion_cli.tools.capabilities import CapabilityRegistry

_HOOKS = (
    "hooks:\n"
    "  PostToolUse:\n"
    "    - matcher: Edit\n"
    "      hooks:\n"
    "        - type: command\n"
    "          command: echo bicimle\n"
)


def _skill(home: Path, name: str, extra: str) -> None:
    folder = home / ".claude" / "skills" / name
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {name} açıklaması\n{extra}---\ngövde", encoding="utf-8"
    )


def _registry(tmp_path: Path) -> tuple[CapabilityRegistry, Path]:
    home, root = tmp_path / "ev", tmp_path / "proje"
    root.mkdir()
    _skill(home, "bicim", _HOOKS)
    _skill(home, "duz", "")
    return CapabilityRegistry(home, root), root


def _commands(session: HookSession) -> list[str]:
    return [c.command for c in session.refresh().for_event(HookEvent.POST_TOOL_USE, ("Edit",))]


def test_beceri_kancasi_cagrida_kaydedilir_ve_oturum_boyunca_kalir(tmp_path: Path) -> None:
    registry, root = _registry(tmp_path)
    session = HookSession(root, loader=HookSet)
    skill = next(s for s in registry.skills() if s.name == "bicim")

    assert _commands(session) == []
    assert skill_hooks.register(session, skill, trusted=True)
    # Sonraki turlarda da (refresh) beceri kancası okunmaya devam eder.
    assert _commands(session) == ["echo bicimle"]
    assert _commands(session) == ["echo bicimle"]
    # İkinci çağrı çiftlemez.
    assert not skill_hooks.register(session, skill, trusted=True)
    assert _commands(session) == ["echo bicimle"]
    assert skill_hooks.registered_names(session) == (skill.qualified_name,)


def test_guvenilmeyen_ya_da_kancasiz_beceri_kaydedilmez(tmp_path: Path) -> None:
    registry, root = _registry(tmp_path)
    session = HookSession(root, loader=HookSet)
    bicim = next(s for s in registry.skills() if s.name == "bicim")
    duz = next(s for s in registry.skills() if s.name == "duz")

    assert not skill_hooks.register(session, bicim, trusted=False)
    assert not skill_hooks.register(session, duz, trusted=True)
    assert _commands(session) == []


def test_disable_all_hooks_beceri_kancasini_da_kapatir_clear_siler(tmp_path: Path) -> None:
    registry, root = _registry(tmp_path)
    session = HookSession(root, loader=lambda: HookSet(disabled_reason="disableAllHooks"))
    skill = next(s for s in registry.skills() if s.name == "bicim")

    skill_hooks.register(session, skill, trusted=True)
    assert _commands(session) == []

    acik = HookSession(root, loader=HookSet)
    skill_hooks.register(acik, skill, trusted=True)
    skill_hooks.forget(acik)
    assert _commands(acik) == []


def test_repl_beceri_komutu_kancayi_kaydeder(tmp_path: Path, monkeypatch) -> None:
    from fusion_cli.cli.repl.skill_commands import skill_handler
    from fusion_cli.cli.repl.state import ReplState
    from fusion_cli.config.loader import load_config
    from fusion_cli.memory.factory import null_memory

    registry, root = _registry(tmp_path)
    source = tmp_path / "config.yaml"
    source.write_text("", encoding="utf-8")
    state = ReplState(config=load_config(source), memory=null_memory(), root=root, home=tmp_path)
    state.capabilities = registry
    skill = next(s for s in registry.skills() if s.name == "bicim")

    skill_handler(skill.qualified_name)(state, "")

    assert skill.qualified_name in skill_hooks.registered_names(state.hooks())
    state.reset_history()
    assert skill_hooks.registered_names(state.hooks()) == ()


def test_kurulu_depo_becerisinin_kancasi_guvenilmez(tmp_path: Path) -> None:
    """`fusion yetenek kur` ile gelen üçüncü taraf beceri: `!`cmd`` gibi kancası da koşmaz."""
    import dataclasses

    from fusion_cli.engines.agent import skill_tool

    registry, root = _registry(tmp_path)
    skill = next(s for s in registry.skills() if s.name == "bicim")
    kurulu = dataclasses.replace(skill, source="kurulu")

    assert skill_tool.hooks_trusted(skill, root)
    assert not skill_tool.hooks_trusted(kurulu, root)


def test_model_skill_araci_kancayi_oturuma_kaydeder(tmp_path: Path) -> None:
    import asyncio
    from types import SimpleNamespace

    from fusion_cli.core.tools import ToolContext
    from fusion_cli.engines.agent import skill_tool
    from fusion_cli.engines.agent.approval import ApprovalMode

    from .fakes import make_config

    registry, root = _registry(tmp_path)
    session = HookSession(root, loader=HookSet)
    deps = SimpleNamespace(
        config=make_config(),
        approval_mode=lambda: ApprovalMode.AUTO,
        home=tmp_path / "ev",
        hooks=session,
    )
    tool = skill_tool.build_skill_tool(registry, deps, depth=0, run_agent=None)  # type: ignore[arg-type]

    result = asyncio.run(tool.run({"skill": "bicim"}, ToolContext(root=root)))

    assert result.ok, result.output
    assert _commands(session) == ["echo bicimle"]
