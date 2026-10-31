"""Masaüstü politikasının uygulama sınırı: hedef çözümü ve okunamayan hedef (P-007 inceleme).

Yardımcı (Swift) çağrılmaz: hedef sorgusu `desktop_policy._swift_probe` sahte yanıtla değişir.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import ClassVar

import pytest

from fusion_cli.core.desktop_frame import DesktopFrame
from fusion_cli.core.desktop_settings import DesktopSettings
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

_REGISTRY = build_registry()
_MAIL = {"ok": True, "app": "Mail", "bundle": "com.apple.mail", "pid": 41}
_UNKNOWN = {"ok": False, "metin": "Noktadaki öğe okunamadı."}


class _Prompter:
    def __init__(self, answer: object = ApprovalAnswer.SESSION) -> None:
        self.asked: list[object] = []
        self._answer = answer

    async def confirm(self, request):
        self.asked.append(request)
        return self._answer


@pytest.fixture
def probe(monkeypatch):
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
    tool = _REGISTRY.get(name)
    request = await resolve_request(tool, args, root=context.root, context=context)
    decision = await build_policy(mode, prompter, memory or ApprovalMemory()).decide(request)
    return request, decision, prompter


# --------------------------------------------------------------------------- pid türü


@pytest.mark.parametrize("pid", [1234, "1234", 1234.0, " 1234 "])
async def test_arka_plan_pid_araclarla_ayni_kuralla_cozulur(tmp_path, probe, pid):
    """Ölçüldü (31 Ekim): "1234" ve 1234.0 için sorgu `{}` (ÖNDEKİ uygulama) idi."""
    await _decide(
        "desktop_background_action",
        {"window_id": 5, "pid": pid, "ref": "r", "action": "press"},
        _context(tmp_path),
    )
    assert probe.requests[-1] == {"pid": 1234}


@pytest.mark.parametrize("pid", [None, "abc", 0, -3, 1.5, True])
async def test_gecersiz_pid_one_uygulamaya_dusmez(tmp_path, probe, pid):
    """Geçersiz pid'de araç zaten çalışmaz; politika öndeki uygulamayı yoklamamalı."""
    request, decision, prompter = await _decide(
        "desktop_background_action",
        {"window_id": 5, "pid": pid, "ref": "r", "action": "press"},
        _context(tmp_path),
        ApprovalMode.BYPASS,
    )
    assert probe.requests == []
    assert decision is Decision.BLOCKED and prompter.asked == []
    assert request.pre_denied


# --------------------------------------------------------------------------- okunamayan hedef


@pytest.mark.parametrize(
    ("name", "args"),
    [
        ("desktop_click", {"x": 5, "y": 5}),
        ("desktop_type", {"text": "merhaba"}),
        ("desktop_key", {"key": "cmd+a"}),
        ("desktop_mouse", {"action": "drag", "x": 1, "y": 1, "to_x": 9, "to_y": 9}),
    ],
)
async def test_hedef_okunamazsa_izinleri_atla_kipinde_de_sorulur(tmp_path, probe, name, args):
    """Ölçüldü (31 Ekim): bypass'ta okunamayan hedefe tık/yazı hiç sorulmadan çalışıyordu."""
    probe.answer = _UNKNOWN
    request, decision, prompter = await _decide(
        name, args, _context(tmp_path, denied_apps=("1Password",)), ApprovalMode.BYPASS
    )
    assert len(prompter.asked) == 1 and decision is Decision.ALLOW
    assert request.effect is ToolEffect.REMOTE_DESTRUCTIVE and not request.unattended_safe
    assert "okunamadı" in (request.danger or "")


async def test_hedef_okunamazsa_oturum_izni_hatirlanmaz(tmp_path, probe):
    probe.answer = _UNKNOWN
    memory = ApprovalMemory()
    prompter = _Prompter(ApprovalAnswer.SESSION)
    for _ in range(2):
        request, _decision, _ = await _decide(
            "desktop_click", {"x": 5, "y": 5}, _context(tmp_path), prompter=prompter, memory=memory
        )
    assert request.desktop_target is None and len(prompter.asked) == 2


async def test_arka_plan_hedefi_okunamazsa_kapanir(tmp_path, probe):
    """Arka plan araçları yardımcıyla çalışır: hedef doğrulanamazsa ret listesi denetlenemez."""
    probe.answer = {"ok": False, "metin": "Süreç bulunamadı."}
    for name in ("desktop_background_screenshot", "desktop_background_inspect"):
        request, decision, prompter = await _decide(
            name, {"window_id": 5, "pid": 77}, _context(tmp_path), ApprovalMode.BYPASS
        )
        assert decision is Decision.BLOCKED and prompter.asked == []
        assert "doğrulanamadı" in (request.pre_denied or "")
