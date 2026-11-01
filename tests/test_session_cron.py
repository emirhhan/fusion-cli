"""Oturum-kapsamlı zamanlayıcı çekirdeği (P-038): aralık, cron, tek seferlik, sınırlar."""

from __future__ import annotations

from datetime import datetime

import pytest

from fusion_cli.core.session_cron import (
    MAX_AGE_S,
    MAX_TASKS,
    Kind,
    SessionCron,
    SessionCronError,
    cron_next,
    parse_cron,
    parse_interval,
)

NOW = 1_800_000_000.0


@pytest.mark.parametrize(
    ("text", "seconds"),
    [("90s", 90), ("5m", 300), ("2h", 7200), ("1d", 86400), ("15", 900), (" 5 M ", 300)],
)
def test_aralik_birimleri_saniyeye_cevrilir(text: str, seconds: int) -> None:
    assert parse_interval(text) == seconds


@pytest.mark.parametrize("text", ["", "abc", "5x", "-5m", "30s"])
def test_gecersiz_ya_da_kisa_aralik_hata_verir(text: str) -> None:
    with pytest.raises(SessionCronError):
        parse_interval(text)


def test_cron_her_15_dakika_sonraki_zamani_bulur() -> None:
    spec = parse_cron("*/15 * * * *")
    sonraki = cron_next(spec, datetime(2026, 10, 31, 10, 7))
    assert sonraki == datetime(2026, 10, 31, 10, 15)


def test_cron_tam_eslesme_ani_bir_sonrakine_atlar() -> None:
    spec = parse_cron("0 9 * * *")
    assert cron_next(spec, datetime(2026, 10, 31, 9, 0)) == datetime(2026, 11, 1, 9, 0)


def test_cron_hafta_ici_ve_pazar_7_desteklenir() -> None:
    hafta_ici = parse_cron("30 8 * * 1-5")
    # 31 Ekim 2026 Cumartesi → Pazartesi 2 Kasım.
    assert cron_next(hafta_ici, datetime(2026, 10, 31, 12, 0)) == datetime(2026, 11, 2, 8, 30)
    pazar = parse_cron("0 10 * * 7")
    assert cron_next(pazar, datetime(2026, 10, 31, 12, 0)) == datetime(2026, 11, 1, 10, 0)


def test_cron_ayin_gunu_ve_haftanin_gunu_ikisi_kisitliysa_biri_yeter() -> None:
    spec = parse_cron("0 0 1 * 1")
    # 1 Kasım 2026 Pazar: ayın 1'i tutar.
    assert cron_next(spec, datetime(2026, 10, 31, 12, 0)) == datetime(2026, 11, 1, 0, 0)


@pytest.mark.parametrize(
    "expr", ["* * * *", "60 * * * *", "a b c d e", "*/0 * * * *", "0 25 * * *"]
)
def test_gecersiz_cron_turkce_hata_verir(expr: str) -> None:
    with pytest.raises(SessionCronError):
        parse_cron(expr)


def test_aralikli_gorev_vadesi_gelince_listelenir_ve_tamamlaninca_ilerler() -> None:
    cron = SessionCron()
    task = cron.create_interval("testleri koştur", "5m", now=NOW)

    assert cron.due(NOW + 299) == ()
    assert cron.due(NOW + 300) == (task,)
    guncel = cron.complete(task.id, now=NOW + 300)
    assert guncel is not None and guncel.runs == 1 and guncel.next_due == NOW + 600
    assert cron.due(NOW + 300) == ()


def test_tek_seferlik_gorev_tamamlaninca_duser() -> None:
    cron = SessionCron()
    task = cron.create_once("beni uyandır", "2m", now=NOW)
    assert task.kind is Kind.ONCE
    assert cron.complete(task.id, now=NOW + 120) is not None
    assert cron.list() == ()


