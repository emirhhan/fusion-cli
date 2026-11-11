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


async def test_terminalde_klavye_sabit_kademe_yuzunden_kapanir(tmp_path, probe):
    """#424: Terminal "Click only"; eski `app_levels` ile tam kontrole çıkarılamaz."""
    probe["answer"] = _answer("Terminal", "com.apple.Terminal")
    context = _context(tmp_path, app_levels=("Terminal=full",))
    request, decision, prompter = await _decide(
        "desktop_key", {"key": "enter"}, context, ApprovalMode.AUTO, ApprovalMemory()
    )
    assert decision is Decision.BLOCKED and prompter.asked == []
    assert "run_shell" in (request.pre_denied or "")


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


def _label_ref(*, title="", identifier="", description="", role="AXButton"):
    token = {
        "path": [0],
        "identity": "\x1f".join((role, title, identifier, description)),
        "fingerprint": "current",
        "id": 100,
        "pid": 9,
    }
    return base64.b64encode(json.dumps(token).encode()).decode()


@pytest.mark.parametrize(
    "identifier",
    ["Delete", "Gönder", "Öde", "DeleteAccount", "Delete_Account", "SendMessage", "PayNow"],
)
def test_identifier_only_exported_button_label_requires_destructive_gate(identifier):
    args = {"action": "press", "ref": _label_ref(identifier=identifier)}
    assert risky_reason("desktop_background_action", args, _MAIL, "") is not None


@pytest.mark.parametrize(
    "title,description,identifier",
    [
        ("Cancel", "", "DeleteCancel"),
        ("Cancel", "", "Delete"),
        ("", "Cancel", "Delete"),
        ("Cancel", "", "DeleteAccount"),
        ("", "Cancel", "SendMessage"),
        ("Cancel", "", "PayNow"),
        ("", "", "Archive"),
    ],
)
def test_human_label_priority_and_harmless_identifier_remain_ordinary(
    title, description, identifier
):
    args = {
        "action": "press",
        "ref": _label_ref(title=title, description=description, identifier=identifier),
    }
    assert risky_reason("desktop_background_action", args, _MAIL, "") is None


@pytest.mark.parametrize("mode", [ApprovalMode.AUTO, ApprovalMode.BYPASS])
@pytest.mark.parametrize(
    "identifier",
    ["Delete", "Send", "Pay", "DeleteAccount", "Delete_Account", "SendMessage", "PayNow"],
)
async def test_identifier_only_press_is_destructive_and_never_reuses_session_consent(
    tmp_path,
    probe,
    mode,
    identifier,
):
    memory = ApprovalMemory()
    context = _context(tmp_path)
    probe["answer"] = _answer("Mail", "com.apple.mail", "Arşivle")
    await _decide("desktop_click", {"x": 1, "y": 1}, context, ApprovalMode.AUTO, memory)
    args = {"window_id": 100, "pid": 9, "action": "press", "ref": _label_ref(identifier=identifier)}
    for _ in range(2):
        request, decision, prompter = await _decide(
            "desktop_background_action", args, context, mode, memory
        )
        assert request.effect is ToolEffect.REMOTE_DESTRUCTIVE
        assert not request.can_remember
        assert decision is Decision.ALLOW and len(prompter.asked) == 1


def test_identifier_fallback_applies_only_to_exported_button_role():
    args = {"action": "press", "ref": _label_ref(identifier="Delete", role="AXTextField")}
    assert risky_reason("desktop_background_action", args, _MAIL, "") is None


def _calculator_ref(**changes):
    token = {
        "path": [0, 0, 1, 0, 2],
        "identity": "\x1f".join(("AXButton", "", "AllClear", "Tümünü Sil")),
        "fingerprint": "f" * 64,
        "id": 100,
        "pid": 9,
    }
    token.update(changes)
    return base64.b64encode(json.dumps(token).encode()).decode()


@pytest.mark.parametrize(
    ("native_proof", "window", "identifier", "verdict"),
    [
        (True, 100, "Four", Decision.ALLOW),
        (False, 100, "Four", Decision.BLOCKED),
        (True, 101, "Four", Decision.BLOCKED),
        (True, 100, "ClearHistory", Decision.BLOCKED),
        (True, 100, "Unrecognized", Decision.BLOCKED),
    ],
)
async def test_promptless_auto_calculator_press_requires_typed_same_window_proof(
    tmp_path, probe, native_proof, window, identifier, verdict
):
    context = _context(tmp_path)
    context.desktop.focused_window = (9, 0, 0, 100, 100)
    context.desktop.focused_window_id = 100
    probe["answer"] = {
        **_answer("Hesap Makinesi", "com.apple.calculator"),
        "system_calculator": native_proof,
    }
    args = {
        "action": "press",
        "pid": 9,
        "window_id": window,
        "ref": _calculator_ref(id=window, identity=f"AXButton\x1f\x1f{identifier}\x1f"),
    }
    request = await resolve_request(
        _REGISTRY.get("desktop_background_action"), args, context=context
    )
    prompter = _Prompter()
    policy = build_policy(ApprovalMode.AUTO, prompter, interaction_prompts=False)
    assert await policy.decide(request) is verdict
    assert prompter.asked == []


