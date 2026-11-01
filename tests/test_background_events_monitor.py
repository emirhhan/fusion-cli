"""Claude Code arka plan bildirimi, TaskStop ve Monitor karşılıkları (#334, #336, #342)."""

from __future__ import annotations

import time
from pathlib import Path

from fusion_cli.core.background_events import (
    BACKGROUND_NOTE_PREFIX,
    MAX_PENDING_EVENTS,
    BackgroundEvents,
)
from fusion_cli.core.tool_emulation import render_tool_instructions
from fusion_cli.core.tools import ToolContext, ToolFamily, tool_family
from fusion_cli.core.types import Message
from fusion_cli.engines.agent.background_notes import append_background_events
from fusion_cli.tools import shell
from fusion_cli.tools.builtin import build_registry
from fusion_cli.tools.monitor_tool import EFFECTIVE_MAX_TIMEOUT_MS, monitor
from fusion_cli.tools.task_stop import task_stop


def _context(tmp_path: Path) -> tuple[ToolContext, BackgroundEvents]:
    events = BackgroundEvents()
    return ToolContext(root=tmp_path, background_events=events), events


def _wait_for(events: BackgroundEvents, needle: str, timeout_s: float = 10.0) -> list[str]:
    seen: list[str] = []
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        seen.extend(events.drain())
        if any(needle in item for item in seen):
            return seen
        time.sleep(0.05)
    raise AssertionError(f"{needle!r} gelmedi: {seen}")


def test_olay_kuyrugu_tek_seferlik_bosalir_ve_tavanda_sayar():
    events = BackgroundEvents()
    for index in range(MAX_PENDING_EVENTS + 3):
        events.push(f"satır {index}")
    events.push("   ")

    items = events.drain()

    assert len(items) == MAX_PENDING_EVENTS + 1
    assert items[-1] == "(+3 olay kuyruk dolu olduğu için düştü)"
    assert events.drain() == ()


def test_uyandirma_yeni_olayda_bir_kez_ve_geri_verilince_yeniden():
    events = BackgroundEvents()
    assert events.claim_wake() is False
    events.push("iş bitti")

    assert events.claim_wake() is True
    assert events.claim_wake() is False
    events.release_wake()
    assert events.claim_wake() is True


def test_olaylar_model_istegine_harness_notu_olarak_girer(tmp_path):
    context, events = _context(tmp_path)
    messages: list[Message] = []
    assert append_background_events(messages, context) is False

    events.push("Arka plan işi abc bitti")
    assert append_background_events(messages, context) is True

    note = messages[-1]
    assert note.harness_note and note.role == "user"
    assert note.content.startswith(BACKGROUND_NOTE_PREFIX)
    assert append_background_events(messages, ToolContext(root=tmp_path)) is False


def test_biten_arka_plan_isi_yoklamasiz_bildirilir_ve_cikti_dosyasi_verilir(tmp_path):
    context, events = _context(tmp_path)

    started = shell.run_shell({"command": "echo merhaba", "run_in_background": True}, context)

    assert "task_stop(task_id=" in started.output and "job_status" not in started.output
    job_id = (started.structured or {})["task_id"]
    seen = _wait_for(events, f"Arka plan işi {job_id} bitti")
    done = next(item for item in seen if job_id in item)
    assert "(çıkış kodu 0)" in done and str((started.structured or {})["output_file"]) in done
    assert "merhaba" in Path(str((started.structured or {})["output_file"])).read_text()


def test_task_stop_isi_durdurur_shell_id_takma_ad(tmp_path):
    context, events = _context(tmp_path)
    started = shell.run_shell({"command": "sleep 30", "run_in_background": True}, context)
    job_id = str((started.structured or {})["task_id"])

    stopped = task_stop({"shell_id": job_id}, context)

    assert stopped.ok and "durduruldu" in stopped.output
    _wait_for(events, f"Arka plan işi {job_id}")
    assert not task_stop({"task_id": "deadbeef"}, context).ok
    assert not task_stop({}, context).ok


