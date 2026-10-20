"""Auto profil seçimi — istek metninden execution profili çıkarımı.

Saf ve deterministik: model çağrısı yok. Master prompt §7.2'deki dört örnek
davranış çıpası olarak doğrudan test edilir.
"""

from __future__ import annotations

from fusion_cli.engines.agent.auto_profile import auto_profile


def test_dosya_adini_degistir_low_secer():
    assert auto_profile("Dosya adını değiştir").profile == "low"


def test_basit_unit_test_medium_secer():
    assert auto_profile("Basit unit test yaz").profile == "medium"


def test_dagitik_cache_bugini_coz_high_secer():
    assert auto_profile("Dağıtık cache bug'ını çöz").profile == "high"


def test_tum_mimariyi_yeniden_tasarla_max_secer():
    assert auto_profile("Tüm mimariyi yeniden tasarla").profile == "max"


def test_kod_kesfi_low_secer():
    assert auto_profile("Bu fonksiyon nerede tanımlı, incele").profile == "low"


def test_belge_gorevi_low_secer():
    assert auto_profile("README'ye kurulum bölümü ekle, docs yaz").profile == "low"


def test_gerekce_gorev_turunu_icerir():
    secim = auto_profile("Dağıtık cache bug'ını çöz")
    assert "görev türü" in secim.reason
    assert "karmaşıklık işaretleri" in secim.reason
    assert "dağıtık" in secim.reason


def test_tek_karmasiklik_isareti_max_e_firlatmaz():
    # Tek "mimari" işareti temel medium'dan bir basamak yükseltir → high, max değil.
    assert auto_profile("mimari gözden geçir").profile == "high"


def test_bos_metin_medium_dondurur():
    # Belirsizlik GENERAL → temel medium; işaret yoksa medium kalır.
    assert auto_profile("").profile == "medium"
