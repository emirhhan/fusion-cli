"""Gemini CLI ve Cursor yapılandırmasını okuma (P-071).

Gemini: `~/.gemini/settings.json` ve proje `.gemini/settings.json` `mcpServers` (`httpUrl`
akışlı HTTP, `url` SSE), kullanıcı dosyasının `tools.allowed/exclude` (eski adları
`allowedTools/excludeTools`) listeleri, `~/.gemini/GEMINI.md` (kullanıcı talimatına `@` başvurusu
olarak bağlanır; kopyalanmaz, tek kaynak kalır) ve `commands/*.toml` özel komutları.

Cursor: `~/.cursor/mcp.json` ve proje `.cursor/mcp.json`, `~/.cursor/cli-config.json`
`permissions.allow/deny` (`Shell(git)`, `Read(src/**)`, `Write(**)`, `Mcp(sunucu:araç)`),
proje `.cursor/rules/*.mdc` (yalnız `alwaysApply` ya da `globs` taşıyanlar; "istekle
uygulanan" kuralın Fusion karşılığı yok) ve `commands/*.md`.

Proje dosyalarından gelen İZİN kuralları taşınmaz: indirilen bir depo kullanıcının genel izin
dosyasına `Bash(*)` yazdıramasın. Proje MCP kayıtları kullanıcıya değil projenin `.mcp.json`'ına
gider (Fusion'ın güven kaydıyla).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

from ..models import McpScope
from ..permission_rules import PermissionDecision, PermissionRule
from .common import (
    FUSION_COMMANDS,
    FUSION_RULES,
    FUSION_USER_INSTRUCTIONS,
    Collector,
    copy_item,
    markdown_files,
)
from .mcp_map import map_json_server
from .model import ImportItem, ImportKind, ImportStatus, LineImport, RuleImport

NATIVE_INSTRUCTIONS = "talimat her turda doğrudan okunuyor"
REASON_TOOL = "Fusion karşılığı yok"
REASON_CURSOR_RULE = "istekle/elle uygulanan Cursor kuralı; Fusion'da karşılığı yok (beceri yaz)"
REASON_PROMPT = "komut dosyasında prompt alanı yok"
EXTENSION_HINT = "Gemini uzantısı; Fusion eklentisi değil — içeriği elle taşı"
GEMINI_LINK = "@~/.gemini/GEMINI.md"

#: Gemini araç adı → Claude/Fusion kural adı.
_GEMINI_TOOLS = {
    "run_shell_command": "Bash",
    "shelltool": "Bash",
    "read_file": "Read",
    "read_many_files": "Read",
    "readfiletool": "Read",
    "write_file": "Write",
    "writefiletool": "Write",
    "replace": "Edit",
    "edittool": "Edit",
    "web_fetch": "WebFetch",
    "webfetchtool": "WebFetch",
    "google_web_search": "WebSearch",
    "websearchtool": "WebSearch",
    "glob": "Glob",
    "search_file_content": "Grep",
    "list_directory": "LS",
}
#: Cursor CLI izin adı → Claude/Fusion kural adı.
_CURSOR_TOOLS = {"shell": "Bash", "read": "Read", "write": "Edit"}
_CALL = re.compile(r"^\s*([A-Za-z_][\w]*)\s*(?:\((.*)\))?\s*$", re.DOTALL)
_ALWAYS = re.compile(r"^alwaysApply[ \t]*:[ \t]*true[ \t]*$", re.I | re.M)
_GLOBS = re.compile(r"^globs[ \t]*:[ \t]*\S", re.I | re.M)
_FRONTMATTER = re.compile(r"\A\s*---\n(.*?)\n---", re.DOTALL)


def read_gemini(home: Path, root: Path, out: Collector) -> None:
    user_file = home / ".gemini" / "settings.json"
    user = out.read_json(user_file) or {}
    _gemini_mcp(user, user_file, McpScope.USER, out)
    project_file = root / ".gemini" / "settings.json"
    _gemini_mcp(out.read_json(project_file) or {}, project_file, McpScope.PROJECT, out)
    tools = user.get("tools")
    tools_map: Mapping[str, object] = tools if isinstance(tools, Mapping) else {}
    for key, legacy, decision in (
        ("allowed", "allowedTools", PermissionDecision.ALLOW),
        ("exclude", "excludeTools", PermissionDecision.DENY),
    ):
        entries = tools_map.get(key, user.get(legacy))
        for entry in entries if isinstance(entries, list) else ():
            out.add(_tool_rule(str(entry), decision, _GEMINI_TOOLS, user_file))
    gemini_md = home / ".gemini" / "GEMINI.md"
    if gemini_md.is_file():
        target = home / FUSION_USER_INSTRUCTIONS
        out.add(
            ImportItem(
                ImportKind.INSTRUCTION,
                "GEMINI.md",
                ImportStatus.NEW,
                str(gemini_md),
                f"{target} içine {GEMINI_LINK} başvurusu",
                LineImport(target, GEMINI_LINK),
            )
        )
    out.native(ImportKind.INSTRUCTION, root / "GEMINI.md", NATIVE_INSTRUCTIONS)
    _gemini_commands(home / ".gemini" / "commands", home / FUSION_COMMANDS, out)
    _gemini_commands(root / ".gemini" / "commands", root / FUSION_COMMANDS, out)
    extensions = home / ".gemini" / "extensions"
    for folder in sorted(extensions.iterdir()) if extensions.is_dir() else ():
        if (folder / "gemini-extension.json").is_file():
            out.add(
                ImportItem(
                    ImportKind.SKILL, folder.name, ImportStatus.SKIPPED, str(folder), EXTENSION_HINT
                )
            )


def read_cursor(home: Path, root: Path, out: Collector) -> None:
    for path, scope in (
        (home / ".cursor" / "mcp.json", McpScope.USER),
        (root / ".cursor" / "mcp.json", McpScope.PROJECT),
    ):
        data = out.read_json(path) or {}
        servers = data.get("mcpServers")
        for raw_name, entry in servers.items() if isinstance(servers, Mapping) else ():
            if isinstance(entry, Mapping):
                out.mcp(str(raw_name), map_json_server(str(raw_name), entry), path, scope)
    cli_file = home / ".cursor" / "cli-config.json"
    permissions = (out.read_json(cli_file) or {}).get("permissions")
    if isinstance(permissions, Mapping):
        for key, decision in (
            ("allow", PermissionDecision.ALLOW),
            ("deny", PermissionDecision.DENY),
        ):
            entries = permissions.get(key)
            for entry in entries if isinstance(entries, list) else ():
                out.add(_tool_rule(str(entry), decision, _CURSOR_TOOLS, cli_file))
    rules = root / ".cursor" / "rules"
    for path in markdown_files(rules, (".mdc", ".md")):
        text = out.read_text(path)
        if text is not None:
            out.add(_cursor_rule(path, rules, root, text))
    out.native(ImportKind.RULE, root / ".cursorrules", NATIVE_INSTRUCTIONS)
    out.native(ImportKind.INSTRUCTION, root / "AGENTS.md", NATIVE_INSTRUCTIONS)
    for base, target in (
        (home / ".cursor" / "commands", home / FUSION_COMMANDS),
        (root / ".cursor" / "commands", root / FUSION_COMMANDS),
    ):
        for path in markdown_files(base):
            text = out.read_text(path)
            if text is not None:
                out.add(copy_item(ImportKind.COMMAND, path, base, target, text, ".md"))


def _gemini_mcp(data: Mapping[str, object], path: Path, scope: McpScope, out: Collector) -> None:
    servers = data.get("mcpServers")
    for raw_name, entry in servers.items() if isinstance(servers, Mapping) else ():
        if isinstance(entry, Mapping):
            out.mcp(
                str(raw_name), map_json_server(str(raw_name), entry, url_is_sse=True), path, scope
            )


def _tool_rule(
    entry: str, decision: PermissionDecision, names: Mapping[str, str], origin: Path
) -> ImportItem:
    """`araç` ya da `araç(belirteç)` → Fusion kuralı; kabukta belirteç ön ektir (`git *`)."""
    match = _CALL.match(entry)
    if match is None:
        return ImportItem(
            ImportKind.PERMISSION, entry, ImportStatus.SKIPPED, str(origin), REASON_TOOL
        )
    head, spec = match.group(1), (match.group(2) or "").strip() or None
    if head.lower() == "mcp" and spec:
        server, _, tool = spec.partition(":")
        tool_name = f"mcp__{server.strip()}" + (f"__{tool.strip()}" if tool.strip(" *") else "")
        rule = PermissionRule(tool_name, None, decision)
    else:
        mapped = names.get(head.lower())
        if mapped is None:
            return ImportItem(
                ImportKind.PERMISSION, entry, ImportStatus.SKIPPED, str(origin), REASON_TOOL
            )
        if mapped == "Bash" and spec and not spec.endswith("*"):
            spec = f"{spec} *"
        rule = PermissionRule(mapped, spec, decision)
    return ImportItem(
        ImportKind.PERMISSION,
        rule.pattern,
        ImportStatus.NEW,
        str(origin),
        f"{decision.value} · kaynak: {entry}",
        RuleImport(rule),
    )


def _gemini_commands(base: Path, target: Path, out: Collector) -> None:
    """`commands/x/y.toml` (`prompt`, `description`) → `.fusion/commands/x/y.md`."""
    for path in markdown_files(base, (".toml",)):
        data = out.read_toml(path) or {}
        prompt = data.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            out.add(
                ImportItem(
                    ImportKind.COMMAND, path.stem, ImportStatus.SKIPPED, str(path), REASON_PROMPT
                )
            )
            continue
        out.add(
            copy_item(ImportKind.COMMAND, path, base, target, gemini_command_markdown(data), ".md")
        )


def gemini_command_markdown(data: Mapping[str, object]) -> str:
    """Gemini TOML komutunu Fusion/Claude komut dosyasına çevir.

    `{{args}}` → `$ARGUMENTS`, `!{komut}` → `` !`komut` `` (Fusion'ın izin denetimiyle koşar).
    """
    body = str(data.get("prompt", "")).replace("{{args}}", "$ARGUMENTS")
    body = re.sub(r"!\{([^{}\n]+)\}", lambda m: f"!`{m.group(1).strip()}`", body)
    description = str(data.get("description") or "").replace("\n", " ").strip()
    head = f"---\ndescription: {description}\n---\n\n" if description else ""
    return head + body.strip() + "\n"


def _cursor_rule(path: Path, base: Path, root: Path, text: str) -> ImportItem:
    head = _FRONTMATTER.match(text)
    meta = head.group(1) if head else ""
    if not (_ALWAYS.search(meta) or _GLOBS.search(meta)):
        return ImportItem(
            ImportKind.RULE, path.stem, ImportStatus.SKIPPED, str(path), REASON_CURSOR_RULE
        )
    return copy_item(ImportKind.RULE, path, base, root / FUSION_RULES, text, ".mdc")
