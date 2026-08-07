"""CLI komutları — Typer üzerinden uçtan uca (ağ yok)."""

from __future__ import annotations

import re

from typer.testing import CliRunner

from fusion_cli import __version__
from fusion_cli.cli import app as app_module
from fusion_cli.core.types import FusionResult, VerdictSource

runner = CliRunner()

#: ANSI kaçış dizilerini ayıklar.
#
# `FORCE_COLOR` kurulu bir kabukta rich sürüm numarasını boyuyor ve düz metin
# bekleyen doğrulama kırılıyordu. Renk bir sunum ayrıntısıdır; bu testin ölçtüğü
# şey değildir. Global bir ortam düzeltmesi denendi ve rengi BEKLEYEN başka bir
# testi bozdu — çözüm o yüzden yerel.
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _duz(metin: str) -> str:
    return _ANSI.sub("", metin)


def test_version_surumu_basar():
    result = runner.invoke(app_module.app, ["version"])

    assert result.exit_code == 0
    assert __version__ in _duz(result.stdout)


def test_config_show_varsayilanlari_basar():
    result = runner.invoke(app_module.app, ["config", "show"])

    assert result.exit_code == 0
    assert "Fusion adayları" in result.stdout
    assert "Hakem" in result.stdout
    assert "max_tokens" in result.stdout


def test_run_bos_gorevi_reddeder():
    result = runner.invoke(app_module.app, ["run", "   "])

    assert result.exit_code != 0


def _sonuc(source):
    return FusionResult(
        task="t",
        task_type="general",
        winner="a",
        final_answer="cevap",
        source=source,
        candidates=(),
    )


def _sahte_tur(monkeypatch, source, kayit=None):
    async def _sahte(task, config, *, sinks, task_type="general", synthesis=None, memory=None):
        if kayit is not None:
            kayit.update(task_type=task_type, synthesis=synthesis)
        return _sonuc(source)

    monkeypatch.setattr(app_module, "run_task", _sahte)


def test_run_basarili_sonucta_sifir_doner(monkeypatch):
    _sahte_tur(monkeypatch, VerdictSource.JUDGE)

    assert runner.invoke(app_module.app, ["run", "merhaba", "--no-memory"]).exit_code == 0


def test_run_cevapsiz_sonucta_bir_doner(monkeypatch):
    _sahte_tur(monkeypatch, VerdictSource.NONE)

    assert runner.invoke(app_module.app, ["run", "merhaba", "--no-memory"]).exit_code == 1


def test_run_gecersiz_gorev_tipini_reddeder():
    result = runner.invoke(app_module.app, ["run", "merhaba", "--type", "olmayan"])

    assert result.exit_code != 0


def test_run_secenekleri_oturuma_gecirilir(monkeypatch):
    kayit = {}
    _sahte_tur(monkeypatch, VerdictSource.JUDGE, kayit)

    runner.invoke(
        app_module.app, ["run", "merhaba", "--type", "code", "--no-synthesis", "--no-memory"]
    )

    assert kayit == {"task_type": "code", "synthesis": False}


# --- Giriş ekranı ------------------------------------------------------------ #


def test_karsilama_kaydirma_gecmisini_de_temizler():
    """console.clear() yalnızca görünen ekranı siler; scrollback kalır.

    Kullanıcı fusion'a girip yukarı kaydırınca eski terminal mesajlarını görüyordu —
    bir CLI uygulamasına girilmiş hissi vermiyordu. `ESC [ 3 J` scrollback'i de siler.
    """
    import io

    from rich.console import Console

    from fusion_cli.ui import banner

    tampon = io.StringIO()
    console = Console(file=tampon, width=80, force_terminal=True)

    banner.print_welcome(console, banner.SessionInfo(**_ornek_oturum()), clear=True)

    assert "\x1b[3J" in tampon.getvalue(), "scrollback temizleme dizisi yazılmadı"


def test_temizleme_kapaliyken_scrollback_silinmez():
    """İlk mesajdan sonraki yeniden çizimlerde geçmiş korunmalı."""
    import io

    from rich.console import Console

    from fusion_cli.ui import banner

    tampon = io.StringIO()
    console = Console(file=tampon, width=80, force_terminal=True)

    banner.print_welcome(console, banner.SessionInfo(**_ornek_oturum()), clear=False)

    assert "\x1b[3J" not in tampon.getvalue()


def _ornek_oturum() -> dict:
    import dataclasses

    from fusion_cli.ui.banner import SessionInfo

    alanlar = {f.name: f for f in dataclasses.fields(SessionInfo)}
    ornek: dict = {}
    for ad, alan in alanlar.items():
        if alan.type in ("str", str) or "str" in str(alan.type):
            ornek[ad] = "x"
        elif "bool" in str(alan.type):
            ornek[ad] = True
        elif "int" in str(alan.type):
            ornek[ad] = 1
        else:
            ornek[ad] = "x"
    return ornek
