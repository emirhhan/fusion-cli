"""Plan kipi kabul kartı ve `/plan` alt komutları (P-025, REPL yüzeyi).

Masaüstündeki "Plan hazır" kartıyla (`SessionApplication.tsx`) AYNI dört seçenek ve
aynı sıra: otomatik kip / düzenlemeleri kabul / her adımda sor / planlamaya devam.
Kabul edilen kip `ReplState.approval`'a yazılır, oturum izinleri sıfırlanır ve
uygulama görevi sonraki tur olarak döner (`loop.py`/`tui_loop.py` çalıştırır).
"""

from __future__ import annotations

import subprocess

from rich.console import Console
from rich.markup import escape

from ...config.paths import preferred_editor
from ...engines.agent import plan_mode
from ...engines.agent.approval import ApprovalMode
from ...ui import messages, theme
from ...ui.picker import Choice, pick
from .state import ReplState

CHOICE_AUTO = "auto"
CHOICE_EDITS = "edits"
CHOICE_SECURITY = "security"
CHOICE_KEEP_PLANNING = "plan"

#: Seçim değeri → kabul sonrası kip. Planlamaya devam kip değiştirmez (None).
_MODES: dict[str, ApprovalMode | None] = {
    CHOICE_AUTO: ApprovalMode.AUTO,
    CHOICE_EDITS: ApprovalMode.ACCEPT_EDITS,
    CHOICE_SECURITY: ApprovalMode.SECURITY,
    CHOICE_KEEP_PLANNING: None,
}


def choices() -> tuple[Choice, ...]:
    """Kartın seçenekleri; masaüstü kartıyla aynı metin ve sıra."""
    return (
        Choice(CHOICE_AUTO, messages.PLAN_CARD_AUTO, messages.PLAN_CARD_AUTO_DESC),
        Choice(CHOICE_EDITS, messages.PLAN_CARD_EDITS, messages.PLAN_CARD_EDITS_DESC),
        Choice(CHOICE_SECURITY, messages.PLAN_CARD_SECURITY, messages.PLAN_CARD_SECURITY_DESC),
        Choice(CHOICE_KEEP_PLANNING, messages.PLAN_CARD_KEEP, messages.PLAN_CARD_KEEP_DESC),
    )


def mode_for(choice: str | None) -> ApprovalMode | None:
    """Seçimin kipi; vazgeçme ve "planlamaya devam" için None."""
    return _MODES.get(choice or "")


def accept(state: ReplState, mode: ApprovalMode) -> str:
    """Planı kabul et: kipi değiştir, oturum izinlerini sıfırla, uygulama görevini ver."""
    path = state.pending_plan or plan_mode.plan_path(state.conversation_id)
    state.pending_plan = None
    if mode is not state.approval:
        state.approval_memory.revoke()
    state.approval = mode
    return messages.PLAN_IMPLEMENT_TASK.format(path=path)


def decline(state: ReplState) -> str:
    """Planlamaya devam: kip değişmez, kart kapanır."""
    state.pending_plan = None
    return messages.PLAN_KEEP_PLANNING


async def offer(state: ReplState, console: Console, *, interactive: bool) -> str | None:
    """Bekleyen plan varsa kartı göster; kabul edilirse çalıştırılacak görevi döndür.

    Etkileşimsiz ortamda (boru, CI) seçici açılmaz: yol basılır, plan kipinde kalınır.
    """
    if state.pending_plan is None:
        return None
    console.print(
        f"[{theme.DIM}]{escape(messages.PLAN_SAVED.format(path=state.pending_plan))}[/{theme.DIM}]"
    )
    if not interactive:
        state.pending_plan = None
        return None
    selected = pick(list(choices()), title=messages.PLAN_CARD_TITLE)
    mode = mode_for(selected)
    if mode is None:
        console.print(f"[{theme.DIM}]{decline(state)}[/{theme.DIM}]")
        return None
    task = accept(state, mode)
    console.print(
        f"[{theme.DIM}]{messages.REPL_MODE_CHANGED.format(mode=mode.value)}[/{theme.DIM}]"
    )
    return task


def show(state: ReplState) -> str:
    """`/plan goster`: kayıtlı planı ve yolunu yaz."""
    text = plan_mode.read_plan(state.conversation_id)
    if text is None:
        return messages.PLAN_NONE
    path = plan_mode.plan_path(state.conversation_id)
    return f"{messages.PLAN_SAVED.format(path=path)}\n\n{text.rstrip()}"


def open_in_editor(state: ReplState) -> str:
    """`/plan ac`: planı `VISUAL`/`EDITOR` ile aç; editör yoksa yolu söyle."""
    if plan_mode.read_plan(state.conversation_id) is None:
        return messages.PLAN_NONE
    path = plan_mode.plan_path(state.conversation_id)
    editor = preferred_editor()
    if editor is None:
        return messages.PLAN_NO_EDITOR.format(path=path)
    try:
        _launch([*editor.split(), str(path)])
    except OSError as error:
        return messages.PLAN_EDITOR_FAILED.format(error=error, path=path)
    return messages.PLAN_OPENED.format(editor=editor, path=path)


def _launch(argv: list[str]) -> None:
    """Editörü ön planda çalıştır ve dönüşünü bekle (terminal editörleri ekranı devralır)."""
    subprocess.run(argv, check=False)


def command(state: ReplState, argument: str) -> str:
    """`/plan [açıklama]`: plan kipine geçer; açıklama verilirse onu hemen görev yapar (#75).

    Claude Code'daki gibi argüman ilk istemdir. Fusion'ın eski tek sözcüklük alt komutları
    (`goster`, `ac`) planı göstermek/açmak için çalışmayı sürdürür.
    """
    text = argument.strip()
    sub = text.casefold()
    if sub in {"goster", "göster"}:
        return show(state)
    if sub in {"ac", "aç"}:
        return open_in_editor(state)
    state.approval = ApprovalMode.PLAN
    changed = messages.REPL_MODE_CHANGED.format(mode=ApprovalMode.PLAN.value)
    if not text:
        return changed
    state.pending_task = text
    return changed


__all__ = [
    "CHOICE_AUTO",
    "CHOICE_EDITS",
    "CHOICE_KEEP_PLANNING",
    "CHOICE_SECURITY",
    "accept",
    "choices",
    "command",
    "decline",
    "mode_for",
    "offer",
    "open_in_editor",
    "show",
]
