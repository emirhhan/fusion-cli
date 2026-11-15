"""Claude Code eklenti sürüm hesabı ve eski sürüm temizliği (#393, #408).

Belge (code.claude.com/docs/en/plugins/loading.md, "How Claude Code computes the version"):
sürüm sırasıyla plugin.json `version`, pazar girdisinin `version`'ı, ikisi de yoksa kaynağın
commit SHA'sının ilk 12 karakteri (`git-subdir`'de alt klasör yolunun karması da eklenir); yerel
klasör ve npm için `unknown`. `update` sürümü yeniden hesaplar; aynıysa kopyaya dokunmaz.

"Cleanup of previous versions": güncellenen ya da kaldırılan eklentinin önceki klasörüne
`.orphaned_at` işareti yazılır, klasör 14 gün sonra arka plan temizliğinde silinir (o sürümü
yüklemiş açık oturum çalışmayı sürdürür). Fusion'da kopya `<eklentiler>/.orphaned/` altına taşınır
ki aynı ad yeniden kurulabilsin; temizlik kurulum/kaldırma/güncellemede çalışır.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import time
from pathlib import Path

_LOG = logging.getLogger(__name__)

UNKNOWN_VERSION = "unknown"
SHORT_SHA = 12
ORPHAN_DIR = ".orphaned"
ORPHAN_MARKER = ".orphaned_at"
ORPHAN_TTL_S = 14 * 86400
_SUBDIR_HASH = 8


def resolve_version(manifest: str, entry: str, commit: str, *, subdir: str = "") -> str:
    """Claude sırası: manifest → girdi → commit[:12] (+ alt klasör karması) → `unknown`."""
    for value in (manifest, entry):
        if value.strip():
            return value.strip()
    if not commit:
        return UNKNOWN_VERSION
    short = commit.strip().lower()[:SHORT_SHA]
    if not subdir:
        return short
    digest = hashlib.sha256(subdir.strip("/").encode("utf-8")).hexdigest()[:_SUBDIR_HASH]
    return f"{short}-{digest}"


def orphan(folder: Path, root: Path, *, now: float | None = None) -> Path:
    """Önceki sürüm klasörünü `.orphaned/` altına taşı ve `.orphaned_at` işaretini yaz."""
    stamp = time.time() if now is None else now
    target_root = root / ORPHAN_DIR
    target_root.mkdir(parents=True, exist_ok=True)
    target = target_root / f"{folder.name}-{int(stamp * 1000)}"
    shutil.move(str(folder), target)
    (target / ORPHAN_MARKER).write_text(str(int(stamp * 1000)), encoding="utf-8")
    return target


def orphaned_dirs(root: Path) -> tuple[Path, ...]:
    base = root / ORPHAN_DIR
    if not base.is_dir():
        return ()
    return tuple(sorted(p for p in base.iterdir() if (p / ORPHAN_MARKER).is_file()))


def _marked_at(folder: Path) -> float | None:
    try:
        return int((folder / ORPHAN_MARKER).read_text(encoding="utf-8").strip()) / 1000
    except (OSError, ValueError):
        return None


def sweep_orphans(root: Path, *, now: float | None = None) -> tuple[Path, ...]:
    """İşaretinden 14 gün geçmiş eski sürüm klasörlerini sil; silinenleri döndür."""
    current = time.time() if now is None else now
    removed: list[Path] = []
    for folder in orphaned_dirs(root):
        marked = _marked_at(folder)
        if marked is None or current - marked < ORPHAN_TTL_S:
            continue
        try:
            shutil.rmtree(folder)
        except OSError as error:
            _LOG.warning("eski eklenti sürümü silinemedi (%s): %s", folder, error)
            continue
        removed.append(folder)
    return tuple(removed)
