"""stream-json alt ajan mesajları ve `--forward-subagent-text` (#289)."""

from __future__ import annotations

import io
import json

from fusion_cli.cli.sdk_messages import SdkStream
from fusion_cli.core.events import (
    Channel,
    SubAgentFinished,
    SubAgentStarted,
    TokenReceived,
    ToolExecuted,
    ToolOutcome,
    ToolStarted,
)


def _events(nested: bool = False):
    events = [
        ToolStarted("spawn_agent", {"task": "ara"}, call_id="toolu_A"),
        SubAgentStarted(task="dosyaları say", sub_id="s1"),
        TokenReceived(Channel.MAIN, "sayıyorum", provisional=True, agent_id="s1"),
        ToolStarted("run_shell", {"command": "ls"}, call_id="c1", agent_id="s1"),
        ToolExecuted("run_shell", {"command": "ls"}, ToolOutcome.OK, "a b", call_id="c1", agent_id="s1"),
    ]
    if nested:
        events += [
            ToolStarted("spawn_agent", {}, call_id="toolu_B", agent_id="s1"),
            SubAgentStarted(task="iç iş", sub_id="s2", depth=2, agent_id="s1"),
            ToolStarted("read_file", {"path": "x"}, call_id="c2", agent_id="s2"),
        ]
    events.append(SubAgentFinished(tool_calls=1, sub_id="s1", summary="2 dosya"))
    return events


def _run(events, **kwargs):
    out = io.StringIO()
    stream = SdkStream("s", lambda: "m", stdout=out, **kwargs)
    for event in events:
        stream.handle(event)
    return [json.loads(line) for line in out.getvalue().splitlines()]


def test_varsayilan_alt_ajan_arac_bloklari_parent_tool_use_id_ile():
    lines = _run(_events())
    main, *subs = lines
    assert main["parent_tool_use_id"] is None
    assert main["message"]["content"][0]["name"] == "Agent"
    assert all(m["parent_tool_use_id"] == "toolu_A" for m in subs)
    assert subs[0]["type"] == "user"
    assert subs[0]["message"]["content"] == [{"type": "text", "text": "dosyaları say"}]
    assert subs[1]["message"]["content"] == [
        {"type": "tool_use", "id": "c1", "name": "Bash", "input": {"command": "ls"}}
    ]
    assert subs[2]["message"]["content"][0]["tool_use_id"] == "c1"
    assert len(subs) == 3  # metin blokları varsayılanda iletilmez


def test_forward_subagent_text_metni_ve_ic_ice_ajanlari_ileter():
    lines = _run(_events(nested=True), forward_subagent_text=True)
    sub_tool = next(
        m for m in lines if m["type"] == "assistant" and m["parent_tool_use_id"] == "toolu_A"
    )
    assert sub_tool["message"]["content"][0] == {"type": "text", "text": "sayıyorum"}
    nested = [m for m in lines if m["parent_tool_use_id"] == "toolu_B"]
    assert [m["type"] for m in nested] == ["user", "assistant"]
    assert lines[-1]["message"]["content"] == [{"type": "text", "text": "2 dosya"}]


def test_varsayilanda_ic_ice_ajan_iletilmez(monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_FORWARD_SUBAGENT_TEXT", raising=False)
    lines = _run(_events(nested=True))
    assert not [m for m in lines if m["parent_tool_use_id"] == "toolu_B"]


def test_ortam_degiskeni_metin_iletimini_acar(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_FORWARD_SUBAGENT_TEXT", "1")
    lines = _run(_events())
    texts = [
        block
        for m in lines
        if m["parent_tool_use_id"] == "toolu_A" and m["type"] == "assistant"
        for block in m["message"]["content"]
        if block["type"] == "text"
    ]
    assert texts[0]["text"] == "sayıyorum"
