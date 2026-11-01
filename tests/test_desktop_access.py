"""#426: toplu uygulama onayı (Claude computer use `request_access`)."""

from __future__ import annotations

import pytest

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
from fusion_cli.engines.agent.desktop_access import apply_access
from fusion_cli.tools import desktop_policy, desktop_turn
from fusion_cli.tools.builtin import build_registry
from fusion_cli.tools.desktop_access import describe, plan_access, requested_apps

_REGISTRY = build_registry()
_MAIL = {"ok": True, "app": "Mail", "bundle": "", "pid": 41}
_NOTES = {"ok": True, "app": "Notes", "bundle": "", "pid": 42}


class _Prompter:
    def __init__(self, answer: object = ApprovalAnswer.SESSION) -> None:
        self.asked: list[object] = []
        self._answer = answer

    async def confirm(self, request):
        self.asked.append(request)
        return self._answer


@pytest.fixture
def probe(monkeypatch):
    state = {"answer": _MAIL}

    async def fake(_request):
        return state["answer"]

    monkeypatch.setattr(desktop_policy, "_swift_probe", fake)
    return state


@pytest.fixture(autouse=True)
def _cli_surface(monkeypatch):
    from fusion_cli.tools import desktop_visibility

    # Gerçek pencere listesi okunmaz.
    monkeypatch.setattr(desktop_visibility, "onscreen_owners", lambda: ("Slack",))
    desktop_turn.use_app_surface(False)
    yield
    desktop_turn.use_app_surface(False)


def _context(tmp_path, **settings) -> ToolContext:
    return ToolContext(root=tmp_path, desktop_settings=DesktopSettings(**settings))


def test_uygulama_listesi_ayrisir_tekrarlar_atilir():
    assert requested_apps({"apps": ["Mail", "mail", " Notes.app ", ""]}) == ("Mail", "Notes")
    assert requested_apps({"apps": "Mail, Notes"}) == ("Mail", "Notes")
    assert requested_apps({}) == ()


def test_istem_uygulamalari_ve_gizlenecek_sayiyi_gosterir():
    plan = plan_access(
        DesktopSettings(),
        ("Mail", "Notes"),
        owners=lambda: ("Mail", "Safari", "Slack", "Fusion", "Slack"),
    )
    text = describe(plan)
    assert "Mail (tam kontrol)" in text and "Notes (tam kontrol)" in text
    assert "diğer 2 uygulama gizlenecek" in text


def test_masaustu_uygulamasinda_arka_planda_calisirken_gizleme_sayisi_yok():
    desktop_turn.use_app_surface(True)
    plan = plan_access(DesktopSettings(background=True), ("Mail",), owners=lambda: ("Slack",))
    assert plan.hidden_count is None
    assert "gizlenecek" not in describe(plan)


async def test_tek_kart_hepsini_oturum_boyu_izinli_yapar(tmp_path, probe):
    context = _context(tmp_path)
    memory = ApprovalMemory()
    prompter = _Prompter()
    tool = _REGISTRY.get("desktop_request_access")
    request = await resolve_request(
        tool, {"apps": ["Mail", "Notes"]}, root=tmp_path, context=context
    )
    assert "diğer 1 uygulama gizlenecek" in (request.note or "")
    assert request.effect is ToolEffect.REMOTE_INTERACT
    assert request.desktop_target is not None and request.desktop_target.app == "Mail, Notes"
    policy = build_policy(ApprovalMode.BYPASS, prompter, memory)
    assert await policy.decide(request) is Decision.ALLOW
    assert len(prompter.asked) == 1

    # Onaylanan iki uygulamada da ilk tıklama artık sorulmaz.
    for answer in (_MAIL, _NOTES):
        probe["answer"] = answer
        click = await resolve_request(
            _REGISTRY.get("desktop_click"), {"x": 5, "y": 5}, root=tmp_path, context=context
        )
        assert await build_policy(ApprovalMode.AUTO, prompter, memory).decide(click) is (
            Decision.ALLOW
        )
    assert len(prompter.asked) == 1
    # Aynı istek tekrar gelirse sorulmaz.
    assert await policy.decide(request) is Decision.ALLOW and len(prompter.asked) == 1


async def test_engelli_uygulama_karta_girmez_hepsi_engelliyse_sorulmaz(tmp_path):
    context = _context(tmp_path, denied_apps=("Slack",))
    tool = _REGISTRY.get("desktop_request_access")
    base = await resolve_request(tool, {"apps": ["Slack"]}, root=tmp_path)
    only_blocked = apply_access(base, {"apps": ["Slack"]}, context, owners=lambda: ())
    assert only_blocked.pre_denied and only_blocked.desktop_blocked
    mixed = apply_access(base, {"apps": ["Slack", "Mail"]}, context, owners=lambda: ())
    assert mixed.desktop_target is not None and mixed.desktop_target.app == "Mail"
    assert "engelli" in (mixed.note or "") and "Slack" in (mixed.note or "")
    assert mixed.extra_consent_keys == ()


async def test_reddedilirse_izin_kaydedilmez(tmp_path):
    context = _context(tmp_path)
    memory = ApprovalMemory()
    tool = _REGISTRY.get("desktop_request_access")
    base = await resolve_request(tool, {"apps": ["Mail"]}, root=tmp_path)
    request = apply_access(base, {"apps": ["Mail"]}, context, owners=lambda: ())
    decision = await build_policy(ApprovalMode.AUTO, _Prompter(ApprovalAnswer.DENY), memory).decide(
        request
    )
    assert decision is not Decision.ALLOW
    assert not memory.is_remembered(request)


def test_arac_sonucu_izinlileri_ve_engellileri_soyler(tmp_path):
    tool = _REGISTRY.get("desktop_request_access")
    result = tool.run({"apps": ["Mail", "Slack"]}, _context(tmp_path, denied_apps=("Slack",)))
    assert result.ok and "Mail" in result.output and "Slack" in result.output
    assert not tool.run({"apps": []}, _context(tmp_path)).ok


async def test_toplu_onay_paket_kimligiyle_cozulen_hedefte_de_gecerli(tmp_path, probe):
    """Gerçek eylemde hedef AX'ten paket kimliğiyle çözülür; adla verilen izin yine eşleşir."""
    context = _context(tmp_path)
    memory = ApprovalMemory()
    prompter = _Prompter()
    request = await resolve_request(
        _REGISTRY.get("desktop_request_access"), {"apps": ["Mail"]}, root=tmp_path,
        context=context,
    )  # fmt: skip
    assert await build_policy(ApprovalMode.AUTO, prompter, memory).decide(request) is (
        Decision.ALLOW
    )
    probe["answer"] = {"ok": True, "app": "Mail", "bundle": "com.apple.mail", "pid": 41}
    click = await resolve_request(
        _REGISTRY.get("desktop_click"), {"x": 5, "y": 5}, root=tmp_path, context=context
    )
    assert await build_policy(ApprovalMode.AUTO, prompter, memory).decide(click) is Decision.ALLOW
    assert len(prompter.asked) == 1
    assert click.consent_key == "desktop:com.apple.mail"
