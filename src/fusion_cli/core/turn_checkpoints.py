"""Tur başına kod + konuşma checkpoint'i ve seçimli geri sarma (`/rewind`).

Claude Code her kullanıcı promptunda bir checkpoint alır ve `/rewind` ile "kod + konuşma /
yalnız konuşma / yalnız kod" geri sarabilir. Fusion'da `/undo` yalnız SON turu tutuyordu
(`ReplState.last_changes`). Bu defter her turun başında iki şeyi saklar:

- **Konuşma**: turdan ÖNCEKİ motor geçmişi (mesaj listesi kopyası).
- **Kod**: turun `ChangeSet`'i — ajan her yazmadan önce dosyanın ilk hâlini oraya alır.

Kayıtlar BELLEKTE durur, diske yazılmaz: içerik kullanıcının kaynak kodudur ve
`ChangeSet` ile aynı gerekçeyle (sızıntı yüzeyi) kopyalanmaz. Kapsam bu süreçtir;
`fusion --continue` ile açılan sohbette konuşma geri gelir ama önceki sürecin kod
checkpoint'leri gelmez — bu bilinen sınır belgelenmiştir.

Ölçüldü (31 Ekim): `commands._undo` yalnız `last_changes`'i geri alıyordu; üç tur önceki
değişikliğe dönmenin ya da konuşmayı geri sarmanın yolu yoktu.
"""

from __future__ import annotations

import dataclasses
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .changeset import ChangeSet
from .types import Message

#: Bellekte tutulacak en fazla checkpoint (Claude Code ile aynı tavan). Eskisi düşer.
MAX_TURN_CHECKPOINTS = 100


class RewindScope(Enum):
    """Neyin geri sarılacağı. Değerler komut argümanıdır (`/rewind 3 kod`)."""

    BOTH = "ikisi"
    CONVERSATION = "konusma"
    CODE = "kod"


#: Kullanıcının yazabileceği eş anlamlılar → kapsam.
_SCOPE_WORDS: dict[str, RewindScope] = {
    "ikisi": RewindScope.BOTH,
    "both": RewindScope.BOTH,
    "hepsi": RewindScope.BOTH,
    "konusma": RewindScope.CONVERSATION,
    "konuşma": RewindScope.CONVERSATION,
    "conversation": RewindScope.CONVERSATION,
    "kod": RewindScope.CODE,
    "code": RewindScope.CODE,
}


def parse_scope(text: str) -> RewindScope | None:
    """`kod` / `konuşma` / `ikisi` sözcüğünü kapsama çevir; tanınmazsa `None`."""
    return _SCOPE_WORDS.get(text.strip().casefold())


@dataclass(frozen=True, slots=True)
class TurnCheckpoint:
    """Bir turun başındaki durum: konuşma kopyası + turun dosya kaydı."""

    #: 1 tabanlı, oturum boyunca artan tur numarası (`/rewind <no>`).
    index: int
    #: Turu başlatan kullanıcı metni (listede tanıma ipucu).
    task: str
    created_at: float
    history_before: tuple[Message, ...]
    changes: ChangeSet

    @property
    def changed_paths(self) -> tuple[Path, ...]:
        return self.changes.paths

    @property
    def user_messages_before(self) -> int:
        """Turdan önceki kullanıcı mesajı sayısı; transcript geri sarması bunu kullanır."""
        return sum(1 for message in self.history_before if message.role == "user")


@dataclass(frozen=True, slots=True)
class RewindResult:
    """Geri sarmanın sonucu; çağıran durumu buna göre günceller."""

    scope: RewindScope
    #: Hedef turun numarası.
    index: int
    restored: tuple[Path, ...] = ()
    failed: tuple[Path, ...] = ()
    #: Konuşma geri sarıldıysa yeni geçmiş; yalnız kod sarıldıysa `None`.
    history: tuple[Message, ...] | None = None
    #: Konuşma geri sarıldıysa kalan kullanıcı mesajı sayısı (transcript için).
    keep_users: int = 0
    #: Defterden düşen tur sayısı.
    dropped_turns: int = 0


class TurnCheckpointLedger:
    """Oturumun tur checkpoint'leri; `begin` ile açılır, `rewind` ile geri sarılır."""

    def __init__(
        self, *, limit: int = MAX_TURN_CHECKPOINTS, clock: Callable[[], float] = time.time
    ) -> None:
        self._entries: list[TurnCheckpoint] = []
        self._next_index = 1
        self._limit = max(1, limit)
        self._clock = clock

    def begin(self, task: str, history_before: Sequence[Message]) -> TurnCheckpoint:
        """Tur başında çağrılır. Dönen kaydın `changes`'i turun `ToolContext`'ine verilir."""
        checkpoint = TurnCheckpoint(
            index=self._next_index,
            task=task,
            created_at=self._clock(),
            history_before=tuple(history_before),
            changes=ChangeSet(),
        )
        self._next_index += 1
        self._entries.append(checkpoint)
        # Tavan aşılınca EN ESKİ düşer; onun dosya kaydı artık geri alınamaz.
        del self._entries[: max(0, len(self._entries) - self._limit)]
        return checkpoint

    def entries(self) -> tuple[TurnCheckpoint, ...]:
        """Eskiden yeniye tüm checkpoint'ler."""
        return tuple(self._entries)

    def latest(self) -> TurnCheckpoint | None:
        return self._entries[-1] if self._entries else None

    def find(self, index: int) -> TurnCheckpoint | None:
        return next((entry for entry in self._entries if entry.index == index), None)

    def clear(self) -> None:
        """Sohbet değişince (`/resume`, `/branch`) eski turların kaydı anlamını yitirir."""
        self._entries.clear()

    def rewind(self, index: int, scope: RewindScope) -> RewindResult:
        """`index` numaralı turun BAŞINA dön.

        Kod: hedef ve sonraki turların dosyaları yeniden eskiye geri alınır; böylece
        birden çok turda değişen dosyada en eski (hedef turdan önceki) hâl kazanır.
        Konuşma: geçmiş hedef turun öncesine iner. Yalnız konuşma sarıldığında kod
        kayıtları KORUNUR (dosyalar hâlâ değişik durumdadır) ama konuşma kopyaları
        yeni geçmişe eşitlenir — eski konuşmaya "geri dönülmez".
        """
        target = self.find(index)
        if target is None:
            raise ValueError(f"Checkpoint bulunamadı: {index}")
        affected = [entry for entry in self._entries if entry.index >= index]
        restored: list[Path] = []
        failed: list[Path] = []
        if scope in (RewindScope.BOTH, RewindScope.CODE):
            for entry in reversed(affected):
                expected = entry.changes.restorable_paths
                done = entry.changes.restore()
                restored.extend(path for path in done if path not in restored)
                failed.extend(path for path in expected if path not in done and path not in failed)
        history: tuple[Message, ...] | None = None
        keep_users = 0
        if scope in (RewindScope.BOTH, RewindScope.CONVERSATION):
            history = target.history_before
            keep_users = target.user_messages_before
        if scope is RewindScope.CONVERSATION:
            # Kod kayıtları kalır; konuşma kopyaları artık geçerli tek geçmişe işaret eder.
            self._entries = [
                dataclasses.replace(entry, history_before=history or ())
                if entry.index >= index
                else entry
                for entry in self._entries
            ]
            dropped = 0
        else:
            self._entries = [entry for entry in self._entries if entry.index < index]
            dropped = len(affected)
        return RewindResult(
            scope=scope,
            index=index,
            restored=tuple(restored),
            failed=tuple(failed),
            history=history,
            keep_users=keep_users,
            dropped_turns=dropped,
        )
