"""Eski ortak veri kökünü TEK bir hesaba bağlama (WP02).

Hesapsız düzende bellek, sır deposu, tarayıcı profilleri ve kayıtlar tek kökte
durur ve kime ait olduğu bilinmez. Plan §5 kuralları:

- Otomatik olarak bütün hesaplara KOPYALANMAZ; kullanıcı bir sahip seçer, diğer
  hesaplar boş başlar.
- Veri KOPYALANIR, taşınmaz: eski kök okunur kalır, geri dönüş mümkündür.
- Kesilen taşıma tekrar çalıştırılınca kaldığı yerden tamamlanır ve çoğaltmaz:
  her girdi geçici adla kopyalanıp atomik olarak yerine konur.
- Tarayıcı profili açıkken (Chrome kilidi) taşıma yapılmaz; oturum dosyaları
  yarım kopyalanmasın.
- Sahiplik kararı eski kökte bir işaret dosyasında durur; ikinci bir hesap aynı
  veriyi sahiplenemez.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from ..config.paths import base_data_dir, tenant_data_dir
from ..core.atomic_file import atomic_replace_text
from ..core.execution_context import PERSONAL_WORKSPACE, validate_identifier

#: Eski kökte sahiplik kararını tutan işaret dosyası.
OWNER_MARKER = ".legacy-owner.json"
#: Hesaba göre ayrılmış köklerin klasörü; kendisi taşınmaz.
_TENANTS_DIR = "tenants"
#: Açık bir Chrome profilinin kilit dosyaları.
_BROWSER_LOCKS = ("SingletonLock", "SingletonCookie", "SingletonSocket", "lockfile")
_PARTIAL_SUFFIX = ".tasiniyor-"
_STATE_COPYING = "kopyalaniyor"
_STATE_DONE = "tamamlandi"


class MigrationError(RuntimeError):
    """Kullanıcıya gösterilebilir taşıma engeli."""


@dataclass(frozen=True, slots=True)
class InventoryEntry:
    name: str
    is_dir: bool
    size_bytes: int


@dataclass(frozen=True, slots=True)
class MigrationInventory:
    source: Path
    #: Sahip seçilmişse onun hesabı; boşsa sahipliği belirsizdir.
    owner: str
    entries: tuple[InventoryEntry, ...]


@dataclass(frozen=True, slots=True)
class MigrationResult:
    owner: str
    target: Path
    copied: tuple[str, ...]
    already_done: bool


def migration_inventory(source: Path | None = None) -> MigrationInventory:
    """Taşınacak eski veriyi (boyutlarıyla) ve varsa sahip kararını listeler."""
    root = source or base_data_dir()
    marker = _read_marker(root)
    return MigrationInventory(
        source=root,
        owner=str(marker.get("owner", "")),
        entries=tuple(
            InventoryEntry(path.name, path.is_dir(), _size(path)) for path in _entries(root)
        ),
    )


def migrate_legacy_data(owner: str, *, source: Path | None = None) -> MigrationResult:
    """Eski ortak veriyi `owner` hesabının kişisel çalışma alanına kopyalar."""
    validate_identifier(owner, "hesap")
    root = source or base_data_dir()
    target = tenant_data_dir(owner) / PERSONAL_WORKSPACE
    marker = _read_marker(root)
    claimed = str(marker.get("owner", ""))
    if claimed and claimed != owner:
        raise MigrationError(f"Eski veri zaten başka bir hesaba bağlandı ({claimed}).")
    if claimed == owner and marker.get("state") == _STATE_DONE:
        return MigrationResult(owner, target, (), already_done=True)
    entries = _entries(root)
    _refuse_open_browser(entries)
    _write_marker(root, owner, _STATE_COPYING)
    target.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for entry in entries:
        destination = target / entry.name
        if destination.exists():
            continue  # Kesilmiş önceki çalıştırma bu girdiyi tamamlamıştı.
        _copy_entry(entry, destination)
        copied.append(entry.name)
    _write_marker(root, owner, _STATE_DONE)
    return MigrationResult(owner, target, tuple(copied), already_done=False)


def _entries(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(
        path
        for path in root.iterdir()
        if path.name not in (_TENANTS_DIR, OWNER_MARKER) and _PARTIAL_SUFFIX not in path.name
    )


def _copy_entry(source: Path, target: Path) -> None:
    """Geçici adla kopyala, sonra atomik yerleştir: yarım kopya hedefte görünmez."""
    partial = target.with_name(f"{target.name}{_PARTIAL_SUFFIX}{os.getpid()}")
    if partial.exists():
        _remove(partial)
    try:
        if source.is_dir() and not source.is_symlink():
            shutil.copytree(source, partial, symlinks=True)
        else:
            shutil.copy2(source, partial, follow_symlinks=False)
        partial.replace(target)
    except BaseException:
        _remove(partial)
        raise


def _remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)


def _refuse_open_browser(entries: list[Path]) -> None:
    for entry in entries:
        if not entry.is_dir():
            continue
        for lock in _BROWSER_LOCKS:
            if any(entry.rglob(lock)):
                raise MigrationError(
                    "Açık bir tarayıcı profili var; Fusion tarayıcısını kapatıp tekrar dene."
                )


def _size(path: Path) -> int:
    try:
        if path.is_file() or path.is_symlink():
            return path.lstat().st_size
        return sum(item.lstat().st_size for item in path.rglob("*") if item.is_file())
    except OSError:
        return -1


def _read_marker(root: Path) -> dict[str, object]:
    try:
        value = json.loads((root / OWNER_MARKER).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _write_marker(root: Path, owner: str, state: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    atomic_replace_text(root / OWNER_MARKER, json.dumps({"owner": owner, "state": state}))
