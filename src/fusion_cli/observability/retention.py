"""Fusion'ın kendi ürettiği dosyaların yaşa göre temizliği (L1-30).

Yalnız çağıranın verdiği Fusion klasöründe, yalnız verilen uzantılı DÜZENLİ dosyalarda
çalışır. Sembolik bağlar izlenmez ve silinmez; bağın gösterdiği dosyaya hiç dokunulmaz.
Kullanıcının dosyasına benzeyen (başka uzantılı) hiçbir şey silinmez.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Collection
from pathlib import Path

_LOG = logging.getLogger(__name__)


def _is_expired_file(entry: os.DirEntry[str], suffixes: Collection[str], cutoff: float) -> bool:
    try:
        if entry.is_symlink() or not entry.is_file(follow_symlinks=False):
            return False
        if Path(entry.name).suffix not in suffixes:
            return False
        return entry.stat(follow_symlinks=False).st_mtime < cutoff
    except OSError:
        return False


def _remove(path: str) -> bool:
    try:
        Path(path).unlink(missing_ok=True)
    except OSError as error:
        _LOG.warning("Saklama temizliği dosyayı silemedi: %s", type(error).__name__)
        return False
    return True


def purge_files(directory: Path, *, suffixes: Collection[str], cutoff: float) -> int:
    """`directory` içindeki (alt klasörsüz) eski düzenli dosyaları sil; silinen sayıyı döndür."""
    removed = 0
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                if _is_expired_file(entry, suffixes, cutoff) and _remove(entry.path):
                    removed += 1
    except OSError:
        return removed
    return removed


def purge_session_dirs(directory: Path, *, suffixes: Collection[str], cutoff: float) -> int:
    """Her doğrudan alt klasörde eski dosyaları sil; boşalan klasörü de kaldır.

    Artifact deposu `<oturum>/<sıra>-<ad>.txt` düzenindedir. Sembolik bağlı klasörler
    atlanır; içinde yabancı dosya kalan klasör silinmez.
    """
    removed = 0
    try:
        with os.scandir(directory) as entries:
            sessions = [
                Path(entry.path)
                for entry in entries
                if entry.is_dir(follow_symlinks=False) and not entry.is_symlink()
            ]
    except OSError:
        return 0
    for session in sessions:
        removed += purge_files(session, suffixes=suffixes, cutoff=cutoff)
        try:
            session.rmdir()  # yalnız boşsa başarılı olur
        except OSError:
            continue
    return removed
