"""Counted response formatting must not create a workspace-write contract."""

from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from fusion_cli.core.tools import ToolResult
from fusion_cli.core.types import ModelSpec
from fusion_cli.engines.agent import loop
from fusion_cli.engines.agent.execution_policy import policy_for
from fusion_cli.engines.agent.teacher_plan import classify_teacher_task
from fusion_cli.engines.effects.detect import required_effect_for
from fusion_cli.tools.builtin import build_registry
from fusion_cli.tools.registry import ToolRegistry
from tests.fakes import ScriptedProvider, make_config, model_result, tool_call
from tests.test_agent_lessons import _deps

TASK = (
    "Python’un en son kararlı sürümünü şu an resmi indirme sayfasından kontrol et. "
    "Sürüm, yayın tarihi ve kaynak bağlantısını 3 kısa satırda yaz. WebFetch kullan; "
    "terminali ve bilgisayarın tarayıcı/masaüstü kontrolünü kullanma. "
    "Bilgiyi belleğinden tahmin etme."
)


@pytest.mark.parametrize(
    "task",
    [
        TASK,
        "Sonucu 3 satırda yaz.",
        "Yanıtı iki kısa satırda yaz.",
        "Yanıtı 3 kısa satırda yazmanı istiyorum.",
        "3 kısa satırda yanıt yaz.",
        "Üç satırlık kısa cevap yaz.",
    ],
)
def test_counted_reply_format_does_not_request_workspace_changes(task):
    assert required_effect_for(task) is None
    assert classify_teacher_task(task).size == "basit"
    policy = policy_for(make_config(), ModelSpec(name="test", model="fake/test"), task)
    assert not policy.complex_task
    assert policy.required_effect is None


@pytest.mark.parametrize(
    "task",
    [
        "Sonucu rapor.txt dosyasına 3 kısa satırda yaz.",
        "src/main.py dosyasını düzenle. Sonucu 3 kısa satırda yaz.",
        "Kodu üç kısa satırda yaz.",
        "Bir HTML sayfa oluştur. Yanıtı 3 kısa satırda yaz.",
        "Bir uygulama yap. Sonucu 3 kısa satırda yaz.",
        "Bir satır ekle.",
        "Bir satır yaz.",
        "Üç satırda değişiklik yap.",
        "Dosyayı sil. Sonucu 3 kısa satırda yaz.",
        "rapor.txt dosyasına 3 kısa satırda yanıt yaz.",
        "rapor.txt dosyasına üç satırlık kısa cevap yaz.",
        "3 satırda kod yaz.",
        "3satırda kod yaz.",
        "Üç satırlık kod yaz.",
    ],
)
def test_reply_format_preserves_affirmative_file_code_and_ui_effects(task):
    assert required_effect_for(task) == "workspace_mutation"


@pytest.mark.parametrize(
    "format_instruction",
    ["3 kısa satırda yaz.", "3 kısa satırda yanıt yaz.", "Üç satırlık kısa cevap yaz."],
)
async def test_successful_official_web_fetch_finalizes_without_file_mutation_or_teacher(
    tmp_path, monkeypatch, format_instruction
):
    deps = _deps(tmp_path)
    registry = ToolRegistry()
    fetch = next(tool for tool in build_registry() if tool.name == "web_fetch")
    delivered = []

    def fetch_fixture(args, context):
        delivered.append(args["url"])
        return ToolResult("Synthetic official page: Python 3.15.2, release 25 October 2026.")

    registry.register(replace(fetch, run=fetch_fixture))
    deps.base_registry = registry
    answer = "3.15.2\n25 Ekim 2026\nhttps://www.python.org/downloads/"
    provider = ScriptedProvider(
        [
            model_result(
                tool_calls=[tool_call("web_fetch", url="https://www.python.org/downloads/")]
            ),
            model_result(answer),
        ]
    )
    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: provider)
    teacher = AsyncMock()
    monkeypatch.setattr(loop, "prepare_teacher_plan", teacher)
    result = await loop.run_agent(
        TASK.replace("3 kısa satırda yaz.", format_instruction),
        deps,
        verify=False,
        self_review=False,
    )
    assert delivered == ["https://www.python.org/downloads/"]
    assert result.ok and result.final_text == answer
    assert provider.calls == 2
    teacher.assert_not_awaited()
    assert not any("[eylem-kanıtı-zorunlu]" in m.content for m in result.messages)
    assert not deps.tool_context.changes.paths
