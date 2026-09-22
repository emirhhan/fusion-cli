"""Öğretmen brief derleyici testleri (Faz 4, Görev 1) — saf, ağ gerektirmez."""

from __future__ import annotations

from fusion_cli.engines.agent.teacher_brief import compile_brief


def test_yalniz_soru_verilirse_yalniz_soru_bolumu_dolu():
    brief = compile_brief(durum="", denenenler="", question="dosya neden yazılamıyor?")

    assert "## Soru" in brief.text
    assert "dosya neden yazılamıyor?" in brief.text
    assert "## Durum" not in brief.text
    assert "## Denenenler" not in brief.text
    assert brief.truncated is False


def test_dokunulan_dosyalar_ilgili_kod_bolumune_toplanir():
    brief = compile_brief(
        durum="çırak takıldı",
        denenenler="",
        question="neden hata veriyor?",
        touched_paths=["src/a.py", "src/b.py"],
    )

    assert "## İlgili kod" in brief.text
    assert "src/a.py" in brief.text
    assert "src/b.py" in brief.text


def test_ayni_dosya_tekrar_eklenmez():
    brief = compile_brief(
        durum="d",
        denenenler="",
        question="soru",
        touched_paths=["src/a.py", "src/a.py"],
    )

    assert brief.text.count("src/a.py") == 1


def test_ilgili_kod_bos_olunca_bolum_hic_basilmaz():
    brief = compile_brief(durum="d", denenenler="", question="soru", touched_paths=[])

    assert "## İlgili kod" not in brief.text


def test_denenenler_verilirse_bolume_girer():
    brief = compile_brief(
        durum="d",
        denenenler="- run_shell ile 3 kez denendi, hep aynı hata",
        question="soru",
    )

    assert "## Denenenler" in brief.text
    assert "run_shell" in brief.text


def test_25000_karakter_sinirini_asan_brief_kirpilir_ve_isaretlenir():
    uzun_denenenler = "y" * 30_000
    brief = compile_brief(durum="d", denenenler=uzun_denenenler, question="kısa soru")

    assert len(brief.text) <= 25_000
    assert brief.truncated is True
    assert "kırpıldı" in brief.text


def test_kirpilsa_bile_soru_bolumu_kaybolmaz():
    uzun_soru = "bu soru kaybolmamalı " + "z" * 30_000
    brief = compile_brief(durum="", denenenler="", question=uzun_soru)

    assert "bu soru kaybolmamalı" in brief.text
    assert brief.truncated is True


def test_char_budget_parametresi_ozellestirilebilir():
    brief = compile_brief(durum="a" * 1_000, denenenler="", question="soru", char_budget=200)

    assert len(brief.text) <= 200
    assert brief.truncated is True
