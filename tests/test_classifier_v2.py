from __future__ import annotations

from fusion_cli.engines.agent.classify import (
    TaskKind,
    classify_task,
    classify_task_details,
)

GAME_PROMPT = """
Tarayıcıda çalışan, bağımlılığı minimum olan bir 2D arena survival oyunu yap.

Gereksinimler:
- Oyuncu WASD ile hareket etsin.
- Düşmanlar oyuncuya doğru gelsin.
- Oyuncu otomatik saldırı yapsın.
- Düşman öldürünce XP düşsün.
- XP toplanınca oyuncu seviye atlasın.
- Level-up olduğunda oyun pause olsun ve 3 rastgele upgrade çıksın.
- En az 8 farklı upgrade olsun.

Teknik beklentiler:
- Önce mevcut proje yapısını incele.
- İş bittikten sonra oyunu gerçekten çalıştır.
- Console hatalarını kontrol et.
- Temel oynanış döngüsünü test et.
- Level-up, ölüm ve restart akışlarını doğrula.
- Bulduğun hataları düzelt ve tekrar test et.
"""


def test_uzun_oyun_promptunda_yardimci_test_bugfix_primaryyi_ele_gecirmez():
    result = classify_task_details(GAME_PROMPT)

    assert result.primary is TaskKind.FEATURE
    assert TaskKind.TEST in result.secondary
    assert TaskKind.BUGFIX in result.secondary
    assert result.score_for(TaskKind.FEATURE) > result.score_for(TaskKind.TEST)


def test_classify_task_geriye_uyumlu_primary_dondurur():
    assert classify_task(GAME_PROMPT) is TaskKind.FEATURE


def test_mevcut_oyundaki_hata_duzeltme_bugfix_kalir():
    request = (
        "Mevcut oyunda düşmanlar ölmüyor ve level değişmiyor. "
        "Bu hataları düzelt, sonra oyunu test et."
    )

    result = classify_task_details(request)

    assert result.primary is TaskKind.BUGFIX
    assert TaskKind.TEST in result.secondary


def test_landing_page_creation_website_kalir():
    result = classify_task_details(
        "Modern bir landing sayfası oluştur. HTML ve CSS kullan. "
        "Sonra responsive davranışı test et."
    )

    assert result.primary is TaskKind.WEBSITE
    assert TaskKind.TEST in result.secondary


def test_readme_belgesi_feature_ekle_kelimesine_yenilmez():
    result = classify_task_details(
        "README dosyasına kurulum belgesi ekle ve örnek komutları yaz."
    )

    assert result.primary is TaskKind.DOCS
    assert TaskKind.FEATURE in result.secondary


def test_test_yazma_feature_yaz_kelimesine_yenilmez():
    result = classify_task_details(
        "Bu fonksiyon için pytest testi yaz ve coverage kontrol et."
    )

    assert result.primary is TaskKind.TEST
    assert TaskKind.FEATURE in result.secondary


def test_bugfix_test_beraberliginde_duzeltme_primarydir():
    result = classify_task_details("testteki hatayı düzelt")

    assert result.primary is TaskKind.BUGFIX
    assert TaskKind.TEST in result.secondary


def test_secondary_skor_sirasina_gore_doner():
    result = classify_task_details(
        "Yeni export özelliği yap. Sonra test et ve sonucu doğrula."
    )

    assert result.primary is TaskKind.FEATURE
    assert len(result.secondary) >= 1


def test_general_gorevde_guven_sifirdir():
    result = classify_task_details("selam nasılsın")

    assert result.primary is TaskKind.GENERAL
    assert result.secondary == ()
    assert result.confidence == 0.0

def test_ciplak_yap_belirsizdir_feature_zorlamaz():
    result = classify_task_details("yap")

    assert result.primary is TaskKind.GENERAL
    assert result.secondary == ()
    assert result.confidence == 0.0

