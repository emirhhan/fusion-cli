"""Web model tercihi yalnız canlı hesap seçeneklerinden kaydedilir."""

from __future__ import annotations

from dataclasses import replace

import pytest

from fusion_cli.providers import web_control
from fusion_cli.providers.web_browser import (
    WEB_BROWSER_PROVIDERS,
    _model_choice_matches_observed,
    model_choices_on_page,
)
from tests.fakes import make_config


class _Option:
    def __init__(self, label: str) -> None:
        self.label = label

    async def inner_text(self) -> str:
        return self.label

    async def is_visible(self) -> bool:
        return True


class _Locator:
    def __init__(self, items: list[object]) -> None:
        self.items = items

    @property
    def first(self):
        return self.items[0]

    @property
    def last(self):
        return self.items[-1]

    async def count(self) -> int:
        return len(self.items)

    def nth(self, index: int):
        return self.items[index]

    def locator(self, selector: str):
        options = [_Option("Flash"), _Option("Pro\nAyrıntı")]
        if "bard-mode-option-" not in selector:
            options.append(_Option("Genişletilmiş düşünme"))
        return _Locator(options)

    async def wait_for(self, **kwargs) -> None:
        return None


class _Button:
    async def count(self) -> int:
        return 1

    async def is_visible(self) -> bool:
        return True

    async def click(self, **kwargs) -> None:
        return None


class _Page:
    def locator(self, selector: str):
        return _Locator([_Button()] if "bard-mode-menu-button" in selector else [_Locator([])])


async def test_canli_model_menusu_yalniz_secenekleri_dondurur():
    page = _Page()
    assert await model_choices_on_page(page, WEB_BROWSER_PROVIDERS["gemini_web"]) == (
        "Flash", "Pro"
    )


def test_kisa_kademe_etiketi_farkli_surumu_dogrulanmis_saymaz():
    assert _model_choice_matches_observed("3.1 Pro", "Pro")
    assert _model_choice_matches_observed("3.1 Pro", "Gemini 3.1 Pro")
    assert not _model_choice_matches_observed("3.1 Pro", "Gemini 3.6 Pro")
    assert not _model_choice_matches_observed("Pro", "Proactive")


async def test_otomatik_web_secenegi_iki_kez_gorunmez(monkeypatch):
    from fusion_cli.config.models import WebSessionConfig

    session = WebSessionConfig(
        model="gemini_web/main/auto", provider="gemini_web", account="main",
        transport="browser", enabled=True, login_verified=True,
    )
    config = replace(make_config(), web_sessions=(session,))

    async def choices(*args):
        return ("Otomatik", "3.1 Pro")

    monkeypatch.setattr(
        "fusion_cli.providers.web_browser.discover_browser_models", choices
    )
    monkeypatch.setattr("fusion_cli.providers.web_registry.web_registry_for", lambda c: None)

    result = await web_control.session_model_choices(config, "gemini_web", "main")

    assert result["secenekler"] == ["Otomatik", "3.1 Pro"]


@pytest.mark.parametrize("selected,ok", [("Pro", True), ("Uydurma", False)])
async def test_web_modeli_canli_menuye_gore_kaydedilir(
    monkeypatch, tmp_path, selected: str, ok: bool
):
    from fusion_cli.config.models import WebSessionConfig

    session = WebSessionConfig(
        model="gemini_web/main/auto", provider="gemini_web", account="main",
        transport="browser", enabled=True, login_verified=True, tool_eval_passed=True,
    )
    config = replace(make_config(), web_sessions=(session,))

    async def choices(*args):
        return {"ok": True, "secenekler": ["Otomatik", "Flash", "Pro"]}

    monkeypatch.setattr(web_control, "session_model_choices", choices)
    monkeypatch.setattr(
        "fusion_cli.config.writer.write_web_sessions", lambda config: tmp_path / "config.yaml"
    )
    updated, result = await web_control.set_session_model_choice(
        config, "gemini_web", "main", selected
    )
    assert result["ok"] is ok
    assert (updated.web_sessions[0].selected_model if updated else "") == (selected if ok else "")
    if updated:
        assert updated.web_sessions[0].tool_eval_passed is False


async def test_ayni_model_tekrar_secilince_arac_olcumu_korunur(monkeypatch):
    from fusion_cli.config.models import WebSessionConfig

    session = WebSessionConfig(
        model="gemini_web/main/auto", provider="gemini_web", account="main",
        transport="browser", enabled=True, login_verified=True,
        selected_model="Pro", tool_eval_passed=True,
    )
    config = replace(make_config(), web_sessions=(session,))

    async def choices(*args):
        return {"ok": True, "secenekler": ["Otomatik", "Pro"]}

    monkeypatch.setattr(web_control, "session_model_choices", choices)
    monkeypatch.setattr(
        "fusion_cli.config.writer.write_web_sessions", lambda config: None
    )
    updated, result = await web_control.set_session_model_choice(
        config, "gemini_web", "main", "Pro"
    )
    assert result["ok"] is True
    assert updated is not None and updated.web_sessions[0].tool_eval_passed is True
