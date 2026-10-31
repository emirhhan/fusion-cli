"""Başka kodlama ajanlarının yapılandırmasını Fusion'a taşıma (P-071) — `/import`, `fusion import`.

Claude Code'un `/import codex|gemini|cursor [--dry-run] [--yes]` komutunun karşılığı; Claude
Code'un kendisi de kaynaktır. Akış iki adımdır: `build_plan` diske DOKUNMADAN önizleme kurar,
`apply_plan` yalnız "eklenecek" satırları uygular:

- MCP → kullanıcı `config.yaml` (proje dosyasından gelen → projenin `.mcp.json`'ı); kayıtlar
  `unreviewed` güvenle girer, ilk araç çağrısı yine onay ister. Sırlar şifreli depoya.
- izin → Fusion'ın kullanıcı izin dosyası (`permissions.json`).
- komut/kural → `.fusion/commands`, `.fusion/rules`; var olan dosyanın üzerine yazılmaz.
- talimat → `~/.fusion/TALIMAT.md` içine `@yol` başvurusu (kopya değil).

Fusion'ın zaten doğrudan okuduğu dosyalar (CLAUDE.md, AGENTS.md, `~/.claude/settings.json`,
`.mcp.json`, beceri dizinleri) "zaten okunuyor" olarak listelenir ve taşınmaz.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Protocol

from ...core.errors import ConfigError
from ..mcp_json import upsert_project_mcp_server
from ..models import Config, McpScope, McpServerConfig
from ..permission_rules import (
    PermissionDecision,
    add_rule,
    format_rule,
    load_permission_rules,
    user_permissions_file,
)
from ..writer import write_mcp_servers
from .claude_codex import read_claude, read_codex
from .common import Collector
from .gemini_cursor import read_cursor, read_gemini
from .model import (
    FileImport,
    ImportItem,
    ImportKind,
    ImportPlan,
    ImportReport,
    ImportStatus,
    LineImport,
    McpImport,
    RuleImport,
)

__all__ = [
    "SOURCES",
    "ImportItem",
    "ImportKind",
    "ImportPlan",
    "ImportReport",
    "ImportStatus",
    "SecretWriter",
    "apply_plan",
    "build_plan",
    "default_secrets",
    "source_names",
]

Reader = Callable[[Path, Path, Collector], None]

#: Kaynak adı → okuyucu. Ad Claude Code'un `/import` argümanıyla aynıdır.
SOURCES: dict[str, Reader] = {
    "claude": read_claude,
    "codex": read_codex,
    "gemini": read_gemini,
    "cursor": read_cursor,
}

UNKNOWN_SOURCE = "Bilinmeyen kaynak: {name}. Geçerli: {known}"
FAIL_SECRET_STORE = "şifreli depo kullanılamıyor; sır taşınmadı (FUSION_SECRET_KEY / anahtarlık)"
FAIL_WRITE = "yazılamadı: {error}"


class SecretWriter(Protocol):
    """Şifreli sır deposunun içe aktarmanın kullandığı parçası."""

    @property
    def available(self) -> bool: ...

    def set(self, env_name: str, value: str) -> None: ...


def default_secrets() -> SecretWriter:
    """Fusion'ın şifreli sır deposu (`secrets.enc`)."""
    from ..credentials import FernetSecretStore
    from ..keys import secret_key
    from ..paths import credentials_file

    return FernetSecretStore(credentials_file(), secret_key=secret_key())


def source_names() -> tuple[str, ...]:
    return tuple(SOURCES)


def build_plan(source: str, *, home: Path, root: Path, config: Config) -> ImportPlan:
    """Kaynağı oku ve önizleme kur; hiçbir dosyaya yazmaz."""
    reader = SOURCES.get(source.strip().lower())
    if reader is None:
        raise ConfigError(UNKNOWN_SOURCE.format(name=source, known=", ".join(SOURCES)))
    collector = Collector()
    reader(home, root, collector)
    items = _settle(tuple(collector.items), config, root)
    return ImportPlan(source.strip().lower(), items, tuple(collector.warnings))


