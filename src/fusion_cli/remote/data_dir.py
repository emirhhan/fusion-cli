"""Uzak erişim verisinin yeri ve eski `~/remote` konumundan otomatik göç.

Ölçüldü (30 Ekim): denetleyici `home / "remote"` kullanıyordu; gerçek kullanıcıda bu
`~/remote/devices.json` ve `projects.json` üretiyordu. Doğru yer Fusion veri dizinidir
(`<veri>/remote`). Göç dosya başınadır, dosya yeni yerde yoksa çalışır: kopyala, doğrula,
eskiyi `.migrated` yap. Eşleşmiş telefonlar kopmaz. İki yerde de varsa yeni kullanılır
ve eskiye dokunulmaz (kullanıcı uyarılır).
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
import shutil
import sqlite3
import tempfile
from pathlib import Path

from ..config.paths import base_data_dir
from ..config.writer import config_lock

_logger = logging.getLogger(__name__)

MIGRATED_SUFFIX = ".migrated"
#: SQLite yan dosyaları ana veritabanıyla birlikte taşınır; tek başlarına işlenmez.
_SQLITE_SIDECARS = ("-wal", "-shm")
_SQLITE_SUFFIXES = (".sqlite3", ".sqlite", ".db")


def remote_data_dir() -> Path:
    """Hesaptan bağımsız Fusion veri dizini altında uzak erişim klasörü."""
    return base_data_dir() / "remote"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree_signature(root: Path) -> list[tuple[str, int]]:
    return sorted(
        (str(item.relative_to(root)), item.stat().st_size)
        for item in root.rglob("*")
        if item.is_file()
    )


def _same(source: Path, copy: Path) -> bool:
    if source.is_dir() != copy.is_dir():
        return False
    if source.is_dir():
        return _tree_signature(source) == _tree_signature(copy)
    return _digest(source) == _digest(copy)


def _copy_sqlite(source: Path, target: Path) -> bool:
    """Çevrimiçi yedekleme API'si: WAL içeriğini de katar. Doğrulama: bütünlük denetimi."""
    reader = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    writer = sqlite3.connect(target)
    try:
        reader.backup(writer)
        writer.commit()
        return bool(writer.execute("PRAGMA integrity_check").fetchone() == ("ok",))
    finally:
        writer.close()
        reader.close()


def _copy_to_temporary(source: Path, target: Path) -> Path | None:
    """`target`ın yanında geçici kopya üret ve doğrula; başarısızsa None (geçici silinir)."""
    handle = tempfile.mkdtemp(dir=target.parent, prefix=f".{target.name}.tmp")
    temporary = Path(handle) / target.name
    try:
        if source.is_dir():
            shutil.copytree(source, temporary)
            good = _same(source, temporary)
        elif source.name.endswith(_SQLITE_SUFFIXES):
            good = _copy_sqlite(source, temporary)
        else:
            shutil.copy2(source, temporary)
            good = _same(source, temporary)
    except (OSError, sqlite3.Error) as error:
        _logger.warning("Uzak erişim verisi kopyalanamadı (%s): %s", source.name, error)
        good = False
    if good:
        return temporary
    shutil.rmtree(handle, ignore_errors=True)
    return None


def _retire(path: Path) -> None:
    """Eski girdiyi (ve SQLite yan dosyalarını) `.migrated` adına çevir; silmez."""
    for candidate in (path, *(path.with_name(path.name + s) for s in _SQLITE_SIDECARS)):
        if not candidate.exists():
            continue
        retired = candidate.with_name(candidate.name + MIGRATED_SUFFIX)
        counter = 1
        while retired.exists():
            retired = candidate.with_name(f"{candidate.name}{MIGRATED_SUFFIX}.{counter}")
            counter += 1
        candidate.rename(retired)


def _migrate_entry(source: Path, target: Path) -> bool:
    """Tek girdiyi taşı; taşındıysa True."""
    if target.exists():
        if _same(source, target) and not source.is_dir() and not target.is_dir():
            if not source.name.endswith(_SQLITE_SUFFIXES):
                _retire(source)  # yarım kalmış önceki göç: içerik aynı, sessizce bitir
            return False
        _logger.warning(
            "Uzak erişim verisi hem eski (%s) hem yeni (%s) konumda var; yeni kullanılıyor, "
            "eski dosyaya dokunulmadı.",
            source,
            target,
        )
        return False
    temporary = _copy_to_temporary(source, target)
    if temporary is None:
        return False
    try:
        temporary.replace(target)
    finally:
        shutil.rmtree(temporary.parent, ignore_errors=True)
    _retire(source)
    return True


def migrate_legacy(legacy: Path, target: Path) -> list[str]:
    """`legacy` altındaki her girdiyi `target`a taşı; taşınan adları döndür.

    Hata hiçbir zaman eski veriyi silmez; taşınamayan girdi yerinde kalır. İdempotenttir:
    taşınmış girdiler `.migrated` adındadır ve bir daha işlenmez.
    """
    if not legacy.is_dir():
        return []
    entries = sorted(
        item
        for item in legacy.iterdir()
        if not item.name.endswith(MIGRATED_SUFFIX)
        and ".migrated." not in item.name
        and not item.name.endswith(_SQLITE_SIDECARS)
    )
    if not entries:
        return []
    target.mkdir(mode=0o700, parents=True, exist_ok=True)
    migrated: list[str] = []
    with config_lock(target / "migration"):
        for source in entries:
            with contextlib.suppress(OSError):
                if _migrate_entry(source, target / source.name):
                    migrated.append(source.name)
    return migrated
