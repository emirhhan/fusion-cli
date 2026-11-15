"""Masaüstü Kits gelen kutusu RPC'leri (`kit.*`) (P-063)."""

from __future__ import annotations

import json

import httpx

from fusion_cli.appserver.kits_routes import dispatch_kits
from fusion_cli.tools import kits


def _client(handler) -> kits.KitsClient:
    return kits.KitsClient(
        kits.KitsEndpoint("http://127.0.0.1:4410", "varsayilan"),
        transport=httpx.MockTransport(handler),
    )


async def test_kit_rpcleri_turkce_anahtarlari_kits_isteklerine_cevirir():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, json.loads(request.content or b"null")))
        if request.method == "POST":
            return httpx.Response(201, json={"kitId": "k1", "taskId": "g1", "status": "queued"})
        if request.url.path == "/api/kits":
            return httpx.Response(200, json={"kits": [{"id": "k1", "name": "Kod"}]})
        return httpx.Response(200, json={"items": []})

    factory = lambda: _client(handler)  # noqa: E731
    liste = await dispatch_kits("kit.listele", {}, factory)
    assert liste["ok"] and liste["kitler"][0]["name"] == "Kod" and liste["adres"]
    gonder = await dispatch_kits(
        "kit.gonder",
        {"kit": "Kod", "metin": "Raporu yaz", "baslik": "Rapor", "tur": "mesaj"},
        factory,
    )
    assert gonder == {"ok": True, "kitId": "k1", "taskId": "g1", "status": "queued"}
    assert seen[1] == (
        "POST",
        "/api/kits/Kod/inbox",
        {"text": "Raporu yaz", "kind": "message", "title": "Rapor"},
    )
    kutu = await dispatch_kits("kit.durum", {"kit": "Kod"}, factory)
    assert kutu == {"ok": True, "kayitlar": []}


async def test_kit_rpc_gecersiz_girdi_ve_kits_hatasinda_ok_false_doner():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403, json={"error": "Bu Kit'in Fusion izni kapalı; Kit ayarlarından aç."}
        )

    factory = lambda: _client(handler)  # noqa: E731
    assert not (await dispatch_kits("kit.gonder", {"metin": "Görev"}, factory))["ok"]
    assert not (await dispatch_kits("kit.gonder", {"kit": "Kod", "metin": "ab"}, factory))["ok"]
    assert not (
        await dispatch_kits("kit.gonder", {"kit": "Kod", "metin": "Görev", "tur": "x"}, factory)
    )["ok"]
    red = await dispatch_kits("kit.gonder", {"kit": "Kod", "metin": "Uzun görev"}, factory)
    assert red == {"ok": False, "metin": "Bu Kit'in Fusion izni kapalı; Kit ayarlarından aç."}
    assert (await dispatch_kits("kit.bilinmeyen", {}, factory))[
        "metin"
    ] == "Bilinmeyen Kits isteği."
