"""Adım, kendisine hiç söylenmemiş bir dosya yolundan sorumlu tutulamaz.

Ölçüldü (7 Eylül canlı Godot koşusu, `game-manager-eksiklerini-tamamla`): plan
adıma `scripts/game_manager.gd` hedefli bir kontrol iliştirdi, adım istemi ise
yalnız başarı koşulunun METNİNİ taşıyordu. Model dosyayı başka bir ada yazdı,
kapı tahmin edilen yola baktı ve "kontrol hedefi dosya bulunamadı" ile düştü;
üç deneme de aynı duvara çarptı ve koşu öldü.

Kapının ölçtüğü yol, adımın gördüğü yol olmalıdır.
"""

from __future__ import annotations

from dataclasses import replace

from fusion_cli.core.execution_plan import VerificationCheck, VerificationCheckKind
from fusion_cli.engines.agent.plan_context import measurement_block, step_prompt
from tests.test_plan_repair import _step


def _adim(*checks, effects=()):
    return replace(_step("adim", expected_effects=effects), verification_checks=checks)


def test_dosya_kontrolunun_hedefi_isteme_yazilir():
    adim = _adim(
        VerificationCheck("koşul", VerificationCheckKind.FILE_EXISTS, "scripts/game_manager.gd")
    )

    assert "scripts/game_manager.gd" in measurement_block(adim)


def test_icerik_kontrolunde_beklenen_metin_de_yazilir():
    adim = _adim(
        VerificationCheck(
            "koşul",
            VerificationCheckKind.FILE_CONTAINS,
            "scripts/game_manager.gd",
            "signal health_changed",
        )
    )

    blok = measurement_block(adim)

    assert "scripts/game_manager.gd" in blok
    assert "signal health_changed" in blok


def test_beklenen_dosya_etkisi_de_kontrat_sayilir():
    """`file:` etkisi de adımı düşürebilir; adım onu da görmeli."""
    adim = _adim(effects=("file:scripts/player.gd",))

    assert "scripts/player.gd" in measurement_block(adim)


def test_komut_kontrolu_isteme_yazilir():
    adim = _adim(
        VerificationCheck(
            "koşul", VerificationCheckKind.COMMAND, "godot --headless --path . --quit"
        )
    )

    assert "godot --headless --path . --quit" in measurement_block(adim)


def test_olculecek_kanit_yoksa_blok_bos():
    """Boş başlık yazmak istemi gürültüyle şişirirdi."""
    assert measurement_block(_adim()) == ""


def test_ayni_hedef_tekrarlanmaz():
    hedef = "scripts/game_manager.gd"
    adim = _adim(
        VerificationCheck("koşul", VerificationCheckKind.FILE_EXISTS, hedef),
        effects=(f"file:{hedef}",),
    )

    assert measurement_block(adim).count(hedef) == 1


def test_kontrat_adim_istemine_giriyor():
    """Yardımcının var olması yetmez: istemin İÇİNE girdiği kanıtlanmalı."""
    adim = _adim(
        VerificationCheck("koşul", VerificationCheckKind.FILE_EXISTS, "scripts/game_manager.gd")
    )

    istem = step_prompt("iş", adim, {})

    assert "scripts/game_manager.gd" in istem
