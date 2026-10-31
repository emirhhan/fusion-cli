"""Ekip ve iş akışı yüzeyleri: `/workflows`, `fusion workflows`, masaüstü RPC'leri."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from fusion_cli.appserver.orchestration_routes import dispatch_orchestration
from fusion_cli.cli.repl.workflow_commands import workflows_command
from fusion_cli.cli.workflow_cli import app as workflow_app
from fusion_cli.engines.agent.workflow_spec import parse_workflow
from fusion_cli.engines.agent.workflow_store import RunRecord, WorkflowStore


@pytest.fixture(autouse=True)
def _kullanici_dizini(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))


def _state(tmp_path):
    from fusion_cli.cli.repl.macros import Mode
    from fusion_cli.cli.repl.state import Engine

    return SimpleNamespace(
        root=tmp_path, engine=Engine.FUSION, pending_task="", pending_mode=Mode.NONE
    )


def _kayitli(tmp_path):
    store = WorkflowStore(tmp_path)
    store.save(parse_workflow({"ad": "rapor", "aciklama": "haftalık", "adimlar": ["a"]}))
    store.write_run(RunRecord("k1", "rapor", "calisiyor", 1.0, pid=__import__("os").getpid()))
    return store


def test_workflows_komutu_listeler_ve_kayitli_akisi_tura_hazirlar(tmp_path):
    _kayitli(tmp_path)
    state = _state(tmp_path)

    liste = workflows_command(state, "")
    hazir = workflows_command(state, "rapor hafta=44")

    assert "rapor  (proje)  — haftalık" in liste and "k1  rapor  calisiyor" in liste
    assert "[" not in liste  # REPL çıktısı Rich işaretlemesiyle basılır
    assert "ajana veriliyor" in hazir
    assert 'ad: "rapor"' in state.pending_task and '"hafta": "44"' in state.pending_task
    assert "workflow_run" in state.pending_task


def test_workflows_komutu_iptal_isareti_birakir_ve_bilinmeyeni_soyler(tmp_path):
    store = _kayitli(tmp_path)
    state = _state(tmp_path)

    assert "İptal işareti" in workflows_command(state, "iptal k1")
    assert store.cancel_requested("k1")
    assert "yok" in workflows_command(state, "yok-boyle")
    assert state.pending_task == ""


def test_fusion_workflows_cli_listeler_gosterir_siler(tmp_path):
    _kayitli(tmp_path)
    runner = CliRunner()

    liste = runner.invoke(workflow_app, ["liste", "--kok", str(tmp_path)])
    goster = runner.invoke(workflow_app, ["goster", "rapor", "--kok", str(tmp_path)])
    sil = runner.invoke(workflow_app, ["sil", "rapor", "--kok", str(tmp_path)])
    yok = runner.invoke(workflow_app, ["iptal", "zzz", "--kok", str(tmp_path)])

    assert liste.exit_code == 0 and "rapor" in liste.output
    assert goster.exit_code == 0 and '"adimlar"' in goster.output
    assert sil.exit_code == 0 and not (tmp_path / ".fusion/workflows/rapor.json").exists()
    assert yok.exit_code == 1


async def test_akis_rpcleri_liste_kosu_ve_iptal(tmp_path):
    store = _kayitli(tmp_path)

    liste = await dispatch_orchestration("akis.liste", {}, tmp_path)
    kosu = await dispatch_orchestration("akis.kosu", {"kimlik": "k1"}, tmp_path)
    iptal = await dispatch_orchestration("akis.iptal", {"kimlik": "k1"}, tmp_path)
    eksik = await dispatch_orchestration("akis.iptal", {}, tmp_path)

    assert liste["ok"] and liste["tanimlar"][0]["ad"] == "rapor"
    assert "pid" not in liste["kosular"][0]
    assert kosu["ok"] and kosu["kosu"]["status"] == "calisiyor"
    assert iptal["ok"] and store.cancel_requested("k1")
    assert eksik == {"ok": False, "metin": "Koşu kimliği gerekli."}