async def test_promptless_auto_blocks_grounded_click_when_native_hit_is_sil(
    tmp_path, monkeypatch, probe
):
    from unittest.mock import AsyncMock

    from fusion_cli.core.events import ToolOutcome
    from fusion_cli.engines.agent import loop
    from fusion_cli.engines.agent.execution_policy import ExecutionPolicy
    from tests.fakes import tool_call
    from tests.test_desktop_visual_grounding import _actor, _capture, _helper_message, _setup

    deps, state, _, _ = _setup(tmp_path)
    desktop = deps.tool_context.desktop
    desktop.focused_window = (9, 0, 0, 100, 100)
    desktop.focused_window_id = 100
    desktop.focused_window_title = "Hesap Makinesi"
    probe["answer"] = {
        **_answer("Hesap Makinesi", "com.apple.calculator", "Sil"),
        "system_calculator": True,
        "window": {"id": 100, "title": "Hesap Makinesi", "bounds": [0, 0, 100, 100]},
    }
    capture, _ = _capture(deps)
    await _actor(monkeypatch, deps, state, [_helper_message(deps, state, capture, "4 is at 10,10")])
    prompter = _Prompter()
    deps.policy = build_policy(ApprovalMode.AUTO, prompter, interaction_prompts=False)
    dispatch = AsyncMock(side_effect=AssertionError("Sil should not dispatch"))
    monkeypatch.setattr(loop, "_execute_registered_tool", dispatch)
    args = {"x": 10, "y": 10}
    assert (
        state.desktop_grounding.preflight(
            "desktop_click", args, deps.tool_context, deps.conversation_id, deps.attempt_id
        )
        is None
    )
    _, outcome = await loop._execute(
        tool_call("desktop_click", **args),
        args,
        deps,
        _REGISTRY,
        execution=ExecutionPolicy(is_web=False),
        state=state,
    )
    assert outcome is ToolOutcome.BLOCKED
    assert desktop.target_pid == 9
    assert not prompter.asked
    dispatch.assert_not_awaited()


@pytest.fixture
def desktop_click_review(tmp_path, probe):
    from types import SimpleNamespace
    from unittest.mock import Mock

    from fusion_cli.core.auto_review import AutoClassifierMode
    from fusion_cli.core.types import Message
    from tests.test_desktop_visual_grounding import _capture

    context = _context(tmp_path)
    context.desktop.focused_window = (9, 0, 0, 1000, 600)
    context.desktop.focused_window_id = 100
    context.desktop.focused_window_title = "Mail"
    probe["answer"] = {
        **_answer("Mail", "com.apple.mail", "Arşivle"),
        "window": {"id": 100, "title": "Mail", "bounds": [0, 0, 1000, 600]},
    }
    memory = ApprovalMemory()
    deps = SimpleNamespace(
        config=SimpleNamespace(
            runtime=SimpleNamespace(
                auto_classifier=AutoClassifierMode.ON, interaction_prompts=False
            )
        ),
        auto_review=memory.auto_review,
        approval_mode=lambda: ApprovalMode.AUTO,
        tool_context=context,
        live_history=lambda: [Message("user", "Mail'de Arşivle düğmesine tıkla.")],
        publisher=Mock(),
    )
    _capture(deps)
    prompter = _Prompter()
    policy = build_policy(ApprovalMode.AUTO, prompter, memory, interaction_prompts=False)
    return deps, policy, prompter


async def _desktop_click_request(deps):
    return await resolve_request(
        _REGISTRY.get("desktop_click"), {"x": 5, "y": 5}, context=deps.tool_context
    )


