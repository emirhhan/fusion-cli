"""Görev gereksinimlerinin sağlayıcı adına değil ölçülen yeteneğe bağlanması."""

from __future__ import annotations

import pytest

from fusion_cli.config.models import WebSessionConfig
from fusion_cli.core.errors import ConfigError
from fusion_cli.core.types import ModelSpec
from fusion_cli.providers.capabilities import (
    TaskRequirements,
    capabilities_for,
    infer_task_requirements,
    select_compatible_model,
)


@pytest.mark.parametrize(
    "task",
    (
        "İnternetten free assetler toplayarak 2d bir oyun yap; hikaye ve ara sahneler olsun.",
        "Tüm projeyi kapsamlı olarak geliştir ve PNG sprite dosyaları oluştur.",
    ),
)
def test_kapsamli_gorev_dogrulanmis_web_araclarini_baslamadan_elemez(task):
    gemini = ModelSpec("gemini", "gemini_web/main/auto", tags=("strict",))
    sessions = (
        WebSessionConfig(
            model=gemini.model,
            provider="gemini_web",
            transport="browser",
            tool_support="emulated",
            tool_eval_passed=True,
        ),
    )

    requirements = infer_task_requirements(task, mutating=True)

    assert requirements.tools
    assert select_compatible_model((gemini,), requirements, sessions, strict=True) == gemini


def test_gercek_gorsel_eki_gorsel_destegi_istemeye_devam_eder():
    assert infer_task_requirements("Bu resmi incele", has_images=True).images


def test_gemini_web_uzun_gorselli_cok_aracli_mutasyon_isinden_elenir():
    gemini = ModelSpec("gemini", "gemini_web/main/auto")
    api = ModelSpec("api", "openrouter/google/gemini-2.5-pro", tags=("agent", "vision"))
    sessions = (
        WebSessionConfig(
            model=gemini.model,
            provider="gemini_web",
            transport="browser",
            tool_support="emulated",
            tool_eval_passed=True,
        ),
    )
    requirements = TaskRequirements(tools=True, images=True, web=True, long_running=True)

    selected = select_compatible_model((gemini, api), requirements, sessions)

    assert selected == api


def test_kullanici_zorunlu_uyumsuz_model_secerse_acik_on_kontrol_hatasi_alir():
    strict = ModelSpec("secilen", "gemini_web/main/auto", tags=("strict",))
    sessions = (WebSessionConfig(model=strict.model, provider="gemini_web", transport="browser"),)

    with pytest.raises(ConfigError, match=r"görsel|uzun"):
        select_compatible_model(
            (strict,),
            TaskRequirements(images=True, long_running=True),
            sessions,
            strict=True,
        )


def test_browser_profili_tek_oturumludur_ve_zorunlu_yetenek_fallbackta_dusmez():
    browser = ModelSpec("web", "claude_web/main/auto")
    no_tools = ModelSpec("small", "local/no-tools", tags=("no-tools",))
    capable = ModelSpec("capable", "openrouter/anthropic/claude-sonnet-4", tags=("agent",))
    sessions = (WebSessionConfig(model=browser.model, provider="claude_web", transport="browser"),)

    assert capabilities_for(browser, sessions).exclusive_session is True
    assert (
        select_compatible_model(
            (no_tools, capable), TaskRequirements(tools=True, native_tools=True), sessions
        )
        == capable
    )
