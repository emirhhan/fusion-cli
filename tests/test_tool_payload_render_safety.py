from __future__ import annotations

import json

from fusion_cli.core.model_capability import ToolSupport
from fusion_cli.core.tool_emulation import PAYLOAD_OPEN, parse_tool_calls, render_tool_instructions
from fusion_cli.core.types import CompletionRequest, Message, StreamDone, TextChunk
from fusion_cli.engines.agent.reflexion import tool_contract_repair_note
from fusion_cli.providers.web_session import WebProviderAdapter, WebSessionCredential
from fusion_cli.tools import build_registry


def _payload_call(content: str, *, close_fence: bool = True) -> str:
    call = {
        "name": "write_file",
        "arguments": {
            "path": "example.py",
            "content": {"$ref": "source-1"},
        },
    }
    closing = "\n```" if close_fence else ""
    # Doğru davranan bir model gibi: `lines` geri okunacak GÖVDEDEN hesaplanır.
    satir_sayisi = len(content.splitlines())
    return (
        f'<tool_payload id="source-1" lines="{satir_sayisi}">\n'
        "```python\n"
        f"{content}"
        f"{closing}\n"
        "</tool_payload>\n"
        f"<tool_call>{json.dumps(call, ensure_ascii=False)}</tool_call>"
    )


def _request() -> CompletionRequest:
    return CompletionRequest(
        messages=(Message("user", "test"),),
        temperature=0.0,
        max_tokens=256,
        timeout_s=5.0,
        tools=(
            {
                "type": "function",
                "function": {
                    "name": "write_file",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "content": {"type": "string"},
                        },
                        "required": ["path", "content"],
                    },
                },
            },
        ),
    )


def _transport(reply: str):
    async def transport(*_args):
        return reply

    return transport


def _adapter(reply: str) -> WebProviderAdapter:
    return WebProviderAdapter(
        model="gemini_web/main/auto",
        credential=WebSessionCredential(),
        transport=_transport(reply),
        tool_support=ToolSupport.EMULATED,
    )


def test_fenced_payload_preserves_python_indentation_and_dunders() -> None:
    source = (
        "def normalize(text: str) -> str:\n"
        "    if not text:\n"
        '        return ""\n'
        "    return text.strip()\n\n"
        'if __name__ == "__main__":\n'
        '    print(normalize("  ok  "))'
    )
    parsed = parse_tool_calls(_payload_call(source))

    assert not parsed.errors
    assert len(parsed.calls) == 1
    arguments = json.loads(parsed.calls[0].arguments)
    assert arguments["content"] == source
    assert "    if not text:" in arguments["content"]
    assert "__name__" in arguments["content"]
    assert "__main__" in arguments["content"]


def test_browser_rendered_payload_without_fence_remains_supported() -> None:
    source = "class Example:\n    def method(self):\n        return 1"
    call = {
        "name": "write_file",
        "arguments": {
            "path": "example.py",
            "content": {"$ref": "source-1"},
        },
    }
    raw = (
        f'<tool_payload id="source-1" lines="{len(source.splitlines())}">\n'
        f"{source}\n"
        "</tool_payload>\n"
        f"<tool_call>{json.dumps(call)}</tool_call>"
    )
    parsed = parse_tool_calls(raw)

    assert not parsed.errors
    arguments = json.loads(parsed.calls[0].arguments)
    assert arguments["content"] == source


def test_unclosed_payload_code_fence_is_rejected() -> None:
    parsed = parse_tool_calls(_payload_call('print("broken")', close_fence=False))

    assert not parsed.calls
    assert any("code fence" in error for error in parsed.errors)


def test_instructions_require_fenced_payload_for_code() -> None:
    instructions = render_tool_instructions(build_registry().schemas())

    assert f'{PAYLOAD_OPEN} id="file-1"' in instructions
    assert "```python" in instructions
    assert "kod bloğu" in instructions
    assert "JSON content stringinin içine koyma" in instructions


def test_repair_note_uses_fenced_payload_example() -> None:
    note = tool_contract_repair_note("invalid JSON")

    assert f'{PAYLOAD_OPEN} id="file-1"' in note.content
    assert "```python" in note.content
    assert "kod bloğu" in note.content


async def test_valid_emulated_tool_turn_streams_preface() -> None:
    """Geçerli bir araç turunda öncü metin AKAR.

    Bu test eskiden tersini bekliyordu: model çağrının yanında "işlem tamamlandı"
    yazıp henüz çalışmamış bir işi bitmiş gösterebiliyordu. Bastırma o iddiayı
    engelliyordu ama bedeli, araç kullanan HER turun sessizleşmesiydi — kullanıcı
    turun neden başladığını hiç görmüyordu.

    Takas bilinçli olarak öncü metin lehine çevrildi: iddia ekranda tek başına
    kalmaz, hemen ardından aracın gerçek sonucu ve turun nihai cevabı basılır.
    Ayrıştırma hatası olan turda bastırma DEVAM eder (aşağıdaki test).
    """
    call = json.dumps(
        {
            "name": "write_file",
            "arguments": {"path": "x.txt", "content": "hello"},
        }
    )
    reply = f"Dosyayı yazıyorum.\n<tool_call>{call}</tool_call>"
    items = [item async for item in _adapter(reply).stream(_request())]

    chunks = [item for item in items if isinstance(item, TextChunk)]
    assert [chunk.text for chunk in chunks] == ["Dosyayı yazıyorum."]
    assert isinstance(items[-1], StreamDone)


async def test_parse_error_does_not_stream_false_success_text() -> None:
    reply = 'FUSION_CODE_ACCEPTANCE_OK\n<tool_call>{"name":"write_file"}</tool_call>'
    items = [item async for item in _adapter(reply).stream(_request())]

    assert not any(isinstance(item, TextChunk) for item in items)
    assert len(items) == 1
    assert isinstance(items[0], StreamDone)


async def test_emulated_final_plain_text_still_streams() -> None:
    items = [item async for item in _adapter("Gerçek nihai cevap").stream(_request())]

    chunks = [item for item in items if isinstance(item, TextChunk)]
    assert len(chunks) == 1
    assert chunks[0].text == "Gerçek nihai cevap"
    assert isinstance(items[-1], StreamDone)
