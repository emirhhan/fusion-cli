"""Claude Code görev araçları: TaskCreate/Get/List/Update ve model bazlı sunum (#329)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from fusion_cli.core.tools import TodoStatus, ToolContext
from fusion_cli.engines.agent.execution_policy import ExecutionPolicy
from fusion_cli.engines.agent.loop import _permitted
from fusion_cli.engines.agent.task_availability import task_tool_mode
from fusion_cli.tools.args import ArgumentError
from fusion_cli.tools.builtin import build_registry
from fusion_cli.tools.task_tools import task_create, task_get, task_list, task_update


@pytest.mark.parametrize(
    ("model", "mode"),
    [
        ("anthropic/claude-opus-4-7", "tasks"),
        ("claude-sonnet-4-6", "tasks"),
        ("claude-haiku-4-5-20251001", "tasks"),
        ("claude-sonnet-4-20250514", "tasks"),
        ("openrouter/anthropic/claude-3.5-sonnet", "tasks"),
        ("claude-3-opus-20240229", "tasks"),
        ("claude-opus-4-8", "none"),
        ("claude-sonnet-5", "none"),
        ("claude-haiku-5-0", "none"),
        ("gpt-5", "none"),
        ("groq/llama-3.3-70b", "none"),
    ],
)
def test_varsayilan_kip_modele_gore(model, mode):
    assert task_tool_mode(model, {}) == mode


def test_ortam_degiskenleri_claude_gibi():
    assert task_tool_mode("gpt-5", {"CLAUDE_CODE_ENABLE_TODO_TOOLS": "1"}) == "tasks"
    assert task_tool_mode("claude-sonnet-4-6", {"CLAUDE_CODE_ENABLE_TASKS": "0"}) == "todo"
    assert task_tool_mode("claude-sonnet-4-6", {"CLAUDE_CODE_ENABLE_TASKS": "false"}) == "todo"
    forced = {"CLAUDE_CODE_ENABLE_TODO_TOOLS": "1", "CLAUDE_CODE_ENABLE_TASKS": "0"}
    assert task_tool_mode("claude-opus-4-8", forced) == "todo"


def _names(mode: str, allowed: set[str] | None = None) -> set[str]:
    names = _permitted(
        allowed, build_registry(), replace(ExecutionPolicy(is_web=False), task_tools=mode)
    )
    assert names is not None
    return names


def test_kipe_gore_sunulan_araclar_ve_acik_istek():
    tasks = {"task_create", "task_get", "task_list", "task_update"}
    assert tasks <= _names("tasks") and "todo_write" not in _names("tasks")
    assert "todo_write" in _names("todo") and not tasks & _names("todo")
    assert not (tasks | {"todo_write"}) & _names("none")
    # `--tools`/`--allowedTools` ile adı verilen araç modelden bağımsız sunulur.
    assert "task_create" in _names("none", {"task_create", "read_file"})
    assert "todo_write" not in _names("none", {"read_file"})  # ALWAYS_ALLOWED geçmez


def test_policy_for_modeli_task_kipine_cevirir(tmp_path):
    from fusion_cli.config.models import ModelSpec
    from fusion_cli.engines.agent.execution_policy import policy_for
    from tests.fakes import make_config

    config = make_config(memory_dir=tmp_path / "m")
    claude = policy_for(config, ModelSpec(name="c", model="claude-sonnet-4-6"), "listele")
    other = policy_for(config, ModelSpec(name="o", model="groq/llama-3.3-70b"), "listele")
    assert claude.task_tools == "tasks" and other.task_tools == "none"


def test_gorev_yasam_dongusu(tmp_path):
    context = ToolContext(root=tmp_path)

    assert "#1" in task_create({"subject": "Testleri yaz", "description": "birim"}, context).output
    task_create({"subject": "Kodu yaz", "description": "", "activeForm": "Kod yazılıyor"}, context)
    task_update({"taskId": "2", "addBlockedBy": ["1"], "status": "in_progress"}, context)

    listed = task_list({}, context).output
    assert "#1 [pending] Testleri yaz" in listed
    assert "#2 [in_progress] Kodu yaz (bekliyor: #1)" in listed
    assert "Engelledikleri: #2" in task_get({"taskId": "1"}, context).output
    assert context.todos.items[1].label == "Kod yazılıyor"

    task_update({"taskId": "1", "status": "completed"}, context)
    assert "(bekliyor" not in task_list({}, context).output
    task_update({"taskId": "1", "status": "deleted"}, context)
    assert [item.task_id for item in context.todos.items] == ["2"]
    assert context.todos.items[0].status is TodoStatus.IN_PROGRESS


def test_gecersiz_girdiler_hata(tmp_path):
    context = ToolContext(root=tmp_path)
    with pytest.raises(ArgumentError):
        task_create({"description": "x"}, context)
    with pytest.raises(ArgumentError):
        task_get({"taskId": "9"}, context)
    task_create({"subject": "a", "description": ""}, context)
    with pytest.raises(ArgumentError):
        task_update({"taskId": "1", "status": "done"}, context)
    with pytest.raises(ArgumentError):
        task_update({"taskId": "1", "addBlocks": ["7"]}, context)
    assert task_list({}, ToolContext(root=tmp_path)).output == "Görev yok."


def test_gorevler_oturum_listesinde_saklanir_ve_geri_gelir(tmp_path):
    from fusion_cli.cli.repl.task_list import StoredTodoList

    path = tmp_path / "liste.json"
    first = StoredTodoList(lambda: path)
    context = ToolContext(root=tmp_path, todos=first)
    task_create({"subject": "a", "description": "ayrıntı"}, context)
    task_create({"subject": "b", "description": ""}, context)
    task_update({"taskId": "2", "addBlockedBy": ["1"]}, context)

    again = StoredTodoList(lambda: path).items

    assert [(item.task_id, item.description, item.blocked_by) for item in again] == [
        ("1", "ayrıntı", ()),
        ("2", "", ("1",)),
    ]


def test_claude_adlari_cozulur():
    registry = build_registry()
    for claude in ("TaskCreate", "TaskGet", "TaskList", "TaskUpdate"):
        tool = registry.resolve(claude)
        assert tool is not None and tool.name.startswith("task_")
