"""İçe aktarma planının veri tipleri (P-071).

Plan önce ÖNİZLENİR, sonra onaylanınca uygulanır (Claude Code `/import --dry-run`/`--yes`).
Her satır ne bulunduğunu, nereden geldiğini ve ne olacağını söyler; sır DEĞERİ hiçbir
satırda görünmez — yalnız adı ve şifreli depoya gideceği yazılır.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from ..models import McpServerConfig
from ..permission_rules import PermissionRule


class ImportKind(StrEnum):
    """İçe aktarılan şeyin türü (kullanıcıya bu adlarla görünür)."""

    MCP = "mcp"
    PERMISSION = "izin"
    INSTRUCTION = "talimat"
    COMMAND = "komut"
    RULE = "kural"
    SKILL = "beceri"
    SETTING = "ayar"


class ImportStatus(StrEnum):
    """Satırın akıbeti."""

    NEW = "eklenecek"
    EXISTS = "zaten var"
    #: Fusion bu dosyayı zaten doğrudan okuyor; taşımaya gerek yok.
    NATIVE = "zaten okunuyor"
    SKIPPED = "atlandı"


@dataclass(frozen=True, slots=True)
class McpImport:
    """Kullanıcı `config.yaml`'ına yazılacak sunucu ve şifreli depoya gidecek sırlar."""

    server: McpServerConfig
    #: `(ortam adı, değer)`; değer YALNIZ şifreli depoya yazılır.
    secrets: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class RuleImport:
    """Fusion'ın kullanıcı izin dosyasına eklenecek kural."""

    rule: PermissionRule


@dataclass(frozen=True, slots=True)
class FileImport:
    """Yoksa oluşturulacak dosya (var olanın üzerine YAZILMAZ)."""

    target: Path
    content: str


@dataclass(frozen=True, slots=True)
class LineImport:
    """Dosyada yoksa sonuna eklenecek tek satır (ör. `@~/.gemini/GEMINI.md`)."""

    target: Path
    line: str


ImportAction = McpImport | RuleImport | FileImport | LineImport


@dataclass(frozen=True, slots=True)
class ImportItem:
    """Önizleme satırı: tür · ad · durum · ayrıntı · kaynak dosya."""

    kind: ImportKind
    name: str
    status: ImportStatus
    origin: str
    detail: str = ""
    action: ImportAction | None = None


@dataclass(frozen=True, slots=True)
class ImportPlan:
    """Bir kaynaktan (claude, codex, gemini, cursor) çıkarılan önizleme."""

    source: str
    items: tuple[ImportItem, ...] = ()
    #: Okunamayan/bozuk dosyalar (plan yine kurulur).
    warnings: tuple[str, ...] = ()

    @property
    def pending(self) -> tuple[ImportItem, ...]:
        """Uygulanacak satırlar."""
        return tuple(item for item in self.items if item.status is ImportStatus.NEW)


@dataclass(frozen=True, slots=True)
class ImportReport:
    """Uygulamanın sonucu."""

    applied: tuple[ImportItem, ...] = ()
    #: `(satır, Türkçe neden)`.
    failed: tuple[tuple[ImportItem, str], ...] = ()
    #: Yazılan dosyalar (gösterim için).
    written: tuple[Path, ...] = ()
