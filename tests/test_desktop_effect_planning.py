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
    from base64 import b64encode
    from dataclasses import replace

    from fusion_cli.core.desktop_frame import DesktopFrame
    from fusion_cli.core.tool_content import ToolContent
    from fusion_cli.core.tools import ToolResult
    from fusion_cli.engines.agent import loop
    from fusion_cli.tools import desktop_policy
    from fusion_cli.tools.builtin import build_registry
    from fusion_cli.tools.registry import ToolRegistry
    from tests.fakes import ScriptedProvider, model_result, tool_call
    from tests.image_fixture import image_bytes
    from tests.test_agent_lessons import _deps

    deps = _deps(tmp_path)
    deps.config = replace(
        deps.config,
        desktop=replace(deps.config.desktop, enabled=True),
        agent=replace(deps.config.agent, tags=("vision",)),
    )
    deps.tool_context = replace(
        deps.tool_context,
        desktop_settings=replace(deps.tool_context.desktop_settings, enabled=True),
    )

    def capture(_args, context):
        width, height = 100, 80
        path = tmp_path / "calculator.png"
        data = image_bytes("PNG", (width, height))
        path.write_bytes(data)
        image = ToolContent.image("image/png", b64encode(data).decode())
        context.desktop.frame = DesktopFrame(width, height, 0, 0, width, height)
        context.desktop.record_capture(path, image.data_uri, data, (0, 0, width, height))
        return ToolResult(str(path), content=(image,))

    delivered = []
    registry = ToolRegistry()
    for tool in build_registry():
        if tool.name == "desktop_screenshot":
            tool = replace(tool, run=capture)
        elif tool.name in {"desktop_click", "desktop_key"}:

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
            model_result(tool_calls=(tool_call("desktop_screenshot"),)),
            replace(
                model_result(tool_calls=(tool_call("desktop_click", x=40, y=30),)),
                model=deps.config.agent.model,
            ),
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


PUBLIC_CLEAR_TASK = (
    "Hesap Makinesi uygulamasını açıp penceresine odaklan ve yeni ekran görüntüsü al. "
    "Tümünü Sil düğmesine bas. Ekrandaki gerçek değeri erişilebilirlik ağacından oku "
    "ve yalnız değeri yaz. Bu turda başka işlem yapma; terminal kullanma."
)


def test_public_clear_button_label_is_not_a_filesystem_delete_predicate():
    assert is_desktop_task(PUBLIC_CLEAR_TASK)
    assert required_effect_for(PUBLIC_CLEAR_TASK) is None
    assert classify_teacher_task(PUBLIC_CLEAR_TASK).size == "basit"


@pytest.mark.parametrize(
    "task",
    [
        "Dosyayı sil ve Tümünü Sil düğmesine bas.",
        "Raporu kaldır. Tümünü Sil düğmesine bas.",
        "Tümünü Sil düğmesine bas. Sonucu rapor.html dosyasına yaz.",
        "HTML sayfasına Sil düğmesi ekle.",
    ],
)
def test_ui_label_cannot_hide_an_independent_filesystem_mutation(task):
    assert required_effect_for(task) == "workspace_mutation"


@pytest.mark.parametrize("app,label", [("Finder", "Sil"), ("Mail", "Gönder"), ("Store", "Öde")])
def test_ui_label_disambiguation_does_not_remove_destructive_action_risk(app, label):
    from fusion_cli.core.desktop_settings import DesktopTarget
    from fusion_cli.tools.desktop_risk import risky_reason

    assert (
        risky_reason(
            "desktop_click", {"x": 1, "y": 1}, DesktopTarget(app, element=f"Button '{label}'"), ""
        )
        is not None
    )


@pytest.mark.parametrize("context", ["uygulamasında", "uygulamada", "uygulamanın içinde"])
def test_existing_application_context_is_not_a_build_object(context):
    task = (
        f"Şimdi Hesap Makinesi {context} 17 × 23 işlemini yap. "
        "Gerçek ekran değerini erişilebilirlik ağacından doğrula ve yalnız sonucu yaz. "
        "Terminal ve tarayıcı kullanma."
    )
    assert is_desktop_task(task)
    assert required_effect_for(task) is None
    assert classify_teacher_task(task).size == "basit"
    policy = policy_for(make_config(), ModelSpec(name="test", model="fake/test"), task)
    assert policy.required_effect is None
    assert not policy.complex_task


@pytest.mark.parametrize(
    "task",
    [
        "Bir uygulama yap.",
        "Uygulamayı yap.",
        "Uygulamasını oluştur.",
        "Uygulamanı düzenle.",
        "Uygulamanın aynısını yap.",
        "Uygulamasının benzerini yap.",
        "Hesap Makinesi uygulamasında kodu değiştir.",
        "Uygulamada bir HTML sayfa oluştur.",
        "Uygulamanın bileşenini güncelle.",
        "Uygulamasında src/app.py dosyasını düzenle.",
        "Uygulamada dosyayı sil.",
        "Uygulamanın dosyalarını kaldır.",
    ],
)
def test_application_context_does_not_erase_real_mutation_objects(task):
    assert required_effect_for(task) == "workspace_mutation"


@pytest.mark.parametrize(
    "task,effect",
    [
        ("Uygulamada git push yap.", "git_push"),
        ("Uygulamanın kodu için git commit oluştur.", "git_commit"),
        ("Uygulamasında npm test çalıştır.", "shell_action"),
    ],
)
def test_application_context_keeps_external_effect_priority(task, effect):
    assert required_effect_for(task) == effect


@pytest.mark.parametrize(
    "task",
    [
        "Mevcut uygulamadan bir kopya yap.",
        "Bu uygulamadan bir kopya yapmanı istiyorum.",
        "Bu uygulamadan bir klon yapabilir misin?",
        "Bu uygulamadan bir klon yap.",
        "Bu uygulamasından bir kopya oluştur.",
        "Bu uygulamadan bir benzerini yap.",
        "Bu uygulamadan aynısını yap.",
    ],
)
def test_explicit_application_source_clone_keeps_teacher_and_effect_contract(task):
    assert required_effect_for(task) == "workspace_mutation"
    assert classify_teacher_task(task).size == "orta-buyuk"
    policy = policy_for(make_config(), ModelSpec(name="test", model="fake/test"), task)
    assert policy.complex_task


@pytest.mark.parametrize(
    "task",
    [
        "Hesap Makinesi uygulamasından sonucu oku ve yalnız sonucu yaz.",
        "Hesap Makinesi uygulamadan 17 × 23 işlemini yap ve sonucu yaz.",
        "Hesap Makinesi uygulamasında bir kopya var mı?",
        "Bu uygulamadan bir klon yapma.",
        "Uygulamadan kopya yapmak nasıl yapılır?",
    ],
)
def test_application_context_does_not_imply_clone_creation(task):
    assert required_effect_for(task) is None
    assert classify_teacher_task(task).size == "basit"
