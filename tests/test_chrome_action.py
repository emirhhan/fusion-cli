from __future__ import annotations

from types import SimpleNamespace

from fusion_cli.core.tools import ToolEffect
from fusion_cli.tools import chrome


class _Kopru:
    def __init__(self) -> None:
        self.cagrilar: list[tuple[str, dict]] = []

    async def invoke(self, name, data):
        self.cagrilar.append((name, data))
        return {"ok": True, "veri": {"tamam": True}}


async def test_iz_birakmayan_islemler_salt_okuma_tus_sorulur():
    for islem in ("scroll", "wait", "tabs", "open", "tab", "select", "screenshot"):
        assert await chrome.chrome_action_effect({"action": islem}, None) is ToolEffect.REMOTE_READ
    # Enter bir formu gönderebilir: aracın kendi (sorulan) etkisi geçerli kalır.
    assert await chrome.chrome_action_effect({"action": "key"}, None) is None


async def test_islemler_eklenti_komutlarina_eslenir():
    kopru = _Kopru()
    baglam = SimpleNamespace(chrome=kopru)

    await chrome.chrome_action({"action": "scroll", "value": "up"}, baglam)
    await chrome.chrome_action({"action": "wait", "value": "Kaydedildi"}, baglam)
    await chrome.chrome_action({"action": "key", "value": "Escape", "ref": "e3"}, baglam)
    await chrome.chrome_action({"action": "select", "ref": "e4", "value": "30 gün"}, baglam)

    assert kopru.cagrilar == [
        ("scroll", {"direction": "up"}),
        ("wait", {"text": "Kaydedildi", "timeout_ms": 20_000}),
        ("key", {"ref": "e3", "key": "Escape"}),
        ("select", {"ref": "e4", "value": "30 gün"}),
    ]


async def test_eksik_degerde_anlasilir_hata():
    baglam = SimpleNamespace(chrome=_Kopru())
    sonuc = await chrome.chrome_action({"action": "wait"}, baglam)
    assert sonuc.ok is False and "value" in sonuc.output
    sonuc = await chrome.chrome_action({"action": "zıpla"}, baglam)
    assert sonuc.ok is False


def test_tum_chrome_araclari_kayitli_ve_panel_turunda_sunuluyor():
    """Ölçüldü: araçlar birleştirilirken chrome_click/chrome_type yanlışlıkla silinmişti."""
    from fusion_cli.appserver.session import CHROME_TURN_TOOLS
    from fusion_cli.tools.builtin import build_registry

    kayitli = set(build_registry().names())
    assert kayitli >= CHROME_TURN_TOOLS
    assert {"chrome_click", "chrome_type", "chrome_page", "chrome_action"} <= CHROME_TURN_TOOLS


class _AdVerenKopru(_Kopru):
    def __init__(self, ad: str, submit: bool = False, link: bool = False) -> None:
        super().__init__()
        self._ad, self._submit, self._link = ad, submit, link

    async def invoke(self, name, data):
        self.cagrilar.append((name, data))
        veri = {"name": self._ad, "type": "", "submit": self._submit, "link": self._link}
        return {"ok": True, "veri": veri}


async def test_siradan_tiklama_sorulmaz_gonderme_ve_silme_sorulur():
    """Claude in Chrome gibi: gezinme ve sıradan tıklama sorulmaz, göndermede durulur."""

    async def etki(ad, submit=False):
        baglam = SimpleNamespace(chrome=_AdVerenKopru(ad, submit))
        return await chrome.chrome_click_effect({"ref": "e1"}, baglam)

    assert await etki("Kampanyalar") is ToolEffect.REMOTE_READ
    assert await etki("Yorumları görüntüle") is ToolEffect.REMOTE_READ
    assert await etki("Paylaş") is None
    assert await etki("Gönder") is None
    assert await etki("Delete campaign") is None
    assert await etki("Devam", submit=True) is None
    assert await chrome.chrome_click_effect({"ref": "e1"}, None) is None


