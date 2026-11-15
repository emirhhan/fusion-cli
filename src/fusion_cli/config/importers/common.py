"""Kaynak okuyucularının ortak yardımcıları (P-071)."""

from __future__ import annotations

import json
import tomllib
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path

from ..models import McpScope
from .mcp_map import MappedServer, describe_server, server_name
from .model import FileImport, ImportItem, ImportKind, ImportStatus, McpImport

#: Fusion'ın kullanıcı komut kökü ve proje kökü (köke/eve göreli; `skill_commands.COMMAND_ROOTS`).
FUSION_COMMANDS = Path(".fusion") / "commands"
#: Fusion'ın proje kural kökü (`instruction_rules.PROJECT_RULE_DIRS`).
FUSION_RULES = Path(".fusion") / "rules"
#: Fusion kullanıcı talimatı (`instruction_layers.USER_LAYER`).
FUSION_USER_INSTRUCTIONS = Path(".fusion") / "TALIMAT.md"
#: Bir kaynaktan okunacak en fazla komut/kural dosyası.
MAX_FILES = 200
#: Bir komut/kural dosyasından okunacak en fazla karakter.
MAX_FILE_CHARS = 60_000

REASON_TOKEN = "proje dosyasında Bearer token: `fusion mcp add --token-env` ile kullanıcıya ekle"
WARN_UNREADABLE = "{path} okunamadı: {error}"


@dataclass(slots=True)
class Collector:
    """Okuyucunun satır ve uyarı biriktirdiği yer (yalnız plan kurulurken yaşar)."""

    items: list[ImportItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add(self, item: ImportItem) -> None:
        self.items.append(item)

    def native(self, kind: ImportKind, path: Path, detail: str) -> None:
        """Fusion'ın doğrudan okuduğu dosya; yalnız varsa satır olur."""
        if path.exists():
            self.add(ImportItem(kind, path.name, ImportStatus.NATIVE, str(path), detail))

    def read_json(self, path: Path) -> Mapping[str, object] | None:
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            self.warnings.append(WARN_UNREADABLE.format(path=path, error=error))
            return None
        return data if isinstance(data, Mapping) else None

    def read_toml(self, path: Path) -> Mapping[str, object] | None:
        if not path.is_file():
            return None
        try:
            return tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, tomllib.TOMLDecodeError) as error:
            self.warnings.append(WARN_UNREADABLE.format(path=path, error=error))
            return None

    def read_text(self, path: Path) -> str | None:
        try:
            return path.read_text(encoding="utf-8")[:MAX_FILE_CHARS]
        except (OSError, UnicodeDecodeError) as error:
            self.warnings.append(WARN_UNREADABLE.format(path=path, error=error))
            return None

    def mcp(self, raw_name: str, mapped: MappedServer, origin: Path, scope: McpScope) -> None:
        name = server_name(raw_name)
        if mapped.server is None:
            self.add(
                ImportItem(ImportKind.MCP, name, ImportStatus.SKIPPED, str(origin), mapped.reason)
            )
            return
        server = replace(mapped.server, name=name, scope=scope)
        if scope is McpScope.PROJECT and server.token_env:
            # `.mcp.json` (Claude biçimi) `token_env` taşımaz; kimliksiz istek üretmesin.
            self.add(
                ImportItem(ImportKind.MCP, name, ImportStatus.SKIPPED, str(origin), REASON_TOKEN)
            )
            return
        detail = describe_server(server, mapped.secrets)
        if scope is McpScope.PROJECT:
            detail = f"proje .mcp.json · {detail}"
        self.add(
            ImportItem(
                ImportKind.MCP,
                name,
                ImportStatus.NEW,
                str(origin),
                detail,
                McpImport(server, mapped.secrets),
            )
        )


def markdown_files(base: Path, suffixes: tuple[str, ...] = (".md",)) -> Iterator[Path]:
    """Kökteki dosyalar (sıralı, sınırlı); sembolik bağ kök dışına çıkıyorsa atlanır."""
    if not base.is_dir():
        return
    bound = base.resolve()
    count = 0
    for path in sorted(base.rglob("*")):
        if path.suffix.lower() not in suffixes or not path.is_file():
            continue
        try:
            if not path.resolve().is_relative_to(bound):
                continue
        except OSError:
            continue
        count += 1
        if count > MAX_FILES:
            return
        yield path


def copy_item(
    kind: ImportKind, source: Path, base: Path, target_root: Path, content: str, suffix: str
) -> ImportItem:
    """`base/x/y.ext` → `target_root/x/y<suffix>` dosya kopyası satırı."""
    relative = source.relative_to(base).with_suffix(suffix)
    target = target_root / relative
    name = ":".join(relative.with_suffix("").parts)
    return ImportItem(
        kind,
        name,
        ImportStatus.NEW,
        str(source),
        f"→ {target}",
        FileImport(target, content),
    )
