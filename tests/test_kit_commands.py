"""`fusion kit` komutları: liste/gonder/gelen/durum, hata çıktısı (P-063).

Ölçüldü (31 Ekim, inceleme): CLI komutlarının testi yoktu; yalnız araç ve RPC test ediliyordu.
"""

from __future__ import annotations

import json
from typing import ClassVar

import pytest
from typer.testing import CliRunner

from fusion_cli.cli import kit_commands
from fusion_cli.core.errors import FusionError
from fusion_cli.tools.kits import KitsEndpoint, KitsError


class _SahteKits:
    """Sahte istemci: çağrıları kaydeder, Kits yanıtlarını taklit eder."""

    calls: ClassVar[list[tuple]] = []
    fail: ClassVar[str | None] = None

    def __init__(self) -> None:
        self.endpoint = KitsEndpoint("http://127.0.0.1:4410", "varsayilan")

    async def list_kits(self):
        self._check()
        return [{"id": "k1", "name": "Kod", "fusionAllowed": True, "inboxThreadId": "t1"}]

    async def send(self, kit, text, *, title=None, kind="gorev"):
        self._check()
        type(self).calls.append(("send", kit, text, title, kind))
        return {"kitId": "k1", "taskId": "g1", "status": "queued"}

    async def inbox(self, kit):
        self._check()
        return [
            {
                "taskId": "g1",
                "kind": "message",
                "title": "Selam",
                "status": "completed",
                "updatedAt": 0,
            }
        ]

    async def status(self, kit, task_id):
        self._check()
        return {"taskId": task_id, "status": "completed", "summary": "Bitti"}

    def _check(self) -> None:
        if type(self).fail:
            raise KitsError(type(self).fail)


@pytest.fixture
def sahte(monkeypatch):
    _SahteKits.calls = []
    _SahteKits.fail = None
    monkeypatch.setattr(kit_commands, "KitsClient", _SahteKits)
    return _SahteKits


def test_liste_ve_gelen_tablo_basar(sahte):
    runner = CliRunner()
    liste = runner.invoke(kit_commands.app, ["liste"])
    assert liste.exit_code == 0 and "Kod" in liste.output and "açık" in liste.output
    gelen = runner.invoke(kit_commands.app, ["gelen", "Kod"])
    assert gelen.exit_code == 0 and "g1" in gelen.output and "completed" in gelen.output
    durum = runner.invoke(kit_commands.app, ["durum", "Kod", "g1"])
    assert durum.exit_code == 0 and json.loads(durum.output)["summary"] == "Bitti"


def test_gonder_mesaj_ve_baslik_secenekleri_istemciye_gecer(sahte):
    runner = CliRunner()
    result = runner.invoke(
        kit_commands.app, ["gonder", "Kod", "Merhaba Kit", "--mesaj", "--baslik", "Selam"]
    )
    assert result.exit_code == 0 and "g1" in result.output
    assert sahte.calls == [("send", "Kod", "Merhaba Kit", "Selam", "mesaj")]
    varsayilan = runner.invoke(kit_commands.app, ["gonder", "Kod", "Şunu yap"])
    assert varsayilan.exit_code == 0 and sahte.calls[-1][-1] == "gorev"


def test_kisa_metin_ve_ulasilamayan_kits_turkce_hata_verir(sahte):
    runner = CliRunner()
    kisa = runner.invoke(kit_commands.app, ["gonder", "Kod", "ab"])
    assert isinstance(kisa.exception, FusionError) and "en az" in str(kisa.exception)
    assert sahte.calls == []
    sahte.fail = "Kits çalışmıyor (http://127.0.0.1:4410). Fusion masaüstünde Kits bölümünü aç."
    kapali = runner.invoke(kit_commands.app, ["liste"])
    assert isinstance(kapali.exception, FusionError)
    assert "Kits bölümünü aç" in str(kapali.exception)
