"""İlerleme ikili değil PUANLIDIR.

SWE-TRACE'in bulgusu: kötü dalı sonradan elemek yerine koşarken budamak daha
etkili; ama budama kararı ölçülebilir olmalı. Fusion'da karar ikiliydi ("bir şey
değişti mi"), bu yüzden hem gürültülü hem ayarlanamazdı: başarısız üç çağrı ile
hiç çağrı yapmamak aynı sayılıyordu.

Puan turun KENDİ sinyallerinden gelir; model yorumu değildir.
"""

from __future__ import annotations

from fusion_cli.core.progress import PROGRESS_THRESHOLD, RoundSignals, score_round


def test_basarili_degisiklik_tam_puan_alir():
    puan = score_round(RoundSignals(mutations=1, new_reads=0, failures=0, repeats=0))

    assert puan >= PROGRESS_THRESHOLD


def test_yeni_okuma_ilerleme_sayilir():
    """Keşif turu ilerlemedir.

    Ölçüldü (kilitlenme ağı): tek okumayı yarım saymak, "listele → oku → düzelt"
    akışındaki modeli düzeltmeye varmadan öldürdü.
    """
    puan = score_round(RoundSignals(mutations=0, new_reads=1, failures=0, repeats=0))

    assert puan >= PROGRESS_THRESHOLD


def test_degisiklik_okumadan_daha_guclu_sinyal():
    okuma = score_round(RoundSignals(new_reads=1))
    degisiklik = score_round(RoundSignals(mutations=1))

    assert degisiklik > okuma


def test_basarisiz_cagrilar_salt_okuma_turunda_puani_dusurur():
    temiz = score_round(RoundSignals(new_reads=1))
    hatali = score_round(RoundSignals(new_reads=1, failures=2))

    assert hatali < temiz


def test_gerceklesen_degisiklik_ceza_ile_silinmez():
    """Dosya değiştiyse tur ilerlemiştir; arada başarısız çağrı olması bunu geri almaz.

    Ölçüldü (kilitlenme ağı): ceza değişikliğin üstüne binince, gerçekten yazan ama
    arada bir çağrıyı tekrarlayan tur "ilerleme yok" sayılıp kesildi.
    """
    puan = score_round(RoundSignals(mutations=1, failures=2, repeats=2))

    assert puan >= PROGRESS_THRESHOLD


def test_tekrarlanan_cagri_ilerleme_sayilmaz():
    puan = score_round(RoundSignals(mutations=0, new_reads=0, failures=0, repeats=2))

    assert puan <= 0


def test_bos_tur_sifir_puan():
    assert score_round(RoundSignals()) == 0.0


def test_puan_sinirlar_icinde_kalir():
    yuksek = score_round(RoundSignals(mutations=9, new_reads=9))
    dusuk = score_round(RoundSignals(failures=9, repeats=9))

    assert 0.0 <= yuksek <= 1.0
    assert 0.0 <= dusuk <= 1.0
