"""Claude Code ve Codex yapılandırmasını okuma (P-071).

Fusion Claude'un `~/.claude/settings.json` (izin, kanca), `CLAUDE.md`, `~/.claude/skills|agents|
commands`, proje `.mcp.json` dosyalarını ve Codex'in `AGENTS.md`, `~/.codex/skills|agents`
dizinlerini ZATEN doğrudan okur; bunlar "zaten okunuyor" satırı olur. Taşınan: Claude'un
`~/.claude.json` MCP kayıtları (kullanıcı + bu projenin yerel kapsamı), Codex'in
`config.toml` `[mcp_servers]` tabloları, `~/.codex/rules/*.rules` `prefix_rule` kuralları ve
`~/.codex/prompts/*.md` özel komutları.
"""

from __future__ import annotations

import ast
import itertools
import re
from collections.abc import Mapping
from pathlib import Path

from ..models import McpScope
from ..permission_rules import PermissionDecision, PermissionRule
from .common import FUSION_COMMANDS, Collector, copy_item, markdown_files
from .mcp_map import map_codex_server, map_json_server
from .model import ImportItem, ImportKind, ImportStatus, RuleImport

NATIVE_PERMISSIONS = "izinler Fusion'da doğrudan geçerli (kancalar bu sürümde çalıştırılmaz)"
NATIVE_INSTRUCTIONS = "talimat her turda doğrudan okunuyor"
NATIVE_SKILLS = "beceri/ajan/komut kataloğunda doğrudan görünüyor"
NATIVE_PROJECT_MCP = "proje .mcp.json doğrudan okunuyor (fusion trust ile)"
CODEX_POLICY = "Fusion karşılığı onay kipi (/auto, /edits, /security) ve /permissions: {value}"
REASON_PATTERN = "kalıp çözülemedi"

#: Codex `prefix_rule` kararı → Fusion izin kararı.
_CODEX_DECISIONS = {
    "allow": PermissionDecision.ALLOW,
    "prompt": PermissionDecision.ASK,
    "forbidden": PermissionDecision.DENY,
}
#: Tek kuralın alternatif açılımında en fazla kalıp (`["git", ["push", "fetch"]]`).
MAX_EXPANSIONS = 16
_RULE_START = re.compile(r"\bprefix_rule\s*\(")
_ASSIGN = re.compile(r"\b(pattern|decision)\s*=(?!=)\s*")
#: Çağrıda yazılmış ama sabit olarak çözülemeyen alan (`decision = BLOCK`).
_UNRESOLVED = object()


def read_claude(home: Path, root: Path, out: Collector) -> None:
    config_file = home / ".claude.json"
    data = out.read_json(config_file) or {}
    for raw_name, entry in _servers(data.get("mcpServers")):
        out.mcp(raw_name, map_json_server(raw_name, entry), config_file, McpScope.USER)
    projects = data.get("projects")
    project = projects.get(str(root)) if isinstance(projects, Mapping) else None
    if isinstance(project, Mapping):
        # Claude'un "local" kapsamı: yalnız bu projede, kullanıcıya özel → Fusion kullanıcı kaydı.
        for raw_name, entry in _servers(project.get("mcpServers")):
            out.mcp(raw_name, map_json_server(raw_name, entry), config_file, McpScope.USER)
    out.native(ImportKind.PERMISSION, home / ".claude" / "settings.json", NATIVE_PERMISSIONS)
    out.native(ImportKind.INSTRUCTION, home / ".claude" / "CLAUDE.md", NATIVE_INSTRUCTIONS)
    for folder in ("skills", "agents", "commands", "output-styles"):
        out.native(ImportKind.SKILL, home / ".claude" / folder, NATIVE_SKILLS)
    out.native(ImportKind.MCP, root / ".mcp.json", NATIVE_PROJECT_MCP)
    out.native(ImportKind.INSTRUCTION, root / "CLAUDE.md", NATIVE_INSTRUCTIONS)


def read_codex(home: Path, root: Path, out: Collector) -> None:
    config_file = home / ".codex" / "config.toml"
    data = out.read_toml(config_file) or {}
    for raw_name, table in _servers(data.get("mcp_servers")):
        out.mcp(raw_name, map_codex_server(raw_name, table), config_file, McpScope.USER)
    for key in ("approval_policy", "sandbox_mode"):
        value = data.get(key)
        if isinstance(value, str):
            out.add(
                ImportItem(
                    ImportKind.SETTING,
                    key,
                    ImportStatus.SKIPPED,
                    str(config_file),
                    CODEX_POLICY.format(value=value),
                )
            )
    for path in markdown_files(home / ".codex" / "rules", (".rules",)):
        text = out.read_text(path)
        if text is not None:
            for item in codex_rule_items(text, path):
                out.add(item)
    prompts = home / ".codex" / "prompts"
    for path in markdown_files(prompts):
        text = out.read_text(path)
        if text is not None:
            out.add(
                copy_item(ImportKind.COMMAND, path, prompts, home / FUSION_COMMANDS, text, ".md")
            )
    out.native(ImportKind.INSTRUCTION, home / ".codex" / "AGENTS.md", NATIVE_INSTRUCTIONS)
    for folder in (
        home / ".codex" / "skills",
        home / ".agents" / "skills",
        home / ".codex" / "agents",
    ):
        out.native(ImportKind.SKILL, folder, NATIVE_SKILLS)
    out.native(ImportKind.INSTRUCTION, root / "AGENTS.md", NATIVE_INSTRUCTIONS)


