"""Yerel durum saklama: 30 günden eski iz, artifact ve tamamlanmış checkpoint (L1-30, M1-44).

Yalnız `memory_dir` altındaki Fusion klasörlerine bakar (`traces`, `hook-transcripts`,
`artifacts`, `workflow-checkpoints`). Denetim günlüğü (`audit`), konuşma dökümleri ve
kullanıcı dosyaları kapsam dışıdır. Açılışta ucuz çalışır: günde en çok bir kez (damga
dosyası), önce dosya değişme zamanına bakar.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from ..core.constants import LOCAL_STATE_PURGE_INTERVAL_S, LOCAL_STATE_RETENTION_S
from ..memory.checkpoint_store import JsonCheckpointStore
from ..observability.retention import purge_files, purge_session_dirs
from .hooks.transcript import HOOK_TRANSCRIPT_DIR

__all__ = [
    "LOCAL_STATE_RETENTION_S",
    "RetentionReport",
    "purge_local_state",
    "purge_local_state_daily",
]

_LOG = logging.getLogger(__name__)
_STAMP_NAME = ".saklama-damgasi"
_TRACE_SUFFIXES = frozenset({".jsonl"})
_ARTIFACT_SUFFIXES = frozenset({".txt"})


@dataclass(frozen=True, slots=True)
class RetentionReport:
    """Bir temizlik turunda silinen dosya sayıları."""

    traces: int = 0
    artifacts: int = 0
    checkpoints: int = 0


def purge_local_state(
    memory_dir: Path, *, now: float, max_age_s: float = LOCAL_STATE_RETENTION_S
) -> RetentionReport:
    """`max_age_s`ten eski Fusion üretimi dosyaları sil."""
    cutoff = now - max_age_s
    return RetentionReport(
        traces=purge_files(memory_dir / "traces", suffixes=_TRACE_SUFFIXES, cutoff=cutoff)
        # Kancaların `transcript_path` dökümleri (Claude `cleanupPeriodDays`: 30 gün).
        + purge_files(memory_dir / HOOK_TRANSCRIPT_DIR, suffixes=_TRACE_SUFFIXES, cutoff=cutoff),
        artifacts=purge_session_dirs(
            memory_dir / "artifacts", suffixes=_ARTIFACT_SUFFIXES, cutoff=cutoff
        ),
        checkpoints=JsonCheckpointStore(memory_dir / "workflow-checkpoints").purge_completed(
            cutoff=cutoff
        ),
    )


def purge_local_state_daily(memory_dir: Path, *, now: float) -> RetentionReport | None:
    """Son temizlikten bir günden az geçtiyse `None`; yoksa temizler ve damgayı yeniler.

    Hata açılışı bozmaz: temizlik en iyi çabadır.
    """
    stamp = memory_dir / _STAMP_NAME
    try:
        if now - stamp.stat().st_mtime < LOCAL_STATE_PURGE_INTERVAL_S:
            return None
    except FileNotFoundError:
        pass
    except OSError:
        return None
    try:
        # Damga ÖNCE yenilenir: aynı anda başlayan ikinci çağıran (CLI turu ile uygulama
        # arka planı) aynı dosyaları ikinci kez taramaz. Temizlik yarıda kalırsa yarın sürer.
        memory_dir.mkdir(parents=True, exist_ok=True)
        stamp.touch()
        os.utime(stamp, (now, now))
        report = purge_local_state(memory_dir, now=now)
    except OSError as error:
        _LOG.warning("Yerel durum temizliği tamamlanamadı: %s", type(error).__name__)
        return None
    return report
