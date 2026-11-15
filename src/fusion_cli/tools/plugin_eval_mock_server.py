"""`plugin eval` MCP sahte sunucusu: `python -m fusion_cli.tools.plugin_eval_mock_server <klasör>`.

Satır başına JSON-RPC (MCP stdio): `initialize`, `tools/list`, `tools/call`, `ping`. Araçlar
`mocks/<sunucu>/<araç>.md`'den (bkz. `plugin_eval_mocks`); `_server.md` `type: agent` ise her
çağrı sahte dünyanın tarifi ve önceki çağrılarla bir `fusion agent` alt sürecine sorulur; yanıt
`ABORT: <neden>` ise koşu durdurulur. `expect:` ihlali de koşuyu durdurur. Her çağrı
`FUSION_EVAL_MOCK_LOG` dosyasına bir satır olarak kaydedilir (record).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import TextIO

from .plugin_eval_mocks import (
    LOG_ENV,
    MockServer,
    MockTool,
    expectation_errors,
    load_server,
    render,
)

PROTOCOL = "2025-06-18"
_ANY_OBJECT: dict[str, object] = {"type": "object", "additionalProperties": True}


def _tool_list(server: MockServer) -> list[dict[str, object]]:
    if server.agent is not None:
        names = server.agent.get("tools")
        listed = [str(n) for n in names] if isinstance(names, list) else []
        known = {t.name: t for t in server.tools}
        return [_describe(known.get(n) or MockTool(n, "")) for n in listed]
    return [_describe(tool) for tool in server.tools]


def _describe(tool: MockTool) -> dict[str, object]:
    return {
        "name": tool.name,
        "description": tool.description or f"Mock of {tool.name}",
        "inputSchema": dict(tool.schema) or _ANY_OBJECT,
    }


def _log(row: Mapping[str, object]) -> None:
    path = os.environ.get(LOG_ENV, "")
    if not path:
        return
    with Path(path).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _agent_reply(server: MockServer, name: str, arguments: Mapping[str, object]) -> str:
    history = os.environ.get(LOG_ENV, "")
    calls = Path(history).read_text("utf-8") if history and Path(history).is_file() else ""
    abort_when = str((server.agent or {}).get("abort_when") or "")
    prompt = (
        "You simulate an MCP server for an eval. Reply ONLY with the tool result.\n"
        f"If any of these conditions holds, reply 'ABORT: <reason>':\n{abort_when}\n\n"
        f"<world>\n{server.world}\n</world>\n<previous_calls>\n{calls}\n</previous_calls>\n"
        f"<call tool={json.dumps(name)}>\n"
        f"{json.dumps(dict(arguments), ensure_ascii=False)}\n</call>"
    )
    from .plugin_eval_run import TEXT_ONLY_ARGS, fusion_command

    # İstemde model üretimi çağrı argümanları ve `world` var: kapılı araç yok, tek tur (#380).
    done = subprocess.run(
        [
            *fusion_command(),
            *("agent", prompt, "--output-format", "json", "--no-memory"),
            *TEXT_ONLY_ARGS,
        ],
        capture_output=True,
        text=True,
        timeout=300,
        stdin=subprocess.DEVNULL,
        check=False,
    )
    last = done.stdout.strip().splitlines()[-1] if done.stdout.strip() else ""
    try:
        return str(json.loads(last).get("sonuc") or "")
    except (ValueError, AttributeError):
        return last


def call_tool(server: MockServer, name: str, arguments: Mapping[str, object]) -> dict[str, object]:
    """Tek bir `tools/call` sonucu (`content`, `isError`) ve kayıt satırı."""
    tool = next((t for t in server.tools if t.name == name), None)
    abort: tuple[str, ...] = ()
    if server.agent is not None:
        text = _agent_reply(server, name, arguments)
        if text.strip().upper().startswith("ABORT:"):
            abort = (text.strip()[6:].strip(),)
        error = bool(abort)
    elif tool is None:
        text, error = f"Unknown mocked tool: {name}", True
    else:
        abort = expectation_errors(tool, arguments)
        text = "; ".join(abort) if abort else render(tool.result, arguments)
        error = tool.error or bool(abort)
    _log({"server": server.name, "tool": name, "input": dict(arguments), "abort": list(abort)})
    return {"content": [{"type": "text", "text": text}], "isError": error}


def handle(server: MockServer, message: Mapping[str, object]) -> dict[str, object] | None:
    method = message.get("method")
    ident = message.get("id")
    if ident is None:
        return None  # bildirim (notifications/initialized …)
    params = message.get("params")
    params = params if isinstance(params, dict) else {}
    if method == "initialize":
        result: dict[str, object] = {
            "protocolVersion": str(params.get("protocolVersion") or PROTOCOL),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": f"mock-{server.name}", "version": "1"},
        }
    elif method == "tools/list":
        result = {"tools": _tool_list(server)}
    elif method == "tools/call":
        arguments = params.get("arguments")
        result = call_tool(
            server, str(params.get("name")), arguments if isinstance(arguments, dict) else {}
        )
    elif method == "ping":
        result = {}
    else:
        return {"jsonrpc": "2.0", "id": ident, "error": {"code": -32601, "message": "not found"}}
    return {"jsonrpc": "2.0", "id": ident, "result": result}


def serve(server: MockServer, stdin: TextIO, stdout: TextIO) -> None:
    for line in stdin:
        try:
            message = json.loads(line)
        except ValueError:
            continue
        reply = handle(server, message) if isinstance(message, dict) else None
        if reply is not None:
            stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
            stdout.flush()


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    serve(load_server(Path(args[0])), sys.stdin, sys.stdout)


if __name__ == "__main__":
    main()
