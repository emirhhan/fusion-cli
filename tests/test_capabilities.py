"""Skill/agent kütüphanesi: frontmatter, arama, araç eşleme, keşif."""

from __future__ import annotations

import pytest

from fusion_cli.tools.capabilities import (
    Capability,
    CapabilityRegistry,
    load_agent_prompt,
    load_skill_text,
    map_tools,
    parse_frontmatter,
    search,
)

SKILL = """---
name: pdf-doldur
description: PDF formlarını programatik olarak doldurur
---

# Talimat
Önce formu incele.
"""

AGENT = """---
name: guvenlik-denetcisi
description: Kod tabanında güvenlik açığı arar
tools: [Read, Grep, Bash]
---

Sen bir güvenlik denetçisisin. Sızıntı ve enjeksiyon ara.
"""


# --- Frontmatter -------------------------------------------------------------- #


def test_frontmatter_alanlari_okunur():
    fields = parse_frontmatter(SKILL)

    assert fields["name"] == "pdf-doldur"
    assert "PDF" in str(fields["description"])


def test_arac_listesi_ayristirilir():
    assert parse_frontmatter(AGENT)["tools"] == ("Read", "Grep", "Bash")


def test_yildiz_tam_yetki_demektir():
    assert parse_frontmatter("---\nname: a\ntools: '*'\n---\ngovde")["tools"] == ("*",)


def test_virgullu_arac_listesi_de_okunur():
    assert parse_frontmatter("---\nname: a\ntools: Read, Bash\n---\nx")["tools"] == ("Read", "Bash")


def test_frontmatter_yoksa_bos_doner():
    assert parse_frontmatter("# Sadece markdown\n") == {}


def test_kapanmamis_frontmatter_bos_doner():
    assert parse_frontmatter("---\nname: a\n") == {}


def test_tirnaklar_soyulur():
    assert parse_frontmatter("---\nname: 'a-b'\n---\nx")["name"] == "a-b"


# --- Araç eşleme --------------------------------------------------------------- #


def test_claude_arac_adlari_fusion_adlarina_cevrilir():
    mapped = map_tools(("Read", "Bash"))

    assert mapped is not None
    assert "read_file" in mapped and "run_shell" in mapped


def test_yildiz_kisitlama_yapmaz():
    assert map_tools(("*",)) is None


def test_bos_liste_kisitlama_yapmaz():
    assert map_tools(()) is None


def test_bilinmeyen_arac_adi_sessizce_atlanir():
    assert map_tools(("Uydurma", "Read")) == {"read_file", "view_file"}


# --- Arama --------------------------------------------------------------------- #


def _yetenek(name, description=""):
    from pathlib import Path

    return Capability(name=name, description=description, path=Path("x"), source="test")


def test_arama_ad_ve_aciklamada_eslesir():
    items = (_yetenek("pdf-doldur", "PDF formu"), _yetenek("excel", "tablo"))

    assert [item.name for item in search(items, "pdf")] == ["pdf-doldur"]


def test_cok_eslesen_one_gelir():
    items = (
        _yetenek("a", "güvenlik"),
        _yetenek("b", "güvenlik denetimi kod"),
    )

    assert search(items, "güvenlik kod denetimi")[0].name == "b"


def test_eslesmeyenler_elenir():
    assert search((_yetenek("a", "tablo"),), "pdf") == ()


def test_bos_sorgu_ilk_girdileri_dondurur():
    items = tuple(_yetenek(f"a{index}") for index in range(10))

    assert len(search(items, "", limit=3)) == 3


# --- Keşif --------------------------------------------------------------------- #


@pytest.fixture
def library(tmp_path):
    home, root = tmp_path / "home", tmp_path / "proje"
    (home / ".claude" / "skills" / "pdf").mkdir(parents=True)
    (home / ".claude" / "skills" / "pdf" / "SKILL.md").write_text(SKILL, encoding="utf-8")
    (home / ".claude" / "agents").mkdir(parents=True)
    (home / ".claude" / "agents" / "guvenlik.md").write_text(AGENT, encoding="utf-8")
    root.mkdir()
    return CapabilityRegistry(home, root)


def test_skill_kesfedilir(library):
    skills = library.skills()

    assert [item.name for item in skills] == ["pdf-doldur"]
    assert skills[0].source == "global"


def test_agent_kesfedilir_ve_araclari_okunur(library):
    agent = library.get_agent("guvenlik-denetcisi")

    assert agent is not None
    assert agent.tools == ("Read", "Grep", "Bash")


def test_proje_yerel_skill_de_bulunur(tmp_path):
    home, root = tmp_path / "home", tmp_path / "proje"
    home.mkdir()
    (root / ".claude" / "skills" / "yerel").mkdir(parents=True)
    (root / ".claude" / "skills" / "yerel" / "SKILL.md").write_text(
        "---\nname: yerel-beceri\ndescription: x\n---\ngovde", encoding="utf-8"
    )

    skills = CapabilityRegistry(home, root).skills()

    assert [item.name for item in skills] == ["yerel-beceri"]
    assert skills[0].source == "proje"


def test_ayni_ad_iki_kaynakta_varsa_ilki_kazanir(tmp_path):
    home, root = tmp_path / "home", tmp_path / "proje"
    for base in (home / ".claude" / "skills" / "a", root / ".claude" / "skills" / "a"):
        base.mkdir(parents=True)
        base.joinpath("SKILL.md").write_text(
            f"---\nname: ayni\ndescription: {base.parts[-3]}\n---\nx", encoding="utf-8"
        )

    skills = CapabilityRegistry(home, root).skills()

    assert len(skills) == 1
    assert skills[0].source == "global"


def test_olmayan_dizin_kesfi_dusurmez(tmp_path):
    registry = CapabilityRegistry(tmp_path / "yok", tmp_path / "yok2")

    assert registry.skills() == () and registry.agents() == ()


def test_skill_metni_okunur(library):
    skill = library.get_skill("pdf-doldur")

    assert skill is not None
    assert "Önce formu incele" in load_skill_text(skill.path)


def test_agent_promptu_frontmattersiz_doner(library):
    agent = library.get_agent("guvenlik-denetcisi")

    assert agent is not None
    prompt = load_agent_prompt(agent.path)
    assert prompt.startswith("Sen bir güvenlik denetçisisin")
    assert "name:" not in prompt


def test_okunamayan_dosya_hata_metni_dondurur(tmp_path):
    assert "okunamadı" in load_skill_text(tmp_path / "yok.md")
