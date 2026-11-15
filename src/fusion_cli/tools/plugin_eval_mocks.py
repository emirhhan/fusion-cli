"""`plugin eval --mocks` MCP sahte sunucuları (Claude Code 2.1.287 `claude plugin eval`, #380).

Biçim (`<eval klasörü>/mocks/<sunucu>/`): `<sunucu>` eklentinin `.mcp.json` anahtarı, her
`<araç>.md` bir sahte araçtır: gövde hazır sonuçtur (`{{input.<alan>}}` çağrının alanını yansıtır),
ön maddede `description`, `expect:` (bu argümanlar tam bu değerde gelmeli; uymazsa koşu durur,
gerileme sinyalidir) ve `error: true` (aracın hata döndürmesi). Çok adımlı akışlar için tek
`_server.md` (`type: agent`, `tools: [...]`, `abort_when: |`, gövde sahte dünyanın tarifi) her
çağrıyı bir yargıç alt süreciyle yanıtlar. `_tools.json` (`tools/list` çıktısı) gerçek açıklama
ve şemaları verir. Gövdesi hâlâ `TODO: replace with …` olan taslak varsa eval başlamaz.

`record` (varsayılan): sahtesi olan eklenti sunucusu yerine sahte başlar, sahtesi olmayan eklenti
sunucusu `--allow-real-servers` yoksa başlamaz (araçları o koşuda yoktur). `off`: sahte yok, gerçek
sunucular başlar. Sahte araç çağrıları koşu başına günlüğe (`FUSION_EVAL_MOCK_LOG`) yazılır.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ..core.plugins import PluginError

STUB = "TODO: replace with the canned result this tool should return"
LOG_ENV = "FUSION_EVAL_MOCK_LOG"
MOCK_MODES = ("record", "off")
_SEGMENT = re.compile(r"^[A-Za-z0-9_-]+$")
ERR_MODE = "--mocks must be record | off"
ERR_SEP = '{path}: "__" is the tool-name separator and cannot appear in a mock directory name'
ERR_SEGMENT = (
    '{path}: name the directory after the server segment of the tool name (letters, digits, "_" '
    'and "-" only), e.g. mocks/<server>/'
)
ERR_TOOL_SEP = '{path}: "__" is the tool-name separator and cannot appear in a mocked tool name'
ERR_STUB = "{path}: mock is still a stub — replace the TODO line with the canned result"
ERR_UNKNOWN = "mocks/{server}/: no server the plugins declare, so this mock is never used"
WARN_UNMOCKED = (
    'MCP server "{server}" has no mock and its tools are unavailable this run; add '
    "mocks/{server}/ to mock it, or pass --allow-real-servers to run the plugin's real server "
    "(as you, outside the sandbox)"
)


@dataclass(frozen=True, slots=True)
class MockTool:
    name: str
    result: str
    description: str = ""
    expect: Mapping[str, object] = field(default_factory=dict)
    error: bool = False
    schema: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MockServer:
    name: str
    folder: Path
    tools: tuple[MockTool, ...] = ()
    agent: Mapping[str, object] | None = None
    world: str = ""


def split_front(text: str) -> tuple[dict[str, object], str]:
    if not text.startswith("---"):
        return {}, text.strip()
    head, sep, body = text[3:].partition("\n---")
    if not sep:
        return {}, text.strip()
    loaded = yaml.safe_load(head) or {}
    return (dict(loaded) if isinstance(loaded, dict) else {}), body.lstrip("\n").strip()


def _schemas(folder: Path) -> dict[str, dict[str, object]]:
    path = folder / "_tools.json"
    try:
        raw = json.loads(path.read_text("utf-8")) if path.is_file() else []
    except (OSError, ValueError):
        return {}
    tools = raw.get("tools") if isinstance(raw, dict) else raw
    return (
        {
            str(t["name"]): dict(t)
            for t in tools
            if isinstance(t, dict) and isinstance(t.get("name"), str)
        }
        if isinstance(tools, list)
        else {}
    )


def _mapping(value: object) -> dict[str, object]:
    return {str(k): v for k, v in value.items()} if isinstance(value, dict) else {}


def load_server(folder: Path) -> MockServer:
    """Bir `mocks/<sunucu>/` klasörü; biçim hatası `PluginError`."""
    name = folder.name
    if "__" in name:
        raise PluginError(ERR_SEP.format(path=f"mocks/{name}/"))
    if not _SEGMENT.match(name):
        raise PluginError(ERR_SEGMENT.format(path=f"mocks/{name}/"))
    schemas = _schemas(folder)
    tools: list[MockTool] = []
    agent: dict[str, object] | None = None
    world = ""
    for path in sorted(folder.glob("*.md")):
        head, body = split_front(path.read_text("utf-8"))
        if STUB in body:
            raise PluginError(ERR_STUB.format(path=f"mocks/{name}/{path.name}"))
        if path.stem == "_server":
            agent, world = head, body
            continue
        if "__" in path.stem:
            raise PluginError(ERR_TOOL_SEP.format(path=f"mocks/{name}/{path.name}"))
        expect = head.get("expect")
        schema = schemas.get(path.stem, {})
        tools.append(
            MockTool(
                path.stem,
                body,
                str(head.get("description") or schema.get("description") or ""),
                dict(expect) if isinstance(expect, dict) else {},
                head.get("error") is True,
                _mapping(schema.get("inputSchema")),
            )
        )
    return MockServer(name, folder, tuple(tools), agent, world)


def load_mocks(eval_folder: Path) -> dict[str, MockServer]:
    root = eval_folder / "mocks"
    if not root.is_dir():
        return {}
    return {p.name: load_server(p) for p in sorted(root.iterdir()) if p.is_dir()}


def mock_env(mode: str, mocks: Mapping[str, MockServer], *, allow_real: bool) -> dict[str, str]:
    """Alt sürece verilecek `FUSION_EVAL_MCP` (bkz. `config.plugin_eval_env`)."""
    from ..config.plugin_eval_env import MCP_ENV

    if mode not in MOCK_MODES:
        raise PluginError(ERR_MODE)
    payload = {
        "mode": mode,
        "allow_real": allow_real,
        "mocks": {name: str(server.folder) for name, server in mocks.items()},
    }
    return {MCP_ENV: json.dumps(payload)}


def mock_notes(
    declared: tuple[str, ...], mocks: Mapping[str, MockServer], *, mode: str, allow_real: bool
) -> tuple[str, ...]:
    """Eklentinin bildirdiği sunucularla sahteleri karşılaştır (uyarılar; bilinmeyen sahte hata)."""
    if mode == "off":
        return ()
    for name in mocks:
        if name not in declared:
            raise PluginError(ERR_UNKNOWN.format(server=name))
    if allow_real:
        return ()
    return tuple(WARN_UNMOCKED.format(server=s) for s in declared if s not in mocks)


def render(template: str, arguments: Mapping[str, object]) -> str:
    def value(match: re.Match[str]) -> str:
        found = arguments.get(match.group(1))
        if found is None:
            return ""
        return found if isinstance(found, str) else json.dumps(found, ensure_ascii=False)

    return re.sub(r"\{\{\s*input\.([A-Za-z0-9_-]+)\s*\}\}", value, template)


def expectation_errors(tool: MockTool, arguments: Mapping[str, object]) -> tuple[str, ...]:
    return tuple(
        f"{tool.name}: expected {key}={json.dumps(want, ensure_ascii=False)}, got "
        f"{json.dumps(arguments.get(key), ensure_ascii=False)}"
        for key, want in tool.expect.items()
        if arguments.get(key) != want
    )


def read_log(path: Path) -> list[dict[str, object]]:
    try:
        lines = path.read_text("utf-8").splitlines() if path.is_file() else []
    except OSError:
        return []
    rows: list[dict[str, object]] = []
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows
