"""Actual verification reports must not corrupt explicitly structured replies."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from fusion_cli.core.events import ChangesDigested, VerificationPassed
from fusion_cli.core.evidence import ToolUse
from fusion_cli.core.tools import ToolContext
from fusion_cli.core.verification import VerificationResult
from fusion_cli.engines.agent import loop

from .test_plan_runner import _FakeDeps


def _verified_turn(tmp_path, text='{"ok":true,"file":"index.html"}'):
    context = ToolContext(tmp_path)
    context.changes.record(tmp_path / "index.html")
    uses = (
        ToolUse("write_file", mutating=True, arguments={"path": "index.html"}),
        ToolUse(
            "run_shell",
            mutating=False,
            arguments={"command": "pytest -q"},
            output="(çıkış kodu 0)\n2 passed",
        ),
    )
    return loop.AgentOutcome(final_text=text, messages=[], tool_uses=uses), _FakeDeps(context)


@pytest.mark.parametrize(
    "task",
    [
        'index.html oluştur. Son yanıtın yalnız geçerli JSON olsun: {"ok":true}.',
        "Dosyayı oluştur; yanıtı sadece JSON olarak ver.",
        "Return only valid JSON with keys ok and file.",
        "Only JSON.",
        "Respond only in JSON.",
        "config.json oluştur. Son yanıt yalnız JSON olsun.",
        "Yanıtı yalnız JSON olarak ver; açıklama istemiyorum.",
        "`config.json` oluştur. Son yanıt yalnız JSON olsun.",
        '"result.txt" oluştur; yanıtı sadece JSON olarak ver.',
    ],
)
def test_verified_mutation_preserves_requested_json_and_publishes_separate_evidence(tmp_path, task):
    outcome, deps = _verified_turn(tmp_path)
    original = outcome.final_text

    loop._apply_turn_report(
        outcome, deps, gate=VerificationResult(ok=True), task=task, change_lines=("index.html +1",)
    )

    assert outcome.ok
    assert outcome.final_text == original
    assert json.loads(outcome.final_text) == {"ok": True, "file": "index.html"}
    assert outcome.completion_report.is_verified is True
    assert any(isinstance(event, VerificationPassed) for event in deps.publisher.events)
    assert any(isinstance(event, ChangesDigested) for event in deps.publisher.events)


def test_blocked_report_replaces_model_success_with_truthful_json_error(tmp_path):
    outcome, deps = _verified_turn(tmp_path)

    loop._apply_turn_report(
        outcome,
        deps,
        gate=VerificationResult(ok=False, findings=("Gerçek test başarısız.",)),
        task="Dosyayı oluştur. Son yanıt yalnız JSON olsun.",
    )

    payload = json.loads(outcome.final_text)
    assert not outcome.ok
    assert "ok" not in payload
    assert payload["error"]["source"] == "fusion"
    assert payload["error"]["code"] == "verification_failed"
    assert payload["error"]["completion_evidence"]["engelliyor"] is True
    assert payload["error"]["completion_evidence"]["dogrulandi"] is False
    assert outcome.completion_report.blocks_success
    assert not any(isinstance(event, VerificationPassed) for event in deps.publisher.events)


@pytest.mark.parametrize(
    "text", ['```json\n{"ok":true}\n```', '{"ok":true}\nBitti.', '{"value":NaN}', "{broken"]
)
def test_invalid_requested_json_is_not_repaired_by_fabricating_requested_values(tmp_path, text):
    outcome, deps = _verified_turn(tmp_path, text)

    loop._apply_turn_report(
        outcome, deps, gate=VerificationResult(ok=True), task="Return only valid JSON."
    )

    payload = json.loads(outcome.final_text)
    assert not outcome.ok
    assert payload["error"]["code"] == "invalid_response_format"
    assert payload["error"]["completion_evidence"]["dogrulandi"] is True
    assert "file" not in payload


@pytest.mark.parametrize(
    "task",
    [
        'Şu örneği açıkla: "Return only JSON."',
        "`yalnız JSON yaz` örneğini açıkla.",
        "Sadece JSON yazma; açıklama da ekle.",
        "Do not return only JSON.",
        "Yalnız JSON olmasın.",
        "Yalnız JSON olsun istemiyorum.",
        "Sadece JSON olsun deme; açıklama yaz.",
        "Sadece JSON dosyasını değiştir.",
        "Only update result.json.",
        "config.json dosyasına sadece JSON yaz.",
        "config.json'a sadece JSON yaz.",
        "result.json içine yalnız JSON yaz.",
        "`config.json` içine sadece JSON yaz.",
        '"result.json" içine yalnız JSON yaz.',
        "'config.json' içine sadece JSON yaz.",
        "result.txt içine sadece JSON yaz.",
        "`result.txt` içine sadece JSON yaz.",
        "Yalnız JSON olsun. Hayır, JSON yazma; açıklama ver.",
        "Sadece JSON ayrıştırmasını açıkla.",
        'Yalnız "JSON" yaz.',
    ],
)
def test_quotes_negations_file_targets_and_explanations_do_not_change_report_format(tmp_path, task):
    outcome, deps = _verified_turn(tmp_path)
    original = outcome.final_text

    loop._apply_turn_report(outcome, deps, gate=VerificationResult(ok=True), task=task)

    assert outcome.final_text == outcome.completion_report.render_with_model_text(original)
    assert not any(isinstance(event, VerificationPassed) for event in deps.publisher.events)


@pytest.mark.parametrize("text", ["456", "Sonuç: 456 — gerçek ekran değeri."])
def test_result_only_request_does_not_gain_report_prose_or_extract_arbitrary_numbers(
    tmp_path, text
):
    outcome, deps = _verified_turn(tmp_path, text)

    loop._apply_turn_report(
        outcome, deps, gate=VerificationResult(ok=True), task="İşlemi yap; yalnız sonucu yaz."
    )

    assert outcome.final_text == text
    assert outcome.completion_report is not None


def test_ordinary_prose_keeps_existing_report_rendering(tmp_path):
    outcome, deps = _verified_turn(tmp_path, "Sayaç oluşturuldu.")

    loop._apply_turn_report(
        outcome,
        deps,
        gate=VerificationResult(ok=True),
        task="Sayaç oluştur ve ne yaptığını açıkla.",
    )

    assert outcome.final_text == outcome.completion_report.render_with_model_text(
        "Sayaç oluşturuldu."
    )


def test_strict_reply_retains_existing_thinking_removal(tmp_path):
    outcome, deps = _verified_turn(tmp_path, '<think>İç taslak.</think>{"ok":true}')

    loop._apply_turn_report(
        outcome, deps, gate=VerificationResult(ok=True), task="Return only valid JSON."
    )

    assert outcome.ok
    assert outcome.final_text == '{"ok":true}'


@pytest.mark.parametrize("disclosure", ["platform", "pull_request"])
async def test_final_runtime_boundary_keeps_late_disclosures_in_truthful_json_error(
    tmp_path, monkeypatch, disclosure
):
    from fusion_cli.engines.effects.pull_request import UNVERIFIED_CREATE

    from .fakes import RecordingSink, ScriptedProvider, model_result
    from .test_agent_loop import _deps, _kur

    text = '{"message":"PR oluşturuldu."}' if disclosure == "pull_request" else '{"ok":true}'
    deps = _deps(tmp_path, RecordingSink())
    if disclosure == "platform":
        deps.platform_names = ("TestPlatform",)
        deps.platform_check_verified = False
    _kur(monkeypatch, ScriptedProvider([model_result(text)]))

    outcome = await loop.run_agent("Return only valid JSON.", deps, verify=False)

    payload = json.loads(outcome.final_text)
    assert not outcome.ok
    assert payload["error"]["source"] == "fusion"
    details = payload["error"]["details"]
    if disclosure == "pull_request":
        assert UNVERIFIED_CREATE in details
    else:
        assert "TestPlatform" in details and "doğrulanamadı" in details
    assert outcome.completion_report is not None


@pytest.mark.parametrize("gate_ok", [False, True])
def test_reapplying_strict_format_preserves_existing_harness_error(tmp_path, gate_ok):
    from fusion_cli.engines.agent.response_format import format_reported_response

    outcome, deps = _verified_turn(tmp_path, "bad JSON")
    task = "Return only valid JSON."
    loop._apply_turn_report(outcome, deps, gate=VerificationResult(ok=gate_ok), task=task)
    original = outcome.final_text

    formatted = format_reported_response(
        task, original, outcome.completion_report, successful=outcome.ok
    )

    assert formatted == (original, False)


async def test_late_disclosure_in_ordinary_prose_keeps_existing_behavior(tmp_path, monkeypatch):
    from .fakes import RecordingSink, ScriptedProvider, model_result
    from .test_agent_loop import _deps, _kur

    deps = _deps(tmp_path, RecordingSink())
    deps.platform_names = ("TestPlatform",)
    _kur(monkeypatch, ScriptedProvider([model_result("İşte açıklama.")]))

    outcome = await loop.run_agent("Konuyu açıkla.", deps, verify=False)

    assert outcome.ok
    assert outcome.final_text.startswith("İşte açıklama.")
    assert "TestPlatform kısıtları resmi kaynaktan doğrulanamadı." in outcome.final_text


@pytest.mark.parametrize("marker", [None, "FUSION_TOOL_CALL"])
async def test_actual_mutation_reply_remains_json_on_app_protocol(tmp_path, monkeypatch, marker):
    from types import SimpleNamespace

    from fusion_cli.appserver.bridges import ProtocolSink
    from fusion_cli.core.types import StreamDone

    from .fakes import RecordingSink, ScriptedProvider, model_result, tool_call
    from .test_agent_loop import _deps, _kur

    class NonStreamingProvider(ScriptedProvider):
        async def stream(self, request):
            yield StreamDone(self._next(request))

    lines = []
    deps = _deps(tmp_path, RecordingSink())
    deps.publisher = SimpleNamespace(publish=ProtocolSink(lines.append).handle)
    expected = {"ok": True, "file": "a.py"}
    if marker is not None:
        expected["literal"] = marker
    provider = NonStreamingProvider(
        [
            model_result("Önce dosyayı oluşturuyorum."),
            model_result(tool_calls=(tool_call("write_file", path="a.py", content="x = 1\n"),)),
            model_result(json.dumps(expected)),
        ]
    )
    _kur(monkeypatch, provider)
    monkeypatch.setattr(
        "fusion_cli.engines.agent.narration.build_provider", lambda *_args, **_kwargs: provider
    )

    outcome = await loop.run_agent(
        "a.py dosyasını oluştur. Son yanıtın yalnız JSON olsun.", deps, verify=False
    )

    assert outcome.ok
    assert (tmp_path / "a.py").read_text() == "x = 1\n"
    events = [json.loads(line)["veri"] for line in lines]
    answers = [event for event in events if event.get("olay") == "TurnAnswered"]
    assert len(answers) == 1
    assert json.loads(answers[0]["text"]) == expected
    assert sum(event.get("olay") == "VerificationPassed" for event in events) == 1


@pytest.mark.parametrize(
    "literal", ["FUSION_TOOL_CALL", "FUSION_PAYLOAD", "<think>keep this</think>"]
)
@pytest.mark.parametrize("prefix", ["", "<think>Private preparation.</think>"])
async def test_requested_json_tool_marker_string_remains_data_on_app_protocol(
    tmp_path, monkeypatch, literal, prefix
):
    from types import SimpleNamespace

    from fusion_cli.appserver.bridges import ProtocolSink
    from fusion_cli.core.types import StreamDone

    from .fakes import RecordingSink, ScriptedProvider, model_result
    from .test_agent_loop import _deps, _kur

    class NonStreamingProvider(ScriptedProvider):
        async def stream(self, request):
            yield StreamDone(self._next(request))

    lines = []
    deps = _deps(tmp_path, RecordingSink())
    deps.publisher = SimpleNamespace(publish=ProtocolSink(lines.append).handle)
    original = json.dumps({"literal": literal})
    provider = NonStreamingProvider([model_result(prefix + original)])
    _kur(monkeypatch, provider)

    outcome = await loop.run_agent("Return only valid JSON.", deps, verify=False)

    assert outcome.ok
    assert outcome.tool_calls_made == 0
    assert provider.calls == 1
    events = [json.loads(line)["veri"] for line in lines]
    answers = [event for event in events if event.get("olay") == "TurnAnswered"]
    assert len(answers) == 1
    assert json.loads(answers[0]["text"]) == {"literal": literal}


async def test_normal_prose_still_filters_emulated_tool_markers_on_app_protocol(
    tmp_path, monkeypatch
):
    from types import SimpleNamespace

    from fusion_cli.appserver.bridges import ProtocolSink
    from fusion_cli.core.types import StreamDone

    from .fakes import RecordingSink, ScriptedProvider, model_result
    from .test_agent_loop import _deps, _kur

    class NonStreamingProvider(ScriptedProvider):
        async def stream(self, request):
            yield StreamDone(self._next(request))

    lines = []
    deps = _deps(tmp_path, RecordingSink())
    deps.publisher = SimpleNamespace(publish=ProtocolSink(lines.append).handle)
    provider = NonStreamingProvider(
        [model_result('Açıklama.\nFUSION_TOOL_CALL\n{"name":"write_file"}\nFUSION_TOOL_CALL_END')]
    )
    _kur(monkeypatch, provider)

    outcome = await loop.run_agent("Konuyu açıkla.", deps, verify=False)

    assert outcome.ok and outcome.tool_calls_made == 0
    events = [json.loads(line)["veri"] for line in lines]
    answers = [event for event in events if event.get("olay") == "TurnAnswered"]
    assert len(answers) == 1
    assert answers[0]["text"] == "Açıklama."


async def test_valid_json_marked_truncated_still_gets_integrity_repair(tmp_path, monkeypatch):
    from fusion_cli.core.types import StreamDone

    from .fakes import RecordingSink, ScriptedProvider, model_result
    from .test_agent_loop import _deps, _kur

    class NonStreamingProvider(ScriptedProvider):
        async def stream(self, request):
            yield StreamDone(self._next(request))

    provider = NonStreamingProvider(
        [
            replace(model_result('{"literal":"FUSION_TOOL_CALL"}'), truncated=True),
            model_result('{"literal":"tamam"}'),
        ]
    )
    deps = _deps(tmp_path, RecordingSink())
    _kur(monkeypatch, provider)

    outcome = await loop.run_agent("Return only valid JSON.", deps, verify=False)

    assert outcome.ok
    assert provider.calls == 2
    assert json.loads(outcome.final_text) == {"literal": "tamam"}


async def test_valid_json_without_requested_mutation_does_not_bypass_action_evidence(
    tmp_path, monkeypatch
):
    from fusion_cli.core.types import StreamDone

    from .fakes import RecordingSink, ScriptedProvider, model_result
    from .test_agent_loop import _deps, _kur

    class NonStreamingProvider(ScriptedProvider):
        async def stream(self, request):
            yield StreamDone(self._next(request))

    provider = NonStreamingProvider(
        [model_result("Dosyayı oluşturuyorum.")]
        + [model_result('{"ok":true,"literal":"FUSION_TOOL_CALL"}')] * 5
    )
    deps = _deps(tmp_path, RecordingSink())
    _kur(monkeypatch, provider)
    monkeypatch.setattr(
        "fusion_cli.engines.agent.narration.build_provider", lambda *_args, **_kwargs: provider
    )

    outcome = await loop.run_agent(
        "a.py dosyasını oluştur. Son yanıt yalnız JSON olsun.", deps, verify=False
    )

    assert not outcome.ok
    assert outcome.tool_calls_made == 0
    assert not (tmp_path / "a.py").exists()
    assert "error" in json.loads(outcome.final_text)


@pytest.mark.parametrize("gate", ["pending_todo", "local_mutation"])
def test_requested_json_keeps_pending_todo_and_local_mutation_continuation_gates(tmp_path, gate):
    from fusion_cli.core.tools import TodoItem, TodoStatus
    from fusion_cli.engines.agent import reflexion
    from fusion_cli.engines.agent.execution_policy import ExecutionPolicy

    from .fakes import RecordingSink
    from .test_agent_loop import _deps

    deps = _deps(tmp_path, RecordingSink())
    deps.budget = loop._new_budget(deps.config)
    state = loop._State(require_local_mutation=gate == "local_mutation")
    if gate == "pending_todo":
        deps.tool_context.todos.replace((TodoItem("Gerçek işi bitir", TodoStatus.PENDING),))

    note = loop._auto_continue_note(
        '{"literal":"FUSION_TOOL_CALL"}',
        deps,
        state,
        plan_mode=False,
        execution=ExecutionPolicy(is_web=False),
        truncated=False,
        task="Return only valid JSON.",
    )

    expected = (
        reflexion.AUTO_CONTINUE_NOTE
        if gate == "pending_todo"
        else reflexion.verification_action_required_note().content
    )
    assert note is not None and note.content == expected
