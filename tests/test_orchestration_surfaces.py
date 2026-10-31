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


# --------------------------------------------------------------------------- #
# Ekip (P-061)
# --------------------------------------------------------------------------- #


def _ekip(tmp_path):
    from fusion_cli.engines.agent.team_board import (
        TeamBoard,
        TeamMember,
        TeamMessage,
        TeamStore,
        TeamTask,
    )

    store = TeamStore(tmp_path)
    store.save(
        TeamBoard(
            "site",
            "Açılış sayfası",
            (TeamMember("kod", "kodcu"), TeamMember("tasarim")),
            (TeamTask("g1", "Palet", status="tamam", owner="tasarim"), TeamTask("g2", "JS")),
        )
    )
    store.append("site", TeamMessage("kod", "lider", "JS yarım, API anahtarı yok"))
    return store


def test_team_komutu_listeler_gosterir_ve_ekip_kurmayi_tura_hazirlar(tmp_path):
    from fusion_cli.cli.repl.team_commands import team_command

    _ekip(tmp_path)
    state = _state(tmp_path)

    liste = team_command(state, "")
    goster = team_command(state, "goster site")
    kur = team_command(state, "giriş sayfasını üç kişiyle yap")

    assert "site  1/2 görev · üyeler: kod, tasarim — Açılış sayfası" in liste
    assert "- g2 bekliyor: JS" in goster and "kod: JS yarım" in goster
    assert "Lider ekibi" in kur
    assert (
        "team_run" in state.pending_task and "giriş sayfasını üç kişiyle yap" in state.pending_task
    )


def test_team_mesaj_ekibi_surdurur_bilinmeyen_ekibi_reddeder(tmp_path):
    from fusion_cli.cli.repl.team_commands import team_command

    _ekip(tmp_path)
    state = _state(tmp_path)

    assert "yok" in team_command(state, "mesaj baska kod selam")
    assert state.pending_task == ""
    team_command(state, "mesaj site kod anahtar .env.example içinde")
    assert '(ad: "site")' in state.pending_task and "kod üyesine" in state.pending_task


def test_fusion_ekip_cli_listeler_gosterir_siler(tmp_path):
    from fusion_cli.cli.team_cli import app as team_app

    _ekip(tmp_path)
    runner = CliRunner()

    liste = runner.invoke(team_app, ["liste", "--kok", str(tmp_path)])
    goster = runner.invoke(team_app, ["goster", "site", "--kok", str(tmp_path)])
    sil = runner.invoke(team_app, ["sil", "site", "--kok", str(tmp_path)])
    yok = runner.invoke(team_app, ["sil", "site", "--kok", str(tmp_path)])

    assert liste.exit_code == 0 and "site" in liste.output
    assert goster.exit_code == 0 and "Palet" in goster.output
    assert sil.exit_code == 0 and not (tmp_path / ".fusion/ekip/site").exists()
    assert yok.exit_code == 1


async def test_ekip_rpcleri_liste_pano_sil(tmp_path):
    _ekip(tmp_path)

    liste = await dispatch_orchestration("ekip.liste", {}, tmp_path)
    pano = await dispatch_orchestration("ekip.pano", {"ad": "site"}, tmp_path)
    sil = await dispatch_orchestration("ekip.sil", {"ad": "site"}, tmp_path)
    yok = await dispatch_orchestration("ekip.pano", {"ad": "site"}, tmp_path)

    assert liste["ekipler"] == [
        {
            "ad": "site",
            "hedef": "Açılış sayfası",
            "uyeler": ["kod", "tasarim"],
            "gorev": 2,
            "tamam": 1,
            "guncellendi": 0.0,
        }
    ]
    assert pano["ok"] and pano["pano"]["lider_mesajlari"][0]["text"].startswith("JS yarım")
    assert sil["ok"] and yok == {"ok": False, "metin": "Bu adla ekip yok."}