def test_cron_gorevi_ifadeye_gore_ilerler() -> None:
    cron = SessionCron()
    simdi = datetime(2026, 10, 31, 10, 7).astimezone().timestamp()
    task = cron.create_cron("günlük rapor", "*/30 * * * *", now=simdi)
    assert datetime.fromtimestamp(task.next_due).minute == 30
    guncel = cron.complete(task.id, now=task.next_due)
    assert guncel is not None and datetime.fromtimestamp(guncel.next_due).minute == 0


def test_bos_metin_ve_tavan_hata_verir() -> None:
    cron = SessionCron()
    with pytest.raises(SessionCronError):
        cron.create_interval("   ", "5m", now=NOW)
    for sira in range(MAX_TASKS):
        cron.create_interval(f"görev {sira}", "5m", now=NOW)
    with pytest.raises(SessionCronError):
        cron.create_interval("fazla", "5m", now=NOW)


def test_yedi_gun_dolunca_son_bir_kez_calisir_sonra_silinir() -> None:
    """Claude: yineleyen görev 7 gün dolunca son bir kez çalışır, sonra kendini siler (#364)."""
    cron = SessionCron()
    gorev = cron.create_interval("eski", "1h", now=NOW)
    son = NOW + MAX_AGE_S
    assert [t.id for t in cron.due(son)] == [gorev.id]
    cron.complete(gorev.id, now=son)
    assert cron.due(son + 7200) == () and cron.list(son + 7200) == ()


def test_tek_seferlik_ve_kendi_tempolu_yedi_gun_sonra_duser() -> None:
    cron = SessionCron()
    cron.create_self_paced("döngü", now=NOW)
    assert cron.due(NOW + MAX_AGE_S + 1) == () and cron.list() == ()


def test_kendi_tempolu_dongu_yedek_uyanmadan_sonra_biter() -> None:
    """Claude: zamanlanmayan yinelemeden ~20 dk sonra tek yedek uyanma; yine yoksa biter (#343)."""
    from fusion_cli.core.session_cron import SELF_PACED_FALLBACK_S

    assert SELF_PACED_FALLBACK_S == 1200
    cron = SessionCron()
    gorev = cron.create_self_paced("bak", now=NOW)
    cron.complete(gorev.id, now=NOW)  # 1. yineleme; ajan zamanlamadı
    yedek = NOW + SELF_PACED_FALLBACK_S
    assert [t.id for t in cron.due(yedek)] == [gorev.id]
    cron.complete(gorev.id, now=yedek)  # yedek yineleme; yine zamanlanmadı
    assert cron.due(yedek + SELF_PACED_FALLBACK_S) == () and cron.list() == ()


def test_kendi_tempolu_dongu_zamanlanirsa_yedek_sifirlanir() -> None:
    from fusion_cli.core.session_cron import SELF_PACED_FALLBACK_S

    cron = SessionCron()
    gorev = cron.create_self_paced("bak", now=NOW)
    cron.complete(gorev.id, now=NOW)
    cron.complete(gorev.id, now=NOW + SELF_PACED_FALLBACK_S)  # yedek kullanıldı
    cron.reschedule_self_paced(gorev.id, 300, now=NOW + SELF_PACED_FALLBACK_S + 1)
    sonraki = NOW + SELF_PACED_FALLBACK_S + 301
    assert [t.id for t in cron.due(sonraki)] == [gorev.id]


def test_surdurmede_kendi_tempolu_ve_vakti_gecmis_tek_seferlik_dusurulur() -> None:
    """Claude (#372): --resume kendi tempolu döngüyü ve vakti geçmiş tek seferliği getirmez."""
    cron = SessionCron()
    aralik = cron.create_interval("a", "1h", now=NOW)
    cron.create_self_paced("döngü", now=NOW)
    geri = cron.restored(NOW + 3 * 3600 + 60)
    gorevler = geri.list(NOW + 3 * 3600 + 60)
    assert [t.id for t in gorevler] == [aralik.id]
    # Kaçırılan üç çalışma telafi edilmez: sıradaki vade gelecekte.
    assert gorevler[0].next_due > NOW + 3 * 3600 + 60