def test_monitor_her_satiri_olay_olarak_verir_ve_biter(tmp_path):
    context, events = _context(tmp_path)

    result = monitor(
        {"command": "printf 'bir\\niki\\n'; printf son", "description": "günlük"}, context
    )

    assert result.ok and "İzleme başladı" in result.output
    assert (result.structured or {})["timeoutMs"] == 300_000
    seen = _wait_for(events, "izleme bitti")
    lines = [item for item in seen if "· günlük]" in item]
    assert [item.rsplit("] ", 1)[1] for item in lines] == ["bir", "iki", "son", "izleme bitti."]
    # Monitor kendi bitiş bildirimini verir; genel "iş bitti" bildirimi tekrar etmez.
    assert not any(item.startswith("Arka plan işi") for item in seen)


def test_monitor_suresi_dolunca_durur_ve_bir_kez_haber_verir(tmp_path):
    context, events = _context(tmp_path)

    result = monitor({"command": "sleep 30", "description": "bekle", "timeout_ms": 300}, context)

    assert result.ok
    seen = _wait_for(events, "süre doldu")
    assert sum("süre doldu" in item for item in seen) == 1


def test_monitor_sinirlar_ve_kapali_durumlar(tmp_path, monkeypatch):
    context, _events = _context(tmp_path)
    assert not monitor({"description": "x"}, context).ok
    assert not monitor({"ws": "wss://x", "description": "x"}, context).ok
    assert not monitor({"command": "true", "description": "x", "timeout_ms": 3_600_001}, context).ok
    assert not monitor({"command": "true", "description": "x"}, ToolContext(root=tmp_path)).ok

    capped = monitor({"command": "true", "description": "x", "timeout_ms": 3_600_000}, context)
    assert (capped.structured or {})["timeoutMs"] == EFFECTIVE_MAX_TIMEOUT_MS

    monkeypatch.setenv("CLAUDE_CODE_DISABLE_BACKGROUND_TASKS", "1")
    assert not monitor({"command": "true", "description": "x"}, context).ok


def test_monitor_bash_izin_ailesinde_task_stop_meta():
    assert tool_family("monitor") is ToolFamily.SHELL
    assert tool_family("task_stop") is ToolFamily.META


def test_claude_adlari_ayni_araclara_cozulur():
    registry = build_registry()
    for claude, fusion in (
        ("TaskStop", "task_stop"),
        ("Monitor", "monitor"),
        ("EnterWorktree", "enter_worktree"),
        ("ExitWorktree", "exit_worktree"),
    ):
        tool = registry.resolve(claude)
        assert tool is not None and tool.name == fusion


def test_ertelenmis_araclar_imzayla_sunulur_job_status_sunulmaz():
    from fusion_cli.engines.agent.execution_policy import ExecutionPolicy
    from fusion_cli.engines.agent.loop import _permitted

    registry = build_registry()
    names = _permitted(None, registry, ExecutionPolicy(is_web=False))
    assert names is not None
    assert {"enter_worktree", "exit_worktree", "monitor", "task_stop"} <= names
    text = render_tool_instructions(registry.schemas(names))

    assert "monitor(command,description,timeout_ms?)" in text
    assert "task_stop(task_id)" in text and "enter_worktree(name?,path?)" in text
    assert "- job_status:" not in text
    assert registry.get("job_status") is not None


def test_masaustu_yoklamasi_bekleyen_olayda_duz_metin_uyandirma_verir():
    from fusion_cli.appserver.background_wake import BACKGROUND_WAKE_ID, background_wake_tasks
    from fusion_cli.ui import messages

    events = BackgroundEvents()
    assert background_wake_tasks(events) == [] and background_wake_tasks(None) == []
    events.push("[monitor abc · günlük] hata")

    tasks = background_wake_tasks(events)

    assert tasks == [
        {
            "id": BACKGROUND_WAKE_ID,
            "gorev": messages.BACKGROUND_WAKE,
            "kaynak": "agent",
            "duz_metin": True,
        }
    ]
    assert background_wake_tasks(events) == []  # aynı olay tekrar uyandırmaz
    events.release_wake()  # arayüz gönderemedi (`cron.geri_ver`)
    assert len(background_wake_tasks(events)) == 1
