"""Kontrol hedefi yoksa, aynı adlı dosyanın NEREDE olduğu söylenmeli.

Ölçüldü (7 Eylül canlı Godot koşusu): plan `scripts/game_manager.gd` bekledi,
model dosyayı depo köküne yazdı. Kapı "kontrol hedefi dosya bulunamadı" dedi ve
sustu; kurtarma yönergesi de aynı yönsüz cümleyi taşıdı. Model ikinci ve üçüncü
denemede dosyayı yeniden ÜRETTİ, taşımadı — çünkü nerede durduğunu bilmiyordu.

Bulgunun görevi kapıyı kapatmak değil, kapının nasıl açılacağını söylemektir.
"""

from __future__ import annotations

from fusion_cli.core.evidence import EvidenceStatus
from fusion_cli.core.execution_plan import VerificationCheck, VerificationCheckKind
from fusion_cli.core.file_lookup import locate_by_name
from fusion_cli.engines.agent.step_verification import evaluate_file_check


def _check(target, kind=VerificationCheckKind.FILE_EXISTS, expected=""):
    return VerificationCheck("koşul", kind, target, expected)


def test_ayni_adli_dosyanin_gercek_yolu_bulgu_metnine_girer(tmp_path):
    (tmp_path / "game_manager.gd").write_text("extends Node\n", encoding="utf-8")

    kanit = evaluate_file_check(_check("scripts/game_manager.gd"), tmp_path)

    assert kanit.status is EvidenceStatus.FAILED
    assert "game_manager.gd" in kanit.summary
    assert "TAŞI" in kanit.summary


def test_alt_dizindeki_dosya_da_bulunur(tmp_path):
    (tmp_path / "src" / "oyun").mkdir(parents=True)
    (tmp_path / "src" / "oyun" / "game_manager.gd").write_text("extends Node\n", encoding="utf-8")

    kanit = evaluate_file_check(_check("scripts/game_manager.gd"), tmp_path)

    assert "src/oyun/game_manager.gd" in kanit.summary


def test_ayni_ad_yoksa_bulgu_kisa_kalir(tmp_path):
    kanit = evaluate_file_check(_check("scripts/game_manager.gd"), tmp_path)

    assert kanit.status is EvidenceStatus.FAILED
    assert kanit.summary == "kontrol hedefi dosya bulunamadı"


def test_vaat_edilmemis_dosyada_arama_yapilmaz(tmp_path):
    """Keşif adımı zaten sorumlu değil; ona yol tarifi vermek gürültüdür."""
    (tmp_path / "game_manager.gd").write_text("extends Node\n", encoding="utf-8")

    kanit = evaluate_file_check(_check("scripts/game_manager.gd"), tmp_path, step_mutates=False)

    assert kanit.status is EvidenceStatus.UNVERIFIED
    assert "game_manager.gd" not in kanit.summary.removeprefix("adım dosya üretmeyi vaat etmedi")


def test_gurultu_dizinleri_taranmaz(tmp_path):
    (tmp_path / "node_modules" / "paket").mkdir(parents=True)
    (tmp_path / "node_modules" / "paket" / "game_manager.gd").write_text("x", encoding="utf-8")

    assert locate_by_name(tmp_path, "game_manager.gd") == ()


def test_bulunan_yol_sayisi_sinirlanir(tmp_path):
    for index in range(10):
        klasor = tmp_path / f"d{index}"
        klasor.mkdir()
        (klasor / "ayni.gd").write_text("x", encoding="utf-8")

    assert len(locate_by_name(tmp_path, "ayni.gd")) <= 3
