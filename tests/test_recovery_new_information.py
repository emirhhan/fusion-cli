"""Üçüncü deneme YALNIZ yeni bilgi varsa verilir.

Ölçüldü (7 Eylül canlı Godot koşusu): adım iki kez aynı yönergeyle denendi ve
"Sınırlı kurtarma hakkı tükendi" ile duraklatıldı. Bulgu bu arada eyleme
dönüştürülebilir hâle geldiyse (dosyanın gerçek yeri bulundu, tanı çıkarıldı)
üçüncü deneme artık kör değildir ve işi bitirebilir.

Aynı yönergeyle üçüncü kez denemek ise sadece bütçe yakar: yeni bilgi yoksa hak
da yoktur.
"""

from __future__ import annotations

from fusion_cli.core.execution_plan import RetrySafety
from fusion_cli.core.failure import FailureCategory, FailureRecord, RecoveryAction
from fusion_cli.engines.agent.recovery import choose_recovery
from tests.test_recovery import _step


def _bulgu(detail):
    return FailureRecord(FailureCategory.VERIFICATION, detail)


def test_yeni_yonerge_ucuncu_denemeyi_acar():
    onceki = choose_recovery(_bulgu("kontrol hedefi dosya bulunamadı"), _step(RetrySafety.SAFE), 1)

    karar = choose_recovery(
        _bulgu("kontrol hedefi dosya bulunamadı; aynı adlı dosya burada: game_manager.gd"),
        _step(RetrySafety.SAFE),
        attempts=2,
        previous_guidance=onceki.guidance,
    )

    assert karar.action is RecoveryAction.REPLAN


def test_ayni_yonergeyle_ucuncu_deneme_verilmez():
    detay = "kontrol hedefi dosya bulunamadı"
    onceki = choose_recovery(_bulgu(detay), _step(RetrySafety.SAFE), 1)

    karar = choose_recovery(
        _bulgu(detay), _step(RetrySafety.SAFE), attempts=2, previous_guidance=onceki.guidance
    )

    assert karar.action is RecoveryAction.PAUSE


def test_dorduncu_deneme_hicbir_kosulda_verilmez():
    karar = choose_recovery(
        _bulgu("yepyeni bir bulgu"),
        _step(RetrySafety.SAFE),
        attempts=3,
        previous_guidance="eski yönerge",
    )

    assert karar.action is RecoveryAction.PAUSE


def test_gecici_hatada_hak_genislemez():
    """Yeni bilgi kuralı yalnız doğrulama hatasına aittir; ağ hatası kör tekrardır."""
    karar = choose_recovery(
        FailureRecord(FailureCategory.TRANSIENT, "bağlantı"),
        _step(RetrySafety.SAFE),
        attempts=2,
        previous_guidance="başka",
    )

    assert karar.action is RecoveryAction.PAUSE
