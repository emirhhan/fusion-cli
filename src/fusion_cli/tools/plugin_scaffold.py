"""`fusion plugin init|new <ad>` iskeleti (Claude Code `claude plugin init`, #380, #401).

Ölçülen Claude 2.1.287 davranışı: `~/.claude/skills/<ad>/` altına `.claude-plugin/plugin.json`
(`$schema`, `name`, `version: 0.1.0`, `description`, `author{name,email}`, `skills: ["./"]`) ve
kök `SKILL.md` yazılır; `--with` ile `skills/example/SKILL.md`, `agents/example.md`,
`hooks/hooks.json` (+ `hooks-handlers/on-session-start.ts`), `.mcp.json`, `.lsp.json`,
`output-styles/<ad>.md`, `channel` (`channels` alanı + `package.json` + `server.ts`) eklenir.
Var olan `.claude-plugin/` `--force` olmadan reddedilir (çıkış 1, hiçbir şey yazılmaz). Ad
yol ayırıcı/boşluk içeremez, ayrılmış ad reddedilir; kebab-case dışı ad ve eksik yazar uyarıdır.
Yazar/e-posta verilmezse `git config user.name/user.email`.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from ..core.atomic_file import atomic_replace_text
from ..core.constants import GIT_TIMEOUT_S
from ..core.plugin_paths import name_warnings, reserved_error
from ..core.plugins import PluginError

COMPONENTS = ("skills", "agents", "hooks", "mcp", "lsp", "output-style", "channel")
SCHEMA_URL = "https://anthropic.com/claude-code/plugin.schema.json"
DEFAULT_DESCRIPTION = "TODO: eklentinin ne sağladığını yaz"
WARN_NO_AUTHOR = "author: Yazar bilgisi yok. Eklentinin kime ait olduğu için author ekle"

ERR_SEPARATOR = (
    'Geçersiz eklenti adı "{name}": ad yol ayırıcı (/ ya da \\), ".." içeremez ya da "." olamaz'
)
ERR_SPACE = 'Geçersiz eklenti adı "{name}": ad boşluk içeremez. kebab-case kullan (ör. "my-plugin")'
ERR_RESERVED = 'Geçersiz eklenti adı "{name}": {reason}'
ERR_EXISTS = "{path} zaten var. Üzerine yazmak için --force kullan."
ERR_COMPONENT = "--with: bilinmeyen bileşen {name!r}; seçenekler: {allowed}"

_SKILL = """---
name: {name}
description: TODO — bu becerinin NE ZAMAN kullanılacağını yaz. Kullanıcının söyleyebileceği
  tetikleyici ifadeleri ekle ("X yap", "Y kur", "Z'yi incele"); istek bu metinle eşleşir.
---

# {name}

TODO: becerinin ne yaptığı ve izlenecek adımlar.
"""
_AGENT = """---
name: example
description: TODO — bu alt ajana ne zaman iş devredilmeli?
tools:
  - Read
  - Grep
---

TODO: alt ajanın sistem istemi.
"""
_STYLE = """---
name: {name}
description: TODO — /config çıktı biçemi seçicisinde görünen tek satır
force-for-plugin: true
keep-coding-instructions: true
---

TODO: biçem istemi. Biçem etkinken sistem istemine eklenir.
"""
_HOOK_HANDLER = """#!/usr/bin/env bun
// SessionStart kanca işleyicisi: olayı stdin'den okur, JSON sonucu stdout'a yazar.
const input = await new Response(Bun.stdin.stream()).text()
JSON.parse(input)
process.stdout.write(JSON.stringify({}))
"""
_SERVER = """#!/usr/bin/env bun
// {name} kanal sunucusu: kanal sözleşmesini uygulayan stdio MCP sunucusu (TODO).
import {{ Server }} from '@modelcontextprotocol/sdk/server/index.js'
import {{ StdioServerTransport }} from '@modelcontextprotocol/sdk/server/stdio.js'

