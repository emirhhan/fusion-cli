"""Öğretmen çağrı bütçesi (Faz 4, Görev 4) — saf, dosya sistemi dışında bağımlılık yok."""

from __future__ import annotations

import json

from fusion_cli.config.paths import user_data_dir
from fusion_cli.engines.agent.teacher_budget import LEGACY_BUDGET_PATH, budget_file, check_and_spend


def test_ilk_cagri_izin_verilir(tmp_path):
    sonuc = check_and_spend(tmp_path, now=1000.0, limit=5, window_s=3600.0)

    assert sonuc.allowed is True
    assert sonuc.used == 1
    assert sonuc.limit == 5


def test_ardisik_cagrilar_sayilir(tmp_path):
    check_and_spend(tmp_path, now=1000.0, limit=5, window_s=3600.0)
    check_and_spend(tmp_path, now=1010.0, limit=5, window_s=3600.0)
    sonuc = check_and_spend(tmp_path, now=1020.0, limit=5, window_s=3600.0)

    assert sonuc.used == 3


def test_sinira_ulasinca_reddedilir(tmp_path):
    for i in range(3):
        check_and_spend(tmp_path, now=1000.0 + i, limit=3, window_s=3600.0)

    sonuc = check_and_spend(tmp_path, now=1010.0, limit=3, window_s=3600.0)

    assert sonuc.allowed is False
    assert sonuc.used == 3


def test_pencere_dolunca_sifirlanir(tmp_path):
    for i in range(3):
        check_and_spend(tmp_path, now=1000.0 + i, limit=3, window_s=3600.0)
    dolu = check_and_spend(tmp_path, now=1010.0, limit=3, window_s=3600.0)
    assert dolu.allowed is False

    sonuc = check_and_spend(tmp_path, now=1000.0 + 3600.0, limit=3, window_s=3600.0)

    assert sonuc.allowed is True
    assert sonuc.used == 1


def test_reddedilen_cagri_sayaci_artirmaz(tmp_path):
    for i in range(2):
        check_and_spend(tmp_path, now=1000.0 + i, limit=2, window_s=3600.0)

    check_and_spend(tmp_path, now=1010.0, limit=2, window_s=3600.0)
    sonuc = check_and_spend(tmp_path, now=1020.0, limit=2, window_s=3600.0)

    assert sonuc.used == 2


def test_bozuk_dosya_sifirdan_baslar(tmp_path):
    hedef = budget_file(tmp_path)
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_text("bozuk json değil", encoding="utf-8")

    sonuc = check_and_spend(tmp_path, now=1000.0, limit=5, window_s=3600.0)

    assert sonuc.allowed is True
    assert sonuc.used == 1


def test_butce_dosyasi_proje_icine_degil_kullanici_veri_dizinine_yazilir(tmp_path):
    """Ölçüldü (30 Ekim): sayaç `.fusion/` altına yazılıp deneme projesinde git'e karıştı."""
    check_and_spend(tmp_path, now=1000.0)

    assert not (tmp_path / ".fusion" / "ogretmen-butce.json").exists()
    assert budget_file(tmp_path).is_relative_to(user_data_dir())
    assert budget_file(tmp_path).exists()


def test_butce_anahtari_projeye_ozeldir(tmp_path):
    bir, iki = tmp_path / "bir", tmp_path / "iki"
    bir.mkdir()
    iki.mkdir()

    check_and_spend(bir, now=1000.0)
    check_and_spend(bir, now=1001.0)
    sonuc = check_and_spend(iki, now=1002.0)

    assert budget_file(bir) != budget_file(iki)
    assert sonuc.used == 1


def test_eski_konumdaki_butce_dosyasi_okunup_tasinir(tmp_path):
    eski = tmp_path / LEGACY_BUDGET_PATH
    eski.parent.mkdir(parents=True)
    eski.write_text(json.dumps({"pencere_baslangic": 900.0, "sayac": 7}), encoding="utf-8")

    sonuc = check_and_spend(tmp_path, now=1000.0, limit=60, window_s=3600.0)

    assert sonuc.used == 8
    assert not eski.exists()
    kayit = json.loads(budget_file(tmp_path).read_text(encoding="utf-8"))
    assert kayit == {"pencere_baslangic": 900.0, "sayac": 8}


def test_yeni_konum_varsa_eski_dosya_sayilmaz_ama_temizlenir(tmp_path):
    check_and_spend(tmp_path, now=1000.0, limit=60)
    eski = tmp_path / LEGACY_BUDGET_PATH
    eski.parent.mkdir(parents=True)
    eski.write_text(json.dumps({"pencere_baslangic": 900.0, "sayac": 50}), encoding="utf-8")

    sonuc = check_and_spend(tmp_path, now=1001.0, limit=60)

    assert sonuc.used == 2
    assert not eski.exists()


def test_reset_in_s_penceredeki_kalan_sureyi_yansitir(tmp_path):
    sonuc = check_and_spend(tmp_path, now=1000.0, window_s=3600.0)

    assert sonuc.reset_in_s == 3600.0


def test_varsayilan_limit_saatte_25_ustundedir():
    """Plan §6.6 kararı: kasıtlı CAPTCHA testi yok, koddaki belgelenmiş eşiğe
    (`ConversationPacer`) dayanan ihtiyatlı bir sayı, saatte 25'in üstünde."""
    from fusion_cli.engines.agent.teacher_budget import HOURLY_LIMIT

    assert HOURLY_LIMIT > 25
