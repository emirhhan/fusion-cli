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
    def __init__(self, ad: str, submit: bool = False) -> None:
        super().__init__()
        self._ad, self._submit = ad, submit

    async def invoke(self, name, data):
        self.cagrilar.append((name, data))
        return {"ok": True, "veri": {"name": self._ad, "type": "", "submit": self._submit}}


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