const mcp = new Server(
  {{ name: '{name}', version: '0.1.0' }},
  {{ capabilities: {{ tools: {{}}, experimental: {{ 'claude/channel': {{}} }} }} }},
)
await mcp.connect(new StdioServerTransport())
"""


@dataclass(frozen=True, slots=True)
class Scaffold:
    root: Path
    name: str
    warnings: tuple[str, ...]


def check_name(name: str) -> None:
    if "/" in name or "\\" in name or ".." in name or name in (".", ""):
        raise PluginError(ERR_SEPARATOR.format(name=name))
    if any(char.isspace() for char in name):
        raise PluginError(ERR_SPACE.format(name=name))
    if reason := reserved_error(name):
        raise PluginError(ERR_RESERVED.format(name=name, reason=reason))


def _git_config(key: str) -> str:
    try:
        done = subprocess.run(
            ["git", "config", "--get", key],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


def _manifest(name: str, description: str, author: str, email: str, channel: bool) -> str:
    who = {"name": author, **({"email": email} if email else {})} if author else None
    data: dict[str, object] = {
        "$schema": SCHEMA_URL,
        "name": name,
        "version": "0.1.0",
        "description": description or DEFAULT_DESCRIPTION,
        **({"author": who} if who else {}),
        "skills": ["./"],
        **({"channels": [{"server": name, "displayName": name}]} if channel else {}),
    }
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def _json(data: object) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def _component_files(name: str, chosen: set[str]) -> dict[str, str]:
    files: dict[str, str] = {}
    if "skills" in chosen:
        files["skills/example/SKILL.md"] = _SKILL.format(name="example")
    if "agents" in chosen:
        files["agents/example.md"] = _AGENT
    if "hooks" in chosen:
        command = 'bun "${CLAUDE_PLUGIN_ROOT}/hooks-handlers/on-session-start.ts"'
        hook = {"type": "command", "command": command}
        files["hooks/hooks.json"] = _json({"hooks": {"SessionStart": [{"hooks": [hook]}]}})
        files["hooks-handlers/on-session-start.ts"] = _HOOK_HANDLER
    if "mcp" in chosen or "channel" in chosen:
        args = ["run", "--cwd", "${CLAUDE_PLUGIN_ROOT}", "--shell=bun", "--silent", "start"]
        files[".mcp.json"] = _json({"mcpServers": {name: {"command": "bun", "args": args}}})
    if "lsp" in chosen:
        server = {"command": "example-language-server", "args": ["--stdio"]}
        files[".lsp.json"] = _json(
            {"example": {**server, "extensionToLanguage": {".example": "example"}}}
        )
    if "output-style" in chosen:
        files[f"output-styles/{name}.md"] = _STYLE.format(name=name)
    if "channel" in chosen:
        files["package.json"] = _json(
            {
                "name": f"claude-channel-{name}",
                "version": "0.1.0",
                "type": "module",
                "scripts": {"start": "bun install --no-summary && bun server.ts"},
                "dependencies": {"@modelcontextprotocol/sdk": "^1.0.0"},
            }
        )
        files["server.ts"] = _SERVER.format(name=name)
    return files


def scaffold_plugin(
    name: str,
    *,
    home: Path | None = None,
    author: str | None = None,
    email: str | None = None,
    description: str = "",
    force: bool = False,
    with_components: Sequence[str] = (),
) -> Scaffold:
    """İskeleti yaz; doğrulama hatasında hiçbir dosya yazılmaz."""
    check_name(name)
    chosen = set(with_components)
    unknown = sorted(chosen - set(COMPONENTS))
    if unknown:
        raise PluginError(ERR_COMPONENT.format(name=unknown[0], allowed=", ".join(COMPONENTS)))
    root = (home or Path.home()) / ".claude" / "skills" / name
    marker = root / ".claude-plugin"
    if marker.exists() and not force:
        raise PluginError(ERR_EXISTS.format(path=marker))
    who = _git_config("user.name") if author is None else author
    mail = _git_config("user.email") if email is None else email
    files = {
        ".claude-plugin/plugin.json": _manifest(name, description, who, mail, "channel" in chosen),
        "SKILL.md": _SKILL.format(name=name),
        **_component_files(name, chosen),
    }
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_replace_text(path, text)
    warnings = (*name_warnings(name), *(() if who else (WARN_NO_AUTHOR,)))
    return Scaffold(root, name, warnings)
