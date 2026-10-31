"""Riskli masaüstü eylem sınıflandırıcısı (P-008): AX hedefi, Terminal Enter, Sistem Ayarları."""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping

import pytest

from fusion_cli.core.desktop_frame import DesktopFrame
from fusion_cli.core.desktop_settings import DesktopSettings, DesktopTarget
from fusion_cli.core.tools import ToolContext, ToolEffect
from fusion_cli.engines.agent.approval import (
    ApprovalAnswer,
    ApprovalMemory,
    ApprovalMode,
    Decision,
    build_policy,
    resolve_request,
)
from fusion_cli.tools import desktop_policy
from fusion_cli.tools.builtin import build_registry
from fusion_cli.tools.desktop_risk import risky_reason
from fusion_cli.tools.risk_words import is_risky_label

_REGISTRY = build_registry()
_MAIL = DesktopTarget("Mail", "com.apple.mail")
_TERMINAL = DesktopTarget("Terminal", "com.apple.Terminal")
_TRASH = DesktopTarget("Finder", element="MenuItem 'Move to Trash'")
_SEND = DesktopTarget("Mail", element="Button 'Gönder'")
_DELETE = DesktopTarget("Mail", element="Button 'Sil'")


def _answer(app: str, bundle: str, title: str = "", role: str = "AXButton") -> dict[str, object]:
    return {
        "ok": True,
        "app": app,
        "bundle": bundle,
        "pid": 9,
        "element": {"role": role, "title": title} if title else None,
    }


class _Prompter:
    def __init__(self) -> None:
        self.asked: list[object] = []

    async def confirm(self, request):
        self.asked.append(request)
        return ApprovalAnswer.SESSION


def _ref(title: str) -> str:
    token = {"path": [0], "identity": f"AXButton\u001f{title}\u001f\u001f", "fingerprint": "x"}
    return base64.b64encode(json.dumps(token).encode()).decode()


@pytest.mark.parametrize(
    ("tool", "args", "target", "category"),
    [
        ("desktop_click", {}, DesktopTarget("Mail", element="Button 'Gönder'"), ""),
        ("desktop_mouse", {"action": "double_click"}, _TRASH, "finder"),
        ("desktop_click", {}, DesktopTarget("Shop", element="Button 'Place order'"), ""),
        ("desktop_key", {"key": "enter"}, _TERMINAL, "terminal"),
        ("desktop_key", {"key": "ls enter"}, _TERMINAL, "terminal"),
        ("desktop_key", {"key": "cmd+enter"}, _MAIL, ""),
        ("desktop_key", {"key": "return", "control": True}, _MAIL, ""),
        ("desktop_key", {"key": "cmd+delete"}, DesktopTarget("Finder"), "finder"),
        ("desktop_key", {"key": "enter"}, DesktopTarget("Mail", element="Button 'Send'"), ""),
        ("desktop_type", {"text": "rm -rf build\n"}, _TERMINAL, "terminal"),
        ("desktop_click", {}, DesktopTarget("System Settings"), "system"),
        ("desktop_background_action", {"action": "press", "ref": _ref("Sil")}, _MAIL, ""),
    ],
)  # fmt: skip
def test_riskli_eylemler(tool, args, target, category):
    assert risky_reason(tool, args, target, category)


@pytest.mark.parametrize(
    ("tool", "args", "target", "category"),
    [
        ("desktop_click", {}, DesktopTarget("Mail", element="Button 'Arşivle'"), ""),
        ("desktop_mouse", {"action": "hover"}, _SEND, ""),
        ("desktop_mouse", {"action": "right_click"}, _DELETE, ""),
        ("desktop_key", {"key": "enter"}, _MAIL, ""),
        ("desktop_key", {"key": "tab tab"}, _TERMINAL, "terminal"),
        ("desktop_key", {"key": "backspace"}, DesktopTarget("Finder"), "finder"),
        ("desktop_type", {"text": "satır 1\nsatır 2"}, DesktopTarget("TextEdit"), ""),
        ("desktop_type", {"text": "ls"}, _TERMINAL, "terminal"),
        ("desktop_background_action", {"action": "press", "ref": _ref("Yenile")}, _MAIL, ""),
        ("desktop_background_action", {"action": "press", "ref": "bozuk"}, _MAIL, ""),
    ],
)  # fmt: skip
def test_siradan_eylemler_riskli_sayilmaz(tool, args, target, category):
    assert risky_reason(tool, args, target, category) is None


def test_ortak_sozcuk_listesi_chrome_ile_ayni():
    from fusion_cli.tools.chrome import _RISKY_CLICK

    assert _RISKY_CLICK.search("Siparişi tamamla")
    assert is_risky_label("Button 'Siparişi tamamla'")
    assert is_risky_label("MenuItem 'Çöp Sepetini Boşalt'")
    assert not is_risky_label("Button 'Arşivle'")


