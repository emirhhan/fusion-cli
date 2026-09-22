"""Öğretmen çağrı bütçesi (Faz 4, Görev 4) — saf, dosya sistemi dışında bağımlılık yok."""

from __future__ import annotations

from fusion_cli.engines.agent.teacher_budget import BUDGET_PATH, check_and_spend


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
    hedef = tmp_path / BUDGET_PATH
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_text("bozuk json değil", encoding="utf-8")

    sonuc = check_and_spend(tmp_path, now=1000.0, limit=5, window_s=3600.0)

    assert sonuc.allowed is True
    assert sonuc.used == 1


def test_dosya_fusion_klasoru_altindadir(tmp_path):
    check_and_spend(tmp_path, now=1000.0)

    assert (tmp_path / ".fusion" / "ogretmen-butce.json").exists()


def test_reset_in_s_penceredeki_kalan_sureyi_yansitir(tmp_path):
    sonuc = check_and_spend(tmp_path, now=1000.0, window_s=3600.0)

    assert sonuc.reset_in_s == 3600.0


def test_varsayilan_limit_saatte_25_ustundedir():
    """Plan §6.6 kararı: kasıtlı CAPTCHA testi yok, koddaki belgelenmiş eşiğe
    (`ConversationPacer`) dayanan ihtiyatlı bir sayı, saatte 25'in üstünde."""
    from fusion_cli.engines.agent.teacher_budget import HOURLY_LIMIT

    assert HOURLY_LIMIT > 25
