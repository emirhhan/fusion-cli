"""JSON onarımı yalnız dizelerin dışındaki fazla virgülleri kaldırır."""

from __future__ import annotations

import json

import pytest

from fusion_cli.core.tool_emulation import CALL_CLOSE, CALL_OPEN, parse_tool_calls


@pytest.mark.parametrize(
    "content",
    [
        "literal,}",
        "literal, \t]",
        'kaçışlı tırnak: " ve içerik,}',
        'ters eğik çizgi ve tırnak: \\" içerik,]',
        "iç virgül, kapanış,} ve son\\",
    ],
)
def test_fazla_virgul_onarimi_dize_icerigini_birebir_korur(content):
    body = json.dumps({"name": "write_file", "arguments": {"content": content}})
    malformed = body[:-1] + ",}"

    parsed = parse_tool_calls(f"{CALL_OPEN}\n{malformed}\n{CALL_CLOSE}")

    assert not parsed.errors
    assert len(parsed.calls) == 1
    assert json.loads(parsed.calls[0].arguments)["content"].encode() == content.encode()


def test_ic_ice_nesne_ve_dizinin_fazla_virgulleri_onarilir():
    body = '{"name":"test","arguments":{"items":[{"text":"a,b",},],},}'

    parsed = parse_tool_calls(f"{CALL_OPEN}\n{body}\n{CALL_CLOSE}")

    assert not parsed.errors
    assert json.loads(parsed.calls[0].arguments) == {"items": [{"text": "a,b"}]}


def test_sarmal_ve_json_metin_arguman_onarimi_icerigi_korur():
    arguments = '{"content":"literal,}",}'
    body = json.dumps({"tool": "write_file", "args": arguments})

    parsed = parse_tool_calls(f"{CALL_OPEN}\n**{body}**\n{CALL_CLOSE}")

    assert not parsed.errors
    assert parsed.calls[0].name == "write_file"
    assert json.loads(parsed.calls[0].arguments) == {"content": "literal,}"}


@pytest.mark.parametrize(
    "body",
    [
        '{"name":"test","arguments":{"text":"kapanmamış,}}',
        '{"name":"test","arguments":{"value":,}}',
        '{"name":"test","arguments":{"value":1,,}}',
        '{"name":"test","arguments":{"value":[,]}}',
        '{"name":"test","arguments":{,}}',
    ],
)
def test_belirsiz_json_onarimla_uydurulmaz(body):
    parsed = parse_tool_calls(f"{CALL_OPEN}\n{body}\n{CALL_CLOSE}")

    assert not parsed.calls
    assert parsed.errors
