"""CLI komutları — Typer üzerinden uçtan uca (ağ yok)."""

from __future__ import annotations

from typer.testing import CliRunner

from fusion_cli import __version__
from fusion_cli.cli import app as app_module
from fusion_cli.core.types import ModelResult

runner = CliRunner()


def test_version_surumu_basar():
    result = runner.invoke(app_module.app, ["version"])

    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_config_show_varsayilanlari_basar():
    result = runner.invoke(app_module.app, ["config", "show"])

    assert result.exit_code == 0
    assert "Agent modeli" in result.stdout
    assert "max_tokens" in result.stdout


def test_run_bos_gorevi_reddeder():
    result = runner.invoke(app_module.app, ["run", "   "])

    assert result.exit_code != 0


def test_run_basarili_sonucta_sifir_doner(monkeypatch):
    async def _sahte(task, config, *, sinks):
        return ModelResult(name="agent", model="m", text="ok", latency_ms=1, ok=True)

    monkeypatch.setattr(app_module, "run_task", _sahte)

    result = runner.invoke(app_module.app, ["run", "merhaba"])

    assert result.exit_code == 0


def test_run_basarisiz_sonucta_bir_doner(monkeypatch):
    async def _sahte(task, config, *, sinks):
        return ModelResult(name="agent", model="m", text="", latency_ms=1, ok=False, error="x")

    monkeypatch.setattr(app_module, "run_task", _sahte)

    result = runner.invoke(app_module.app, ["run", "merhaba"])

    assert result.exit_code == 1
