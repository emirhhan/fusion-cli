"""`-p --include-hook-events` (#289): stream-json'a `hook_started` / `hook_response`."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from fusion_cli.cli import app as app_module
from fusion_cli.cli import print_run
from fusion_cli.core.hooks.events import HookCommand, HookEvent, HookRun, HookSet
from fusion_cli.engines.hooks import lifecycle
from fusion_cli.engines.hooks.session import HookSession

runner = CliRunner()


def _command(event: HookEvent = HookEvent.PRE_TOOL_USE) -> HookCommand:
    return HookCommand(event=event, matcher="Bash", command="echo hi", timeout_s=5)


def _fake_run_hook(exit_code: int | None = 0, *, stdout: str = "çıktı\n", stderr: str = ""):
    async def _run(command, payload, **_kwargs):
        return HookRun(command, exit_code, stdout, stderr)

    return _run


def test_gozlemci_yokken_kayit_yok(monkeypatch):
    monkeypatch.setattr(lifecycle, "run_hook", _fake_run_hook())
    run = asyncio.run(
        lifecycle.run_observed(
            _command(), {}, subjects=("Bash",), cwd=Path.cwd(), environment={}
        )
    )
    assert run.exit_code == 0


def test_hook_session_emit_gozlemciye_baslangic_ve_cevap_verir(monkeypatch, tmp_path):
    monkeypatch.setattr(lifecycle, "run_hook", _fake_run_hook(2, stderr="engellendi"))
    seen: list[dict[str, object]] = []
    session = HookSession(root=tmp_path, loader=lambda: HookSet((_command(),)))
    with lifecycle.observe_hook_lifecycle(seen.append):
        asyncio.run(session.emit(HookEvent.PRE_TOOL_USE, subjects=("Bash",)))
    started, response = seen
    assert started["subtype"] == "hook_started"
    assert started["hook_name"] == "PreToolUse:Bash"
    assert started["hook_event"] == "PreToolUse"
    assert response["subtype"] == "hook_response"
    assert response["hook_id"] == started["hook_id"]
    assert response["exit_code"] == 2 and response["outcome"] == "error"
    assert response["stderr"] == "engellendi" and response["stdout"] == "çıktı\n"
    assert lifecycle._observers == []


def test_zaman_asimi_hata_sonucudur():
    fields = lifecycle.response_fields(HookRun(_command(), None, timed_out=True))
    assert fields["outcome"] == "error" and "exit_code" not in fields
    assert fields["stderr"]


def _print(monkeypatch, args):
    monkeypatch.setattr(lifecycle, "run_hook", _fake_run_hook())

    async def _fake(task, config, **kwargs):
        await lifecycle.run_observed(
            _command(HookEvent.USER_PROMPT_SUBMIT),
            {},
            subjects=(),
            cwd=Path.cwd(),
            environment={},
        )
        return SimpleNamespace(
            final_text="tamam",
            ok=True,
            stop_reason=None,
            model_calls_made=1,
            hit_step_limit=False,
            messages=[],
        )

    monkeypatch.setattr(print_run, "run_agent_task", _fake)
    return runner.invoke(app_module.app, args)


def _messages(stdout: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in stdout.splitlines() if line.startswith("{")]


def test_stream_json_kanca_olaylarini_yazar(monkeypatch):
    result = _print(
        monkeypatch,
        ["-p", "selam", "--output-format", "stream-json", "--verbose", "--include-hook-events"],
    )
    assert result.exit_code == 0, result.output
    assert "--include-hook-events" not in result.stderr
    hooks = [m for m in _messages(result.stdout) if str(m.get("subtype", "")).startswith("hook_")]
    assert [m["subtype"] for m in hooks] == ["hook_started", "hook_response"]
    assert all(m["type"] == "system" and m["session_id"] and m["uuid"] for m in hooks)
    assert hooks[0]["hook_name"] == "UserPromptSubmit"
    assert hooks[1]["outcome"] == "success" and hooks[1]["exit_code"] == 0
    assert lifecycle._observers == []


def test_bayraksiz_kanca_olayi_yazilmaz(monkeypatch):
    result = _print(monkeypatch, ["-p", "selam", "--output-format", "stream-json", "--verbose"])
    assert result.exit_code == 0, result.output
    assert not [m for m in _messages(result.stdout) if "hook_id" in m]


def _print_with_followup(monkeypatch, args, items):
    from fusion_cli.core.events import FollowupsSuggested

    async def _fake(task, config, **kwargs):
        if items:
            for sink in kwargs["sinks"]:
                sink.handle(FollowupsSuggested(items))
        return SimpleNamespace(
            final_text="tamam",
            ok=True,
            stop_reason=None,
            model_calls_made=1,
            hit_step_limit=False,
            messages=[],
        )

    monkeypatch.setattr(print_run, "run_agent_task", _fake)
    return runner.invoke(app_module.app, args)


STREAM = ["-p", "selam", "--output-format", "stream-json", "--verbose"]


def test_prompt_suggestions_sonuctan_sonra_oneri_yazar(monkeypatch):
    items = (("Testleri çalıştır", "pytest -q ile testleri çalıştır"), ("Başka", "başka iş"))
    result = _print_with_followup(monkeypatch, [*STREAM, "--prompt-suggestions"], items)
    assert result.exit_code == 0, result.output
    assert "--prompt-suggestions" not in result.stderr
    messages = _messages(result.stdout)
    types = [m["type"] for m in messages]
    assert types[-2:] == ["result", "prompt_suggestion"]
    suggestion = messages[-1]
    assert suggestion["suggestion"] == "pytest -q ile testleri çalıştır"
    assert suggestion["session_id"] == messages[-2]["session_id"] and suggestion["uuid"]


def test_prompt_suggestions_kanit_yoksa_mesaj_yok(monkeypatch):
    result = _print_with_followup(monkeypatch, [*STREAM, "--prompt-suggestions"], ())
    assert result.exit_code == 0, result.output
    assert "prompt_suggestion" not in result.stdout


def test_bayraksiz_oneri_yazilmaz(monkeypatch):
    items = (("a", "b"),)
    result = _print_with_followup(monkeypatch, STREAM, items)
    assert "prompt_suggestion" not in result.stdout
