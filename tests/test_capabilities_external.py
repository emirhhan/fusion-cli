"""Diğer araçların skill ve agent kütüphanelerinin keşfi."""

from __future__ import annotations

from fusion_cli.tools.capabilities import CapabilityRegistry, load_agent_prompt

SKILL = """---
name: {name}
description: {desc}
---

Gövde.
"""


def _skill_yaz(kok, ad, desc="açıklama"):
    hedef = kok / ad
    hedef.mkdir(parents=True, exist_ok=True)
    (hedef / "SKILL.md").write_text(SKILL.format(name=ad, desc=desc), encoding="utf-8")


def test_codex_skilleri_bulunur(tmp_path):
    _skill_yaz(tmp_path / ".codex" / "skills" / ".system", "imagegen")

    isimler = {s.name: s.source for s in CapabilityRegistry(tmp_path, tmp_path).skills()}

    assert isimler.get("imagegen") == "codex"


def test_hermes_skilleri_bulunur(tmp_path):
    _skill_yaz(tmp_path / ".hermes" / "skills" / "research", "deep-research")

    isimler = {s.name: s.source for s in CapabilityRegistry(tmp_path, tmp_path).skills()}

    assert isimler.get("deep-research") == "hermes"


def test_claude_ayni_adli_skili_yener(tmp_path):
    _skill_yaz(tmp_path / ".claude" / "skills", "ortak", desc="claude sürümü")
    _skill_yaz(tmp_path / ".hermes" / "skills", "ortak", desc="hermes sürümü")

    bulunan = {s.name: s for s in CapabilityRegistry(tmp_path, tmp_path).skills()}

    assert bulunan["ortak"].source == "global"


def test_kaynak_yoksa_kesif_dusmez(tmp_path):
    assert CapabilityRegistry(tmp_path, tmp_path).skills() == ()


TOML_AGENT = '''
name = "architect"
description = "Sistem tasarımı uzmanı"
developer_instructions = """
Sen bir mimarsın.
"""
'''


def _toml_agent_yaz(home, ad, govde=TOML_AGENT):
    hedef = home / ".codex" / "agents"
    hedef.mkdir(parents=True, exist_ok=True)
    icerik = govde.replace('name = "architect"', f'name = "{ad}"')
    (hedef / f"{ad}.toml").write_text(icerik, encoding="utf-8")


def test_codex_toml_agenti_bulunur(tmp_path):
    _toml_agent_yaz(tmp_path, "architect")

    bulunan = {a.name: a for a in CapabilityRegistry(tmp_path, tmp_path).agents()}

    assert bulunan["architect"].description == "Sistem tasarımı uzmanı"
    assert bulunan["architect"].source == "codex"


def test_bozuk_toml_kesfi_dusurmez(tmp_path):
    _toml_agent_yaz(tmp_path, "saglam")
    _toml_agent_yaz(tmp_path, "bozuk", govde='name = "bozuk"\ndescription = ')

    isimler = {a.name for a in CapabilityRegistry(tmp_path, tmp_path).agents()}

    assert "saglam" in isimler
    assert "bozuk" not in isimler


def test_adsiz_toml_dosya_adina_duser(tmp_path):
    _toml_agent_yaz(tmp_path, "adsiz", govde='description = "yalnız açıklama"')

    isimler = {a.name for a in CapabilityRegistry(tmp_path, tmp_path).agents()}

    assert "adsiz" in isimler


def test_claude_agenti_ayni_adli_codex_agentini_yener(tmp_path):
    hedef = tmp_path / ".claude" / "agents"
    hedef.mkdir(parents=True)
    (hedef / "architect.md").write_text(
        "---\nname: architect\ndescription: claude sürümü\n---\n", encoding="utf-8"
    )
    _toml_agent_yaz(tmp_path, "architect")

    bulunan = {a.name: a for a in CapabilityRegistry(tmp_path, tmp_path).agents()}

    assert bulunan["architect"].source == "global"


def test_codex_toml_agent_promptu_developer_talimati_doner(tmp_path):
    _toml_agent_yaz(tmp_path, "architect")
    agent = CapabilityRegistry(tmp_path, tmp_path).get_agent("architect")

    assert agent is not None
    prompt = load_agent_prompt(agent.path)

    assert prompt.strip() == "Sen bir mimarsın."
    assert "developer_instructions" not in prompt


def test_bozuk_ve_eksik_codex_promptu_bos_doner(tmp_path):
    _toml_agent_yaz(tmp_path, "bozuk", govde='name = "bozuk"\ndescription = ')
    _toml_agent_yaz(tmp_path, "eksik", govde='name = "eksik"')

    assert load_agent_prompt(tmp_path / ".codex" / "agents" / "bozuk.toml") == ""
    assert load_agent_prompt(tmp_path / ".codex" / "agents" / "eksik.toml") == ""