@pytest.mark.parametrize(
    ("label", "review", "changed", "expected"),
    [
        ("Arşivle", "safe", None, Decision.ALLOW),
        ("Arşivle", "risky", None, Decision.BLOCKED),
        ("Arşivle", "unavailable", None, Decision.BLOCKED),
        ("Arşivle", "safe", "Sil", Decision.BLOCKED),
        ("", "safe", None, Decision.BLOCKED),
        ("Sil", "safe", None, Decision.BLOCKED),
    ],
)
async def test_promptless_auto_reviewed_click_checks_native_target(
    desktop_click_review, monkeypatch, probe, label, review, changed, expected
):
    from unittest.mock import AsyncMock

    from fusion_cli.core.auto_review import ReviewOutcome, ReviewSource, ReviewVerdict
    from fusion_cli.engines.agent import risk_classifier

    deps, policy, prompter = desktop_click_review
    probe["answer"] = {**probe["answer"], **_answer("Mail", "com.apple.mail", label)}
    request = await _desktop_click_request(deps)
    outcome = ReviewOutcome(
        "desktop_click",
        ReviewVerdict.RISKY if review == "risky" else ReviewVerdict.SAFE,
        "fixture",
        ReviewSource.RULE if review == "unavailable" else ReviewSource.MODEL,
        "fixture",
    )
    classify = AsyncMock(return_value=outcome)
    monkeypatch.setattr(risk_classifier, "classify", classify)
    reviewed = await risk_classifier.review_auto_request(request, deps)
    if changed is not None:
        probe["answer"] = {**probe["answer"], "element": {"role": "AXButton", "title": changed}}
    assert await policy.decide(reviewed) is expected
    assert not prompter.asked


async def test_promptless_click_reviews_same_label_in_new_capture_again(
    desktop_click_review, monkeypatch
):
    from unittest.mock import AsyncMock

    from fusion_cli.core.auto_review import ReviewOutcome, ReviewSource, ReviewVerdict
    from fusion_cli.engines.agent import risk_classifier
    from tests.test_desktop_visual_grounding import _capture

    deps, policy, prompter = desktop_click_review
    classify = AsyncMock(
        side_effect=[
            ReviewOutcome(
                "desktop_click", ReviewVerdict.SAFE, "first", ReviewSource.MODEL, "fixture"
            ),
            ReviewOutcome(
                "desktop_click", ReviewVerdict.RISKY, "second", ReviewSource.MODEL, "fixture"
            ),
        ]
    )
    monkeypatch.setattr(risk_classifier, "classify", classify)
    first = await risk_classifier.review_auto_request(await _desktop_click_request(deps), deps)
    assert await policy.decide(first) is Decision.ALLOW
    _capture(deps, name="second.png")
    second = await risk_classifier.review_auto_request(await _desktop_click_request(deps), deps)
    assert classify.await_count == 2
    assert await policy.decide(second) is Decision.BLOCKED
    assert not prompter.asked


async def test_promptless_click_rejects_recapture_during_review(desktop_click_review, monkeypatch):
    from fusion_cli.core.auto_review import ReviewOutcome, ReviewSource, ReviewVerdict
    from fusion_cli.engines.agent import risk_classifier
    from tests.test_desktop_visual_grounding import _capture

    deps, policy, prompter = desktop_click_review

    async def classify(*_args, **_kwargs):
        _capture(deps, name="during-review.png")
        return ReviewOutcome(
            "desktop_click", ReviewVerdict.SAFE, "old", ReviewSource.MODEL, "fixture"
        )

    monkeypatch.setattr(risk_classifier, "classify", classify)
    reviewed = await risk_classifier.review_auto_request(await _desktop_click_request(deps), deps)
    assert await policy.decide(reviewed) is Decision.BLOCKED
    assert not prompter.asked


async def _calculator_session(tmp_path, probe, *, native=None):
    answer = _answer("Hesap Makinesi", "com.apple.calculator", "7")
    answer["system_calculator"] = True
    if native:
        answer.update(native)
    probe["answer"] = answer
    context, memory = _context(tmp_path), ApprovalMemory()
    await _decide("desktop_click", {"x": 1, "y": 1}, context, ApprovalMode.AUTO, memory)
    return context, memory


@pytest.mark.parametrize("mode", [ApprovalMode.AUTO, ApprovalMode.BYPASS])
async def test_verified_system_calculator_allclear_reuses_app_consent(tmp_path, probe, mode):
    context, memory = await _calculator_session(tmp_path, probe)
    args = {"window_id": 100, "pid": 9, "action": "press", "ref": _calculator_ref()}
    for _ in range(2):
        request, decision, prompter = await _decide(
            "desktop_background_action", args, context, mode, memory
        )
        assert request.effect is ToolEffect.REMOTE_INTERACT
        assert request.can_remember is True
        assert decision is Decision.ALLOW and prompter.asked == []


