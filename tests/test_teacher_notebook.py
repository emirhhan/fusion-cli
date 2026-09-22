"""`.fusion/ogretmen.md` günlüğü (Faz 4, Görev 3) — saf, ağ/dosya-sistemi dışında bağımlılık yok."""

from __future__ import annotations

from fusion_cli.engines.agent.teacher_notebook import NOTEBOOK_PATH, append_entry


def test_ilk_yazimda_baslik_eklenir(tmp_path):
    append_entry(
        tmp_path,
        timestamp="2026-09-22T10:00:00+00:00",
        question="soru",
        answer="cevap",
        lesson_written=False,
    )

    icerik = (tmp_path / NOTEBOOK_PATH).read_text(encoding="utf-8")
    assert icerik.startswith("# Öğretmen günlüğü")


def test_soru_ve_cevap_dosyaya_yazilir(tmp_path):
    append_entry(
        tmp_path,
        timestamp="2026-09-22T10:00:00+00:00",
        question="dosya neden yazılamıyor?",
        answer="izin sorunu olabilir",
        lesson_written=False,
    )

    icerik = (tmp_path / NOTEBOOK_PATH).read_text(encoding="utf-8")
    assert "dosya neden yazılamıyor?" in icerik
    assert "izin sorunu olabilir" in icerik


def test_durum_verilirse_eklenir_verilmezse_eklenmez(tmp_path):
    append_entry(
        tmp_path,
        timestamp="t",
        question="s",
        durum="ÖZEL_DURUM",
        answer="c",
        lesson_written=False,
    )
    icerik = (tmp_path / NOTEBOOK_PATH).read_text(encoding="utf-8")
    assert "ÖZEL_DURUM" in icerik
    assert "**Durum:**" in icerik


def test_ders_yazildiysa_bildirim_gorunur(tmp_path):
    append_entry(tmp_path, timestamp="t", question="s", answer="c", lesson_written=True)
    icerik = (tmp_path / NOTEBOOK_PATH).read_text(encoding="utf-8")
    assert "Ders belleğe kaydedildi" in icerik


def test_ders_atlandiysa_gerekce_gorunur(tmp_path):
    append_entry(
        tmp_path,
        timestamp="t",
        question="s",
        answer="c",
        lesson_written=False,
        lesson_skip_reason="çelişebilir",
    )
    icerik = (tmp_path / NOTEBOOK_PATH).read_text(encoding="utf-8")
    assert "çelişebilir" in icerik


def test_ikinci_girdi_ilkini_silmez(tmp_path):
    append_entry(tmp_path, timestamp="t1", question="ilk soru", answer="c1", lesson_written=False)
    append_entry(
        tmp_path, timestamp="t2", question="ikinci soru", answer="c2", lesson_written=False
    )

    icerik = (tmp_path / NOTEBOOK_PATH).read_text(encoding="utf-8")
    assert "ilk soru" in icerik
    assert "ikinci soru" in icerik


def test_dosya_yolu_fusion_klasoru_altindadir(tmp_path):
    yol = append_entry(tmp_path, timestamp="t", question="s", answer="c", lesson_written=False)

    assert yol == tmp_path / ".fusion" / "ogretmen.md"
