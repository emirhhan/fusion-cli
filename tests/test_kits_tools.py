"""Fusion → Kit gelen kutusu araçları, istemci ve adres çözümü (P-063).

Ölçüldü (31 Ekim): Fusion'da bir Kit'e mesaj bırakan araç/komut yoktu; Kits adresi hiçbir
yerden öğrenilmiyordu.
"""

from __future__ import annotations

import json
import os
from types import SimpleNamespace

import httpx
import pytest

from fusion_cli.core.tools import ToolFamily, tool_family
from fusion_cli.tools import kits
from fusion_cli.tools.builtin import build_registry


def _state(tmp_path, url="http://127.0.0.1:51234", pid=None):
    path = tmp_path / "kits-bridge.json"
    path.write_text(json.dumps({"fusion_kits_bridge": 1, "url": url, "pid": pid or os.getpid()}))
    return path


def test_durum_dosyasi_canli_pid_ve_yerel_adresle_okunur(tmp_path):
    assert kits.resolve_kits_endpoint(_state(tmp_path)) == kits.KitsEndpoint(
        "http://127.0.0.1:51234", "masaustu"
    )
    # Sorgu/yol taşımaz; yalnız origin.
    assert kits.read_kits_state(_state(tmp_path, "http://localhost:4411/x?y=1")).url == (
        "http://localhost:4411"
    )


def test_olu_pid_uzak_adres_ve_bozuk_dosya_varsayilana_duser(tmp_path):
    # 2^22-1: Linux/macOS'ta pratikte kullanılmayan, ölü sayılan pid.
    assert kits.read_kits_state(_state(tmp_path, pid=4_194_303)) is None
    assert kits.read_kits_state(_state(tmp_path, url="http://example.com:4410")) is None
    assert kits.read_kits_state(_state(tmp_path, url="https://127.0.0.1:4410")) is None
    bozuk = tmp_path / "bozuk.json"
    bozuk.write_text("{")
    assert kits.read_kits_state(bozuk) is None
    assert kits.resolve_kits_endpoint(tmp_path / "yok.json") == kits.KitsEndpoint(
        kits.KITS_DEFAULT_URL, "varsayilan"
    )


class _Kits:
    """Sahte Kits sunucusu: istekleri kaydeder, gelen kutusu uçlarını taklit eder."""

    def __init__(self) -> None:
        self.requests: list[tuple[str, str, object]] = []
        self.fail_status: int | None = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        self.requests.append((request.method, request.url.path, body))
        if self.fail_status:
            return httpx.Response(self.fail_status, json={"error": "Görev yürütme izni kapalı."})
        if request.url.path == "/api/kits":
            return httpx.Response(
                200,
                json={
                    "kits": [
                        {"id": "k1", "name": "Kod", "fusionAllowed": True, "inboxThreadId": None}
                    ]
                },
            )
        if request.method == "POST":
            return httpx.Response(
                201, json={"kitId": "k1", "threadId": "t1", "taskId": "g1", "status": "queued"}
            )
        if request.url.path.endswith("/inbox"):
            return httpx.Response(200, json={"items": [{"taskId": "g1", "status": "queued"}]})
        return httpx.Response(200, json={"taskId": "g1", "status": "completed", "result": "Bitti"})


def _client(sahte: _Kits) -> kits.KitsClient:
    return kits.KitsClient(
        kits.KitsEndpoint("http://127.0.0.1:4410", "varsayilan"),
        transport=httpx.MockTransport(sahte.handler),
    )


async def test_araclar_kits_uclarina_dogru_istekleri_gonderir():
    sahte = _Kits()
    baglam = SimpleNamespace(kits=_client(sahte))
    liste = await kits.kits_list({}, baglam)
    assert liste.ok and json.loads(liste.output) == [
        {"id": "k1", "ad": "Kod", "fusion_izni": True, "gelen_kutusu": None}
    ]
    gonder = await kits.kit_send(
        {"kit": "Kod", "text": "Testleri çalıştır", "title": "Test", "kind": "mesaj"}, baglam
    )
    assert gonder.ok
    makbuz = json.loads(gonder.output)
    assert makbuz["durum"] == "kuyrukta" and makbuz["gorev_id"] == "g1"
    assert "bittiği anlamına gelmez" in makbuz["not"]
    durum = await kits.kit_task_status({"kit": "Kod", "task_id": "g1"}, baglam)
    assert json.loads(durum.output)["status"] == "completed"
    kutu = await kits.kit_task_status({"kit": "Kod"}, baglam)
    assert json.loads(kutu.output) == [{"taskId": "g1", "status": "queued"}]
    assert [(m, p) for m, p, _ in sahte.requests] == [
        ("GET", "/api/kits"),
        ("POST", "/api/kits/Kod/inbox"),
        ("GET", "/api/kits/Kod/inbox/g1"),
        ("GET", "/api/kits/Kod/inbox"),
    ]
    assert sahte.requests[1][2] == {"text": "Testleri çalıştır", "kind": "message", "title": "Test"}


async def test_kisa_metin_kits_hatasi_ve_ulasilamayan_sunucu_turkce_hata_verir():
    sahte = _Kits()
    baglam = SimpleNamespace(kits=_client(sahte))
    kisa = await kits.kit_send({"kit": "Kod", "text": "ab"}, baglam)
    assert not kisa.ok and "en az 3" in kisa.output
    assert sahte.requests == []
    sahte.fail_status = 403
    red = await kits.kit_send({"kit": "Kod", "text": "Uzun bir görev"}, baglam)
    assert not red.ok and red.output == "Görev yürütme izni kapalı."

    def kopuk(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("bağlanamadı")

    kopuk_istemci = kits.KitsClient(
        kits.KitsEndpoint("http://127.0.0.1:4410", "varsayilan"),
        transport=httpx.MockTransport(kopuk),
    )
    sonuc = await kits.kits_list({}, SimpleNamespace(kits=kopuk_istemci))
    assert not sonuc.ok and "npm run kits:start" in sonuc.output
    masaustu = kits.KitsClient(
        kits.KitsEndpoint("http://127.0.0.1:51234", "masaustu"),
        transport=httpx.MockTransport(kopuk),
    )
    sonuc = await kits.kits_list({}, SimpleNamespace(kits=masaustu))
    assert not sonuc.ok and "Kits bölümünü" in sonuc.output


def test_araclar_defterde_kayitli_ve_etkileri_dogru():
    registry = build_registry()
    kit_send = registry.get("kit_send")
    assert kit_send is not None and kit_send.mutating
    assert kit_send.effect.value == "remote_write"
    assert registry.get("kits_list") is not None and not registry.get("kits_list").mutating
    assert registry.get("kit_task_status") is not None
    assert tool_family("kit_send") is ToolFamily.DELEGATION
    assert tool_family("kits_list") is ToolFamily.META


@pytest.mark.parametrize("metin", ["", "  ab ", "x" * 4001])
def test_metin_dogrulamasi(metin):
    assert kits.validate_text(metin) is not None
    assert kits.validate_text("Yeterince uzun") is None


async def test_kits_olmayan_yerel_servis_kit_listesi_sanilmaz():
    # Ölçüldü (31 Ekim, inceleme): 4410'u dinleyen başka bir süreç "Kit yok" sanılıyordu;
    # Kits imzası (`kits` listesi) olmayan yanıt ulaşılamadı gibi ele alınır.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>Başka bir servis</html>")

    client = kits.KitsClient(
        kits.KitsEndpoint("http://127.0.0.1:4410", "varsayilan"),
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(kits.KitsError, match="Kits değil"):
        await client.list_kits()