@pytest.mark.parametrize("mode", [ApprovalMode.AUTO, ApprovalMode.BYPASS])
@pytest.mark.parametrize(
    "native,args_changes,ref_changes",
    [
        ({"system_calculator": False}, {"system_calculator": True}, {}),
        ({"system_calculator": None}, {}, {}),
        ({"system_calculator": "true"}, {}, {}),
        ({"bundle": "evil.calculator"}, {}, {}),
        ({"bundle": "com.apple.mail"}, {}, {}),
        ({"pid": 88}, {}, {}),
        ({}, {}, {"pid": 88}),
        ({}, {}, {"id": 101}),
        ({}, {}, {"identity": "AXButton\x1f\x1fClearHistory\x1fTümünü Sil"}),
        ({}, {}, {"identity": "AXButton\x1f\x1fClearHistory\x1f"}),
        ({}, {}, {"identity": "AXButton\x1f\x1fDelete\x1fSil"}),
        ({}, {}, {"identity": "AXMenuItem\x1f\x1fAllClear\x1fTümünü Sil"}),
        ({}, {}, {"identity": "AXUnknown\x1f\x1fAllClear\x1fTümünü Sil"}),
        ({}, {}, {"identity": "AXCustom\x1f\x1fUnrecognized\x1f"}),
        ({}, {}, {"identity": "AXButton\x1f\x1fUnrecognized\x1f"}),
        ({}, {}, {"identity": "AXButton\x1f\x1f\x1f"}),
        ({}, {}, {"fingerprint": "not-a-native-fingerprint"}),
        ({}, {}, {"path": [True]}),
    ],
)
async def test_calculator_clear_exception_requires_native_proof_and_bound_exact_control(
    tmp_path, probe, mode, native, args_changes, ref_changes
):
    context, memory = await _calculator_session(tmp_path, probe, native=native)
    args = {"window_id": 100, "pid": 9, "action": "press", "ref": _calculator_ref(**ref_changes)}
    args.update(args_changes)
    request, decision, prompter = await _decide(
        "desktop_background_action", args, context, mode, memory
    )
    assert request.effect is ToolEffect.REMOTE_DESTRUCTIVE
    assert request.can_remember is False
    assert decision is Decision.ALLOW and len(prompter.asked) == 1


@pytest.mark.parametrize("mode", [ApprovalMode.AUTO, ApprovalMode.BYPASS])
@pytest.mark.parametrize("description", ["", "7"])
async def test_known_calculator_math_buttons_remain_ordinary(tmp_path, probe, mode, description):
    context, memory = await _calculator_session(tmp_path, probe)
    ref = _calculator_ref(identity=f"AXButton\x1f\x1fSeven\x1f{description}")
    args = {"window_id": 100, "pid": 9, "action": "press", "ref": ref}
    request, decision, prompter = await _decide(
        "desktop_background_action", args, context, mode, memory
    )
    assert request.effect is ToolEffect.REMOTE_INTERACT
    assert decision is Decision.ALLOW and prompter.asked == []


@pytest.mark.parametrize("mode", [ApprovalMode.AUTO, ApprovalMode.BYPASS])
async def test_remembered_calculator_consent_does_not_remember_native_attestation(
    tmp_path, probe, mode
):
    context, memory = await _calculator_session(tmp_path, probe)
    answer = dict(probe["answer"])
    answer.pop("system_calculator")
    probe["answer"] = answer
    args = {
        "window_id": 100,
        "pid": 9,
        "action": "press",
        "ref": _calculator_ref(),
        "system_calculator": True,
    }
    request, decision, prompter = await _decide(
        "desktop_background_action", args, context, mode, memory
    )
    assert request.effect is ToolEffect.REMOTE_DESTRUCTIVE
    assert not request.can_remember
    assert decision is Decision.ALLOW and len(prompter.asked) == 1


@pytest.mark.parametrize("mode", [ApprovalMode.AUTO, ApprovalMode.BYPASS])
@pytest.mark.parametrize("ref", ["bozuk", "", _calculator_ref(identity="")])
async def test_verified_calculator_unknown_reference_still_requires_per_action_consent(
    tmp_path, probe, mode, ref
):
    context, memory = await _calculator_session(tmp_path, probe)
    args = {"window_id": 100, "pid": 9, "action": "press", "ref": ref}
    request, decision, prompter = await _decide(
        "desktop_background_action", args, context, mode, memory
    )
    assert request.effect is ToolEffect.REMOTE_DESTRUCTIVE
    assert request.can_remember is False
    assert decision is Decision.ALLOW and len(prompter.asked) == 1
