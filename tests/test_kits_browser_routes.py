"""Kit → kullanıcının Chrome'u köprüsü: `chrome.kit_komut` RPC'si (P-063)."""

from __future__ import annotations

import json

from fusion_cli.appserver import kits_browser_routes as browser
from fusion_cli.appserver.protocol import Request
from fusion_cli.appserver.session import AppSession


class _Kopru:
    def __init__(self, veri=None, hata=None) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.veri = veri if veri is not None else {"title": "Sayfa", "elements": [{"ref": "e1"}]}
        self.hata = hata

    async def invoke(self, operation, args):
        self.calls.append((operation, args))
        if self.hata:
            raise self.hata
        return {"ok": True, "veri": self.veri}


def test_kit_eylemleri_eklenti_komutlarina_eslenir_ve_adres_kapisi_uygulanir(monkeypatch):
    assert browser.build_command({"action": "read"}) == ("snapshot", {})
    assert browser.build_command({"action": "tabs"}) == ("tabs", {})
    assert browser.build_command({"action": "find", "value": " Gönder "}) == (
        "find",
        {"query": "Gönder"},
    )
    assert browser.build_command({"action": "text", "value": "2"}) == ("text_page", {"page": 2})
    assert browser.build_command({"action": "scroll", "value": "up:300", "ref": "e2"}) == (
        "scroll",
        {"direction": "up", "amount": 300, "ref": "e2"},
    )
    # Adres kapısı DNS çözer; açık adres için kapı testte geçirilir, kapalı adres aşağıda.
    monkeypatch.setattr(browser, "browser_block_reason", lambda url: None)
    assert browser.build_command({"action": "navigate", "url": "ornek.com"}) == (
        "navigate",
        {"url": "https://ornek.com"},
    )
    monkeypatch.undo()
    assert browser.build_command({"action": "click", "ref": "e3"}) == ("click", {"ref": "e3"})
    assert browser.build_command({"action": "type", "ref": "e3", "value": "merhaba"}) == (
        "type",
        {"ref": "e3", "text": "merhaba"},
    )
    assert browser.build_command({"action": "key", "value": "Escape"}) == ("key", {"key": "Escape"})
    # Geçersizler Türkçe hata metni döndürür; komut hiç kurulmaz.
    assert "Bilinmeyen" in browser.build_command({"action": "screenshot"})
    assert "ref" in browser.build_command({"action": "click"})
    assert "value" in browser.build_command({"action": "find"})
    # İç ağ ve bulut metadata adresleri Kit için de kapalıdır.
    engel = browser.build_command({"action": "navigate", "url": "http://169.254.169.254/"})
    assert isinstance(engel, str) and "erişilemez" in engel
    assert browser.is_read_action("read") and not browser.is_read_action("click")


async def test_kit_chrome_istegi_yalniz_metin_doner_ve_sirlari_gizler():
    kopru = _Kopru(
        veri={
            "text": "API anahtarı: sk-proj-abcdefghijklmnop1234567890",
            "image": "data:image/jpeg;base64,AAAA",
        }
    )
    sonuc = await browser.dispatch_kits_browser({"action": "read"}, kopru)
    assert sonuc["ok"] and sonuc["status"] == "ok"
    assert "sk-proj" not in sonuc["text"] and "image" not in sonuc["text"]
    assert kopru.calls == [("snapshot", {})]
    yok = await browser.dispatch_kits_browser({"action": "read"}, None)
    assert yok == {"ok": False, "status": "unavailable", "text": "Chrome köprüsü bu oturumda yok."}
    kopuk = await browser.dispatch_kits_browser(
        {"action": "click", "ref": "e1"},
        _Kopru(hata=ConnectionError("Chrome eklentisi bağlı değil.")),
    )
    assert kopuk["status"] == "unavailable"
    zaman = await browser.dispatch_kits_browser(
        {"action": "click", "ref": "e1"}, _Kopru(hata=TimeoutError())
    )
    assert zaman["status"] == "failed" and "yeniden oku" in zaman["text"]


async def test_oturum_kit_chrome_rpcsini_koprusune_yonlendirir(tmp_path, monkeypatch):
    lines = []
    session = AppSession(lines.append, root=tmp_path, home=tmp_path / "ev")
    kopru = _Kopru()
    monkeypatch.setattr(session, "_chrome", kopru)
    await session.handle(Request("1", "chrome.kit_komut", {"action": "find", "value": "Giriş"}))
    sonuc = json.loads(lines[-1])["veri"]
    assert sonuc["ok"] and json.loads(sonuc["text"])["elements"] == [{"ref": "e1"}]
    assert kopru.calls == [("find", {"query": "Giriş"})]
    await session.handle(Request("2", "chrome.kit_komut", {"action": "screenshot"}))
    assert not json.loads(lines[-1])["veri"]["ok"]
