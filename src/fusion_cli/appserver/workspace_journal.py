"""Bir uygulama oturumunda Fusion'ın yaptığı dosya değişikliklerinin günlüğü.

Geri alma yalnız bu günlükteki kayıtlara dayanır: her kayıt değişiklikten ÖNCEKİ
ve SONRAKİ içeriği taşır. Dosyanın şu anki hâli kaydın "sonra" hâliyle aynı
değilse geri alma çatışmadır; kullanıcının sonradan yaptığı iş ezilmez. Kayıt
yoksa önceki sürüm de yoktur — Git taban sürümü kullanıcının commit'lenmemiş
işini taşımadığı için yerine geçemez.

Günlük ayrıca dosyanın TAMAMININ okunduğu (veya yazıldığı) sürümleri tutar:
kesilmiş önizlemenin karması tam dosya yazımına izin vermez.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass

#: Günlüğe kimin yazdığı. Arayüz düzenlemesi ve ajan turu aynı geri alma yolunu izler.
OWNER_UI = "ui"
OWNER_AGENT = "agent"


@dataclass(frozen=True)
class UndoEntry:
    path: str
    existed: bool
    before: bytes
    after: bytes
    diff: str
    added: int
    removed: int
    #: Değişiklikten sonra dosya var mıydı? Ajan dosyayı silmiş olabilir.
    exists_after: bool = True
    owner: str = OWNER_UI


class WorkspaceJournal:
    """Bir uygulama oturumundaki Fusion yazımlarının sınırlı günlüğü."""

    def __init__(self, *, max_entries: int = 20, max_bytes: int = 8 * 1024 * 1024) -> None:
        self._max_entries = max_entries
        self._max_bytes = max_bytes
        self._entries: list[UndoEntry] = []
        self._bytes = 0
        self._full_reads: dict[str, str] = {}

    def record(self, entry: UndoEntry) -> None:
        self._entries.append(entry)
        self._bytes += len(entry.before) + len(entry.after)
        while self._entries and (
            len(self._entries) > self._max_entries or self._bytes > self._max_bytes
        ):
            removed = self._entries.pop(0)
            self._bytes -= len(removed.before) + len(removed.after)

    def latest(self) -> list[UndoEntry]:
        by_path: dict[str, UndoEntry] = {}
        for entry in self._entries:
            by_path[entry.path] = entry
        return list(by_path.values())

    def peek(self, path: str) -> UndoEntry | None:
        """Yolun en son kaydı; günlükten çıkarmaz."""
        for entry in reversed(self._entries):
            if entry.path == path:
                return entry
        return None

    def owns(self, path: str) -> bool:
        return self.peek(path) is not None

    def pop(self, path: str) -> UndoEntry | None:
        for index in range(len(self._entries) - 1, -1, -1):
            entry = self._entries[index]
            if entry.path == path:
                self._entries.pop(index)
                self._bytes -= len(entry.before) + len(entry.after)
                return entry
        return None

    def note_full_read(self, path: str, sha256: str) -> None:
        """İstemci bu sürümün tamamını gördü (tam okuma ya da kendi yazımı)."""
        self._full_reads[path] = sha256

    def has_full_read(self, path: str, sha256: str) -> bool:
        return self._full_reads.get(path) == sha256

    def clear(self) -> None:
        self._entries.clear()
        self._bytes = 0
        self._full_reads.clear()


def text_diff(path: str, before: bytes, after: bytes) -> tuple[str, int, int]:
    """UTF-8 metin için birleşik diff ve eklenen/silinen satır sayısı."""
    old = before.decode("utf-8").splitlines(keepends=True)
    new = after.decode("utf-8").splitlines(keepends=True)
    lines = list(
        difflib.unified_diff(old, new, fromfile=f"a/{path}", tofile=f"b/{path}", lineterm="")
    )
    body = "\n".join(line.rstrip("\n") for line in lines)
    added = sum(1 for line in lines if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in lines if line.startswith("-") and not line.startswith("---"))
    return body, added, removed
