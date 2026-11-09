"""Production smoke kabulü: stdout yerine gerçek yerel protokol ve dosya kanıtı."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import os
import signal
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult, ListToolsResult, TextContent

MCP_TIMEOUT_SECONDS = 15
LARGE_SHA256 = "70840c06abe530b3cc3ab00c411a94d86705cdaf322e8c8ede5c5b1b611c6b39"


class _SmokeClient(Protocol):
    async def list_tools(self) -> ListToolsResult: ...
    async def call_tool(self, name: str, arguments: dict[str, object]) -> CallToolResult: ...


def _measured_client(session: ClientSession) -> tuple[_SmokeClient, Callable[[], bool]]:
    listed = False
    called = False

    class MeasuredClient:
        __slots__ = ()

        async def list_tools(self) -> ListToolsResult:
            nonlocal listed
            result = await session.list_tools()
            listed = any(tool.name == "ping" for tool in result.tools)
            return result

        async def call_tool(self, name: str, arguments: dict[str, object]) -> CallToolResult:
            nonlocal called
            result = await session.call_tool(name, arguments)
            called = (
                listed
                and name == "ping"
                and not result.isError
                and any(
                    isinstance(item, TextContent) and item.text == "pong" for item in result.content
                )
            )
            return result

    # Kabul kaydı adayın yazabildiği nesnenin alanı değildir; sahibi harness'tir.
    return MeasuredClient(), lambda: listed and called


_CANDIDATE_BRIDGE = r"""
import asyncio, importlib.util, json, sys
from mcp.types import ListToolsResult, CallToolResult
_protocol = sys.stdout
sys.stdout = sys.stderr
class Client:
    def request(self, payload):
        print(json.dumps(payload), file=_protocol, flush=True)
        line = sys.stdin.readline()
        if not line:
            raise RuntimeError('trusted MCP observer closed')
        return json.loads(line)
    async def list_tools(self):
        return ListToolsResult.model_validate(self.request({'op': 'list_tools'}))
    async def call_tool(self, name, arguments):
        payload = {'op': 'call_tool', 'name': name, 'arguments': arguments}
        return CallToolResult.model_validate(self.request(payload))
spec = importlib.util.spec_from_file_location('candidate_smoke', sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
asyncio.run(module.smoke(Client()))
"""


async def _bounded_stderr(stream: asyncio.StreamReader) -> bytes:
    tail = bytearray()
    while chunk := await stream.read(4096):
        tail.extend(chunk)
        del tail[:-8192]
    return bytes(tail)


async def _observe_candidate(root: Path, client: _SmokeClient) -> int:
    """Candidate exits cannot end the trusted observer or modify its witness state."""
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-I",
        "-c",
        _CANDIDATE_BRIDGE,
        str(root / "mcp_candidate.py"),
        cwd=root,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=os.name == "posix",
    )
    assert process.stdin is not None and process.stdout is not None and process.stderr is not None
    stderr_task = asyncio.create_task(_bounded_stderr(process.stderr))
    try:
        while line := await process.stdout.readline():
            request = json.loads(line)
            if request == {"op": "list_tools"}:
                result = (await client.list_tools()).model_dump(mode="json")
            elif (
                isinstance(request, dict)
                and set(request) == {"op", "name", "arguments"}
                and request["op"] == "call_tool"
                and request["name"] == "ping"
                and request["arguments"] == {}
            ):
                result = (await client.call_tool("ping", {})).model_dump(mode="json")
            else:
                raise ValueError("Candidate MCP bridge request is invalid.")
            process.stdin.write((json.dumps(result) + "\n").encode())
            await process.stdin.drain()
        return await process.wait()
    finally:
        if os.name == "posix":
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
        elif process.returncode is None:
            process.kill()
        await process.wait()
        diagnostic = await stderr_task
        if process.returncode != 0 and diagnostic:
            from fusion_cli.core.redaction import redact

            # Failure text is diagnostic only; parent-owned MCP witness and exit
            # status remain the acceptance authority. No candidate PASS parsing.
            print(redact(diagnostic.decode("utf-8", errors="replace")), file=sys.stderr)


async def check_mcp(root: Path) -> None:
    """Only parent-observed calls on the real, secret-free MCP session count."""
    server = Path(__file__).with_name("oauth_mcp_server.py")
    parameters = StdioServerParameters(command=sys.executable, args=[str(server), "--stdio"])
    async with (
        asyncio.timeout(MCP_TIMEOUT_SECONDS),
        stdio_client(parameters) as (reader, writer),
        ClientSession(reader, writer) as session,
    ):
        await session.initialize()
        client, completed = _measured_client(session)
        code = await _observe_candidate(root, client)
        if code != 0 or not completed():
            raise ValueError("Gerçek MCP list_tools ve ping çağrısı gözlenmedi.")


def check_large(root: Path) -> None:
    """Yalnız TARGET değişmeli; büyük dosyanın diğer tüm baytları korunmalı."""
    digest = hashlib.sha256((root / "large.py").read_bytes()).hexdigest()
    if digest != LARGE_SHA256:
        raise ValueError("Büyük dosya eksik, bozuk veya TARGET dışında değiştirilmiş.")


def check_assets(root: Path) -> None:
    from fusion_cli.core.assets import inspect_image_asset, validate_asset_manifest

    image = root / "assets/player.png"
    if not inspect_image_asset(image).valid or validate_asset_manifest(image, root):
        raise ValueError("Gerçek PNG ve lisans kaydı gerekli.")
    if (root / "project.godot").read_text() != '[application]\nconfig/name="Fusion Eval"\n':
        raise ValueError("Godot proje dosyası korunmalı.")


def check_replan(root: Path) -> None:
    if (
        json.loads((root / "config.json").read_text()).get("enabled") is not True
        or (root / "legacy").exists()
    ):
        raise ValueError("Gerçek hedef güncellenmeli; legacy oluşturulmamalı.")


def check_json(root: Path) -> None:
    if json.loads((root / "conversation-a.json").read_text()) != {
        "status": "done",
        "owner": "a",
    } or json.loads((root / "conversation-b.json").read_text()) != {
        "status": "pending",
        "owner": "b",
    }:
        raise ValueError("Yalnız conversation-a durum alanı değişmeli.")


def main() -> None:
    if sys.argv[1:] == ["mcp"]:
        asyncio.run(check_mcp(Path.cwd()))
        return
    checks = {
        "large": check_large,
        "assets": check_assets,
        "replan": check_replan,
        "json": check_json,
    }
    if len(sys.argv) != 2 or sys.argv[1] not in checks:
        raise SystemExit("Kabul türü mcp, large, assets, replan veya json olmalı.")
    checks[sys.argv[1]](Path.cwd())


if __name__ == "__main__":
    main()
