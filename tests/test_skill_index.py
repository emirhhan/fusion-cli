"""Beceri dizininin sistem bağlamına bütçeli enjeksiyonu (P-018).

Ölçüldü (31 Ekim): capabilities.py 'Liste modele BASILMAZ' diyordu; expertise.py ölçümüne göre
model find_skill'i 1.696 araç çağrısında 0 kez çağırdı — beceriler fiilen görünmezdi.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fusion_cli.core.types import Message
from fusion_cli.engines.agent import loop as agent_loop
from fusion_cli.engines.agent.skill_index import (
    DESCRIPTION_CHARS,
    HEADER,
    index_budget_for,
    skill_index_block,
)
from fusion_cli.tools.capabilities import CapabilityRegistry

from .fakes import RecordingSink, ScriptedProvider, make_config, model_result
from .test_agent_loop import _deps, _kur


def _skill(home: Path, name: str, description: str, extra: str = "") -> None:
    folder = home / ".claude" / "skills" / name
    folder.mkdir(parents=True)
    folder.joinpath("SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n{extra}---\nGövde {name}",
        encoding="utf-8",
    )


@pytest.fixture
def ev(tmp_path: Path) -> Path:
    home = tmp_path / "ev"
    _skill(home, "pdf-doldur", "PDF formlarını programatik olarak doldurur")
    _skill(home, "seo", "x" * (DESCRIPTION_CHARS + 80))
    _skill(home, "gizli", "yalnız kullanıcı çağırır", "disable-model-invocation: true\n")
    return home


def test_dizin_ad_ve_kirpilmis_aciklama_tasir(ev, tmp_path):
    blok = skill_index_block(CapabilityRegistry(ev, tmp_path / "proje"))

    assert blok.startswith(HEADER)
    assert "- pdf-doldur — PDF formlarını programatik olarak doldurur" in blok
    satir = next(s for s in blok.splitlines() if s.startswith("- seo"))
    assert len(satir) <= len("- seo — ") + DESCRIPTION_CHARS
    assert satir.endswith("…")


def test_disable_model_invocation_dizine_girmez(ev, tmp_path):
    blok = skill_index_block(CapabilityRegistry(ev, tmp_path / "proje"))

    assert "gizli" not in blok


def test_butce_asilinca_adlar_kalir_aciklama_sondan_duser(ev, tmp_path):
    """Claude Code (#164): her ad her zaman listede; aşımda açıklamalar düşer."""
    blok = skill_index_block(CapabilityRegistry(ev, tmp_path / "proje"), budget=len(HEADER) + 70)

    assert "pdf-doldur" in blok
    assert "\n- seo" in blok  # ad kaldı, açıklaması düştü
    assert "beceri daha" not in blok


def test_bos_kutuphane_ve_sifir_butce_bos_doner(tmp_path):
    bos = CapabilityRegistry(tmp_path / "yok", tmp_path / "proje")

    assert skill_index_block(bos) == ""
    assert skill_index_block(None) == ""


def test_butce_ayardan_ve_pencereden_gelir():
    config = make_config()

    assert index_budget_for(config) > 0


def test_butce_pencerenin_yuzde_biri_ayar_ve_ortam_degiskeni(tmp_path, monkeypatch):
    """Claude Code (#164): %1 varsayılan, ayar ve SLASH_COMMAND_TOOL_CHAR_BUDGET."""
    import json
    from types import SimpleNamespace

    from fusion_cli.engines.agent import skill_index
    from fusion_cli.engines.agent.context_budget import CHARS_PER_TOKEN_ESTIMATE
    from fusion_cli.engines.agent.skill_index import description_limit

    config = make_config()
    window = 200_000
    monkeypatch.setattr(
        skill_index, "context_budget", lambda *_: SimpleNamespace(window_tokens=window)
    )
    beklenen = int(window * CHARS_PER_TOKEN_ESTIMATE * 0.01)
    assert index_budget_for(config, root=tmp_path) == beklenen
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text(
        json.dumps({"skillListingBudgetFraction": 0.02, "skillListingMaxDescChars": 200}),
        encoding="utf-8",
    )
    assert index_budget_for(config, root=tmp_path) == int(window * CHARS_PER_TOKEN_ESTIMATE * 0.02)
    assert description_limit(tmp_path, None) == 200
    assert description_limit(None, None) == 1_536
    monkeypatch.setenv("SLASH_COMMAND_TOOL_CHAR_BUDGET", "1234")
    assert index_budget_for(config, root=tmp_path) == 1234


async def test_dizin_kok_turun_sistem_baglamina_girer(monkeypatch, tmp_path, ev):
    provider = _kur(monkeypatch, ScriptedProvider([model_result("tamam")]))
    deps = _deps(tmp_path, RecordingSink(), home=ev)
    deps.capabilities = CapabilityRegistry(ev, tmp_path)

    await agent_loop.run_agent("merhaba", deps)

    sistem = provider.seen_messages[0][0]
    assert isinstance(sistem, Message) and sistem.role == "system"
    assert HEADER in sistem.content
    assert "pdf-doldur" in sistem.content and "gizli" not in sistem.content


def test_find_skill_disable_model_invocation_olani_gostermez(ev, tmp_path):
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.engines.agent.engine_tools import _find_skill_tool

    tool = _find_skill_tool(CapabilityRegistry(ev, tmp_path / "proje"))
    sonuc = tool.run({"query": "kullanıcı çağırır"}, ToolContext(root=tmp_path))

    assert "gizli" not in sonuc.output


def test_proje_becerileri_tek_duz_listede(ev, tmp_path):
    """Claude Code (#181): proje becerisi ayrı blokta ya da güvenilmezlik notuyla işaretlenmez."""
    proje = tmp_path / "proje"
    folder = proje / ".claude" / "skills" / "tuzak"
    folder.mkdir(parents=True)
    folder.joinpath("SKILL.md").write_text(
        "---\nname: tuzak\ndescription: Proje becerisi\n---\nx", encoding="utf-8"
    )

    blok = skill_index_block(CapabilityRegistry(ev, proje))

    assert "- pdf-doldur" in blok and "- tuzak — Proje becerisi" in blok
    assert "<proje_becerileri>" not in blok and "DEĞİLDİR" not in blok


def test_butce_asilinca_az_cagrilanin_aciklamasi_once_duser(tmp_path):
    """Belge: bütçe dolunca en az çağrılan becerilerin açıklaması önce düşer (#156)."""
    from fusion_cli.engines.agent import skill_usage

    home = tmp_path / "ev2"
    _skill(home, "alfa", "A" * 60)
    _skill(home, "beta", "B" * 60)
    registry = CapabilityRegistry(home, tmp_path)
    memory = tmp_path / "bellek"
    for _ in range(3):
        skill_usage.record_invocation(memory, "alfa")
    budget = len(HEADER) + 100

    block = skill_index_block(registry, budget, usage=skill_usage.load_counts(memory))

    assert "A" * 60 in block  # sık çağrılan açıklamasını korur
    assert "B" * 60 not in block and "beta" in block  # adı kalır
    assert skill_usage.load_counts(memory) == {"alfa": 3}
