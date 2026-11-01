"""Claude Code `Skill` aracı ve `allowed-tools`/`disallowed-tools` anlamı (#139, #141, #142, #180).

Belge: code.claude.com/docs/en/skills — model beceriyi `Skill` aracıyla çağırır, işlenmiş gövde
konuşmaya girer; `allowed-tools` listedeki araçları beceri etkinken onaysız kullandırır (diğer
araçlar kalır); `disallowed-tools` araçları havuzdan çıkarır — desenli girdi (`Bash(rm *)`)
aracın tamamını yasaklar (belge desen anlamını tanımlamıyor; güvenli taraf, #180).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from fusion_cli.config.permission_rules import PermissionDecision
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent import skill_grants, skill_tool
from fusion_cli.engines.agent.approval import ApprovalMode
from fusion_cli.tools.capabilities import CapabilityRegistry
from fusion_cli.tools.permission_match import evaluate
from fusion_cli.tools.skill_commands import map_denied_tools

from .fakes import make_config


def _skill(home: Path, name: str, front: str, body: str) -> None:
    folder = home / ".claude" / "skills" / name
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(f"---\nname: {name}\n{front}---\n{body}", encoding="utf-8")


@pytest.fixture
def ortam(tmp_path: Path) -> SimpleNamespace:
    home, root = tmp_path / "ev", tmp_path / "proje"
    root.mkdir()
    _skill(
        home,
        "rapor",
        "description: Rapor yazar\nallowed-tools: Bash(git status *) Read\n"
        "disallowed-tools: Bash(rm *)\n",
        "Konu: $ARGUMENTS\nDurum: !`echo canli`\n",
    )
    _skill(home, "gizli", "description: x\ndisable-model-invocation: true\n", "gizli gövde")
    library = CapabilityRegistry(home, root)
    deps = SimpleNamespace(config=make_config(), approval_mode=lambda: ApprovalMode.AUTO, home=home)
    tool = skill_tool.build_skill_tool(library, deps, depth=0, run_agent=None)  # type: ignore[arg-type]
    return SimpleNamespace(home=home, root=root, tool=tool, library=library, deps=deps)


def _run(tool, args: dict, context: ToolContext):
    return asyncio.run(tool.run(args, context))


def test_skill_araci_islenmis_govdeyi_dondurur(ortam: SimpleNamespace) -> None:
    context = ToolContext(root=ortam.root)

    result = _run(ortam.tool, {"skill": "rapor", "args": "satışlar"}, context)

    assert result.ok, result.output
    assert ortam.tool.name == "Skill"
    assert "Konu: satışlar" in result.output
    assert "Durum: canli" in result.output  # !`cmd` model çağrısında da çalışır


def test_kullaniciya_ozel_beceri_modelce_cagrilamaz(ortam: SimpleNamespace) -> None:
    result = _run(ortam.tool, {"skill": "gizli"}, ToolContext(root=ortam.root))

    assert not result.ok
    assert "/gizli" in result.output


def test_allowed_tools_on_onay_disallowed_arac_yasak(ortam: SimpleNamespace) -> None:
    context = ToolContext(root=ortam.root)
    _run(ortam.tool, {"skill": "rapor"}, context)

    rules = skill_grants.with_grants(None, context)
    assert rules is not None
    allow = evaluate(rules, "run_shell", {"command": "git status --short"}, ortam.root)
    other = evaluate(rules, "read_file", {"path": "a.txt"}, ortam.root)
    # `disallowed-tools: Bash(rm *)` aracın tamamını yasaklar (belge: "removed from the pool").
    deny = evaluate(rules, "run_shell", {"command": "npm test"}, ortam.root)
    assert allow is not None
    assert deny is not None and deny.decision is PermissionDecision.DENY
    assert other is None or other.decision is PermissionDecision.ALLOW


def test_skill_deny_kurali_cagriyi_engeller(ortam: SimpleNamespace) -> None:
    from fusion_cli.config.permission_rules import PermissionRuleSet, parse_rule

    rule = parse_rule("Skill(rapor)", PermissionDecision.DENY)
    assert rule is not None
    ortam.deps.permission_rules = PermissionRuleSet((rule,))

    result = _run(ortam.tool, {"skill": "rapor"}, ToolContext(root=ortam.root))

    assert not result.ok and "yasak" in result.output


def test_yeni_kullanici_mesaji_on_onayi_kaldirir(ortam: SimpleNamespace) -> None:
    context = ToolContext(root=ortam.root)
    _run(ortam.tool, {"skill": "rapor"}, context)

    skill_grants.begin_turn(context, ())

    assert skill_grants.with_grants(None, context) is None


def test_disallowed_deseni_aracin_tamamini_kaldirir() -> None:
    assert "run_shell" in map_denied_tools(("Bash(rm *)",))


def test_guvenilmeyen_proje_becerisinin_on_onayi_gecmez(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "depo"
    folder = root / ".claude" / "skills" / "depo-b"
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(
        "---\nname: depo-b\nallowed-tools: Bash(*)\ndisallowed-tools: Bash(rm *)\n---\ngövde",
        encoding="utf-8",
    )
    skill = CapabilityRegistry(tmp_path / "ev", root).get_skill("depo-b")
    assert skill is not None
    monkeypatch.setattr(
        skill_tool.trust, "resolve_project_trust", lambda _root: SimpleNamespace(trusted=False)
    )

    assert skill_tool.grant_entries(skill, root) == (("deny", "Bash"),)


def test_fork_becerisi_gecmissiz_alt_ajanda_kosar(tmp_path: Path, monkeypatch) -> None:
    home, root = tmp_path / "ev", tmp_path / "proje"
    root.mkdir()
    _skill(home, "arastir", "context: fork\nagent: Explore\n", "Şunu araştır: $ARGUMENTS")
    library = CapabilityRegistry(home, root)
    deps = SimpleNamespace(config=make_config(), approval_mode=lambda: ApprovalMode.AUTO, home=home)
    seen: dict[str, object] = {}

    async def fake_subagent(deps, subtask, *, depth, run_agent):  # type: ignore[no-untyped-def]
        seen["task"], seen["persona"] = subtask.task, subtask.persona
        seen["inherit"] = subtask.inherit_context
        return SimpleNamespace(text="bulgu")

    from fusion_cli.engines.agent import team

    monkeypatch.setattr(team, "run_subagent", fake_subagent)
    monkeypatch.setattr(team, "depth_limit_reached", lambda _deps, _depth: False)
    tool = skill_tool.build_skill_tool(library, deps, depth=0, run_agent=None)  # type: ignore[arg-type]

    result = _run(tool, {"skill": "arastir", "args": "önbellek"}, ToolContext(root=root))

    assert result.output == "bulgu"
    assert "Şunu araştır: önbellek" in str(seen["task"])
    assert seen["persona"] == "Explore" and seen["inherit"] is False


def test_kullanici_fork_becerisi_gecmissiz_kosar(monkeypatch) -> None:
    """`/ad` ile çağrılan `context: fork` becerisi ana geçmişi devralmaz (#141)."""
    from fusion_cli.cli.repl.state import PendingExtras
    from fusion_cli.core.types import Message
    from fusion_cli.engines.agent import team, team_fork

    seen: dict[str, object] = {}

    async def fake_subagent(deps, subtask, *, depth, run_agent):  # type: ignore[no-untyped-def]
        seen["inherit"], seen["history"] = subtask.inherit_context, deps.live_history()
        return SimpleNamespace(text="özet", ok=True, tool_calls=0)

    monkeypatch.setattr(team, "run_subagent", fake_subagent)
    runner = PendingExtras(fresh_fork=True).fork_runner(team_fork.run_forked_turn)
    deps = SimpleNamespace(live_history=None)
    gecmis = [Message("user", "eski konu"), Message("assistant", "eski yanıt")]

    outcome = asyncio.run(runner("araştır", deps, history=gecmis))

    assert seen["inherit"] is False and seen["history"] == []
    assert outcome.final_text == "özet"
    assert outcome.messages[: len(gecmis)] == gecmis  # ana geçmiş korunur, yalnız özet eklenir


def test_cagrilan_beceri_sonraki_turlarda_baglamda_kalir() -> None:
    """#140: gövde sonraki turlarda da gider; aynı beceri yeniden çağrılınca yalnız sonuncusu."""
    from fusion_cli.engines.agent.skill_context import (
        CHARS_PER_TOKEN,
        PER_SKILL_TOKENS,
        InvokedSkills,
    )

    kayit = InvokedSkills("s1").remember("a", "A1").remember("b", "B" * 30_000)
    kayit = kayit.remember("a", "A2")

    blok = kayit.carried_block()
    assert "A2" in blok and "A1" not in blok
    assert blok.index("A2") < blok.index("BBB")  # en yeni önce
    # Sıkıştırmadan önce gövde TAM kalır (Claude: mesaj konuşmada durur).
    assert blok.count("B") >= 30_000
    sonra = kayit.compacted().carried_block()
    assert sonra.count("B") <= PER_SKILL_TOKENS * CHARS_PER_TOKEN + 5
    assert kayit.carried_block(exclude="a").count("A2") == 0
    assert kayit.for_conversation("s2").carried_block() == ""


def test_repl_durumu_beceriyi_sonraki_tura_tasir(tmp_path: Path) -> None:
    from fusion_cli.cli.repl.state import ReplState
    from fusion_cli.memory.factory import null_memory

    state = ReplState(config=make_config(), memory=null_memory(), root=tmp_path, home=tmp_path)
    state.pending_context, state.pending_skill_name = '<beceri ad="r">GÖVDE</beceri>', "r"

    ilk = state.take_pending_extras()
    ikinci = state.take_pending_extras()
    state.reset_history()
    ucuncu = state.take_pending_extras()

    assert "GÖVDE" in ilk.context and ilk.context.count("GÖVDE") == 1
    assert "GÖVDE" in ikinci.context
    assert "GÖVDE" not in ucuncu.context  # /clear


def _model_skill_ortam(tmp_path: Path, front: str):  # type: ignore[no-untyped-def]
    home, root = tmp_path / "ev", tmp_path / "proje"
    root.mkdir()
    _skill(home, "derin", front, "Derin düşün: $ARGUMENTS")
    library = CapabilityRegistry(home, root)
    deps = SimpleNamespace(
        config=make_config(),
        approval_mode=lambda: ApprovalMode.AUTO,
        home=home,
        active_model_override=None,
        turn_effort_override=None,
    )
    tool = skill_tool.build_skill_tool(library, deps, depth=0, run_agent=None)  # type: ignore[arg-type]
    return deps, tool, root


def test_model_cagrisi_model_ve_eforu_turun_kalanina_uygular(tmp_path: Path) -> None:
    """Belge: "The override applies for the rest of the current turn" (#139)."""
    from fusion_cli.core.reasoning import ReasoningEffort

    deps, tool, root = _model_skill_ortam(
        tmp_path, "description: x\nmodel: openai/gpt-derin\neffort: high\n"
    )

    result = _run(tool, {"skill": "derin", "args": "konu"}, ToolContext(root=root))

    assert result.ok, result.output
    assert deps.active_model_override is not None
    assert deps.active_model_override.model == "openai/gpt-derin"
    assert deps.turn_effort_override is ReasoningEffort.HIGH
    assert "bu tur model: openai/gpt-derin" in result.output


def test_inherit_modeli_degistirmez(tmp_path: Path) -> None:
    deps, tool, root = _model_skill_ortam(tmp_path, "description: x\nmodel: inherit\n")

    _run(tool, {"skill": "derin"}, ToolContext(root=root))

    assert deps.active_model_override is None and deps.turn_effort_override is None


def test_fork_becerisi_etkilesimli_oturumda_arka_planda_kosar(tmp_path: Path, monkeypatch) -> None:
    """Belge: fork varsayılan arka planda; `background: false` bekletir (#141)."""
    from fusion_cli.engines.agent import agent_runtime_tools, team

    home, root = tmp_path / "ev", tmp_path / "proje"
    root.mkdir()
    _skill(home, "arka", "context: fork\nmodel: openai/m\neffort: low\n", "iş: $ARGUMENTS")
    _skill(home, "bekle", "context: fork\nbackground: false\n", "iş")
    library = CapabilityRegistry(home, root)
    deps = SimpleNamespace(
        config=make_config(), approval_mode=lambda: ApprovalMode.AUTO, home=home, interactive=True
    )
    seen: dict[str, object] = {}

    async def fake_launch(deps, subtask, args, *, depth, run_agent):  # type: ignore[no-untyped-def]
        seen["launch"] = (subtask.model, subtask.effort, args)
        return SimpleNamespace(ok=True, output="arka plan makbuzu")

    async def fake_subagent(deps, subtask, *, depth, run_agent):  # type: ignore[no-untyped-def]
        seen["wait"] = subtask.task
        return SimpleNamespace(text="beklendi")

    monkeypatch.setattr(agent_runtime_tools, "launch_agent", fake_launch)
    monkeypatch.setattr(team, "run_subagent", fake_subagent)
    monkeypatch.setattr(team, "depth_limit_reached", lambda _deps, _depth: False)
    tool = skill_tool.build_skill_tool(library, deps, depth=0, run_agent=None)  # type: ignore[arg-type]

    arka = _run(tool, {"skill": "arka", "args": "x"}, ToolContext(root=root))
    bekle = _run(tool, {"skill": "bekle"}, ToolContext(root=root))

    assert arka.output == "arka plan makbuzu"
    assert seen["launch"] == ("openai/m", "low", {"run_in_background": True})
    assert bekle.output == "beklendi" and seen["wait"]


def test_kullanici_fork_becerisi_arka_planda_baslar(monkeypatch) -> None:
    """`/ad` fork becerisi etkileşimli oturumda arka planda başlar (#141)."""
    import json

    from fusion_cli.cli.repl.state import PendingExtras
    from fusion_cli.core.tools import ToolResult
    from fusion_cli.engines.agent import agent_runtime_tools, team_fork

    seen: dict[str, object] = {}

    async def fake_launch(deps, subtask, args, *, depth, run_agent):  # type: ignore[no-untyped-def]
        seen["args"], seen["inherit"] = args, subtask.inherit_context
        return ToolResult(json.dumps({"status": "async_launched", "agentId": "a-1"}))

    monkeypatch.setattr(agent_runtime_tools, "launch_agent", fake_launch)
    runner = PendingExtras(fresh_fork=True, fork_background=True).fork_runner(
        team_fork.run_forked_turn
    )
    deps = SimpleNamespace(live_history=None, interactive=True)

    outcome = asyncio.run(runner("araştır", deps, history=[]))

    assert seen == {"args": {"run_in_background": True}, "inherit": False}
    assert "arka planda" in outcome.final_text and "a-1" in outcome.final_text


def test_background_false_repl_durumuna_tasinir(tmp_path: Path) -> None:
    from fusion_cli.cli.repl.skill_commands import skill_handler
    from fusion_cli.cli.repl.state import ReplState

    home = tmp_path / "ev"
    _skill(home, "kuyruk", "context: fork\n", "iş")
    _skill(home, "bekle", "context: fork\nbackground: false\n", "iş")
    state = ReplState(config=make_config(), memory=None, root=tmp_path, home=home)  # type: ignore[arg-type]
    state.capabilities = CapabilityRegistry(home, tmp_path)

    skill_handler("kuyruk")(state, "")
    assert state.take_pending_extras().fork_background is True
    skill_handler("bekle")(state, "")
    assert state.take_pending_extras().fork_background is False