@pytest.fixture
def probe(monkeypatch):
    holder: dict[str, Mapping[str, object]] = {"answer": _answer("Mail", "com.apple.mail")}

    async def fake(_request: dict[str, object]) -> Mapping[str, object]:
        return holder["answer"]

    monkeypatch.setattr(desktop_policy, "_swift_probe", fake)
    return holder


def _context(tmp_path, **settings) -> ToolContext:
    context = ToolContext(root=tmp_path, desktop_settings=DesktopSettings(**settings))
    context.desktop.frame = DesktopFrame(1000, 600, 0.0, 0.0, 1000.0, 600.0)
    return context


async def _decide(name, args, context, mode, memory):
    prompter = _Prompter()
    request = await resolve_request(_REGISTRY.get(name), args, root=context.root, context=context)
    decision = await build_policy(mode, prompter, memory).decide(request)
    return request, decision, prompter


@pytest.mark.parametrize("mode", [ApprovalMode.AUTO, ApprovalMode.BYPASS])
async def test_riskli_tik_oturum_izni_olsa_da_her_seferinde_sorulur(tmp_path, probe, mode):
    memory = ApprovalMemory()
    context = _context(tmp_path)
    # Önce sıradan bir tık: oturum izni verilir.
    probe["answer"] = _answer("Mail", "com.apple.mail", "Arşivle")
    await _decide("desktop_click", {"x": 1, "y": 1}, context, ApprovalMode.AUTO, memory)

    probe["answer"] = _answer("Mail", "com.apple.mail", "Gönder")
    for _ in range(2):
        request, decision, prompter = await _decide(
            "desktop_click", {"x": 1, "y": 1}, context, mode, memory
        )
        assert decision is Decision.ALLOW and len(prompter.asked) == 1
    assert request.effect is ToolEffect.REMOTE_DESTRUCTIVE
    assert "Gönder" in (request.danger or "")
    assert request.can_remember is False


async def test_terminalde_enter_her_seferinde_sorulur(tmp_path, probe):
    probe["answer"] = _answer("Terminal", "com.apple.Terminal")
    context = _context(tmp_path, app_levels=("Terminal=full",))
    memory = ApprovalMemory()
    request, _decision, prompter = await _decide(
        "desktop_key", {"key": "enter"}, context, ApprovalMode.AUTO, memory
    )
    assert "Enter komutu" in (request.danger or "") and len(prompter.asked) == 1
    # Ok tuşu riskli değildir: oturum onayıyla bir kez sorulur, sonra sorulmaz.
    for _ in range(2):
        request, _decision, prompter = await _decide(
            "desktop_key", {"key": "up"}, context, ApprovalMode.AUTO, memory
        )
    assert request.danger is None and prompter.asked == []


# --- İnceleme (31 Ekim): down/up, sohbet uygulamasında Enter, rol öneki ------------------------

_SLACK = DesktopTarget("Slack", "com.tinyspeck.slackmacgap")
_WHATSAPP = DesktopTarget("‎WhatsApp", "")


@pytest.mark.parametrize("action", ["down", "up"])
def test_basili_tutup_birakmak_da_tiklama_sayilir(action):
    """Ölçüldü (31 Ekim): down+up ile 'Gönder' düğmesi hiç sorulmadan tıklanıyordu."""
    assert risky_reason("desktop_mouse", {"action": action}, _SEND, "")
    assert risky_reason("desktop_mouse", {"action": "hover"}, _SEND, "") is None


@pytest.mark.parametrize("target", [_SLACK, _WHATSAPP])
def test_sohbet_uygulamasinda_enter_ve_satir_sonu_gonderir(target):
    """Ölçüldü (31 Ekim): Slack/WhatsApp'ta düz Enter ve 'merhaba\\n' sorulmadan gönderiyordu."""
    category = desktop_policy.category_for(target.app, target.bundle)
    assert category is not None and category.key == "chat"
    assert risky_reason("desktop_key", {"key": "enter"}, target, "chat")
    assert risky_reason("desktop_type", {"text": "merhaba\n"}, target, "chat")
    assert risky_reason("desktop_type", {"text": "merhaba"}, target, "chat") is None
    # Shift+Enter sohbet uygulamalarında satır ekler, göndermez.
    assert risky_reason("desktop_key", {"key": "shift+enter"}, target, "chat") is None


def test_metin_kutusu_aciklamasi_riskli_sayilmaz_rol_oneki_aranmaz():
    field = DesktopTarget("Notes", element="TextArea 'Write a post'")
    assert risky_reason("desktop_click", {}, field, "") is None
    button = DesktopTarget("Notes", element="Button 'Post'")
    assert risky_reason("desktop_click", {}, button, "")
    # Rol adı ("Button") tek başına riskli değil; ad yoksa eşleşme yapılmaz.
    assert risky_reason("desktop_click", {}, DesktopTarget("Notes", element="Button"), "") is None
