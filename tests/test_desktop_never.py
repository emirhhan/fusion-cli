"""Terminal ve TUI onayında "Her zaman reddet" (P-007 inceleme: yarım yüzey).

Gerçek yapılandırma dosyasına yazılmaz: kalıcı yazım sahte geri çağrıyla verilir; dosyaya
yazan yol `tmp_path` altındaki yapılandırmayla ayrıca denenir.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

from fusion_cli.cli.desktop_never import AppDenials, config_persist, offers_never
from fusion_cli.cli.prompter import ConsolePrompter
from fusion_cli.cli.repl.tui import FusionTui
from fusion_cli.cli.repl.tui_loop import TuiPrompter, _preview
from fusion_cli.config.desktop_denied import with_denied_app
from fusion_cli.core.desktop_settings import DesktopLevel, DesktopSettings, DesktopTarget
from fusion_cli.core.errors import ConfigError
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.approval import ApprovalAnswer, ApprovalReply, ApprovalRequest

from .fakes import make_config


class _Tool:
    name = "desktop_click"


_MAIL = DesktopTarget("Mail", "com.apple.mail", 41, DesktopLevel.FULL)


def _request(**changes) -> ApprovalRequest:
    request = ApprovalRequest(
        tool=_Tool(),
        args={"x": 1, "y": 1},
        danger=None,
        risk="ilk kullanım",
        unattended_safe=False,
        read_only=False,
        desktop_target=_MAIL,
        consent_key="desktop:com.apple.mail",
    )
    return replace(request, **changes)


def _recording() -> tuple[AppDenials, list[str]]:
    written: list[str] = []

    def persist(app: str) -> str:
        written.append(app)
        return f"{app} eklendi"

    return AppDenials(persist), written


def test_secenek_yalniz_uygulama_onayinda_sunulur():
    assert offers_never(_request())
    assert not offers_never(_request(consent_key=None))
    assert not offers_never(_request(desktop_target=None))


# --------------------------------------------------------------------------- TUI


def _tui() -> FusionTui:
    return FusionTui(
        on_submit=lambda _t: None,
        on_interrupt=lambda: None,
        on_exit=lambda: None,
        on_cycle_mode=lambda: None,
    )


def test_tui_onizlemesi_hedef_uygulamayi_ve_kademeyi_gosterir():
    assert "Uygulama: Mail · kademe: tam kontrol" in _preview(_request())


async def test_tui_uygulama_onayi_yalniz_oturum_ve_reddet_sunar():
    """#426: Claude'da uygulama onayı "Allow for this session / Deny"; tek çağrılık "Evet" ve
    "Her zaman reddet" yok."""
    tui = _tui()
    denials, written = _recording()
    prompter = TuiPrompter(tui, None, denials=denials)
    shown: list[list[str]] = []
    original = tui.await_choice

    async def capture(title, choices):
        shown.append([choice.value for choice in choices])
        return await original(title, choices)

    tui.await_choice = capture  # type: ignore[method-assign]
    task = asyncio.ensure_future(prompter.confirm(_request()))
    await asyncio.sleep(0)
    assert shown[0] == ["session", "deny"]
    tui._resolve("session")
    assert await task is ApprovalAnswer.SESSION and written == []


# --------------------------------------------------------------------------- düz terminal


@pytest.mark.parametrize(
    ("line", "expected"), [("", ApprovalAnswer.SESSION), ("e", ApprovalAnswer.SESSION),
                           ("o", ApprovalAnswer.SESSION), ("h", False), ("r", False)],
)  # fmt: skip
async def test_terminalde_uygulama_onayi_oturum_ya_da_red(tmp_path, monkeypatch, line, expected):
    """#426, #452: CLI'de ret listesi yönetilmez; `r` artık sıradan "hayır"dır."""
    from rich.console import Console

    denials, written = _recording()
    prompter = ConsolePrompter(
        Console(file=None, quiet=True), ToolContext(root=tmp_path), denials=denials
    )
    monkeypatch.setattr(prompter, "_interactive", True)
    monkeypatch.setattr(prompter, "_ask", lambda _question: line)

    assert await prompter.confirm(_request()) == expected and written == []


async def test_terminalde_r_uygulama_onayi_degilse_hayir_sayilir(tmp_path, monkeypatch):
    from rich.console import Console

    denials, written = _recording()
    prompter = ConsolePrompter(Console(quiet=True), ToolContext(root=tmp_path), denials=denials)
    monkeypatch.setattr(prompter, "_interactive", True)
    monkeypatch.setattr(prompter, "_ask", lambda _question: "r")

    assert await prompter.confirm(_request(consent_key=None)) is False and written == []


# --------------------------------------------------------------------------- yazım


def test_ret_listesi_yazimi_dogrular_ve_tekrar_eklemez(tmp_path, monkeypatch):
    calls: list[tuple[str, str]] = []

    def fake_write(config, path, raw, file=None):
        calls.append((path, raw))
        desktop = replace(config.desktop, denied_apps=tuple(raw.split(",")))
        return replace(config, desktop=desktop), tmp_path / "config.yaml"

    monkeypatch.setattr("fusion_cli.config.desktop_denied.write_setting", fake_write)
    config = replace(make_config(), desktop=DesktopSettings(denied_apps=("Notes",)))

    updated, text = with_denied_app(config, " Mail ")
    assert calls == [("desktop.denied_apps", "Notes,Mail")] and "eklendi" in text
    assert updated.desktop.denied_apps == ("Notes", "Mail")
    same, text = with_denied_app(updated, "mail")
    assert same is updated and "zaten" in text
    with pytest.raises(ConfigError):
        with_denied_app(config, "a,b")

    applied: list[object] = []
    persist = config_persist(lambda: config, applied.append)
    assert "eklendi" in persist("Mail") and len(applied) == 1
    assert "virgül" in persist("a,b") and len(applied) == 1
