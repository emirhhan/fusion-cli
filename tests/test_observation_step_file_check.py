"""Değişiklik VAAT ETMEYEN adım, olmayan bir dosyadan sorumlu tutulamaz.

Ölçüldü (7 Eylül, `mevcut-projeye-uy` — üç koşunun üçü): plan bir KEŞİF adımı
üretti ("projeyi incele"), adımın hiçbir dosya yazma vaadi yoktu ama plan ona bir
`file_exists` kontrolü iliştirdi ve hedefi yanlıştı. Kontrol düştü, adım
bloklandı, kurtarma hakkı tükendi ve TÜM koşu öldü — üstelik asıl düzenleme adımı
doğru çalışıyordu ve dosyayı doğru yazmıştı.

Planın tutarsız kontrolü, adımın hatası sayılmaz. Ama gevşetme DAR olmalı:
dosya yazmayı vaat eden adımda eksik dosya hâlâ başarısızlıktır.
"""

from __future__ import annotations

from fusion_cli.core.evidence import EvidenceStatus
from fusion_cli.core.execution_plan import VerificationCheck, VerificationCheckKind
from fusion_cli.engines.agent.step_verification import evaluate_file_check


def _kontrol() -> VerificationCheck:
    return VerificationCheck("koşul", VerificationCheckKind.FILE_EXISTS, "olmayan.py", "")


def test_kesif_adiminda_eksik_dosya_basarisizlik_degildir(tmp_path):
    kanit = evaluate_file_check(_kontrol(), tmp_path, step_mutates=False)

    assert kanit.status is EvidenceStatus.UNVERIFIED
    assert "vaat etmedi" in kanit.summary


def test_yazma_vaat_eden_adimda_eksik_dosya_hala_basarisizliktir(tmp_path):
    """Gevşetme dar: asıl koruma yerinde kalmalı."""
    kanit = evaluate_file_check(_kontrol(), tmp_path, step_mutates=True)

    assert kanit.status is EvidenceStatus.FAILED


def test_varsayilan_siki_taraftadir(tmp_path):
    """Parametre verilmezse davranış eskisi gibi katı kalır."""
    assert evaluate_file_check(_kontrol(), tmp_path).status is EvidenceStatus.FAILED


def test_var_olan_dosya_kesif_adiminda_da_gecer(tmp_path):
    (tmp_path / "kod.py").write_text("x = 1\n", encoding="utf-8")
    kontrol = VerificationCheck("koşul", VerificationCheckKind.FILE_EXISTS, "kod.py", "")

    assert evaluate_file_check(kontrol, tmp_path, step_mutates=False).status is (
        EvidenceStatus.PASSED
    )
