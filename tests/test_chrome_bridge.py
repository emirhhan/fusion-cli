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


async def test_panel_canli_adimlari_uzun_yoklamayla_alir_ve_soruyu_cevaplar() -> None:
    """Claude in Chrome gibi: panel adımları canlı görür, izin kartını kendisi cevaplar."""
    from fusion_cli.appserver.protocol import encode_event, encode_question

    cevaplar: list[tuple[str, dict]] = []

    def cevapla(kimlik: str, veri: dict) -> bool:
        cevaplar.append((kimlik, veri))
        return kimlik == "7"

    bridge = ChromeBridge(on_answer=cevapla)
    state = await bridge.start()
    address = f"http://127.0.0.1:{state['port']}"
    headers = {"Origin": ORIGIN, "Authorization": f"Bearer {state['anahtar']}"}
    yazilan: list[str] = []
    yaz = bridge.tee(yazilan.append)
    async with httpx.AsyncClient(trust_env=False) as client:
        bekleyen = asyncio.create_task(
            client.post(f"{address}/events", headers=headers, json={"after": 0})
        )
        await asyncio.sleep(0.05)
        yaz(
            encode_event(
                {
                    "olay": "ToolExecuted",
                    "name": "chrome_action",
                    "args": {"action": "scroll"},
                    "outcome": "ok",
                    "output": "{}",
                }
            )
        )
        yaz(encode_event({"olay": "TokenReceived", "text": "x"}))
        cevap = (await bekleyen).json()
        assert [olay["metin"] for olay in cevap["olaylar"]] == ["Sayfa aşağı kaydırıldı"]
        son = cevap["son"]

        yaz(encode_question("7", {"tur": "onay", "baslik": "Tıklansın mı?"}))
        cevap = (
            await client.post(f"{address}/events", headers=headers, json={"after": son})
        ).json()
        assert cevap["olaylar"][0]["tur"] == "soru" and cevap["olaylar"][0]["id"] == "7"

        sonuc = await client.post(
            f"{address}/answer", headers=headers, json={"id": "7", "veri": {"secim": "once"}}
        )
        assert sonuc.json() == {"ok": True}
        assert cevaplar == [("7", {"secim": "once"})]
        # Yalnız secim/metin alanları iletilir; kimliksiz cevap reddedilir.
        await client.post(
            f"{address}/answer",
            headers=headers,
            json={"id": "8", "veri": {"secim": "deny", "kod": "x"}},
        )
        assert cevaplar[-1] == ("8", {"secim": "deny"})
        assert (
            await client.post(f"{address}/answer", headers=headers, json={"veri": {}})
        ).status_code == 400
    # Masaüstü teline yazılan her satır aynen geçer.
    assert len(yazilan) == 3
    await bridge.close()


async def test_tiklamadan_once_okunan_oge_adi_izin_karti_icin_saklanir() -> None:
    bridge = ChromeBridge()
    state = await bridge.start()
    address = f"http://127.0.0.1:{state['port']}"
    headers = {"Origin": ORIGIN, "Authorization": f"Bearer {state['anahtar']}"}
    async with httpx.AsyncClient(trust_env=False) as client:
        await client.get(f"{address}/status", headers=headers)
        task = asyncio.create_task(bridge.invoke("describe", {"ref": "e52"}))
        command = (await client.post(f"{address}/poll", headers=headers, json={})).json()
        await client.post(
            f"{address}/result",
            headers=headers,
            json={"id": command["id"], "ok": True, "veri": {"name": "  Yorum yap ", "tag": "div"}},
        )
        await task
    assert bridge.element_name("e52") == "Yorum yap"
    assert bridge.element_name("e1") is None
    assert bridge.element_name(None) is None
    await bridge.close()