def test_sil_ve_temizle() -> None:
    cron = SessionCron()
    task = cron.create_interval("a", "5m", now=NOW)
    cron.create_interval("b", "5m", now=NOW)
    assert cron.delete(task.id) is True
    assert cron.delete(task.id) is False
    assert cron.clear() == 1


def test_sozluge_yazilip_geri_okunur_bozuk_kayit_duser() -> None:
    cron = SessionCron()
    task = cron.create_interval("a", "5m", now=NOW)
    veri = cron.to_dict()
    veri["gorevler"].append({"id": "bozuk"})  # type: ignore[union-attr]
    geri = SessionCron.from_dict(veri)
    assert [t.id for t in geri.list()] == [task.id]
    assert SessionCron.from_dict("çöp").list() == ()


def test_ozet_satiri_aralik_ve_sayac_icerir() -> None:
    cron = SessionCron()
    task = cron.create_interval("testleri koştur", "5m", now=NOW)
    assert "her 5 dk" in task.describe() and "testleri koştur" in task.describe()


def test_kaynak_sozluge_yazilir_eski_kayit_kullanici_sayilir() -> None:
    from fusion_cli.core.session_cron import Source

    cron = SessionCron()
    ajan = cron.create_once("uyan", "5m", now=0.0, source=Source.AGENT)
    veri = cron.to_dict()
    assert veri["gorevler"][0]["source"] == "ajan"  # type: ignore[index]
    geri = SessionCron.from_dict(veri)
    assert geri.get(ajan.id).source is Source.AGENT  # type: ignore[union-attr]
    # Eski kayıtta alan yok: kullanıcı görevi sayılır.
    eski = {
        "gorevler": [{"id": "x", "prompt": "a", "kind": "aralik", "created_at": 0, "next_due": 60}]
    }
    assert SessionCron.from_dict(eski).get("x").source is Source.USER  # type: ignore[union-attr]


@pytest.fixture
def berlin(monkeypatch):
    """Yaz saatli bir yerel dilim (25 Ekim 2026 03:00'te CEST → CET)."""
    import time

    if not hasattr(time, "tzset"):
        pytest.skip("tzset yok")
    monkeypatch.setenv("TZ", "Europe/Berlin")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


def test_cron_vadesi_yaz_saati_gecisinde_yerel_saati_korur(berlin) -> None:
    """Ölçüldü (31 Ekim): `astimezone()` sabit ofset veriyordu; 24 Ekim'de kurulan
    '0 9 * * *' 25 Ekim'de yerel 08:00'da tetikleniyordu."""
    kurulus = datetime(2026, 10, 24, 10, 0).astimezone().timestamp()
    cron = SessionCron()
    gorev = cron.create_cron("rapor", "0 9 * * *", now=kurulus)
    ilk = datetime.fromtimestamp(gorev.next_due)
    assert (ilk.day, ilk.hour, ilk.minute) == (25, 9, 0)
    sonraki = cron.complete(gorev.id, now=gorev.next_due)
    assert sonraki is not None
    ikinci = datetime.fromtimestamp(sonraki.next_due)
    assert (ikinci.day, ikinci.hour) == (26, 9)


def test_cron_en_kucuk_aralik_ifadeden_hesaplanir() -> None:
    from fusion_cli.core.session_cron import cron_min_gap_minutes

    assert cron_min_gap_minutes(parse_cron("* 9 * * *")) == 1
    assert cron_min_gap_minutes(parse_cron("*/15 * * * *")) == 15
    assert cron_min_gap_minutes(parse_cron("0 9 * * *")) == 1440
    assert cron_min_gap_minutes(parse_cron("50 8 * * *")) == 1440
    assert cron_min_gap_minutes(parse_cron("55 8,9 * * *")) == 60
