"""CLI komutları — Typer üzerinden uçtan uca (ağ yok)."""

from __future__ import annotations

from typer.testing import CliRunner

from fusion_cli import __version__
from fusion_cli.cli import app as app_module
from fusion_cli.core.types import FusionResult, VerdictSource

runner = CliRunner()


def test_version_surumu_basar():
    result = runner.invoke(app_module.app, ["version"])

    assert result.exit_code == 0
    assert __version__ in result.stdout


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
    async def _sahte(task, config, *, sinks, task_type="general", synthesis=None):
        if kayit is not None:
            kayit.update(task_type=task_type, synthesis=synthesis)
        return _sonuc(source)

    monkeypatch.setattr(app_module, "run_task", _sahte)


def test_run_basarili_sonucta_sifir_doner(monkeypatch):
    _sahte_tur(monkeypatch, VerdictSource.JUDGE)

    assert runner.invoke(app_module.app, ["run", "merhaba"]).exit_code == 0


def test_run_cevapsiz_sonucta_bir_doner(monkeypatch):
    _sahte_tur(monkeypatch, VerdictSource.NONE)

    assert runner.invoke(app_module.app, ["run", "merhaba"]).exit_code == 1


def test_run_gecersiz_gorev_tipini_reddeder():
    result = runner.invoke(app_module.app, ["run", "merhaba", "--type", "olmayan"])

    assert result.exit_code != 0


def test_run_secenekleri_oturuma_gecirilir(monkeypatch):
    kayit = {}
    _sahte_tur(monkeypatch, VerdictSource.JUDGE, kayit)

    runner.invoke(app_module.app, ["run", "merhaba", "--type", "code", "--no-synthesis"])

    assert kayit == {"task_type": "code", "synthesis": False}