def _servers(raw: object) -> tuple[tuple[str, Mapping[str, object]], ...]:
    if not isinstance(raw, Mapping):
        return ()
    return tuple((str(name), entry) for name, entry in raw.items() if isinstance(entry, Mapping))


# --- Codex `.rules` (Starlark `prefix_rule`) ----------------------------------- #


def codex_rule_items(text: str, path: Path) -> tuple[ImportItem, ...]:
    """`prefix_rule(pattern=[…], decision="…")` çağrılarını `Bash(…)` kurallarına çevir.

    Tam bir Starlark yorumlayıcısı yazılmaz: kalıp listesi düz dize (ya da dize alternatifleri)
    taşımıyorsa satır gerekçesiyle atlanır; hiçbir şey sessizce düşmez.
    """
    items: list[ImportItem] = []
    for call in _calls(text):
        fields = _fields(call)
        # Yazılmış ama çözülemeyen karar varsayılan "allow"a DÜŞMEZ: yasak kuralı izin olurdu.
        raw_decision = fields.get("decision", "allow")
        decision = None if raw_decision is _UNRESOLVED else _CODEX_DECISIONS.get(str(raw_decision))
        patterns = _expand(fields.get("pattern"))
        raw_pattern = fields.get("pattern")
        tokens = raw_pattern if isinstance(raw_pattern, list) else []
        label = " ".join(str(p) for p in tokens) or call.strip()[:40]
        if decision is None or not patterns:
            items.append(
                ImportItem(
                    ImportKind.PERMISSION, label, ImportStatus.SKIPPED, str(path), REASON_PATTERN
                )
            )
            continue
        for words in patterns:
            rule = PermissionRule("Bash", f"{' '.join(words)} *", decision)
            items.append(
                ImportItem(
                    ImportKind.PERMISSION,
                    rule.pattern,
                    ImportStatus.NEW,
                    str(path),
                    decision.value,
                    RuleImport(rule),
                )
            )
    return tuple(items)


def _calls(text: str) -> list[str]:
    """`prefix_rule(` ile başlayan çağrıların parantez içi metni (dizeler atlanarak)."""
    calls: list[str] = []
    for match in _RULE_START.finditer(text):
        depth, index, quote = 1, match.end(), ""
        while index < len(text) and depth:
            char = text[index]
            if quote:
                quote = "" if char == quote and text[index - 1] != "\\" else quote
            elif char in "\"'":
                quote = char
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            index += 1
        if depth == 0:
            calls.append(text[match.end() : index - 1])
    return calls


def _fields(call: str) -> dict[str, object]:
    """Üst düzey `pattern=`/`decision=` atamaları; dize içindeki `decision=` metni sayılmaz.

    Ölçüldü (31 Ekim): `decision = BLOCK` (değişken) alanı sessizce düşüyor, varsayılan "allow"
    uygulanıyordu; `justification` dizesinde geçen `decision="allow"` da atama sanılıyordu.
    """
    fields: dict[str, object] = {}
    top_level = _top_level_offsets(call)
    for match in _ASSIGN.finditer(call):
        if match.start() not in top_level:
            continue
        value = _literal_prefix(call[match.end() :])
        fields[match.group(1)] = _UNRESOLVED if value is None else value
    return fields


def _top_level_offsets(call: str) -> frozenset[int]:
    """Dize ve köşeli/normal parantez DIŞINDA kalan karakter konumları."""
    offsets: set[int] = set()
    depth, quote = 0, ""
    for index, char in enumerate(call):
        if quote:
            if char == quote and call[index - 1] != "\\":
                quote = ""
            continue
        if char in "\"'":
            quote = char
        elif char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        elif depth == 0:
            offsets.add(index)
    return frozenset(offsets)


def _literal_prefix(text: str) -> object | None:
    """Metnin başındaki Python/Starlark sabitini (dize ya da liste) çöz."""
    for end in range(1, min(len(text), 4_000) + 1):
        if text[end - 1] not in "]\"'":
            continue
        try:
            value: object = ast.literal_eval(text[:end])
            return value
        except (ValueError, SyntaxError):
            continue
    return None


def _expand(pattern: object) -> tuple[tuple[str, ...], ...]:
    if not isinstance(pattern, list) or not pattern:
        return ()
    options: list[tuple[str, ...]] = []
    for element in pattern:
        if isinstance(element, str) and element.strip():
            options.append((element.strip(),))
        elif isinstance(element, list) and element and all(isinstance(e, str) for e in element):
            options.append(tuple(e.strip() for e in element))
        else:
            return ()
    combos = tuple(itertools.islice(itertools.product(*options), MAX_EXPANSIONS + 1))
    return combos if len(combos) <= MAX_EXPANSIONS else ()
