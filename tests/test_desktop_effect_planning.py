"""Desktop actions must not inherit filesystem planning from another clause."""

from __future__ import annotations

import pytest

from fusion_cli.core.types import ModelSpec
from fusion_cli.engines.agent.execution_policy import policy_for
from fusion_cli.engines.agent.expertise import is_desktop_task
from fusion_cli.engines.agent.teacher_plan import classify_teacher_task
from fusion_cli.engines.effects.detect import required_effect_for
from tests.fakes import make_config


@pytest.mark.parametrize(
    "task",
    [
        (
            "Hesap Makinesi uygulamasını aç. Ekranı sıfırla. "
            "17*23 işlemini yap ve sonucu yaz. Terminal kullanma."
        ),
        "Hesap Makinesi uygulamasını aç ve 17*23 işlemini yap; sonucu yaz. Terminal kullanma.",
        "Hesap Makinesi uygulamasını aç, 17*23 işlemini yap, sonucu yaz.",
        "Hesap Makinesi uygulamasını aç\nEkranı sıfırla\n17*23 işlemini yap ve sonucu yaz.",
    ],
)
def test_calculator_operation_does_not_become_workspace_mutation(task):
    assert is_desktop_task(task)
    assert required_effect_for(task) != "workspace_mutation"
    policy = policy_for(make_config(), ModelSpec(name="test", model="fake/test"), task)
    assert not policy.complex_task
    assert classify_teacher_task(task).size == "basit"


@pytest.mark.parametrize(
    "task",
    [
        "Bir uygulama yap.",
        "Bir HTML rapor yaz.",
        "Hesap Makinesi uygulamasını aç. Sonucu rapor.html dosyasına yaz.",
        "Hesap Makinesi uygulamasını aç ve sonuç için bir HTML sayfa oluştur.",
        "Hesap Makinesi uygulamasını aç; src/app.py dosyasını düzenle.",
        "README.md ve src/app.py dosyalarını güncelle.",
        "Bir arama kutusu ekle.",
    ],
)
def test_explicit_application_or_html_file_work_still_requires_mutation(task):
    assert required_effect_for(task) == "workspace_mutation"


@pytest.mark.parametrize(
    "task,effect",
    [
        ("Repoyu pushla ama terminal kullanma.", "git_push"),
        ("Hesap Makinesi uygulamasını aç. git commit oluştur.", "git_commit"),
        ("Hesap Makinesi uygulamasını aç; npm test çalıştır.", "shell_action"),
        ("Dosya oluşturma. Terminal kullanma. Yalnız cevabı yaz.", None),
    ],
)
def test_external_effect_and_prohibition_rules_remain_authoritative(task, effect):
    assert required_effect_for(task) == effect


def test_accusative_application_object_uses_existing_desktop_lane():
    assert is_desktop_task("Hesap Makinesi uygulamasını aç.")
    assert not is_desktop_task("Bir web uygulamasını yap.")
    assert not is_desktop_task("Bir mobil uygulamasını yap.")


@pytest.mark.parametrize(
    "task", ["Bir uygulama ve oyun yap.", "HTML ve CSS yaz.", "Bir uygulama, oyun yap."]
)
def test_coordinated_build_objects_still_bind_to_their_shared_verb(task):
    assert required_effect_for(task) == "workspace_mutation"


async def test_calculator_lane_admits_explicit_click_and_key_with_trusted_target(
    tmp_path, monkeypatch
):
    from dataclasses import replace

    from fusion_cli.core.desktop_frame import DesktopFrame
    from fusion_cli.core.tools import ToolResult
    from fusion_cli.engines.agent import loop
    from fusion_cli.tools import desktop_policy
    from fusion_cli.tools.builtin import build_registry
    from fusion_cli.tools.registry import ToolRegistry
    from tests.fakes import ScriptedProvider, model_result, tool_call
    from tests.test_agent_lessons import _deps

    deps = _deps(tmp_path)
    deps.config = replace(deps.config, desktop=replace(deps.config.desktop, enabled=True))
    deps.tool_context = replace(
        deps.tool_context,
        desktop_settings=replace(deps.tool_context.desktop_settings, enabled=True),
    )
    deps.tool_context.desktop.frame = DesktopFrame(1000, 800, 0, 0, 1000, 800)
    delivered = []
    registry = ToolRegistry()
    for tool in build_registry():
        if tool.name in {"desktop_click", "desktop_key"}:

            def deliver(args, context, name=tool.name):
                delivered.append(name)
                return ToolResult("Synthetic event delivered; application result not measured.")

            tool = replace(tool, run=deliver)
        registry.register(tool)
    deps.base_registry = registry

    async def probe(request):
        return {
            "ok": True,
            "app": "Calculator",
            "bundle": "com.apple.calculator",
            "pid": 42,
            "element": {"role": "AXButton", "title": "1"},
        }

    monkeypatch.setattr(desktop_policy, "_swift_probe", probe)
    provider = ScriptedProvider(
        [
            model_result(tool_calls=(tool_call("desktop_click", x=400, y=300),)),
            model_result(tool_calls=(tool_call("desktop_key", key="1"),)),
            model_result("Sentetik etkileşim kaydı tamamlandı."),
        ]
    )
    monkeypatch.setattr(loop, "build_provider", lambda *a, **k: provider)
    task = (
        "Hesap Makinesi uygulamasını aç. Ekranı sıfırla. "
        "17*23 işlemini yap ve sonucu yaz. Terminal kullanma."
    )
    outcome = await loop.run_agent(task, deps, verify=False, self_review=False)
    assert outcome.ok
    assert deps.execution is not None and not deps.execution.complex_task
    assert "masaustu" in deps.tool_context.task_kinds
    assert delivered == ["desktop_click", "desktop_key"]
    assert all(use.ok for use in outcome.tool_uses if use.name in delivered)
    names = {schema["function"]["name"] for schema in provider.seen_requests[0]}
    assert {"desktop_click", "desktop_key", "desktop_background_inspect"} <= names
