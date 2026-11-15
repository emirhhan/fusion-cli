"""Chrome'da her kipte yasak ve her kipte sorulan eylemler (#422).

Claude in Chrome: satın alma/finansal işlem, hesap oluşturma ve bot doğrulaması hiçbir kipte
yapılmaz; izin/yetki verme ve hassas bilgi girme her kipte (Skip all approvals dahil) sorulur.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from fusion_cli.core.tools import ToolContext, ToolEffect
from fusion_cli.engines.agent.approval import ApprovalMode, Decision, build_policy, resolve_request
from fusion_cli.tools import chrome
from fusion_cli.tools.builtin import build_registry


class _Kopru:
    def __init__(self, veri: dict) -> None:
        self._veri = veri
        self.calls: list[str] = []

    async def invoke(self, name, data):
        self.calls.append(name)
        if name.startswith("describe"):
            return {"ok": True, "veri": self._veri}
        return {"ok": True, "veri": {"changed": True}}


def _baglam(tmp_path, veri: dict) -> ToolContext:
    return ToolContext(root=tmp_path, chrome=_Kopru(veri))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "ad", ["Satın al", "Siparişi tamamla", "Buy now", "Place order", "Hesap oluştur",
           "Sign up", "I'm not a robot", "reCAPTCHA"],
)  # fmt: skip
async def test_yasak_tiklama_calismaz(tmp_path, ad):
    context = _baglam(tmp_path, {"name": ad, "type": "button"})
    result = await chrome.chrome_click({"ref": "e1"}, context)
    assert not result.ok and "her kipte yasak" in result.output
    assert "click" not in context.chrome.calls  # type: ignore[union-attr]


async def test_yasak_form_enter_ve_koordinat_tiklamasi_calismaz(tmp_path):
    context = _baglam(tmp_path, {"editable": True, "submit_name": "Ödemeyi tamamla"})
    result = await chrome.chrome_action({"action": "key", "value": "Enter"}, context)
    assert not result.ok and "key" not in context.chrome.calls  # type: ignore[union-attr]
    context = _baglam(tmp_path, {"name": "Checkout"})
    result = await chrome.chrome_action({"action": "double_click", "ref": "e2"}, context)
    assert not result.ok and "click" not in context.chrome.calls  # type: ignore[union-attr]


async def test_siradan_tiklama_calisir(tmp_path):
    context = _baglam(tmp_path, {"name": "Devamını oku", "type": "button"})
    assert (await chrome.chrome_click({"ref": "e1"}, context)).ok


async def test_yetki_verme_bypass_dahil_her_kipte_sorulur(tmp_path):
    effect = await chrome.chrome_click_effect(
        {"ref": "e1"}, SimpleNamespace(chrome=_Kopru({"name": "Authorize app"}))
    )
    assert effect is ToolEffect.REMOTE_DESTRUCTIVE


@pytest.mark.parametrize(
    "veri", [{"type": "password", "name": "Parola"}, {"name": "Kart numarası"},
             {"name": "x", "autocomplete": "cc-number"}, {"name": "CVV"}],
)  # fmt: skip
async def test_hassas_alana_yazma_bypassta_da_sorulur(tmp_path, veri):
    context = _baglam(tmp_path, veri)
    tool = build_registry().get("chrome_type")
    request = await resolve_request(
        tool, {"ref": "e1", "text": "1234"}, root=tmp_path, context=context
    )
    asked: list[object] = []

    class _Sor:
        async def confirm(self, req):
            asked.append(req)
            return True

    decision = await build_policy(ApprovalMode.BYPASS, _Sor()).decide(request)
    assert request.effect is ToolEffect.REMOTE_DESTRUCTIVE
    assert decision is Decision.ALLOW and len(asked) == 1


async def test_siradan_alana_yazma_etkilesimdir(tmp_path):
    context = _baglam(tmp_path, {"name": "Ad soyad"})
    assert await chrome.chrome_type_effect({"ref": "e1"}, context) is ToolEffect.REMOTE_INTERACT


@pytest.mark.parametrize(
    "ad", ["Place your order", "Continue to payment", "Proceed to checkout", "Confirm order",
           "Submit order", "Complete your purchase", "Join now", "Siparişi gönder",
           "Ödemeye devam et"],
)  # fmt: skip
async def test_gercek_magaza_dugmeleri_de_yasak(tmp_path, ad):
    """Amazon 'Place your order' ve benzeri gerçek düğme adları da yasak deseninde (#422)."""
    context = _baglam(tmp_path, {"name": ad, "type": "button"})
    result = await chrome.chrome_click({"ref": "e1"}, context)
    assert not result.ok and "her kipte yasak" in result.output
    assert "click" not in context.chrome.calls  # type: ignore[union-attr]


class _OkunmayanKopru:
    """Öğe tarifi zaman aşımına uğrar; diğer komutlar çalışır."""

    async def invoke(self, name, data):
        if name.startswith("describe"):
            raise TimeoutError("describe yanıt vermedi")
        return {"ok": True, "veri": {"changed": True}}


@pytest.mark.parametrize(
    ("tool", "args"),
    [("chrome_click", {"ref": "e1"}), ("chrome_type", {"ref": "e1", "text": "x"}),
     ("chrome_action", {"action": "double_click", "ref": "e1"})],
)  # fmt: skip
async def test_tarif_okunamazsa_bypassta_da_sorulur(tmp_path, tool, args):
    """Açık kapı yok: öğe okunamazsa yasak/hassas denetimi yapılamaz, her kipte sorulur."""
    context = ToolContext(root=tmp_path, chrome=_OkunmayanKopru())  # type: ignore[arg-type]
    request = await resolve_request(
        build_registry().get(tool), args, root=tmp_path, context=context
    )
    asked: list[object] = []

    class _Sor:
        async def confirm(self, req):
            asked.append(req)
            return False

    decision = await build_policy(ApprovalMode.BYPASS, _Sor()).decide(request)
    assert request.effect is ToolEffect.REMOTE_DESTRUCTIVE
    assert decision is not Decision.ALLOW and len(asked) == 1
