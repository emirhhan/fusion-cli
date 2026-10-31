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


async def test_sinirda_kesilen_anahtar_ve_hata_metni_de_redakte_edilir():
    # Ölçüldü (31 Ekim): `redact(text[:MAX])` sırası, sınırda yarım kalan anahtarın
    # ("sk-proj-abcd") desene uymayıp Kit'e sızmasına izin veriyordu.
    onek = '{"text": "'
    dolgu = "x" * (browser.MAX_TEXT_CHARS - len(onek) - len(" sk-proj-abcd"))
    kopru = _Kopru(veri={"text": dolgu + " sk-proj-abcdefghijklmnop1234567890"})
    sonuc = await browser.dispatch_kits_browser({"action": "read"}, kopru)
    assert "sk-proj" not in sonuc["text"]
    assert len(sonuc["text"]) <= browser.MAX_TEXT_CHARS
    hatali = _Kopru()
    hatali.veri = None

    async def invoke(operation, args):
        return {"ok": False, "hata": "Öğe bulunamadı: token=sk-proj-abcdefghijklmnop1234567890"}

    hatali.invoke = invoke
    sonuc = await browser.dispatch_kits_browser({"action": "click", "ref": "e1"}, hatali)
    assert sonuc["status"] == "failed" and "sk-proj" not in sonuc["text"]
    kopuk = await browser.dispatch_kits_browser(
        {"action": "click", "ref": "e1"},
        _Kopru(hata=ConnectionError("Bağlı değil: sk-proj-abcdefghijklmnop1234567890")),
    )
    assert "sk-proj" not in kopuk["text"]


async def test_kapali_araclar_kit_yolunu_da_kapatir():
    # Ölçüldü (31 Ekim): `runtime.disabled_tools` yalnız model araçlarını süzüyordu;
    # `chrome_click` kapalı kullanıcıda Kit yine tıklayabiliyordu.
    kopru = _Kopru()
    assert browser.disabled_reason("click", ("chrome_click",))
    assert browser.disabled_reason("read", ("chrome_page",))
    assert browser.disabled_reason("tabs", ("chrome_action",))
    assert browser.disabled_reason("read", ("fusion_browser",))
    assert browser.disabled_reason("read", ("chrome_click",)) is None
    sonuc = await browser.dispatch_kits_browser(
        {"action": "click", "ref": "e1"}, kopru, disabled=("chrome_click",)
    )
    assert sonuc["status"] == "denied" and "chrome_click" in sonuc["text"]
    assert kopru.calls == []
    tarif = await browser.describe_kits_browser(
        {"action": "click", "ref": "e1"}, kopru, disabled=("fusion_browser",)
    )
    assert tarif["status"] == "denied" and kopru.calls == []


async def test_etkilesim_tarifi_oge_adini_ve_riskini_verir():
    # Ölçüldü (31 Ekim): onay penceresi click/type/key için hedefi göstermiyordu.
    riskli = _Kopru(veri={"name": "Siparişi onayla", "type": "button", "submit": True})
    tarif = await browser.describe_kits_browser({"action": "click", "ref": "e12"}, riskli)
    assert tarif == {"ok": True, "status": "ok", "hedef": "Siparişi onayla", "riskli": True}
    assert riskli.calls == [("describe", {"ref": "e12"})]
    sakin = _Kopru(veri={"name": "Sonraki sayfa", "type": "button"})
    tarif = await browser.describe_kits_browser({"action": "click", "ref": "e2"}, sakin)
    assert tarif["hedef"] == "Sonraki sayfa" and tarif["riskli"] is False
    # Adı okunamayan öğe riskli sayılır; kullanıcı körlemesine onaylamaz.
    okunmaz = _Kopru(hata=TimeoutError())
    tarif = await browser.describe_kits_browser({"action": "click", "ref": "e2"}, okunmaz)
    assert tarif["ok"] and tarif["riskli"] is True and tarif["hedef"] == ""
    # Enter: mesaj kutusunda gönderir (riskli), arama kutusunda gezinir.
    mesaj = _Kopru(veri={"name": "Mesaj", "editable": True})
    tarif = await browser.describe_kits_browser({"action": "key", "ref": "e5"}, mesaj)
    assert tarif["riskli"] is True and mesaj.calls == [("describe_key", {"ref": "e5"})]
    arama = _Kopru(veri={"name": "Ara", "search": True})
    tarif = await browser.describe_kits_browser({"action": "key", "value": "Enter"}, arama)
    assert tarif["riskli"] is False and arama.calls == [("describe_key", {})]
    # Escape eklentiye sorulmaz; yazma hedef alanın adını taşır.
    esc = _Kopru()
    tarif = await browser.describe_kits_browser({"action": "key", "value": "Escape"}, esc)
    assert tarif["riskli"] is False and esc.calls == []
    alan = _Kopru(veri={"name": "Arama kutusu", "type": "input"})
    tarif = await browser.describe_kits_browser(
        {"action": "type", "ref": "e7", "value": "merhaba"}, alan
    )
    assert tarif["hedef"] == "Arama kutusu" and tarif["riskli"] is False
    # Hedef adı sayfadan gelir: sırlar gizlenir, uzunluk sınırlıdır.
    uzun = _Kopru(veri={"name": "sk-proj-abcdefghijklmnop1234567890 " + "a" * 300})
    tarif = await browser.describe_kits_browser({"action": "click", "ref": "e1"}, uzun)
    assert "sk-proj" not in tarif["hedef"] and len(tarif["hedef"]) <= browser.MAX_TARGET_CHARS
    assert (await browser.describe_kits_browser({"action": "click", "ref": "e1"}, None))[
        "status"
    ] == "unavailable"


async def test_oturum_kit_tarif_rpcsi_ve_kapali_arac_kapisi(tmp_path, monkeypatch):
    import dataclasses

    lines = []
    session = AppSession(lines.append, root=tmp_path, home=tmp_path / "ev")
    kopru = _Kopru(veri={"name": "Gönder", "type": "button"})
    monkeypatch.setattr(session, "_chrome", kopru)
    await session.handle(Request("1", "chrome.kit_tarif", {"action": "click", "ref": "e1"}))
    sonuc = json.loads(lines[-1])["veri"]
    assert sonuc == {"ok": True, "status": "ok", "hedef": "Gönder", "riskli": True}
    config = session._state.config
    session._state.config = dataclasses.replace(
        config, runtime=dataclasses.replace(config.runtime, disabled_tools=("chrome_click",))
    )
    kopru.calls.clear()
    await session.handle(Request("2", "chrome.kit_komut", {"action": "click", "ref": "e1"}))
    assert json.loads(lines[-1])["veri"]["status"] == "denied" and kopru.calls == []
    await session.handle(Request("3", "chrome.kit_komut", {"action": "read"}))
    assert json.loads(lines[-1])["veri"]["ok"]
