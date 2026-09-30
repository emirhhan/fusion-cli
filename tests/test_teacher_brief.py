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


def test_ogretmen_rolu_ve_cevap_bicimi_paketin_basinda_durur():
    brief = compile_brief(durum="d", denenenler="", question="neden?")
    assert brief.text.startswith("## Rolün\n")
    assert "## Cevap biçimi" in brief.text
    assert brief.text.rstrip().endswith("neden?")


def test_kod_kesitleri_eklenir_ve_uzun_dosya_ortadan_kisaltilir():
    from fusion_cli.engines.agent.teacher_brief import EXCERPT_CHAR_BUDGET

    uzun = "BAS\n" + "x" * (EXCERPT_CHAR_BUDGET * 2) + "\nSON"
    brief = compile_brief(
        durum="d", denenenler="", question="q", code_excerpts=[("src/a.py", uzun)]
    )
    assert "### src/a.py" in brief.text
    assert "BAS" in brief.text and "SON" in brief.text
    assert "[…dosyanın ortası kısaltıldı…]" in brief.text


def test_ogretmen_kesitleri_env_dosyasini_okumaz_ve_anahtari_maskeler(tmp_path):
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.engines.agent.engine_tools import _teacher_excerpts

    env = tmp_path / ".env"
    env.write_text("OPENROUTER_API_KEY=sk-or-v1-gercekgibi0123456789abcdef\n", encoding="utf-8")
    kod = tmp_path / "app.py"
    kod.write_text('KEY = "sk-or-v1-gercekgibi0123456789abcdef"\nprint(KEY)\n', encoding="utf-8")
    context = ToolContext(root=tmp_path)
    context.touched.update({env, kod})

    kesitler = dict(_teacher_excerpts(context))
    assert list(kesitler) == ["app.py"]
    assert "sk-or-v1-gercekgibi" not in kesitler["app.py"]