async def test_gonderi_karti_ve_baglanti_sorulmaz_eylem_dugmesi_sorulur():
    """Ölçüldü (27 Eylül): Instagram gönderi kartının adı "1.234 beğenme, 12 yorum"
    içeriyor ve "beğen" kuralına takılıp okuma turunu izin sorusunda durduruyordu."""

    async def etki(ad, link=False):
        baglam = SimpleNamespace(chrome=_AdVerenKopru(ad, link=link))
        return await chrome.chrome_click_effect({"ref": "e1"}, baglam)

    assert await etki("1.234 beğenme, 12 yorum") is ToolEffect.REMOTE_READ
    assert await etki("Beğen") is None
    assert await etki("Beğeni ekle ve paylaş", link=True) is ToolEffect.REMOTE_READ
    assert await etki("Kampanyayı sil", link=True) is ToolEffect.REMOTE_READ
    # Bağlantı olsa da oturumu kapatmak kullanıcıya sorulur.
    assert await etki("Çıkış yap", link=True) is None
    assert await etki("Log out", link=True) is None


async def test_claude_in_chrome_esdegeri_yeni_islemler_eklenti_komutlarina_eslenir():
    kopru = _Kopru()
    baglam = SimpleNamespace(chrome=kopru)

    for islem, deger, ref in (
        ("back", None, None),
        ("forward", None, None),
        ("reload", None, None),
        ("close", "42", None),
        ("hover", None, "e7"),
        ("text", "3", None),
        ("text", None, None),
    ):
        args = {"action": islem}
        if deger is not None:
            args["value"] = deger
        if ref is not None:
            args["ref"] = ref
        assert (await chrome.chrome_action(args, baglam)).ok, islem

    assert kopru.cagrilar == [
        ("history", {"dir": "back"}),
        ("history", {"dir": "forward"}),
        ("history", {"dir": "reload"}),
        ("tab_close", {"id": 42}),
        ("hover", {"ref": "e7"}),
        ("text_page", {"page": 3}),
        ("text_page", {"page": 1}),
    ]
    assert not (await chrome.chrome_action({"action": "close"}, baglam)).ok
    assert not (await chrome.chrome_action({"action": "hover"}, baglam)).ok
    for islem in ("back", "forward", "reload", "close", "hover", "text"):
        assert await chrome.chrome_action_effect({"action": islem}, None) is ToolEffect.REMOTE_READ


def _jpeg(genislik: int, yukseklik: int) -> bytes:
    """En küçük SOF0 başlıklı sahte JPEG."""
    sof = bytes([0xFF, 0xC0, 0x00, 0x11, 0x08]) + yukseklik.to_bytes(2, "big")
    return b"\xff\xd8" + sof + genislik.to_bytes(2, "big") + b"\x03" + b"\x00" * 9


def test_jpeg_boyutu_basliktan_okunur():
    assert chrome.jpeg_size(_jpeg(2880, 1600)) == (2880, 1600)
    assert chrome.jpeg_size(b"bozuk") is None


async def test_koordinata_tiklama_retina_olcegini_cevirir_ve_riskliyse_sorulur():
    import base64

    class _EkranKopru(_Kopru):
        def __init__(self, ad: str) -> None:
            super().__init__()
            self._ad = ad

        async def invoke(self, name, data):
            self.cagrilar.append((name, data))
            if name == "screenshot":
                goruntu = base64.b64encode(_jpeg(2880, 1600)).decode()
                veri = {"image": f"data:image/jpeg;base64,{goruntu}", "width": 1440}
                return {"ok": True, "veri": veri}
            if name == "describe_at":
                return {"ok": True, "veri": {"name": self._ad, "tag": "button"}}
            return {"ok": True, "veri": {}}

    kopru = _EkranKopru("Kampanyalar")
    baglam = SimpleNamespace(chrome=kopru)
    goruntu = await chrome.chrome_action({"action": "screenshot"}, baglam)
    assert "click_at" in goruntu.output

    # Görüntü 2880 px, sayfa 1440 CSS px: (400, 300) → (200, 150).
    assert await chrome.chrome_action_effect(
        {"action": "click_at", "value": "400,300"}, baglam
    ) is ToolEffect.REMOTE_READ
    assert (await chrome.chrome_action({"action": "click_at", "value": "400, 300"}, baglam)).ok
    assert ("describe_at", {"x": 200.0, "y": 150.0}) in kopru.cagrilar
    assert ("click_at", {"x": 200.0, "y": 150.0}) in kopru.cagrilar

    riskli = SimpleNamespace(chrome=_EkranKopru("Satın al"))
    assert await chrome.chrome_action_effect({"action": "click_at", "value": "1,1"}, riskli) is None
    assert not (await chrome.chrome_action({"action": "click_at", "value": "abc"}, baglam)).ok
