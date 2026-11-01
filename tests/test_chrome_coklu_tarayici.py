"""#432: köprüye birden çok tarayıcı bağlanır; liste, seçim, geçiş ve kalıcı seçim."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from fusion_cli.appserver.chrome_bridge import ChromeBridge
from fusion_cli.appserver.chrome_devices import BrowserChoiceRequired, parse_device
from fusion_cli.cli.repl import chrome_command
from fusion_cli.cli.repl.chrome_cli import ChromeSession
from fusion_cli.core.tools import ToolContext
from fusion_cli.tools.builtin import build_registry

pytestmark = pytest.mark.asyncio
ORIGIN = "chrome-extension://abcdefghijklmnop"
P = "claude-in-chrome__"
_REGISTRY = build_registry()


def _iki_tarayici(bridge: ChromeBridge) -> None:
    bridge._mark_command_channel_alive("chrome-1", "Chrome")
    bridge._mark_command_channel_alive("edge-1", "Edge")


async def test_iki_tarayici_listelenir_secim_yokken_kullaniciya_sorulur() -> None:
    bridge = ChromeBridge()
    await bridge.start()
    _iki_tarayici(bridge)
    adlar = {b["deviceId"]: b for b in bridge.browsers()}
    assert set(adlar) == {"chrome-1", "edge-1"}
    assert not any(b["inUse"] for b in adlar.values())
    with pytest.raises(BrowserChoiceRequired) as hata:
        await bridge.invoke("snapshot", {})
    assert "Kullanıcıya" in str(hata.value) and "select_browser" in str(hata.value)
    assert not bridge._pending  # askıda kalan komut yok
    await bridge.close()


async def test_secilen_tarayiciya_komut_gider_ve_secim_yeni_baglantida_korunur() -> None:
    bridge = ChromeBridge()
    state = await bridge.start()
    address = f"http://127.0.0.1:{state['port']}"
    headers = {"Origin": ORIGIN, "Authorization": f"Bearer {state['anahtar']}"}
    _iki_tarayici(bridge)
    assert bridge.select_browser("edge-1") == {"deviceId": "edge-1", "name": "Edge"}
    bridge._mark_command_channel_alive("brave-1", "Brave")  # üçüncü tarayıcı bağlandı
    assert [b["deviceId"] for b in bridge.browsers() if b["inUse"]] == ["edge-1"]
    async with httpx.AsyncClient(trust_env=False) as client:
        task = asyncio.create_task(bridge.invoke("snapshot", {}))
        await asyncio.sleep(0)
        assert bridge._devices.queue("chrome-1").empty()
        body = {"cihaz": {"id": "edge-1", "ad": "Edge"}}
        command = (await client.post(f"{address}/poll", headers=headers, json=body)).json()
        assert command["islem"] == "snapshot"
        await client.post(
            f"{address}/result",
            headers=headers,
            json={"id": command["id"], "ok": True, "veri": {"title": "E"}, **body},
        )
        assert (await task)["veri"] == {"title": "E"}
    await bridge.close()
    await bridge.start()  # yeniden bağlanma seçimi silmez
    assert bridge._devices.selected == "edge-1"
    await bridge.close()


async def test_switch_browser_panelden_secimle_biter() -> None:
    bridge = ChromeBridge()
    state = await bridge.start()
    address = f"http://127.0.0.1:{state['port']}"
    headers = {"Origin": ORIGIN, "Authorization": f"Bearer {state['anahtar']}"}
    _iki_tarayici(bridge)
    context = ToolContext(root=".", chrome=bridge)  # type: ignore[arg-type]
    task = asyncio.create_task(_REGISTRY.execute(P + "switch_browser", {}, context))
    await asyncio.sleep(0.05)
    assert bridge._feed[-1]["tur"] == "tarayici_sec"
    async with httpx.AsyncClient(trust_env=False) as client:
        answer = await client.post(
            f"{address}/select", headers=headers, json={"cihaz": {"id": "chrome-1", "ad": "Chrome"}}
        )
    assert answer.json()["ok"] is True
    result = await task
    assert result.ok and "chrome-1" in result.output
    await bridge.close()


async def test_arac_katmani_gercek_listeyi_ve_secimi_kullanir(tmp_path) -> None:
    bridge = ChromeBridge()
    await bridge.start()
    _iki_tarayici(bridge)
    context = ToolContext(root=tmp_path, chrome=bridge)  # type: ignore[arg-type]
    liste = await _REGISTRY.execute(P + "list_connected_browsers", {}, context)
    assert {b["deviceId"] for b in json.loads(liste.output)} == {"chrome-1", "edge-1"}
    bilinmeyen = await _REGISTRY.execute(P + "select_browser", {"deviceId": "x"}, context)
    assert not bilinmeyen.ok and "chrome-1" in bilinmeyen.output
    secim = await _REGISTRY.execute(P + "select_browser", {"deviceId": "chrome-1"}, context)
    assert secim.ok and bridge._devices.selected == "chrome-1"
    await bridge.close()


async def test_chrome_select_komutu_numarayla_secer() -> None:
    bridge = ChromeBridge()
    await bridge.start()
    _iki_tarayici(bridge)
    session = ChromeSession(bridge=bridge)
    liste = chrome_command.select(session, "")
    assert "1. Chrome (chrome-1)" in liste and "2. Edge (edge-1)" in liste
    assert "Edge (edge-1) seçildi" in chrome_command.select(session, "2")
    assert "kullanılıyor" in chrome_command.select(session, "").splitlines()[2]
    assert "yok" in chrome_command.select(session, "olmayan")
    await bridge.close()


async def test_eski_eklenti_kimliksiz_yerel_cihaz_sayilir() -> None:
    assert parse_device({}) == ("fusion-local", "Chrome")
    assert parse_device({"cihaz": {"id": "../x", "ad": "A"}}) == ("fusion-local", "Chrome")
    assert parse_device({"cihaz": {"id": "abc", "ad": " Brave "}}) == ("abc", "Brave")


async def test_masaustu_ayarlari_tarayici_secer() -> None:
    from fusion_cli.appserver.chrome_settings import dispatch_chrome_settings

    bridge = ChromeBridge()
    await bridge.start()
    _iki_tarayici(bridge)
    ok = await dispatch_chrome_settings(bridge, "chrome.tarayici_sec", {"deviceId": "edge-1"})
    assert ok["ok"] and bridge.status()["secili"] == "edge-1"
    yok = await dispatch_chrome_settings(bridge, "chrome.tarayici_sec", {"deviceId": "x"})
    assert not yok["ok"]
    await bridge.close()
