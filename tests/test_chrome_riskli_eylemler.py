"""Chrome eklentisinde gönderme kısayolları ve yaygın 'kalıcı' düğmeler sorulur (T1-16, T1-17).

Ölçüldü (29 Ekim): `_key_effect` yalnız çıplak "Enter"a odak bakıyordu; Gmail/Slack'te
Meta+Enter / Ctrl+Enter mesajı GÖNDERİR ama sorulmuyordu, Delete/Backspace da sorulmuyordu.
`_RISKY_CLICK` "Place order", "Allow", "Donate", "Withdraw", "Unfollow" gibi düğmeleri
tanımıyordu.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from fusion_cli.core.tools import ToolEffect
from fusion_cli.tools import chrome
from fusion_cli.tools.chrome import _RISKY_CLICK


class _OdakKoprusu:
    def __init__(self, veri: dict) -> None:
        self._veri = veri

    async def invoke(self, name, data):
        del name, data
        return {"ok": True, "veri": self._veri}


async def _tus_etkisi(tus: str, veri: dict) -> ToolEffect | None:
    baglam = SimpleNamespace(chrome=_OdakKoprusu(veri))
    return await chrome.chrome_action_effect({"action": "key", "value": tus}, baglam)


@pytest.mark.parametrize("tus", ["Meta+Enter", "Control+Enter", "Ctrl+Enter", "Shift+Enter"])
async def test_degistiricili_enter_cubuk_enter_gibi_mesaj_kutusunda_sorulur(tus):
    assert await _tus_etkisi(tus, {"editable": True, "hint": "Mesaj yaz"}) is None


@pytest.mark.parametrize("tus", ["Meta+Enter", "Control+Enter"])
async def test_degistiricili_enter_arama_kutusunda_sorulmaz(tus):
    assert await _tus_etkisi(tus, {"search": True, "name": "Ara"}) is ToolEffect.REMOTE_INTERACT


@pytest.mark.parametrize("tus", ["Delete", "Backspace", "Meta+Backspace", "Shift+Delete"])
async def test_silme_tuslari_yazi_alani_disinda_sorulur(tus):
    assert await _tus_etkisi(tus, {"editable": False, "name": "E-posta listesi"}) is None


@pytest.mark.parametrize("tus", ["Delete", "Backspace"])
async def test_silme_tuslari_yazi_alaninda_yazmadir_sorulmaz(tus):
    assert await _tus_etkisi(tus, {"editable": True, "name": "Ad"}) is ToolEffect.REMOTE_INTERACT


@pytest.mark.parametrize("tus", ["Delete", "Meta+Enter"])
async def test_odak_okunamazsa_silme_ve_gonderme_kisayolu_sorulur(tus):
    assert await chrome.chrome_action_effect({"action": "key", "value": tus}, None) is None


@pytest.mark.parametrize("tus", ["Tab", "Escape", "ArrowDown", "Meta+a", "Shift+Tab"])
async def test_zararsiz_tuslar_sorulmaz(tus):
    assert await chrome.chrome_action_effect({"action": "key", "value": tus}, None) is (
        ToolEffect.REMOTE_INTERACT
    )


@pytest.mark.parametrize(
    "ad",
    [
        "Siparişi ver",
        "Sipariş ver",
        "Place order",
        "Order now",
        "Allow",
        "Authorize app",
        "İzin ver",
        "Yetki ver",
        "Subscribe",
        "Donate",
        "Bağış yap",
        "Withdraw",
        "Transfer",
        "Havale yap",
        "Teklif ver",
        "Place bid",
        "Upgrade",
        "Yükselt",
        "Cancel subscription",
        "Aboneliği iptal et",
        "Siparişi iptal et",
        "Unfollow",
        "Takibi bırak",
        "Ödemeye geç",
        "Ödemeyi tamamla",
        "Approve",
        "Pay now",
    ],
)
def test_yaygin_kalici_dugmeler_riskli_sayilir(ad):
    assert _RISKY_CLICK.search(ad), ad


@pytest.mark.parametrize(
    "ad",
    ["Reklamlar", "İptal", "Cancel", "1.234 beğenme, 12 yorum", "Sipariş geçmişi", "Allowance"],
)
def test_zararsiz_adlar_riskli_sayilmaz(ad):
    assert not _RISKY_CLICK.search(ad), ad
