"""`/rewind` — çok adımlı checkpoint'e geri sarma (kod + konuşma / yalnız konuşma / yalnız kod).

Komut saf ve senkrondur: durumu değiştirir, tek metin döndürür. Seçicileri yüzeyler
açar — düz REPL `pick()`, TUI uygulama-içi modal, masaüstü `komut.secenekler` — ve seçimi
ARGÜMAN olarak buraya verir (`/rewind 3 kod`). Böylece üç yüzey tek işleyiciyi paylaşır.
Esc Esc (TUI, boş girdi) aynı komutu gönderir.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from ...core.turn_checkpoints import (
    RewindResult,
    RewindScope,
    TurnCheckpoint,
    TurnCheckpointLedger,
    parse_scope,
)
from ...ui import messages
from ...ui.picker import Choice, pick
from .state import ReplState
from .transcript_store import TranscriptStore

#: Seçim listesinde görev metninin en fazla uzunluğu.
TASK_PREVIEW_CHARS = 60
_REWIND_CONFLICT = "Geri alma çakışması: {count} dosya ve ilk kayıtları korundu."


def turn_choices(entries: Sequence[TurnCheckpoint]) -> list[Choice]:
    """Checkpoint'leri yeniden eskiye seçim satırlarına çevir."""
    return [
        Choice(
            str(entry.index),
            messages.REWIND_TURN_LABEL.format(
                index=entry.index, task=_preview(entry.task, TASK_PREVIEW_CHARS)
            ),
            messages.REWIND_TURN_DETAIL.format(
                when=_when(entry.created_at), files=len(entry.changed_paths)
            ),
        )
        for entry in reversed(entries)
    ]


#: Menünün "Never mind" satırının değeri; argüman olarak gelirse hiçbir şey yapılmaz (#199).
CANCEL_VALUE = "vazgec"


def scope_choices(entries: Sequence[TurnCheckpoint] = (), index: int | None = None) -> list[Choice]:
    """Kapsam seçenekleri; sıra Claude Code'unkidir, sonda 'Vazgeç' satırı durur (#199).

    Kod seçenekleri yalnız hedef ya da sonraki turlarda izlenen dosya değişikliği varsa
    görünür. Defter verilmezse (eski çağıranlar) hepsi gösterilir.
    """
    has_code = not entries or any(
        entry.changes for entry in entries if index is None or entry.index >= index
    )
    rows = [
        *((Choice(RewindScope.BOTH.value, messages.REWIND_SCOPE_BOTH, ""),) if has_code else ()),
        Choice(RewindScope.CONVERSATION.value, messages.REWIND_SCOPE_CONVERSATION, ""),
        *((Choice(RewindScope.CODE.value, messages.REWIND_SCOPE_CODE, ""),) if has_code else ()),
    ]
    return [*rows, Choice(CANCEL_VALUE, messages.REWIND_CANCEL, "")]


def parse_arguments(
    argument: str, ledger: TurnCheckpointLedger
) -> tuple[int | None, RewindScope | None, str]:
    """`/rewind [no] [kapsam]` argümanını (tur, kapsam, hata) üçlüsüne çevir.

    İki parçanın sırası serbesttir (`/rewind kod 3` de geçer). Eksik parça `None`
    döner; yüzey onu seçtirir. Hata doluysa diğer ikisi anlamsızdır.
    """
    index: int | None = None
    scope: RewindScope | None = None
    for word in argument.split():
        if word.isdigit():
            if index is not None:
                return None, None, messages.REWIND_USAGE
            index = int(word)
            continue
        parsed = parse_scope(word)
        if parsed is None or scope is not None:
            return None, None, messages.REWIND_USAGE
        scope = parsed
    if index is not None and ledger.find(index) is None:
        return None, None, messages.REWIND_UNKNOWN_TURN.format(index=index)
    return index, scope, ""


