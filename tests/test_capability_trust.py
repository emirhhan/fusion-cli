"""Kurulu üçüncü taraf repo yerel dosya sızdıramaz; aynı adlı skill belirsizliği söylenir.

T1-15: Ölçüldü (29 Ekim) — `fusion yetenek kur` ile gelen repodaki `SKILL.md`, `~/.ssh/id_rsa`
gibi kök dışı bir dosyaya sembolik bağ olabilir; keşif (`_read_head`) ve `read_skill`
bağı izleyip içeriği modele veriyordu. `skill_pages.skill_file` ek dosyalarda kök denetimi
yapıyordu, keşif/başlık okumada yoktu.

T1-14: `get_skill(ad)` aynı adlı farklı içerikli skill'lerde None döner (kaynak seçimi
bilinçli, bkz. test_capabilities_external); ama model "yok" mesajı alıyordu.
"""

from __future__ import annotations

import pytest

from fusion_cli.tools import capabilities as capabilities_module
from fusion_cli.tools.capabilities import CapabilityRegistry

SKILL = "---\nname: {ad}\ndescription: {desc}\n---\nGövde.\n"


@pytest.fixture
def kurulu_kok(tmp_path, monkeypatch):
    kok = tmp_path / "yetenekler"
    kok.mkdir()
    monkeypatch.setattr(capabilities_module, "capabilities_dir", lambda: kok)
    return kok


def test_kurulu_repodaki_kok_disina_sembolik_skill_atlanir(tmp_path, kurulu_kok):
    sir = tmp_path / "ev" / ".ssh" / "id_rsa"
    sir.parent.mkdir(parents=True)
    sir.write_text("-----BEGIN OPENSSH PRIVATE KEY-----\n", encoding="utf-8")
    depo = kurulu_kok / "kotu-repo" / "skills" / "tuzak"
    depo.mkdir(parents=True)
    (depo / "SKILL.md").symlink_to(sir)

    registry = CapabilityRegistry(tmp_path / "ev", tmp_path / "proje")

    assert "tuzak" not in {s.name for s in registry.skills()}
    assert registry.get_skill("tuzak") is None


def test_kurulu_repodaki_kok_disina_sembolik_ajan_atlanir(tmp_path, kurulu_kok):
    sir = tmp_path / "gizli.md"
    sir.write_text("---\nname: ajan\n---\nparola=1\n", encoding="utf-8")
    depo = kurulu_kok / "kotu-repo" / "agents"
    depo.mkdir(parents=True)
    (depo / "ajan.md").symlink_to(sir)

    registry = CapabilityRegistry(tmp_path / "ev", tmp_path / "proje")

    assert "ajan" not in {a.name for a in registry.agents()}


def test_kurulu_repo_icindeki_sembolik_baglar_calisir(tmp_path, kurulu_kok):
    depo = kurulu_kok / "iyi-repo"
    (depo / "ortak").mkdir(parents=True)
    (depo / "ortak" / "SKILL.md").write_text(SKILL.format(ad="ic", desc="d"), encoding="utf-8")
    (depo / "takma").mkdir()
    (depo / "takma" / "SKILL.md").symlink_to(depo / "ortak" / "SKILL.md")

    registry = CapabilityRegistry(tmp_path / "ev", tmp_path / "proje")

    assert {s.name for s in registry.skills()} == {"ic"}


def test_kullanicinin_kendi_sembolik_skilli_calismaya_devam_eder(tmp_path, kurulu_kok):
    """Güvenilir kökler (~/.claude/skills) dotfile yöneticileriyle bağ kullanabilir."""
    gercek = tmp_path / "dotfiles" / "SKILL.md"
    gercek.parent.mkdir(parents=True)
    gercek.write_text(SKILL.format(ad="benim", desc="d"), encoding="utf-8")
    hedef = tmp_path / "ev" / ".claude" / "skills" / "benim"
    hedef.mkdir(parents=True)
    (hedef / "SKILL.md").symlink_to(gercek)

    registry = CapabilityRegistry(tmp_path / "ev", tmp_path / "proje")

    assert registry.get_skill("benim") is not None


def test_belirsiz_skill_adi_nitelikli_adaylarla_aciklanir(tmp_path, kurulu_kok):
    ev, proje = tmp_path / "ev", tmp_path / "proje"
    for kok, desc in ((ev / ".claude" / "skills", "a"), (proje / ".fusion" / "skills", "b")):
        (kok / "ortak").mkdir(parents=True)
        (kok / "ortak" / "SKILL.md").write_text(SKILL.format(ad="ortak", desc=desc), "utf-8")
    (ev / ".hermes" / "skills" / "ortak").mkdir(parents=True)
    (ev / ".hermes" / "skills" / "ortak" / "SKILL.md").write_text(
        SKILL.format(ad="ortak", desc="c"), "utf-8"
    )

    registry = CapabilityRegistry(ev, proje)

    assert registry.get_skill("ortak") is None
    adaylar = registry.candidates("ortak")
    assert len(adaylar) == 3
    assert all(ad.startswith("ortak@") for ad in adaylar)
    assert all(registry.get_skill(ad) is not None for ad in adaylar)
    assert registry.candidates("yok-boyle-bir-sey") == ()


def test_read_skill_araci_belirsizlikte_adaylari_soyler(tmp_path, kurulu_kok):
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.engines.agent.engine_tools import _read_skill_tool

    ev, proje = tmp_path / "ev", tmp_path / "proje"
    for kok, desc in ((ev / ".claude" / "skills", "a"), (proje / ".fusion" / "skills", "b")):
        (kok / "ortak").mkdir(parents=True)
        (kok / "ortak" / "SKILL.md").write_text(SKILL.format(ad="ortak", desc=desc), "utf-8")
    registry = CapabilityRegistry(ev, proje)

    sonuc = _read_skill_tool(registry).run({"name": "ortak"}, ToolContext(root=proje))

    assert not sonuc.ok
    assert "birden çok kaynakta" in sonuc.output and "ortak@" in sonuc.output
