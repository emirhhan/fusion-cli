"""Plan kipi kabul kartı ve `/plan` alt komutları (P-025, REPL yüzeyi).

Claude Code (permission-modes, "Review and approve a plan") üç seçenek sunar (#325):
"Yes, and use auto mode" (otomatik kip yoksa "Yes, auto-accept edits"; bypass açık
başladıysa "Yes, and switch to BYPASS PERMISSIONS…") / "Yes, manually approve edits" /
"No, keep planning". Masaüstü kartı (`SessionApplication.tsx`) aynı üçlüdür. Kabul edilen kip
`ReplState.approval`'a yazılır; oturum izinleri korunur (belgede sıfırlama yok). Adsız oturuma
plandan başlık verilir. Uygulama görevi sonraki tur olarak döner.
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
from .transcript_store import TranscriptStore

CHOICE_AUTO = "auto"
CHOICE_EDITS = "edits"
CHOICE_BYPASS = "bypass"
CHOICE_SECURITY = "security"
CHOICE_KEEP_PLANNING = "plan"
#: `showClearContextOnPlanAccept` seçeneğinin değeri: önek + birincil seçeneğin değeri.
CLEAR_PREFIX = "clear:"
#: Ctrl+G (Claude Code): planı varsayılan editörde aç, kartı düzenlenmiş planla yeniden göster.
CHOICE_EDIT_PLAN = "edit-plan"
PLAN_HOTKEYS = {"c-g": CHOICE_EDIT_PLAN}
#: Kart en çok bu kadar kez yeniden gösterilir (sonsuz düzenleme döngüsüne karşı).
_MAX_EDIT_ROUNDS = 20

#: Seçim değeri → kabul sonrası kip. Planlamaya devam kip değiştirmez (None).
_MODES: dict[str, ApprovalMode | None] = {
    CHOICE_AUTO: ApprovalMode.AUTO,
    CHOICE_EDITS: ApprovalMode.ACCEPT_EDITS,
    CHOICE_BYPASS: ApprovalMode.BYPASS,
    CHOICE_SECURITY: ApprovalMode.SECURITY,
    CHOICE_KEEP_PLANNING: None,
}


def choices(state: ReplState | None = None) -> tuple[Choice, ...]:
    """Kartın seçenekleri (Claude sırası); ilk seçenek oturumun durumuna göre değişir.

    `showClearContextOnPlanAccept: true` (Claude settings.json) başa "bağlamı temizle ve …"
    seçeneğini ekler: planı onaylar, planlama konuşmasını siler, uygulama yalnız planla başlar.
    """
    primary = _primary(state)
    base = (
        primary,
        Choice(CHOICE_SECURITY, messages.PLAN_CARD_SECURITY, messages.PLAN_CARD_SECURITY_DESC),
        Choice(CHOICE_KEEP_PLANNING, messages.PLAN_CARD_KEEP, messages.PLAN_CARD_KEEP_DESC),
    )
    if state is None or not show_clear_context(state):
        return base
    clear = Choice(
        CLEAR_PREFIX + primary.value,
        messages.PLAN_CARD_CLEAR.format(rest=_rest(primary.label)),
        messages.PLAN_CARD_CLEAR_DESC,
    )
    return (clear, *base)


def _rest(label: str) -> str:
    """'Evet, ve otomatik kipi kullan' → 'otomatik kipi kullan' (temizleme etiketinin devamı)."""
    rest = label.removeprefix("Evet,").strip()
    return rest.removeprefix("ve ").strip()


def show_clear_context(state: ReplState) -> bool:
    """Claude `showClearContextOnPlanAccept` (varsayılan false; managed > … > kullanıcı)."""
    from ...config.claude_settings import claude_setting

    try:
        return claude_setting(state.root, "showClearContextOnPlanAccept") is True
    except OSError:
        return False


def clears_context(choice: str | None) -> bool:
    """Seçim bağlamı temizleyerek onaylıyor mu?"""
    return bool(choice) and str(choice).startswith(CLEAR_PREFIX)


def _primary(state: ReplState | None) -> Choice:
    if state is not None and getattr(state, "bypass_available", False):
        return Choice(CHOICE_BYPASS, messages.PLAN_CARD_BYPASS, messages.PLAN_CARD_BYPASS_DESC)
    if state is not None and not _auto_available(state):
        return Choice(CHOICE_EDITS, messages.PLAN_CARD_EDITS, messages.PLAN_CARD_EDITS_DESC)
    return Choice(CHOICE_AUTO, messages.PLAN_CARD_AUTO, messages.PLAN_CARD_AUTO_DESC)


def _auto_available(state: ReplState) -> bool:
    """Otomatik kip bu oturumda kullanılabilir mi (`disableAutoMode`, desteklenen modeller)?"""
    settings = getattr(state.config, "agent_launch", None)
    if settings is None:
        return True
    supported = getattr(settings, "auto_supported_models", ())
    return not settings.disable_auto_mode and (
        not supported or state.config.agent.model in supported
    )


def _title_from_plan(text: str | None) -> str:
    """Plandan oturum başlığı: ilk başlık ya da ilk dolu satır (en çok 60 karakter)."""
    for line in (text or "").splitlines():
        cleaned = line.strip().lstrip("#").strip().strip("*").strip()
        if cleaned:
            return cleaned[:60].rstrip()
    return ""


def mode_for(choice: str | None) -> ApprovalMode | None:
    """Seçimin kipi; vazgeçme ve "planlamaya devam" için None."""
    return _MODES.get((choice or "").removeprefix(CLEAR_PREFIX))


def accept(state: ReplState, mode: ApprovalMode, *, clear: bool = False) -> str:
    """Planı kabul et: kipi değiştir, adsız oturuma başlık ver, uygulama görevini döndür.

    `clear` (Claude "Yes, clear context and …"): planlama konuşması silinir; uygulama turu
    yalnız plan dosyasıyla başlar.
    """
    path = state.pending_plan or plan_mode.plan_path(state.conversation_id, state.root)
    state.pending_plan = None
    state.approval = mode
    if clear:
        state.reset_history()
    if not state.conversation_name.strip():
        title = _title_from_plan(plan_mode.read_plan(state.conversation_id, state.root))
        if title:
            _name_session(state, title)
    return messages.PLAN_IMPLEMENT_TASK.format(path=path)


def _name_session(state: ReplState, title: str) -> None:
    try:
        TranscriptStore(
            state.config.memory_dir, state.root, conversation_id=state.conversation_id
        ).record_name(title)
    except OSError:
        return
    state.conversation_name = title


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
    selected = None
    for _ in range(_MAX_EDIT_ROUNDS):
        selected = pick(list(choices(state)), title=messages.PLAN_CARD_TITLE, hotkeys=PLAN_HOTKEYS)
        if selected != CHOICE_EDIT_PLAN:
            break
        console.print(f"[{theme.DIM}]{escape(open_in_editor(state))}[/{theme.DIM}]")
    mode = mode_for(selected)
    if mode is None:
        console.print(f"[{theme.DIM}]{decline(state)}[/{theme.DIM}]")
        return None
    task = accept(state, mode, clear=clears_context(selected))
    console.print(
        f"[{theme.DIM}]{messages.REPL_MODE_CHANGED.format(mode=mode.value)}[/{theme.DIM}]"
    )
    return task


def show(state: ReplState) -> str:
    """`/plan goster`: kayıtlı planı ve yolunu yaz."""
    text = plan_mode.read_plan(state.conversation_id, state.root)
    if text is None:
        return messages.PLAN_NONE
    path = plan_mode.plan_path(state.conversation_id, state.root)
    return f"{messages.PLAN_SAVED.format(path=path)}\n\n{text.rstrip()}"


def open_in_editor(state: ReplState) -> str:
    """`/plan ac`: planı `VISUAL`/`EDITOR` ile aç; editör yoksa yolu söyle."""
    if plan_mode.read_plan(state.conversation_id, state.root) is None:
        return messages.PLAN_NONE
    path = plan_mode.plan_path(state.conversation_id, state.root)
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
    "CHOICE_BYPASS",
    "CHOICE_EDITS",
    "CHOICE_EDIT_PLAN",
    "CHOICE_KEEP_PLANNING",
    "CHOICE_SECURITY",
    "CLEAR_PREFIX",
    "accept",
    "choices",
    "clears_context",
    "command",
    "decline",
    "mode_for",
    "offer",
    "open_in_editor",
    "show",
    "show_clear_context",
]
