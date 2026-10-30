"""Dalga 4 (plan-dogrulama): önizleme araçları (A3-19..A3-23)."""

from __future__ import annotations

import pytest

from fusion_cli.engines.agent import preview_tools


def test_en_iyi_tema_yedegi_alt_klasorleri_de_kopyalar(tmp_path):
    """Ölçüldü (29 Ekim): yalnız üst düzey kopyalanıyor, `inc/` yedeğe girmiyordu."""
    tema = tmp_path / "wp-content" / "themes" / "kopya"
    (tema / "inc").mkdir(parents=True)
    (tema / "node_modules" / "x").mkdir(parents=True)
    (tema / "style.css").write_text("/* Theme Name: k */", encoding="utf-8")
    (tema / "inc" / "yardim.php").write_text("<?php ?>", encoding="utf-8")
    (tema / "node_modules" / "x" / "a.php").write_text("<?php ?>", encoding="utf-8")

    preview_tools._snapshot_theme(tmp_path)

    yedek = tmp_path / preview_tools.BEST_THEME_DIR
    assert (yedek / "inc" / "yardim.php").is_file()
    assert (yedek / "style.css").is_file()
    assert not (yedek / "node_modules").exists()


def test_en_iyi_tema_yedegi_tema_silinmisse_patlamaz(tmp_path, monkeypatch):
    tema = tmp_path / "wp-content" / "themes" / "kopya"
    tema.mkdir(parents=True)
    (tema / "style.css").write_text("/* Theme Name: k */", encoding="utf-8")
    monkeypatch.setattr(preview_tools, "project_theme", lambda root: "kopya")
    tema.joinpath("style.css").unlink()
    tema.rmdir()

    preview_tools._snapshot_theme(tmp_path)  # OSError atmamalı


@pytest.mark.parametrize(
    ("host", "kaynak", "beklenen"),
    [
        ("example.com", "example.com", True),
        ("www.example.com", "example.com", True),
        ("cdn.example.com", "example.com", True),
        ("notexample.com", "example.com", False),
        ("example.com.evil.io", "example.com", False),
    ],
)
def test_kaynak_site_eslesmesi_sonek_degil_alan_adi_sinirina_bakar(host, kaynak, beklenen):
    assert preview_tools._is_same_site(host, kaynak) is beklenen


def test_yonetici_giris_dosyasi_gitignore_a_eklenir(tmp_path):
    from fusion_cli.tools.wordpress_setup import CREDENTIALS_FILE, write_credentials

    yol = write_credentials(tmp_path, "http://127.0.0.1:8770", "parola")
    write_credentials(tmp_path, "http://127.0.0.1:8770", "parola")  # tekrar: çoğaltmaz

    ignore = (tmp_path / ".fusion" / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ignore == [CREDENTIALS_FILE.name]
    assert yol.is_file()


# --- A3-24 / A3-25 / A3-26: reflexion notları ve isteğe bağlı sorular ------------ #


def test_dogrulama_eylem_notu_harness_notudur():
    from fusion_cli.engines.agent import reflexion

    assert reflexion.verification_action_required_note().harness_note is True


def test_dizin_onerisindeki_ozel_karakterler_kabukta_yorumlanmaz():
    from fusion_cli.engines.agent import reflexion

    not_ = reflexion.wrong_workspace_note("/x", '/tmp/a"b$(rm -rf ~)').content

    assert "cd '/tmp/a\"b$(rm -rf ~)' && fusion" in not_


async def test_bosluk_yalniz_cevap_atlanmis_sayilir():
    import asyncio

    from fusion_cli.engines.agent.questions import PendingUserQuestions, QuestionState

    async def cevap() -> str:
        return "   "

    sorular = PendingUserQuestions()
    sorular.start(cevap())
    await asyncio.sleep(0.01)

    assert sorular.drain()[0].state is QuestionState.SKIPPED
    await sorular.close()
