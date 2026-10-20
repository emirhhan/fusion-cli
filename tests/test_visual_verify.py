"""Görsel kapı — sayfayı gören bir modele DAR sorular sorar.

Biçim ölçümle belirlendi. Aynı model, aynı görselde:

- "Kalp ikonu butona göre çok mu büyük?" (tek soru, kırpılmış kart) → doğru cevap
- "Görsel hataları listele" (açık uçlu, tam sayfa) → ya susuyor ya uyduruyor
- Dört soru tek çağrıda → hepsine HAYIR, ayırt etme gücü sıfır

Bu yüzden her soru AYRI çağrıdır ve cevap ikili beklenir. Pahalıdır; varsayılan
kapalıdır ve yalnızca ölçülemeyen şeyler sorulur.
"""

from __future__ import annotations

from fusion_cli.engines.agent.visual_verify import VISUAL_CHECKS, parse_verdict, to_finding


def test_evet_cevabi_sorun_sayilir():
    assert parse_verdict("EVET") is True
    assert parse_verdict("evet, ikon çok büyük") is True


def test_hayir_cevabi_temiz_sayilir():
    assert parse_verdict("HAYIR") is False
    assert parse_verdict("hayır, sorun yok") is False


def test_belirsiz_cevap_temiz_sayilir():
    """Model kararsızsa sorun YOK sayılır: gürültülü kapı hiç kapıdan kötüdür."""
    assert parse_verdict("") is False
    assert parse_verdict("bilmiyorum") is False
    assert parse_verdict("Bu bir web sayfası ekran görüntüsüdür.") is False


def test_bozuk_yazim_da_kabul_edilir():
    """Ölçümde model 'TAMAK' gibi bozuk yazımlar üretti; ikili karar bundan etkilenmemeli."""
    assert parse_verdict("EVET.") is True
    assert parse_verdict(" HAYIR ") is False


def test_her_kontrolun_sorusu_ve_bulgusu_var():
    assert VISUAL_CHECKS
    for kontrol in VISUAL_CHECKS:
        assert kontrol.question.strip()
        assert kontrol.finding.strip()
        assert "EVET" in kontrol.question and "HAYIR" in kontrol.question


def test_bulgu_bolgeyi_ve_ne_yapilacagini_soyler():
    kontrol = VISUAL_CHECKS[0]

    bulgu = to_finding(kontrol, "header")

    assert "header" in bulgu
    assert len(bulgu) > 30
