"""Kanca (hook) olay kataloğu ve değer tipleri (P-009) — Claude Code ile aynı adlar.

Kullanıcı bir olaya (`PreToolUse`, `Stop`…) kabuk komutu bağlar; Fusion olay anında
komutu çalıştırır, stdin'e olayın JSON'unu yazar ve çıkış kodu + stdout JSON'undan
kararı okur (bkz. `decision.py`). Adlar Claude Code ve Codex ile birebir aynıdır:
`~/.claude/settings.json` içindeki kancalar Fusion'da da çalışır.

Bu modül saf tiptir: süreç açmaz, dosya okumaz (çalıştırma `engines/hooks`, yükleme
`config/hooks.py`).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum

from .matcher import matcher_matches


class HookEvent(Enum):
    """Fusion'ın tetiklediği olaylar; değer ayar dosyasındaki anahtardır."""

    PRE_TOOL_USE = "PreToolUse"
    POST_TOOL_USE = "PostToolUse"
    POST_TOOL_USE_FAILURE = "PostToolUseFailure"
    USER_PROMPT_SUBMIT = "UserPromptSubmit"
    STOP = "Stop"
    SUBAGENT_STOP = "SubagentStop"
    SESSION_START = "SessionStart"
    SESSION_END = "SessionEnd"
    NOTIFICATION = "Notification"
    PRE_COMPACT = "PreCompact"
    CWD_CHANGED = "CwdChanged"
    TASK_CREATED = "TaskCreated"
    TASK_COMPLETED = "TaskCompleted"
    TEAMMATE_IDLE = "TeammateIdle"


#: Olay başına eşleştiricinin (`matcher`) neye bakacağı; `None` = eşleştirici yok sayılır.
MATCHER_SUBJECT: dict[HookEvent, str | None] = {
    HookEvent.PRE_TOOL_USE: "araç adı",
    HookEvent.POST_TOOL_USE: "araç adı",
    HookEvent.POST_TOOL_USE_FAILURE: "araç adı",
    HookEvent.USER_PROMPT_SUBMIT: None,
    HookEvent.STOP: None,
    HookEvent.SUBAGENT_STOP: "ajan türü",
    HookEvent.SESSION_START: "kaynak (startup|resume|clear|compact)",
    HookEvent.SESSION_END: "neden (clear|logout|prompt_input_exit|other)",
    HookEvent.NOTIFICATION: "bildirim türü (permission_prompt|idle_prompt)",
    HookEvent.PRE_COMPACT: "tetik (manual|auto)",
    HookEvent.CWD_CHANGED: None,
    HookEvent.TASK_CREATED: None,
    HookEvent.TASK_COMPLETED: None,
    HookEvent.TEAMMATE_IDLE: None,
}

#: Çıkış 2 ile engelleyebilen (ya da modele geri bildirim veren) olaylar. Ötekilerde
#: çıkış 2 yalnız kullanıcıya gösterilen bir hatadır.
BLOCKING_EVENTS = frozenset(
    {
        HookEvent.PRE_TOOL_USE,
        HookEvent.POST_TOOL_USE,
        HookEvent.POST_TOOL_USE_FAILURE,
        HookEvent.USER_PROMPT_SUBMIT,
        HookEvent.STOP,
        HookEvent.SUBAGENT_STOP,
        # Ekip kapıları (P-061): çıkış 2 görevi eklemez/bitirmez, üyeyi boşa düşürmez.
        HookEvent.TASK_CREATED,
        HookEvent.TASK_COMPLETED,
        HookEvent.TEAMMATE_IDLE,
    }
)

#: Düz (JSON olmayan) stdout'u modele bağlam olarak ekleyen olaylar (Claude ile aynı).
STDOUT_CONTEXT_EVENTS = frozenset({HookEvent.USER_PROMPT_SUBMIT, HookEvent.SESSION_START})

#: Claude Code'un tanıdığı ama Fusion'ın (henüz) tetiklemediği olaylar: listede
#: "tetiklenmiyor" diye görünür, hata sayılmaz.
CLAUDE_ONLY_EVENTS = frozenset(
    {
        "Setup",
        "UserPromptExpansion",
        "PermissionRequest",
        "PermissionDenied",
        "PostToolBatch",
        "MessageDisplay",
        "SubagentStart",
        "StopFailure",
        "InstructionsLoaded",
        "ConfigChange",
        "DirectoryAdded",
        "FileChanged",
        "WorktreeCreate",
        "WorktreeRemove",
        "PostCompact",
        "PreModelSwitch",
        "PostModelSwitch",
        "Elicitation",
        "ElicitationResult",
    }
)

