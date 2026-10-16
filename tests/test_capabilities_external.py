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


def test_farkli_skill_icerikleri_kaynaklariyla_ayri_kalir(tmp_path):
    _skill_yaz(tmp_path / ".claude" / "skills", "ortak", desc="claude sürümü")
    _skill_yaz(tmp_path / ".hermes" / "skills", "ortak", desc="hermes sürümü")

    entries = [
        item for item in CapabilityRegistry(tmp_path, tmp_path).skills() if item.name == "ortak"
    ]
    assert {item.source for item in entries} == {"claude+proje", "hermes"}
    assert {item.description for item in entries} == {"claude sürümü", "hermes sürümü"}


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


def test_farkli_agent_kaynaklari_ayri_secilebilir(tmp_path):
    hedef = tmp_path / ".claude" / "agents"
    hedef.mkdir(parents=True)
    (hedef / "architect.md").write_text(
        "---\nname: architect\ndescription: claude sürümü\n---\n", encoding="utf-8"
    )
    _toml_agent_yaz(tmp_path, "architect")

    registry = CapabilityRegistry(tmp_path, tmp_path)
    entries = [item for item in registry.agents() if item.name == "architect"]
    assert {item.source for item in entries} == {"claude+proje", "codex"}
    assert registry.get_agent("architect") is None
    assert all(registry.get_agent(item.qualified_name) == item for item in entries)


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


def test_project_skill_source_selected_explicitly(tmp_path) -> None:
    root = tmp_path / "proje"
    _skill_yaz(root / ".claude" / "skills", "ortak", desc="proje sürümü")
    _skill_yaz(tmp_path / ".codex" / "skills", "ortak", desc="codex sürümü")
    _skill_yaz(tmp_path / ".hermes" / "skills", "ortak", desc="hermes sürümü")

    registry = CapabilityRegistry(tmp_path, root)
    assert registry.get_skill("ortak") is None
    selected = next(
        item for item in registry.skills() if item.name == "ortak" and item.source == "proje"
    )
    capability = registry.get_skill(selected.qualified_name)

    assert capability is not None
    assert capability.source == "proje"
    assert capability.description == "proje sürümü"


def test_project_agent_source_selected_explicitly(tmp_path) -> None:
    root = tmp_path / "proje"
    target = root / ".claude" / "agents"
    target.mkdir(parents=True)
    (target / "architect.md").write_text(
        "---\nname: architect\ndescription: proje sürümü\n---\n", encoding="utf-8"
    )
    _toml_agent_yaz(tmp_path, "architect")

    registry = CapabilityRegistry(tmp_path, root)
    assert registry.get_agent("architect") is None
    selected = next(
        item for item in registry.agents() if item.name == "architect" and item.source == "proje"
    )
    capability = registry.get_agent(selected.qualified_name)

    assert capability is not None
    assert capability.source == "proje"
    assert capability.description == "proje sürümü"


def test_ayni_ad_birden_fazla_kaynaktaysa_hepsi_etikette_gorunur(tmp_path):
    """Çakışan yetenek listeyi ikiye katlamaz; kaynaklar TEK etikette birleşir.

    Ölçüldü: Codex'in 97 agent'ının 97'si de Claude'unkilerle aynı adı taşıyor ve
    içerikleri bayt bayt aynı. İki ayrı satır göstermek listeyi ikiye katlar ve
    hiçbir yeni yetenek kazandırmaz. Kullanıcının sorusu "bu nereden geliyor?"
    olduğuna göre doğru cevap tek satırda tüm kaynakları göstermektir.
    """
    home, root = tmp_path / "ev", tmp_path / "proje"
    _skill_yaz(home / ".claude" / "skills", "ortak", desc="claude sürümü")
    _skill_yaz(home / ".codex" / "skills", "ortak", desc="claude sürümü")

    bulunan = {s.name: s for s in CapabilityRegistry(home, root).skills()}

    assert bulunan["ortak"].source == "claude+codex"
    # İçerik ÖNCELİKLİ kaynaktan gelir; yalnız etiket birleşir.
    assert bulunan["ortak"].description == "claude sürümü"


def test_tek_kaynakli_yetenegin_etiketi_sade_kalir(tmp_path):
    home, root = tmp_path / "ev", tmp_path / "proje"
    _skill_yaz(home / ".hermes" / "skills", "yalniz-hermes")

    bulunan = {s.name: s for s in CapabilityRegistry(home, root).skills()}

    assert bulunan["yalniz-hermes"].source == "hermes"


def test_claude_kutuphanesi_arac_adiyla_etiketlenir(tmp_path):
    """Etiket "nereden geldiğini" söylemeli; birden çok araç varken "global" belirsizdir."""
    home, root = tmp_path / "ev", tmp_path / "proje"
    _skill_yaz(home / ".claude" / "skills", "claude-skili")

    bulunan = {s.name: s for s in CapabilityRegistry(home, root).skills()}

    assert bulunan["claude-skili"].source == "claude"
