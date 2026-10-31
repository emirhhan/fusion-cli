"""Ekip (P-061) ve iş akışı (P-062) bağımsız inceleme bulgularının regresyon testleri."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from fusion_cli.appserver.orchestration_routes import dispatch_orchestration
from fusion_cli.cli.team_cli import app as team_app
from fusion_cli.engines.agent.team_board import TeamBoard, TeamMember, TeamMessage, TeamStore


@pytest.fixture(autouse=True)
def _kullanici_dizini(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))


def _kurban(root):
    """`.fusion/ekip/` dışında, içinde `pano.json` bulunan bir dizin (silinmemeli).

    `.fusion/ekip/../../kurban` tam olarak buraya çözülür.
    """
    # Ekip dizini var olmalı: yoksa işletim sistemi `..` geçişini zaten çözemez.
    (root / ".fusion" / "ekip").mkdir(parents=True)
    victim = root / "kurban"
    victim.mkdir()
    (victim / "pano.json").write_text(json.dumps({"name": "x", "members": []}), encoding="utf-8")
    (victim / "degerli.txt").write_text("silinmemeli", encoding="utf-8")
    return victim


@pytest.mark.parametrize(
    "ad", ["../../kurban", "../../kurban/", "..", "Büyük", "a/../../../kurban"]
)
def test_ekip_deposu_gecersiz_adla_yol_disina_cikmaz(tmp_path, ad):
    root = tmp_path / "proje"
    root.mkdir()
    victim = _kurban(root)
    store = TeamStore(root)

    assert store.delete(ad) is False
    assert store.load(ad) is None
    assert store.inbox(ad, "lider") == []
    assert (victim / "degerli.txt").is_file()


def test_ekip_deposu_gecerli_adla_siler_ve_alici_adini_dogrular(tmp_path):
    store = TeamStore(tmp_path)
    store.save(TeamBoard("site", "hedef", (TeamMember("kod"),)))
    store.append("site", TeamMessage("kod", "lider", "merhaba"))

    assert store.inbox("site", "../../site/pano") == []
    assert [m.text for m in store.inbox("site", "lider")] == ["merhaba"]
    assert store.delete("site") is True
    assert store.load("site") is None


async def test_ekip_sil_ve_pano_rpcsi_yol_gecisini_reddeder(tmp_path):
    root = tmp_path / "proje"
    root.mkdir()
    victim = _kurban(root)

    silme = await dispatch_orchestration("ekip.sil", {"ad": "../../kurban"}, root)
    pano = await dispatch_orchestration("ekip.pano", {"ad": "../../kurban"}, root)

    assert silme["ok"] is False and "ad" in silme["metin"].casefold()
    assert pano["ok"] is False
    assert (victim / "degerli.txt").is_file()


def test_fusion_ekip_sil_yol_gecisini_reddeder(tmp_path):
    root = tmp_path / "proje"
    root.mkdir()
    victim = _kurban(root)

    result = CliRunner().invoke(team_app, ["sil", "../../kurban", "--kok", str(root)])

    assert result.exit_code == 1
    assert (victim / "degerli.txt").is_file()