#: Desteklenen işleyici türü; `http`, `prompt`, `agent`, `mcp_tool` listede "desteklenmiyor".
COMMAND_HANDLER = "command"


def parse_event(name: str) -> HookEvent | None:
    """Ayar anahtarını olaya çevir; tanınmayan ad `None`."""
    for event in HookEvent:
        if event.value == name:
            return event
    return None


@dataclass(frozen=True, slots=True)
class HookCommand:
    """Bir olaya bağlı tek bir kabuk komutu ve nereden geldiği."""

    event: HookEvent
    matcher: str
    command: str
    timeout_s: float
    #: Katman adı (`fusion`, `kullanici`, `proje`, `yerel`).
    source: str = ""
    #: Tanımın okunduğu dosya.
    path: str = ""


@dataclass(frozen=True, slots=True)
class HookSkip:
    """Okunan ama çalıştırılmayacak tanım (güvenilmeyen katman, desteklenmeyen tür…)."""

    event: str
    matcher: str
    detail: str
    reason: str
    source: str = ""
    path: str = ""


@dataclass(frozen=True, slots=True)
class HookSet:
    """Tüm katmanlardan okunmuş kancalar; `disabled_reason` doluysa hiçbiri çalışmaz."""

    commands: tuple[HookCommand, ...] = ()
    skipped: tuple[HookSkip, ...] = ()
    disabled_reason: str | None = None
    #: Dosyası var ama güvenilmediği için kancaları okunmayan katmanlar.
    untrusted_layers: tuple[str, ...] = ()
    #: `disableAllHooks: true` taşıyan ama güvenilmediği için yok sayılan katmanlar.
    ignored_disable_layers: tuple[str, ...] = ()

    def for_event(self, event: HookEvent, subjects: Iterable[str] = ()) -> tuple[HookCommand, ...]:
        """Olaya ve eşleştiriciye uyan komutlar; aynı komut metni bir kez (Claude gibi)."""
        if self.disabled_reason is not None:
            return ()
        names = tuple(subjects)
        uses_matcher = MATCHER_SUBJECT[event] is not None
        found: list[HookCommand] = []
        seen: set[str] = set()
        for command in self.commands:
            if command.event is not event or command.command in seen:
                continue
            if uses_matcher and not matcher_matches(command.matcher, names):
                continue
            seen.add(command.command)
            found.append(command)
        return tuple(found)


@dataclass(frozen=True, slots=True)
class HookRun:
    """Bir komutun ham sonucu."""

    command: HookCommand
    exit_code: int | None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    #: Süreç hiç başlatılamadıysa nedeni.
    error: str | None = None


@dataclass(frozen=True, slots=True)
class HookVerdict:
    """Bir olayın tüm kancalarından birleşik karar."""

    #: Çıkış 2 ya da `decision: block` / `permissionDecision: deny`.
    blocked: bool = False
    reason: str = ""
    #: PreToolUse: `allow` (sormadan; deny/ask kurallarını geçemez) ya da `ask` (her zaman sor).
    permission: str | None = None
    #: PreToolUse `updatedInput`: araç bu argümanlarla çalışır.
    updated_input: Mapping[str, object] | None = None
    #: PostToolUse `updatedToolOutput`: modele bu metin gider.
    updated_output: str | None = None
    additional_context: tuple[str, ...] = ()
    #: Kullanıcıya gösterilecek `systemMessage` satırları.
    system_messages: tuple[str, ...] = ()
    #: `continue: false` — tur burada durur.
    halt: bool = False
    stop_reason: str = ""
    #: Engellemeyen hatalar (çıkış ≠ 0/2, zaman aşımı); kullanıcıya gösterilir.
    errors: tuple[str, ...] = ()
    #: Kaç komut çalıştı.
    ran: int = 0

    @property
    def context_text(self) -> str:
        return "\n\n".join(part for part in self.additional_context if part)