def rewind_command(state: ReplState, argument: str) -> str:
    """`/rewind [no] [kod|konuşma|ikisi]` — seçilen turun başına dön."""
    entries = state.checkpoints.entries()
    if not entries:
        return messages.REWIND_NOTHING
    if CANCEL_VALUE in argument.split():
        return ""
    index, scope, error = parse_arguments(argument, state.checkpoints)
    if error:
        return error
    if index is None:
        chosen = pick(turn_choices(entries), title=messages.REWIND_PICK_TURN)
        if chosen is None:
            return ""
        index = int(chosen)
    if scope is None:
        picked = pick(scope_choices(entries, index), title=messages.REWIND_PICK_SCOPE)
        if picked is None or picked == CANCEL_VALUE:
            return ""
        scope = parse_scope(picked) or RewindScope.BOTH
    return apply_rewind(state, index, scope)


def apply_rewind(state: ReplState, index: int, scope: RewindScope) -> str:
    """Geri sarmayı duruma uygula ve tek satırlık sonucu döndür.

    Konuşma geri sarılınca hedef turun istemi giriş kutusuna konur (Claude Code #200).
    """
    target = state.checkpoints.find(index)
    try:
        result = state.checkpoints.rewind(index, scope)
    except ValueError:
        return messages.REWIND_UNKNOWN_TURN.format(index=index)
    if result.history is not None:
        state.history = list(result.history)
        state.pending_input = target.task if target is not None else ""
        # Transcript eklemelidir: silinen mesaj kalır, yükleyici olaydan sonrasını atlar.
        TranscriptStore(
            state.config.memory_dir, state.root, conversation_id=state.conversation_id
        ).record_rewind(result.keep_users)
    if scope is not RewindScope.CONVERSATION:
        # `/undo`'nun bakacağı son tur kaydı geri alındı ya da düştü.
        state.last_changes = None
    from . import session_snapshot

    session_snapshot.save(state)
    return summarize(result)


def undo_last(state: ReplState) -> str:
    """`/undo` kısayolu: son turun yalnız KOD değişikliklerini geri al."""
    latest = state.checkpoints.latest()
    if latest is None:
        return messages.UNDO_NOTHING
    if not latest.changes:
        # Dosya değiştirmeyen tur: geri alınacak kod yok; kayıt yine de düşmesin.
        return messages.UNDO_NOTHING
    return apply_rewind(state, latest.index, RewindScope.CODE)


def summarize(result: RewindResult) -> str:
    """Sonucu kullanıcı diline çevir: kaç dosya, kaç mesaj, neresi başarısız."""
    lines: list[str] = []
    if result.scope is not RewindScope.CONVERSATION:
        if result.restored or result.failed:
            lines.append(
                messages.REWIND_CODE_DONE.format(index=result.index, count=len(result.restored))
            )
            lines.extend(f"  {path}" for path in result.restored)
            if result.conflicts:
                lines.append(_REWIND_CONFLICT.format(count=len(result.conflicts)))
                lines.extend(
                    f"  {conflict.path}: {conflict.reason}" for conflict in result.conflicts
                )
            protected = {conflict.path for conflict in result.conflicts}
            failed = tuple(path for path in result.failed if path not in protected)
            if failed:
                lines.append(messages.REWIND_CODE_FAILED.format(count=len(failed)))
                lines.extend(f"  {path}" for path in failed)
        else:
            lines.append(messages.REWIND_CODE_EMPTY.format(index=result.index))
    if result.history is not None:
        lines.append(
            messages.REWIND_CONVERSATION_DONE.format(index=result.index, count=len(result.history))
        )
    return "\n".join(lines)


def _preview(text: str, limit: int) -> str:
    first = text.strip().splitlines()[0] if text.strip() else ""
    return first if len(first) <= limit else first[: limit - 1] + "…"


def _when(epoch: float) -> str:
    if not epoch:
        return ""
    return datetime.fromtimestamp(epoch).strftime("%H:%M")
