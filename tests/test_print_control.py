"""`--input-format stream-json` denetim kanalı (#280): kesme, onay, kip/model istekleri."""

from __future__ import annotations

import asyncio
import io
import json
import queue
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from fusion_cli.cli import app as app_module
from fusion_cli.cli import print_run, print_stream
from fusion_cli.cli.print_control import ControlChannel, StdioPrompter
from fusion_cli.engines.agent.approval import ApprovalAnswer, ApprovalMode

runner = CliRunner()
_STREAM = ["-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose"]


class _Feed:
    """Satırları testin verdiği sırayla bekleyerek veren sahte stdin."""

    def __init__(self) -> None:
        self.lines: queue.Queue[str | None] = queue.Queue()

    def put(self, data: dict[str, object] | None) -> None:
        self.lines.put(None if data is None else json.dumps(data) + "\n")

    def __iter__(self):
        while True:
            line = self.lines.get()
            if line is None:
                return
            yield line


def _channel() -> tuple[ControlChannel, _Feed, list[dict]]:
    feed, out = _Feed(), []
    return ControlChannel(feed, out.append).start(), feed, out  # type: ignore[arg-type]


async def _until(predicate, limit_s: float = 2.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + limit_s
    while not predicate():
        if loop.time() > deadline:
            raise AssertionError("koşul gerçekleşmedi")
        await asyncio.sleep(0.01)


def _user(text: str) -> dict[str, object]:
    return {"type": "user", "message": {"role": "user", "content": text}}


def _control(subtype: str, rid: str = "r1", **fields: object) -> dict[str, object]:
    return {"type": "control_request", "request_id": rid, "request": {"subtype": subtype, **fields}}


def test_interrupt_suren_turu_keser_ve_cevaplar():
    channel, feed, out = _channel()

    async def scenario() -> None:
        started = asyncio.Event()

        async def turn() -> str:
            started.set()
            await asyncio.sleep(30)
            return "bitmedi"

        task = asyncio.ensure_future(channel.guard(turn()))
        await started.wait()
        feed.put(_control("interrupt", "k1"))
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
    feed.put(None)
    assert channel.interrupted
    assert out[0]["type"] == "control_response"
    assert out[0]["response"] == {"subtype": "success", "request_id": "k1", "response": {}}


def test_bilinmeyen_denetim_istegi_hata_doner():
    channel, feed, out = _channel()
    feed.put(_control("rewind_files", "x9"))
    feed.put(None)
    list(channel.users())
    assert out[0]["response"]["subtype"] == "error"
    assert out[0]["response"]["request_id"] == "x9"
    assert "rewind_files" in out[0]["response"]["error"]


@pytest.mark.parametrize(
    ("behavior", "expected"),
    [("allow", ApprovalAnswer.ONCE), ("deny", ApprovalAnswer.UNAVAILABLE)],
)
def test_stdio_onayi_can_use_tool_istegiyle_sorulur(behavior, expected):
    channel, feed, out = _channel()
    prompter = StdioPrompter(channel)
    request = SimpleNamespace(tool=SimpleNamespace(name="run_shell"), args={"command": "ls"})
    request.call_id = "toolu_1"

    async def scenario() -> object:
        pending = asyncio.ensure_future(prompter.confirm(request))  # type: ignore[arg-type]
        await _until(lambda: bool(out))
        asked = out[0]
        assert asked["type"] == "control_request"
        assert asked["request"]["subtype"] == "can_use_tool"
        assert asked["request"]["tool_name"] == "Bash"
        assert asked["request"]["input"] == {"command": "ls"}
        assert asked["request"]["tool_use_id"] == "toolu_1"
        feed.put(
            {
                "type": "control_response",
                "response": {
                    "subtype": "success",
                    "request_id": asked["request_id"],
                    "response": {"behavior": behavior, "message": "hayır"},
                },
            }
        )
        return await pending

    assert asyncio.run(scenario()) is expected
    feed.put(None)


def test_stdin_kapaninca_bekleyen_onay_reddedilir():
    channel, feed, out = _channel()
    prompter = StdioPrompter(channel)
    request = SimpleNamespace(tool=SimpleNamespace(name="write_file"), args={})

    async def scenario() -> object:
        pending = asyncio.ensure_future(prompter.confirm(request))  # type: ignore[arg-type]
        await _until(lambda: bool(out))
        feed.put(None)
        return await pending

    assert asyncio.run(scenario()) is ApprovalAnswer.UNAVAILABLE


def _invoke(monkeypatch, lines, *, delay: float = 0.0):
    calls: list[dict] = []

    async def _fake(task, config, **kwargs):
        calls.append({"task": task, "config": config, **kwargs})
        await asyncio.sleep(delay)
        return SimpleNamespace(
            final_text="tamam",
            ok=True,
            stop_reason=None,
            model_calls_made=1,
            hit_step_limit=False,
            messages=[],
        )

    monkeypatch.setattr(print_run, "run_agent_task", _fake)
    stdin = "".join(json.dumps(line) + "\n" for line in lines)
    result = runner.invoke(app_module.app, _STREAM, input=stdin)
    out = [json.loads(x) for x in result.stdout.splitlines() if x.strip()]
    return calls, result, out


def test_initialize_ve_set_permission_mode_sonraki_tura_uygulanir(monkeypatch):
    calls, result, out = _invoke(
        monkeypatch,
        [
            _control("initialize", "i1"),
            _control("set_permission_mode", "m1", mode="acceptEdits"),
            _user("bir"),
        ],
    )
    assert result.exit_code == 0, result.output
    responses = {
        m["response"]["request_id"]: m["response"] for m in out if m["type"] == "control_response"
    }
    assert responses["i1"]["subtype"] == "success"
    assert responses["m1"]["subtype"] == "success"
    assert calls[0]["mode"] is ApprovalMode.ACCEPT_EDITS


def test_gecersiz_kip_istegi_hata_doner(monkeypatch):
    _calls, _result, out = _invoke(
        monkeypatch, [_control("set_permission_mode", "m2", mode="yokboyle"), _user("bir")]
    )
    response = next(m["response"] for m in out if m["type"] == "control_response")
    assert response["subtype"] == "error" and response["request_id"] == "m2"


def test_kesilen_tur_sonucu_hata_olarak_yazilir(monkeypatch):
    class _Interrupting(ControlChannel):
        async def guard(self, coro):
            task = asyncio.ensure_future(coro)
            await asyncio.sleep(0)
            self.interrupted = True
            task.cancel()
            return await task

    monkeypatch.setattr(print_stream, "ControlChannel", _Interrupting)
    _calls, result, out = _invoke(monkeypatch, [_user("bir")], delay=5)
    final = out[-1]
    assert final["type"] == "result" and final["is_error"] is True
    assert final["subtype"] == "error_during_execution"
    assert "[Request interrupted by user]" in final["errors"]
    assert result.exit_code == 1


def test_stdio_onay_araci_mcp_aracina_gitmez(monkeypatch):
    from fusion_cli.cli.print_runtime import PrintPrompter

    run = SimpleNamespace(
        plan=SimpleNamespace(request=SimpleNamespace(permission_prompt_tool="stdio")),
        control=None,
        root=None,
    )
    assert type(print_run._prompter(run)) is PrintPrompter  # type: ignore[arg-type]
    run.control = ControlChannel(io.StringIO(""), lambda _m: None)
    assert isinstance(print_run._prompter(run), StdioPrompter)  # type: ignore[arg-type]