def _settle(items: tuple[ImportItem, ...], config: Config, root: Path) -> tuple[ImportItem, ...]:
    """Fusion'da zaten bulunanları "zaten var" yap (aynı ad plan içinde ikinci kez de)."""
    servers = {server.name for server in config.mcp_servers}
    rules = {(format_rule(r), r.decision) for r in load_permission_rules(root).rules}
    files: set[Path] = set()
    settled: list[ImportItem] = []
    for item in items:
        if item.status is ImportStatus.NEW and _exists(item.action, servers, rules, files):
            item = replace(item, status=ImportStatus.EXISTS)
        settled.append(item)
    return tuple(settled)


def _exists(
    action: object,
    servers: set[str],
    rules: set[tuple[str, PermissionDecision]],
    files: set[Path],
) -> bool:
    if isinstance(action, McpImport):
        seen = action.server.name in servers
        servers.add(action.server.name)
        return seen
    if isinstance(action, RuleImport):
        key = (format_rule(action.rule), action.rule.decision)
        seen = key in rules
        rules.add(key)
        return seen
    if isinstance(action, FileImport):
        seen = action.target.exists() or action.target in files
        files.add(action.target)
        return seen
    if isinstance(action, LineImport):
        try:
            return action.line in action.target.read_text(encoding="utf-8").splitlines()
        except OSError:
            return False
    return False


def apply_plan(
    plan: ImportPlan, *, config: Config, root: Path, secrets: SecretWriter | None
) -> tuple[Config, ImportReport]:
    """ "Eklenecek" satırları uygula; dönen `Config` yeni MCP kayıtlarını taşır."""
    applied: list[ImportItem] = []
    failed: list[tuple[ImportItem, str]] = []
    written: list[Path] = []
    user_servers: list[McpServerConfig] = []
    for item in plan.pending:
        error = _apply_one(item, root, secrets, user_servers, written)
        if error is None:
            applied.append(item)
        else:
            failed.append((item, error))
    if user_servers:
        updated = replace(config, mcp_servers=(*config.mcp_servers, *user_servers))
        try:
            written.append(write_mcp_servers(updated))
            config = updated
        except (ConfigError, OSError) as error:
            moved = [
                i
                for i in applied
                if isinstance(i.action, McpImport) and i.action.server.scope is McpScope.USER
            ]
            applied = [i for i in applied if i not in moved]
            failed.extend((i, FAIL_WRITE.format(error=error)) for i in moved)
    return config, ImportReport(tuple(applied), tuple(failed), tuple(dict.fromkeys(written)))


def _apply_one(
    item: ImportItem,
    root: Path,
    secrets: SecretWriter | None,
    user_servers: list[McpServerConfig],
    written: list[Path],
) -> str | None:
    """Tek satırı uygula; başarısızsa Türkçe neden."""
    action = item.action
    try:
        if isinstance(action, McpImport):
            return _apply_mcp(action, root, secrets, user_servers, written)
        if isinstance(action, RuleImport):
            target = user_permissions_file()
            add_rule(target, action.rule)
            written.append(target)
        elif isinstance(action, FileImport):
            action.target.parent.mkdir(parents=True, exist_ok=True)
            # `x` kipi: araya giren bir dosyanın üzerine de yazmaz.
            with action.target.open("x", encoding="utf-8") as handle:
                handle.write(action.content)
            written.append(action.target)
        elif isinstance(action, LineImport):
            action.target.parent.mkdir(parents=True, exist_ok=True)
            current = action.target.read_text(encoding="utf-8") if action.target.exists() else ""
            separator = "" if not current or current.endswith("\n") else "\n"
            action.target.write_text(f"{current}{separator}{action.line}\n", encoding="utf-8")
            written.append(action.target)
    except (ConfigError, OSError) as error:
        return FAIL_WRITE.format(error=error)
    return None


def _apply_mcp(
    action: McpImport,
    root: Path,
    secrets: SecretWriter | None,
    user_servers: list[McpServerConfig],
    written: list[Path],
) -> str | None:
    if action.secrets:
        if secrets is None or not secrets.available:
            return FAIL_SECRET_STORE
        for name, value in action.secrets:
            secrets.set(name, value)
    if action.server.scope is McpScope.PROJECT:
        written.append(upsert_project_mcp_server(root, action.server))
    else:
        user_servers.append(action.server)
    return None
