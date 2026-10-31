"""Uygulama başına oturum onayı ve kademe tablosu (P-007).

Yardımcı (Swift) çağrılmaz: hedef sorgusu `desktop_policy._swift_probe` sahte yanıtla değişir.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from typing import ClassVar

import pytest

from fusion_cli.appserver.bridges import PendingQuestions, ProtocolPrompter
from fusion_cli.cli.prompter import parse_console_answer
from fusion_cli.core.desktop_frame import DesktopFrame
from fusion_cli.core.desktop_settings import DesktopLevel, DesktopSettings
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
from fusion_cli.tools.desktop_policy import app_level, required_level

_REGISTRY = build_registry()
_MAIL = {"ok": True, "app": "Mail", "bundle": "com.apple.mail", "pid": 41}
_NOTES = {"ok": True, "app": "Notes", "bundle": "com.apple.Notes", "pid": 42}
_TERMINAL = {"ok": True, "app": "Terminal", "bundle": "com.apple.Terminal", "pid": 43}
_SAFARI = {"ok": True, "app": "Safari", "bundle": "com.apple.Safari", "pid": 44}
_FUSION = {"ok": True, "app": "Fusion", "bundle": "com.fusion.desktop", "pid": 45}


class _Prompter:
    """Her soruyu kaydeder ve verilen cevabı döndürür."""

    def __init__(self, answer: object = ApprovalAnswer.SESSION) -> None:
        self.asked: list[object] = []
        self._answer = answer

    async def confirm(self, request):
        self.asked.append(request)
        return self._answer


@pytest.fixture
def probe(monkeypatch):
    """`_swift_probe` yerine sabit yanıt; testte `probe.answer = …` ile değişir."""

    class _Probe:
        answer: ClassVar[Mapping[str, object]] = _MAIL
        requests: ClassVar[list[dict[str, object]]] = []

    async def fake(request: dict[str, object]) -> Mapping[str, object]:
        _Probe.requests.append(request)
        return _Probe.answer

    _Probe.requests = []
    monkeypatch.setattr(desktop_policy, "_swift_probe", fake)
    return _Probe


def _context(tmp_path, **settings) -> ToolContext:
    context = ToolContext(root=tmp_path, desktop_settings=DesktopSettings(**settings))
    context.desktop.frame = DesktopFrame(1000, 600, 0.0, 0.0, 1000.0, 600.0)
    return context


async def _decide(name, args, context, mode=ApprovalMode.AUTO, prompter=None, memory=None):
    prompter = prompter or _Prompter()
    memory = memory or ApprovalMemory()
    tool = _REGISTRY.get(name)
    request = await resolve_request(tool, args, root=context.root, context=context)
    decision = await build_policy(mode, prompter, memory).decide(request)
    return request, decision, prompter


# --------------------------------------------------------------------------- kademe tablosu


@pytest.mark.parametrize(
    ("app", "bundle", "level"),
    [
        ("Safari", "com.apple.Safari", DesktopLevel.OBSERVE),
        ("Google Chrome", "com.google.Chrome", DesktopLevel.OBSERVE),
        ("Terminal", "com.apple.Terminal", DesktopLevel.CLICK),
        ("iTerm2", "com.googlecode.iterm2", DesktopLevel.CLICK),
        ("Code", "com.microsoft.VSCode", DesktopLevel.CLICK),
        ("Mail", "com.apple.mail", DesktopLevel.FULL),
        ("Finder", "com.apple.finder", DesktopLevel.FULL),
    ],
)
def test_kategori_kademeleri(app, bundle, level):
    assert app_level(DesktopSettings(), app, bundle)[0] is level


@pytest.mark.parametrize(
    ("app", "bundle"),
    [("Binance", "com.binance.BinanceDesktop"), ("1Password", "com.1password.1password"),
     ("Fusion", "com.fusion.desktop"), ("MetaTrader 5", "")],
)  # fmt: skip
def test_engelli_kategoriler(app, bundle):
    level, _category, reason = app_level(DesktopSettings(), app, bundle)
    assert level is None and reason


def test_uygulama_kademesi_kategoriyi_ezer_tavan_ve_ret_ezilmez():
    settings = DesktopSettings(app_levels=("Terminal=full", "Binance=observe", "Fusion=full"))
    assert app_level(settings, "Terminal", "com.apple.Terminal")[0] is DesktopLevel.FULL
    assert app_level(settings, "Binance", "")[0] is DesktopLevel.OBSERVE
    # Fusion kendi penceresini hiçbir ayarla yönetemez.
    assert app_level(settings, "Fusion", "com.fusion.desktop")[0] is None
    capped = DesktopSettings(control_level=DesktopLevel.CLICK, app_levels=("Terminal=full",))
    assert app_level(capped, "Terminal", "com.apple.Terminal")[0] is DesktopLevel.CLICK
    denied = DesktopSettings(denied_apps=("com.apple.mail",), app_levels=("Mail=full",))
    assert app_level(denied, "Mail", "com.apple.mail")[0] is None


def test_kategori_kapali_ise_her_uygulama_tavani_alir():
    settings = DesktopSettings(category_defaults=False)
    assert app_level(settings, "Safari", "com.apple.Safari")[0] is DesktopLevel.FULL
    assert app_level(settings, "Binance", "")[0] is DesktopLevel.FULL


def test_eylemin_istedigi_kademe():
    assert required_level("desktop_click", {}) is DesktopLevel.CLICK
    assert required_level("desktop_mouse", {"action": "drag"}) is DesktopLevel.FULL
    assert required_level("desktop_type", {}) is DesktopLevel.FULL
    assert required_level("desktop_background_action", {"action": "press"}) is DesktopLevel.CLICK
    assert required_level("desktop_screenshot", {}) is None


# --------------------------------------------------------------------------- hedef + onay


async def test_tiklama_noktasi_ekran_noktasina_cevrilip_sorulur(tmp_path, probe):
    context = _context(tmp_path)
    context.desktop.frame = DesktopFrame(500, 300, 0.0, 0.0, 1000.0, 600.0)

    request, _decision, _prompter = await _decide("desktop_click", {"x": 100, "y": 50}, context)

    assert probe.requests[-1] == {"point": [200.0, 100.0]}
    assert request.desktop_target is not None and request.desktop_target.app == "Mail"


async def test_ilk_kullanim_sorulur_oturum_izni_uygulamaya_baglidir(tmp_path, probe):
    context = _context(tmp_path)
    memory = ApprovalMemory()
    prompter = _Prompter(ApprovalAnswer.SESSION)

    request, first, _ = await _decide(
        "desktop_click", {"x": 5, "y": 5}, context, prompter=prompter, memory=memory
    )
    assert first is Decision.ALLOW and len(prompter.asked) == 1
    assert request.effect is ToolEffect.REMOTE_INTERACT and "Mail" in (request.note or "")
    assert request.consent_key == "desktop:com.apple.mail"
    assert "yalnız Mail" in (request.remembered_scope_description or "")

    # Aynı uygulamada başka araç (yazma) aynı izinle geçer: izin araca değil uygulamaya bağlı.
    _, second, _ = await _decide(
        "desktop_type", {"text": "merhaba"}, context, prompter=prompter, memory=memory
    )
    assert second is Decision.ALLOW and len(prompter.asked) == 1

    probe.answer = _NOTES
    _, third, _ = await _decide(
        "desktop_click", {"x": 5, "y": 5}, context, prompter=prompter, memory=memory
    )
    assert third is Decision.ALLOW and len(prompter.asked) == 2


async def test_yalniz_bu_kez_izni_hatirlanmaz(tmp_path, probe):
    context = _context(tmp_path)
    memory = ApprovalMemory()
    prompter = _Prompter(ApprovalAnswer.ONCE)
    for _ in range(2):
        await _decide("desktop_click", {"x": 5, "y": 5}, context, prompter=prompter, memory=memory)
    assert len(prompter.asked) == 2


@pytest.mark.parametrize("mode", [ApprovalMode.ACCEPT_EDITS, ApprovalMode.SECURITY])
async def test_duzenleme_ve_manuel_kipte_de_ilk_kullanim_sorulur(tmp_path, probe, mode):
    _, decision, prompter = await _decide(
        "desktop_click", {"x": 5, "y": 5}, _context(tmp_path), mode
    )
    assert decision is Decision.ALLOW and len(prompter.asked) == 1


async def test_bypass_oturum_onayi_sormaz_plan_yapmaz(tmp_path, probe):
    context = _context(tmp_path)
    _, bypass, prompter = await _decide(
        "desktop_click", {"x": 5, "y": 5}, context, ApprovalMode.BYPASS
    )
    assert bypass is Decision.ALLOW and prompter.asked == []
    _, plan, prompter = await _decide("desktop_click", {"x": 5, "y": 5}, context, ApprovalMode.PLAN)
    assert plan is Decision.BLOCKED and prompter.asked == []


async def test_onay_kapaliyken_otomatik_kip_sormaz(tmp_path, probe):
    _, decision, prompter = await _decide(
        "desktop_click", {"x": 5, "y": 5}, _context(tmp_path, app_consent=False)
    )
    assert decision is Decision.ALLOW and prompter.asked == []


@pytest.mark.parametrize("mode", list(ApprovalMode))
async def test_engelli_uygulama_her_kipte_sorulmadan_kapanir(tmp_path, probe, mode):
    probe.answer = _FUSION
    request, decision, prompter = await _decide(
        "desktop_click", {"x": 5, "y": 5}, _context(tmp_path), mode
    )
    assert decision is Decision.BLOCKED and prompter.asked == []
    assert "Fusion kendi penceresini" in (request.pre_denied or "")


async def test_kademe_yetmezse_yol_gosterir(tmp_path, probe):
    probe.answer = _TERMINAL
    request, decision, _ = await _decide("desktop_type", {"text": "ls"}, _context(tmp_path))
    assert decision is Decision.BLOCKED and "run_shell" in (request.pre_denied or "")
    probe.answer = _SAFARI
    request, decision, _ = await _decide("desktop_click", {"x": 5, "y": 5}, _context(tmp_path))
    assert decision is Decision.BLOCKED and "chrome_*" in (request.pre_denied or "")
    # Terminal'e tıklamak (kademe: tıkla) serbesttir.
    probe.answer = _TERMINAL
    _, decision, _ = await _decide("desktop_click", {"x": 5, "y": 5}, _context(tmp_path))
    assert decision is Decision.ALLOW


async def test_reddedilen_uygulama_arka_plan_goruntusunde_de_kapanir(tmp_path, probe):
    probe.answer = _MAIL
    context = _context(tmp_path, denied_apps=("Mail",))
    request, decision, _ = await _decide(
        "desktop_background_screenshot", {"window_id": 7, "pid": 41}, context, ApprovalMode.BYPASS
    )
    assert probe.requests[-1] == {"pid": 41}
    assert decision is Decision.BLOCKED and "desktop.denied_apps" in (request.pre_denied or "")
    probe.answer = _NOTES
    _, decision, prompter = await _decide(
        "desktop_background_screenshot", {"window_id": 7, "pid": 42}, context, ApprovalMode.SECURITY
    )
    assert decision is Decision.ALLOW and prompter.asked == []


async def test_desktop_open_ada_gore_engellenir(tmp_path, probe):
    _request, decision, _ = await _decide(
        "desktop_open", {"app": "Binance"}, _context(tmp_path), ApprovalMode.BYPASS
    )
    assert decision is Decision.BLOCKED and probe.requests == []


async def test_hedef_okunamazsa_eski_temkinli_onay(tmp_path, probe):
    probe.answer = {"ok": False, "metin": "izin yok"}
    memory = ApprovalMemory()
    prompter = _Prompter(ApprovalAnswer.SESSION)
    for _ in range(2):
        request, _decision, _ = await _decide(
            "desktop_click", {"x": 5, "y": 5}, _context(tmp_path), prompter=prompter, memory=memory
        )
    assert request.effect is ToolEffect.REMOTE_WRITE and request.desktop_target is None
    assert len(prompter.asked) == 2


# --------------------------------------------------------------------------- yüzeyler


async def test_kart_uygulamayi_gosterir_her_zaman_reddet_listeye_yazar(tmp_path, probe):
    request = await resolve_request(
        _REGISTRY.get("desktop_click"), {"x": 5, "y": 5}, root=tmp_path, context=_context(tmp_path)
    )
    lines: list[str] = []
    denied: list[str] = []
    pending = PendingQuestions()

    async def on_denied(app: str) -> None:
        denied.append(app)

    prompter = ProtocolPrompter(lines.append, pending, on_app_denied=on_denied)
    task = asyncio.ensure_future(prompter.confirm(request))
    await asyncio.sleep(0)
    question = json.loads(lines[0])
    payload = question["veri"]
    assert payload["masaustu"]["uygulama"] == "Mail"
    assert payload["masaustu"]["kademe"] == "full"
    values = {option["deger"]: option["etiket"] for option in payload["secenekler"]}
    assert values["session"] == "Bu oturumda Mail için izin ver"
    assert "never" in values

    pending.resolve(question["id"], {"secim": "never"})
    assert await task is ApprovalAnswer.DENY
    assert denied == ["Mail"]


async def test_terminalde_o_oturum_izni_verir(tmp_path, probe):
    request = await resolve_request(
        _REGISTRY.get("desktop_click"), {"x": 5, "y": 5}, root=tmp_path, context=_context(tmp_path)
    )
    assert parse_console_answer("o", request) is ApprovalAnswer.SESSION
    assert parse_console_answer("e", request) is True
