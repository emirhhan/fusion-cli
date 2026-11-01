"""Beceri `model`/`effort`, `disallowed-tools` ve fork `agent` alanları turda uygulanır (P-020).

Ölçüldü (31 Ekim): bu alanlar okunuyor ama turda hiç uygulanmıyordu; `/beceri` "model/effort
alanı okundu ama bu turda uygulanmadı" notu düşüyordu, `disallowed-tools` ve `agent` becerilerde
yok sayılıyordu.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from fusion_cli.cli.repl.skill_commands import skill_handler
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.core.reasoning import ReasoningEffort
from fusion_cli.core.types import ModelSpec
from fusion_cli.engines.agent import team_fork
from fusion_cli.engines.agent.skill_turn import TurnModelChoice, resolve_turn_model
from fusion_cli.memory.factory import null_memory

from .fakes import make_config


def _state(tmp_path: Path, frontmatter: str) -> tuple[ReplState, str]:
    folder = tmp_path / "ev" / ".claude" / "skills" / "beceri"
    folder.mkdir(parents=True)
    folder.joinpath("SKILL.md").write_text(
        f"---\nname: beceri\ndescription: d\n{frontmatter}---\nGövde", encoding="utf-8"
    )
    config = make_config(
        agent=ModelSpec(name="agent", model="oturum/ana", fallback=("oturum/yedek",)),
        task_model_map={"general": "aday"},
    )
    state = ReplState(config=config, memory=null_memory(), root=tmp_path, home=tmp_path / "ev")
    assert state.capabilities is not None
    skill = state.capabilities.get_skill("beceri")
    assert skill is not None
    return state, skill.qualified_name


def test_beceri_modeli_ve_eforu_yalniz_o_tura_uygulanir(tmp_path: Path):
    state, name = _state(tmp_path, "model: saglayici/beceri-modeli\neffort: high\n")
    before = state.config

    cikti = skill_handler(name)(state, "işi yap")
    extras = state.take_pending_extras()
    turn = extras.turn_config(state.config)

    assert "bu tur model: saglayici/beceri-modeli" in cikti and "bu tur efor: high" in cikti
    assert turn.agent.model == "saglayici/beceri-modeli"
    # Oturum modeli ve yedeği zincirde kalır: beceri modeli düşerse tur düşmez.
    assert turn.agent.fallback == ("oturum/ana", "oturum/yedek")
    assert turn.task_model_map == {}
    assert turn.runtime.reasoning_effort is ReasoningEffort.HIGH
    # Oturumun seçimi değişmez; ekler bir kez tüketilir.
    assert state.config is before
    assert state.take_pending_extras().turn_config(state.config) is state.config


@pytest.mark.parametrize("model", ["inherit", "sonnet", ""])
def test_miras_takma_adi_modeli_degistirmez(model: str):
    resolution = resolve_turn_model(model, "")

    assert resolution.choice.is_empty and resolution.notes == ()


def test_taninmayan_model_ve_efor_not_duser_uygulanmaz():
    resolution = resolve_turn_model("gpt-x", "cok-yuksek")
    config = make_config()

    assert resolution.choice.apply(config) is config
    assert any("gpt-x" in note for note in resolution.notes)
    assert any("cok-yuksek" in note for note in resolution.notes)


def test_disallowed_tools_kisilik_yasaklariyla_birlesir(tmp_path: Path):
    state, name = _state(tmp_path, "disallowed-tools: Bash, mcp__github\n")

    skill_handler(name)(state, "x")
    extras = state.take_pending_extras()

    assert extras.merged_denied(frozenset({"web_fetch"})) == {
        "web_fetch",
        "run_shell",
        "github__*",
    }


async def test_fork_agent_alani_fork_turunu_o_ajanla_kosar(tmp_path: Path, monkeypatch):
    state, name = _state(tmp_path, "context: fork\nagent: inceleyici\n")
    cikti = skill_handler(name)(state, "incele")
    extras = state.take_pending_extras()
    seen: dict[str, object] = {}

    async def _sahte_alt_ajan(deps, subtask, *, depth, run_agent):
        seen["persona"] = subtask.persona
        return SimpleNamespace(text="özet", ok=True, tool_calls=0)

    monkeypatch.setattr("fusion_cli.engines.agent.team.run_subagent", _sahte_alt_ajan)
    runner = extras.fork_runner(team_fork.run_forked_turn)
    await runner("incele", SimpleNamespace(live_history=None), history=[])

    assert "inceleyici" in cikti
    assert seen["persona"] == "inceleyici"
    assert TurnModelChoice().is_empty


async def test_masaustu_katalog_secimi_beceri_modelini_tura_uygular(tmp_path: Path, monkeypatch):
    """Masaüstü `yetenek.kullan` → sonraki tur becerinin modeli/eforu ve fork ajanıyla koşar."""
    from fusion_cli.appserver.protocol import Request
    from fusion_cli.appserver.session import AppSession
    from fusion_cli.cli import session as cli_session

    ev = tmp_path / "ev"
    beceri = ev / ".claude" / "skills" / "derin"
    beceri.mkdir(parents=True)
    (beceri / "SKILL.md").write_text(
        "---\nname: derin\ndescription: d\nmodel: saglayici/derin-model\neffort: low\n"
        "context: fork\nagent: inceleyici\ndisallowed-tools: Bash\n---\nİncele.",
        encoding="utf-8",
    )
    oturum = AppSession([].append, root=tmp_path, home=ev)
    gorulen: list[tuple[object, dict[str, object]]] = []

    async def _sahte(_task, config, **kwargs):
        gorulen.append((config, kwargs))
        return SimpleNamespace(ok=True, final_text="bitti", messages=[])

    monkeypatch.setattr(cli_session, "run_agent_task", _sahte)
    await oturum.handle(
        Request(id="1", name="yetenek.kullan", data={"tur": "beceri", "ad": "derin"})
    )
    await oturum.handle(Request(id="2", name="tur.calistir", data={"gorev": "incele"}))
    await oturum.handle(Request(id="3", name="tur.calistir", data={"gorev": "sıradan"}))

    (config, kwargs), (sonraki, _) = gorulen
    assert config.agent.model == "saglayici/derin-model"  # type: ignore[attr-defined]
    assert config.runtime.reasoning_effort is ReasoningEffort.LOW  # type: ignore[attr-defined]
    assert "run_shell" in kwargs["denied_tools"]  # type: ignore[operator]
    assert getattr(kwargs["turn_runner"], "keywords", {}) == {"persona": "inceleyici"}
    assert sonraki.agent.model != "saglayici/derin-model"  # type: ignore[attr-defined]
    await oturum.close()


def test_guvenilmeyen_projenin_becerisi_modeli_degistiremez(tmp_path: Path, monkeypatch):
    """Ölçüldü (31 Ekim): depo kaynaklı `/ad` becerisi `model:` ile turu güvenilmeyen
    projede bile başka bir sağlayıcıya yönlendirebiliyordu."""
    from fusion_cli.cli.repl import skill_commands

    root = tmp_path / "depo"
    folder = root / ".claude" / "skills" / "depo-becerisi"
    folder.mkdir(parents=True)
    folder.joinpath("SKILL.md").write_text(
        "---\nname: depo-becerisi\ndescription: d\nmodel: pahali/model\neffort: high\n---\nG",
        encoding="utf-8",
    )
    state = ReplState(
        config=make_config(agent=ModelSpec(name="agent", model="oturum/ana")),
        memory=null_memory(),
        root=root,
        home=tmp_path / "ev",
    )
    skill = state.capabilities.get_skill("depo-becerisi")  # type: ignore[union-attr]
    assert skill is not None and "proje" in skill.source
    trusted = SimpleNamespace(trusted=False)
    monkeypatch.setattr(skill_commands.trust, "resolve_project_trust", lambda _root: trusted)

    cikti = skill_handler(skill.qualified_name)(state, "")
    turn = state.take_pending_extras().turn_config(state.config)

    assert "uygulanmadı" in cikti and "fusion trust" in cikti
    assert turn.agent.model == "oturum/ana"
    assert turn.runtime.reasoning_effort is ReasoningEffort.HIGH

    trusted.trusted = True
    skill_handler(skill.qualified_name)(state, "")
    assert state.take_pending_extras().turn_config(state.config).agent.model == "pahali/model"


def test_kisa_ad_yapilandirilmis_claude_modeline_gecer():
    """Claude Code (#170): `model: opus` o modele geçirir."""
    from fusion_cli.engines.agent.skill_turn import resolve_turn_model

    sonuc = resolve_turn_model("opus", "", aliases={"opus": "anthropic/claude-opus-4"})

    assert sonuc.choice.model == "anthropic/claude-opus-4"
    assert resolve_turn_model("opus", "").choice.model == ""  # eşleme yoksa oturum modeli
