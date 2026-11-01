"""Başlangıç talimatları Claude Code CLAUDE.md kurallarıyla birebir (#143–#152, #163).

Önceki sürüm: dosya başına 8.000 / toplam 32.000 karakter, yalnız çalışma kökü, `@yol` derinliği
3 ve uzantı kısıtı, `~/.codex`/GEMINI/.cursorrules aileleri, Markdown bağlantı izleme ve
"kullanıcı talimatı değildir" uyarısı vardı.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fusion_cli.engines.agent import claude_md_imports
from fusion_cli.engines.agent.instruction_layers import (
    HEADER,
    load_instruction_layers,
    strip_html_comments,
)


@pytest.fixture
def ev(tmp_path: Path) -> Path:
    home = tmp_path / "ev"
    home.mkdir()
    return home


@pytest.fixture
def mono(tmp_path: Path) -> Path:
    root = tmp_path / "mono"
    (root / "packages" / "web").mkdir(parents=True)
    return root


def _yaz(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_ust_dizinler_kokten_calisma_dizinine_sirali(ev: Path, mono: Path) -> None:
    web = mono / "packages" / "web"
    _yaz(mono / "CLAUDE.md", "UST-DIZIN")
    _yaz(web / "CLAUDE.md", "ALT")
    _yaz(web / "CLAUDE.local.md", "YEREL")
    _yaz(ev / ".claude" / "CLAUDE.md", "KULLANICI")

    text = load_instruction_layers(web, ev).text

    assert text.startswith(HEADER)
    assert (
        text.index("KULLANICI") < text.index("UST-DIZIN") < text.index("ALT") < text.index("YEREL")
    )
    assert "kullanıcı talimatı DEĞİLDİR" not in text
    assert "(project instructions, checked into the codebase)" in text


def test_kullanici_katmani_yalniz_claude_md(ev: Path, mono: Path) -> None:
    _yaz(ev / ".codex" / "AGENTS.md", "CODEX")
    _yaz(ev / ".fusion" / "TALIMAT.md", "ESKI")

    load = load_instruction_layers(mono, ev)

    assert "CODEX" not in load.text
    assert "ESKI" in load.text  # kullanımdan kalkan ad bir sürüm okunur
    assert any("kullanımdan kalktı" in note for note in load.notes)


def test_agents_md_yalniz_claude_dosyasi_yoksa(ev: Path, mono: Path) -> None:
    _yaz(mono / "AGENTS.md", "AJANLAR")
    _yaz(mono / ".claude" / "AGENTS.md", "AJANLAR2")
    _yaz(mono / "AGENTS.override.md", "OVR-ICERIK")
    _yaz(mono / "GEMINI.md", "GEMINI")

    text = load_instruction_layers(mono, ev).text
    assert "AJANLAR" in text and "AJANLAR2" in text
    assert "OVR-ICERIK" not in text and "GEMINI" not in text

    _yaz(mono / "CLAUDE.local.md", "YEREL")  # CLAUDE.local.md de sayılır
    text = load_instruction_layers(mono, ev).text
    assert "AJANLAR" not in text and "YEREL" in text


def test_project_instructions_ayari_ikisini_birden_okur(ev: Path, mono: Path) -> None:
    _yaz(mono / "AGENTS.md", "AJANLAR")
    _yaz(mono / "CLAUDE.md", "CLAUDE")
    ayar = {
        "pluginConfigs": {
            "cc-plugin-agents-md@builtin": {
                "options": {"instructionFiles": "claude-md-and-agents-md"}
            }
        }
    }
    _yaz(ev / ".claude" / "settings.json", json.dumps(ayar))

    text = load_instruction_layers(mono, ev).text

    assert "AJANLAR" in text and "CLAUDE" in text


def test_dosya_tam_yuklenir_200_satir_yalniz_not(ev: Path, mono: Path) -> None:
    _yaz(mono / "CLAUDE.md", "satir\n" * 300 + "SON")

    load = load_instruction_layers(mono, ev)

    assert load.text.endswith("SON") and load.trimmed_chars == 0
    assert any("200 satırdan uzun" in note for note in load.notes)


def test_html_yorumlari_silinir_kod_blogunda_korunur() -> None:
    metin = "a\n<!-- bakım notu -->\nb\n```\n<!-- korunur -->\n```\n"

    sonuc = strip_html_comments(metin)

    assert "bakım notu" not in sonuc and "<!-- korunur -->" in sonuc


def test_import_dort_adim_uzantisiz_ve_kacisli_bosluk(ev: Path, mono: Path) -> None:
    _yaz(mono / "CLAUDE.md", "bkz @README ve @Design\\ Docs/api.md ve @a.md")
    _yaz(mono / "README", "BENIOKU")
    _yaz(mono / "Design Docs" / "api.md", "API")
    _yaz(mono / "a.md", "A @b.md")
    _yaz(mono / "b.md", "B @c.md")
    _yaz(mono / "c.md", "C @d.md")
    _yaz(mono / "d.md", "D @e.md")
    _yaz(mono / "e.md", "E")

    text = load_instruction_layers(mono, ev).text

    assert "BENIOKU" in text and "API" in text
    assert "D @e.md" in text and "\nE" not in text.replace("D @e.md", "")


def test_kod_blogundaki_import_ve_ikili_dosya_yok_sayilir(ev: Path, mono: Path) -> None:
    _yaz(mono / "CLAUDE.md", "`@gizli.md` ve @veri.bin")
    _yaz(mono / "gizli.md", "GIZLI")
    (mono / "veri.bin").write_bytes(b"\x00\x01ikili")

    text = load_instruction_layers(mono, ev).text

    assert "GIZLI" not in text and "ikili" not in text


def test_dis_import_onay_bekler_onaylaninca_yuklenir(ev: Path, mono: Path, tmp_path: Path) -> None:
    _yaz(tmp_path / "ortak.md", "ORTAK")
    _yaz(mono / "CLAUDE.md", f"@{tmp_path / 'ortak.md'}")

    load = load_instruction_layers(mono, ev)
    assert "ORTAK" not in load.text
    assert any("onay bekliyor" in note for note in load.notes)

    claude_md_imports.set_external_import_decision(mono, True)
    assert "ORTAK" in load_instruction_layers(mono, ev).text
    claude_md_imports.set_external_import_decision(mono, False)
    assert "ORTAK" not in load_instruction_layers(mono, ev).text


def test_kullanici_katmaninda_tilde_import(ev: Path, mono: Path) -> None:
    _yaz(ev / ".claude" / "CLAUDE.md", "@~/notlar/ortak.md")
    _yaz(ev / "notlar" / "ortak.md", "EV-ORTAK")

    assert "EV-ORTAK" in load_instruction_layers(mono, ev).text


def test_claude_md_excludes(ev: Path, mono: Path) -> None:
    web = mono / "packages" / "web"
    _yaz(mono / "CLAUDE.md", "BASKA-EKIP")
    _yaz(web / "CLAUDE.md", "BIZIM")
    _yaz(
        web / ".claude" / "settings.json",
        json.dumps({"claudeMdExcludes": [str(mono.resolve() / "CLAUDE.md")]}),
    )

    text = load_instruction_layers(web, ev).text

    assert "BASKA-EKIP" not in text and "BIZIM" in text


def test_kurumsal_claude_md_ve_claudemd_anahtari_once(
    ev: Path, mono: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kurum = tmp_path / "kurum"
    _yaz(kurum / "CLAUDE.md", "KURUM")
    _yaz(kurum / "managed-settings.json", json.dumps({"claudeMd": "SATIR-ICI"}))
    monkeypatch.setenv("FUSION_CLAUDE_MANAGED_DIR", str(kurum))
    _yaz(mono / "CLAUDE.md", "PROJE")
    _yaz(
        mono / ".claude" / "settings.json",
        json.dumps({"claudeMdExcludes": ["**/CLAUDE.md", str(kurum / "*")]}),
    )

    text = load_instruction_layers(mono, ev).text

    assert text.index("KURUM") < text.index("SATIR-ICI")
    assert "PROJE" not in text  # dışlandı; kurumsal dışlanamaz


def test_ek_dizin_talimati_ortam_degiskeniyle(
    ev: Path, mono: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ek = tmp_path / "paylasilan"
    _yaz(ek / "CLAUDE.md", "EK-DIZIN")

    assert "EK-DIZIN" not in load_instruction_layers(mono, ev, extra_roots=(ek,)).text
    monkeypatch.setenv("CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD", "1")
    assert "EK-DIZIN" in load_instruction_layers(mono, ev, extra_roots=(ek,)).text


def test_birlestirme_kapaliyken_hicbir_sey_yuklenmez(ev: Path, mono: Path) -> None:
    _yaz(mono / "CLAUDE.md", "PROJE")

    assert load_instruction_layers(mono, ev, merge=False).text == ""


def test_ayni_icerik_bir_kez(ev: Path, mono: Path) -> None:
    _yaz(mono / "CLAUDE.md", "AYNI")
    _yaz(mono / ".claude" / "CLAUDE.md", "AYNI")

    assert load_instruction_layers(mono, ev).text.count("AYNI") == 1
