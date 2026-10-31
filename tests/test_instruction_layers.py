"""Talimat hiyerarşisi (P-015) ve `@yol` içe aktarma (P-017) — saf fonksiyonlar.

Ölçüldü (31 Ekim): `read_project_instructions` kökteki İLK dosyayı okuyordu; `~/.claude/CLAUDE.md`,
`.claude/CLAUDE.md` ve `CLAUDE.local.md` hiç prompta girmiyordu; `@yol` sözdizimi yoktu.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fusion_cli.engines.agent.instruction_layers import (
    MAX_FILE_CHARS,
    MAX_IMPORT_CHARS,
    load_instruction_layers,
)
from fusion_cli.engines.agent.project_instructions import read_project_instructions


@pytest.fixture
def ev(tmp_path: Path) -> Path:
    home = tmp_path / "ev"
    home.mkdir()
    return home


@pytest.fixture
def proje(tmp_path: Path) -> Path:
    root = tmp_path / "proje"
    root.mkdir()
    return root


# --- Katmanlar ---------------------------------------------------------------- #


def test_kullanici_katmani_guvenilir_etiketle_once_gelir(ev, proje):
    (ev / ".claude").mkdir()
    (ev / ".claude" / "CLAUDE.md").write_text("her zaman Türkçe yaz", encoding="utf-8")
    (proje / "CLAUDE.md").write_text("proje kuralı", encoding="utf-8")

    yuk = load_instruction_layers(proje, ev)

    assert "her zaman Türkçe yaz" in yuk.text
    assert "proje kuralı" in yuk.text
    assert yuk.text.index("her zaman Türkçe yaz") < yuk.text.index("proje kuralı")
    assert '<kullanici_talimati kaynak="~/.claude/CLAUDE.md">' in yuk.text
    katmanlar = {dosya.label: dosya for dosya in yuk.files}
    assert katmanlar["~/.claude/CLAUDE.md"].trusted is True
    assert katmanlar["CLAUDE.md"].trusted is False


def test_codex_override_varsa_agents_md_yerine_okunur(ev, proje):
    (ev / ".codex").mkdir()
    (ev / ".codex" / "AGENTS.md").write_text("eski genel", encoding="utf-8")
    (ev / ".codex" / "AGENTS.override.md").write_text("yeni genel", encoding="utf-8")

    yuk = load_instruction_layers(proje, ev)

    assert "yeni genel" in yuk.text
    assert "eski genel" not in yuk.text


def test_proje_katmani_claude_md_ailesini_birlestirir(ev, proje):
    (proje / "CLAUDE.md").write_text("kök kural", encoding="utf-8")
    (proje / ".claude").mkdir()
    (proje / ".claude" / "CLAUDE.md").write_text("gizli klasör kuralı", encoding="utf-8")
    (proje / "CLAUDE.local.md").write_text("yerel kural", encoding="utf-8")
    (proje / "AGENTS.md").write_text("agents kuralı", encoding="utf-8")

    yuk = load_instruction_layers(proje, ev)

    assert "kök kural" in yuk.text
    assert "gizli klasör kuralı" in yuk.text
    assert "yerel kural" in yuk.text
    # Claude ailesi varken AGENTS.md ikinci bir kaynak olarak eklenmez (ilk aile kazanır).
    assert "agents kuralı" not in yuk.text


def test_ayni_icerikli_claude_ve_agents_dosyasi_iki_kez_okunmaz(ev, proje):
    (proje / "AGENTS.md").write_text("tek kural", encoding="utf-8")
    (proje / "CLAUDE.md").symlink_to(proje / "AGENTS.md")

    yuk = load_instruction_layers(proje, ev, merge=False)
    assert yuk.text.count("tek kural") == 1


def test_birlestirme_kapaliyken_eski_davranis_ilk_dosya(ev, proje):
    (ev / ".claude").mkdir()
    (ev / ".claude" / "CLAUDE.md").write_text("genel", encoding="utf-8")
    (proje / "CLAUDE.md").write_text("kök", encoding="utf-8")
    (proje / "CLAUDE.local.md").write_text("yerel", encoding="utf-8")

    yuk = load_instruction_layers(proje, ev, merge=False)

    assert "kök" in yuk.text
    assert "genel" not in yuk.text
    assert "yerel" not in yuk.text


def test_toplam_butce_asilinca_kirpma_acikca_bildirilir(ev, proje):
    (proje / "CLAUDE.md").write_text("a" * MAX_FILE_CHARS, encoding="utf-8")
    (proje / "CLAUDE.local.md").write_text("b" * MAX_FILE_CHARS, encoding="utf-8")

    yuk = load_instruction_layers(proje, ev, max_chars=MAX_FILE_CHARS + 100)

    assert yuk.text.count("a") >= MAX_FILE_CHARS
    assert "b" * 200 not in yuk.text
    assert yuk.trimmed_chars > 0
    assert "bütçe" in yuk.text
    assert any("CLAUDE.local.md" in not_ for not_ in yuk.notes)


def test_read_project_instructions_geri_uyumlu_tek_kok(proje):
    (proje / "AGENTS.md").write_text("kural: testsiz kod yok", encoding="utf-8")

    sonuc = read_project_instructions(proje)

    assert "kural: testsiz kod yok" in sonuc
    assert '<proje_talimati kaynak="AGENTS.md">' in sonuc


# --- @import ----------------------------------------------------------------- #


def test_at_import_kok_icindeki_dosyayi_getirir(ev, proje):
    (proje / "CLAUDE.md").write_text("Kurallar: @docs/kurallar.md", encoding="utf-8")
    (proje / "docs").mkdir()
    (proje / "docs" / "kurallar.md").write_text("ilk import", encoding="utf-8")

    yuk = load_instruction_layers(proje, ev)

    assert "ilk import" in yuk.text
    assert '<proje_kurali kaynak="docs/kurallar.md">' in yuk.text


def test_at_import_kod_blogunda_yok_sayilir(ev, proje):
    (proje / "CLAUDE.md").write_text("```\n@gizli.md\n```\nve `@satir.md` içi\n", encoding="utf-8")
    (proje / "gizli.md").write_text("blok içeriği", encoding="utf-8")
    (proje / "satir.md").write_text("satır içeriği", encoding="utf-8")

    yuk = load_instruction_layers(proje, ev)

    assert "blok içeriği" not in yuk.text
    assert "satır içeriği" not in yuk.text


def test_at_import_ozyinelemeli_ama_derinlik_sinirli(ev, proje):
    (proje / "CLAUDE.md").write_text("@a.md", encoding="utf-8")
    (proje / "a.md").write_text("seviye1 @b.md", encoding="utf-8")
    (proje / "b.md").write_text("seviye2 @c.md", encoding="utf-8")
    (proje / "c.md").write_text("seviye3 @d.md", encoding="utf-8")
    (proje / "d.md").write_text("seviye4", encoding="utf-8")

    yuk = load_instruction_layers(proje, ev)

    assert "seviye1" in yuk.text and "seviye2" in yuk.text and "seviye3" in yuk.text
    assert "seviye4" not in yuk.text


def test_at_import_dongu_korumasi(ev, proje):
    (proje / "CLAUDE.md").write_text("@a.md", encoding="utf-8")
    (proje / "a.md").write_text("a içeriği @b.md", encoding="utf-8")
    (proje / "b.md").write_text("b içeriği @a.md @CLAUDE.md", encoding="utf-8")

    yuk = load_instruction_layers(proje, ev)

    assert yuk.text.count("a içeriği") == 1
    assert yuk.text.count("b içeriği") == 1


def test_proje_katmaninda_kok_disi_import_atlanir_ve_notta_gorunur(ev, proje):
    disari = proje.parent / "sizinti.md"
    disari.write_text("sızdırılan içerik", encoding="utf-8")
    (proje / "CLAUDE.md").write_text("@../sizinti.md ve @~/.ssh/config", encoding="utf-8")

    yuk = load_instruction_layers(proje, ev)

    assert "sızdırılan içerik" not in yuk.text
    assert any("sizinti.md" in not_ for not_ in yuk.notes)


def test_kullanici_katmaninda_tilde_import_izinli(ev, proje, monkeypatch):
    (ev / ".claude").mkdir()
    (ev / ".claude" / "CLAUDE.md").write_text("@~/.claude/ortak.md", encoding="utf-8")
    (ev / ".claude" / "ortak.md").write_text("ortak kullanıcı kuralı", encoding="utf-8")

    yuk = load_instruction_layers(proje, ev)

    assert "ortak kullanıcı kuralı" in yuk.text
    assert '<kullanici_kurali kaynak="~/.claude/ortak.md">' in yuk.text


def test_at_import_butcesi_asilmaz(ev, proje):
    (proje / "CLAUDE.md").write_text("@buyuk.md", encoding="utf-8")
    (proje / "buyuk.md").write_text("x" * (MAX_IMPORT_CHARS * 2), encoding="utf-8")

    yuk = load_instruction_layers(proje, ev)

    assert yuk.text.count("x") <= MAX_IMPORT_CHARS


def test_eposta_ve_paket_adi_import_sayilmaz(ev, proje):
    (proje / "CLAUDE.md").write_text(
        "yazar ali@ornek.com, paket @anthropic-ai/sdk kullanılır", encoding="utf-8"
    )

    yuk = load_instruction_layers(proje, ev)

    assert yuk.notes == ()
    assert "ali@ornek.com" in yuk.text


# --- İnceleme bulguları (31 Ekim) --------------------------------------------- #


def test_proje_kokundeki_kok_disi_sembolik_bag_okunmaz(ev, proje, tmp_path):
    """Ölçüldü: `.claude/CLAUDE.md -> ~/.ssh/id_rsa` bağı proje talimatı olarak prompta girdi."""
    sir = tmp_path / "sir.txt"
    sir.write_text("TOPSECRET", encoding="utf-8")
    (proje / ".claude").mkdir()
    (proje / ".claude" / "CLAUDE.md").symlink_to(sir)
    (proje / "CLAUDE.local.md").symlink_to(sir)
    (proje / "AGENTS.md").write_text("gerçek talimat", encoding="utf-8")

    yuk = load_instruction_layers(proje, ev)

    assert "TOPSECRET" not in yuk.text
    assert "gerçek talimat" in yuk.text
    assert sum("sembolik bağ" in not_ for not_ in yuk.notes) == 2
