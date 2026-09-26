"""Eklenti köprüsü yalnız doğru anahtarlı, güvenli istekleri kabul eder."""

from __future__ import annotations

import asyncio
import base64

import httpx
import pytest

from fusion_cli.appserver.chrome_bridge import ChromeBridge
from fusion_cli.core.tool_content import ToolContentType
from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import chrome

pytestmark = pytest.mark.asyncio
ORIGIN = "chrome-extension://abcdefghijklmnop"


async def test_yalniz_eklenti_origin_ve_anahtari_kabul_edilir() -> None:
    bridge = ChromeBridge()
    state = await bridge.start()
    address = f"http://127.0.0.1:{state['port']}"
    async with httpx.AsyncClient(trust_env=False) as client:
        assert (await client.get(f"{address}/status")).status_code == 401
        assert (
            await client.get(f"{address}/status", headers={"Origin": "https://example.com"})
        ).status_code == 403
        assert (
            await client.get(f"{address}/status", headers={"Origin": ORIGIN})
        ).status_code == 401
        response = await client.get(
            f"{address}/status",
            headers={"Origin": ORIGIN, "Authorization": f"Bearer {state['anahtar']}"},
        )
        assert response.status_code == 200
        assert response.json()["bagli"] is True
        assert "anahtar" in response.json() and response.json()["anahtar"] is None
        # Chrome uzantı sayfasının ayrıcalıklı fetch'i GET'te Origin göndermeyebilir.
        response = await client.get(
            f"{address}/status", headers={"Authorization": f"Bearer {state['anahtar']}"}
        )
        assert response.status_code == 200
        assert (await client.options(f"{address}/status")).status_code == 403
    await bridge.close()


async def test_komut_izinli_eklentiye_gider_ve_sonuc_araca_doner(tmp_path) -> None:
    bridge = ChromeBridge()
    state = await bridge.start()
    address = f"http://127.0.0.1:{state['port']}"
    headers = {"Origin": ORIGIN, "Authorization": f"Bearer {state['anahtar']}"}
    async with httpx.AsyncClient(trust_env=False) as client:
        await client.get(f"{address}/status", headers=headers)
        context = ToolContext(root=tmp_path, chrome=bridge)
        task = asyncio.create_task(chrome.chrome_page({}, context))
        command = (await client.post(f"{address}/poll", headers=headers, json={})).json()
        assert command["islem"] == "snapshot"
        result = await client.post(
            f"{address}/result",
            headers=headers,
            json={"id": command["id"], "ok": True, "veri": {"title": "Deneme"}},
        )
        assert result.json() == {"ok": True}
        outcome = await task
        assert outcome.ok and "Deneme" in outcome.output
    await bridge.close()


async def test_kopuk_eklenti_ve_yanlis_url_acik_hata_verir(tmp_path) -> None:
    bridge = ChromeBridge()
    context = ToolContext(root=tmp_path, chrome=bridge)
    assert not (await chrome.chrome_page({}, context)).ok
    assert not (await chrome.chrome_navigate({"url": "file:///etc/passwd"}, context)).ok


async def test_ekran_goruntusu_gorsel_icerik_olarak_doner(tmp_path) -> None:
    class FakeChrome:
        async def invoke(self, operation, args):
            assert operation == "screenshot"
            return {
                "ok": True,
                "veri": {"image": "data:image/jpeg;base64," + base64.b64encode(b"jpeg").decode()},
            }

    result = await chrome.chrome_screenshot({}, ToolContext(root=tmp_path, chrome=FakeChrome()))

    assert result.ok
    assert result.content[0].type is ToolContentType.IMAGE


async def test_kapat_ac_eski_komutu_yeni_eklentiye_vermez() -> None:
    bridge = ChromeBridge()
    first = await bridge.start()
    address = f"http://127.0.0.1:{first['port']}"
    headers = {"Origin": ORIGIN, "Authorization": f"Bearer {first['anahtar']}"}
    async with httpx.AsyncClient(trust_env=False) as client:
        await client.get(f"{address}/status", headers=headers)
        task = asyncio.create_task(bridge.invoke("snapshot", {}))
        await asyncio.sleep(0)
        await bridge.close()
        with pytest.raises(ConnectionError):
            await task
        second = await bridge.start()
        address = f"http://127.0.0.1:{second['port']}"
        headers["Authorization"] = f"Bearer {second['anahtar']}"
        await client.get(f"{address}/status", headers=headers)
        response = await client.post(f"{address}/poll", headers=headers, json={})
        assert response.json() == {}
    await bridge.close()


async def test_panel_calisan_turu_durdurabilir() -> None:
    cancelled: list[bool] = []

    def cancel() -> dict[str, object]:
        cancelled.append(True)
        return {"ok": True, "metin": "Durduruldu"}

    bridge = ChromeBridge(on_cancel=cancel)
    state = await bridge.start()
    address = f"http://127.0.0.1:{state['port']}"
    headers = {"Origin": ORIGIN, "Authorization": f"Bearer {state['anahtar']}"}
    async with httpx.AsyncClient(trust_env=False) as client:
        response = await client.post(f"{address}/cancel", headers=headers, json={})
        assert response.json() == {"ok": True, "metin": "Durduruldu"}
        assert cancelled == [True]
        denied = await client.post(f"{address}/cancel", headers={"Origin": ORIGIN}, json={})
        assert denied.status_code == 401
    await bridge.close()
