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
from dataclasses import dataclass, field
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
    SUBAGENT_START = "SubagentStart"
    SESSION_START = "SessionStart"
    SESSION_END = "SessionEnd"
    NOTIFICATION = "Notification"
    PRE_COMPACT = "PreCompact"
    POST_COMPACT = "PostCompact"
    CWD_CHANGED = "CwdChanged"
    TASK_CREATED = "TaskCreated"
    TASK_COMPLETED = "TaskCompleted"
    TEAMMATE_IDLE = "TeammateIdle"
    PERMISSION_REQUEST = "PermissionRequest"
    STOP_FAILURE = "StopFailure"
    POST_TOOL_BATCH = "PostToolBatch"
    INSTRUCTIONS_LOADED = "InstructionsLoaded"
    USER_PROMPT_EXPANSION = "UserPromptExpansion"


#: Olay başına eşleştiricinin (`matcher`) neye bakacağı; `None` = eşleştirici yok sayılır.
MATCHER_SUBJECT: dict[HookEvent, str | None] = {
    HookEvent.PRE_TOOL_USE: "araç adı",
    HookEvent.POST_TOOL_USE: "araç adı",
    HookEvent.POST_TOOL_USE_FAILURE: "araç adı",
    HookEvent.USER_PROMPT_SUBMIT: None,
    HookEvent.STOP: None,
    HookEvent.SUBAGENT_STOP: "ajan türü",
    HookEvent.SUBAGENT_START: "ajan türü",
    HookEvent.SESSION_START: "kaynak (startup|resume|clear|compact)",
    HookEvent.SESSION_END: "neden (clear|logout|prompt_input_exit|other)",
    HookEvent.NOTIFICATION: "bildirim türü (permission_prompt|idle_prompt)",
    HookEvent.PRE_COMPACT: "tetik (manual|auto)",
    HookEvent.POST_COMPACT: "tetik (manual|auto)",
    HookEvent.CWD_CHANGED: None,
    HookEvent.TASK_CREATED: None,
    HookEvent.TASK_COMPLETED: None,
    HookEvent.TEAMMATE_IDLE: None,
    HookEvent.PERMISSION_REQUEST: "araç adı",
    HookEvent.POST_TOOL_BATCH: None,
    HookEvent.USER_PROMPT_EXPANSION: "komut adı (command_name)",
    HookEvent.INSTRUCTIONS_LOADED: (
        "yükleme nedeni (session_start|nested_traversal|path_glob_match|include|compact)"
    ),
    HookEvent.STOP_FAILURE: "hata türü (rate_limit|authentication_failed|server_error|…)",
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
        # Claude: PreCompact çıkış 2 ya da `decision: block` ile özetlemeyi engeller.
        HookEvent.PRE_COMPACT,
        # PostToolBatch: döngü sonraki model çağrısından önce durur.
        HookEvent.POST_TOOL_BATCH,
        # UserPromptExpansion: komut açılmaz, gerekçe kullanıcıya.
        HookEvent.USER_PROMPT_EXPANSION,
    }
)

#: Düz (JSON olmayan) stdout'u modele bağlam olarak ekleyen olaylar (Claude ile aynı).
STDOUT_CONTEXT_EVENTS = frozenset(
    {HookEvent.USER_PROMPT_SUBMIT, HookEvent.SESSION_START, HookEvent.USER_PROMPT_EXPANSION}
)

#: Claude Code'un tanıdığı ama Fusion'ın (henüz) tetiklemediği olaylar: listede
#: "tetiklenmiyor" diye görünür, hata sayılmaz.
CLAUDE_ONLY_EVENTS = frozenset(
    {
        "Setup",
        "PermissionDenied",
        "MessageDisplay",
        "ConfigChange",
        "DirectoryAdded",
        "FileChanged",
        "WorktreeCreate",
        "WorktreeRemove",
        "PreModelSwitch",
        "PostModelSwitch",
        "Elicitation",
        "ElicitationResult",
    }
)

#: İşleyici türleri (Claude: command, http, mcp_tool, prompt, agent).
COMMAND_HANDLER = "command"
#: Olay JSON'unu POST eden kanca (yanıt gövdesi stdout gibi okunur; iç ağ korumalı).
HTTP_HANDLER = "http"
#: Yapılandırılmış MCP sunucusunun aracını çağıran kanca (metin içeriği stdout gibi okunur).
MCP_TOOL_HANDLER = "mcp_tool"
#: Tek atış model değerlendirmesi (`{"ok": …, "reason": …}`).
PROMPT_HANDLER = "prompt"
#: Read/Grep/Glob'lu doğrulayıcı alt ajan (en çok 50 tur; deneysel).
AGENT_HANDLER = "agent"
#: Model kullanan işleyiciler.
MODEL_HANDLERS = frozenset({PROMPT_HANDLER, AGENT_HANDLER})


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
    #: İşleyici türü; `http` ise `command` hedef adrestir.
    handler: str = COMMAND_HANDLER
    #: `http`: istek başlıkları; değerdeki `$AD`/`${AD}` yalnız `allowed_env_vars`'tan dolar.
    headers: tuple[tuple[str, str], ...] = ()
    allowed_env_vars: tuple[str, ...] = ()
    args: tuple[str, ...] | None = None
    once: bool = False
    run_async: bool = False
    async_rewake: bool = False
    shell: str = ""
    on_failure: str = ""
    status_message: str = ""
    #: `if`: izin kuralı sözdizimi (`Bash(git *)`); yalnız araç olaylarında değerlendirilir.
    condition: str = ""
    #: `timeout` tanımda yazılı mı? (Yazılmadıysa olayın Claude varsayılanı uygulanır.)
    timeout_explicit: bool = False
    #: `mcp_tool`: sunucu ve araç adı; `input` JSON metni (`${yol}` yerleştirmeli).
    server: str = ""
    tool: str = ""
    tool_input_json: str = ""
    #: `prompt`/`agent`: `model` (boş = arka plan modeli) ve `continueOnBlock` (yalnız prompt).
    model: str = ""
    continue_on_block: bool = False
    #: Eklenti kancası: `CLAUDE_PLUGIN_ROOT` ve `CLAUDE_PLUGIN_DATA` (boş = eklenti değil).
    plugin_root: str = ""
    plugin_data: str = ""


@dataclass(frozen=True, slots=True)
class HookSkip:
    """Okunan ama çalıştırılmayacak tanım (güvenilmeyen katman, desteklenmeyen tür…)."""

    event: str
    matcher: str
    detail: str
    reason: str
    source: str = ""
    path: str = ""
    definition_json: str = field(default="", repr=False)


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
    #: Oturumda bir kez kullanıcıya gösterilecek uyarılar (kullanımdan kalkan katman vb.).
    notices: tuple[str, ...] = ()

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
    #: Çıkış 2 ile engelleyen kancanın komutu (modele `[komut]:` önekiyle gider).
    block_source: str = ""
    #: PreToolUse `ask` gerekçesi (onay kartında gösterilir).
    ask_reason: str = ""
    #: PostToolUse `classifierContext`: otomatik kip sınıflandırıcısına not.
    classifier_context: str = ""
    #: UserPromptSubmit/SessionStart `sessionTitle`.
    session_title: str = ""
    #: UserPromptSubmit `suppressOriginalPrompt`: engel mesajı istemi içermez.
    suppress_original_prompt: bool = False
    #: SessionStart `initialUserMessage` (yalnız `-p`).
    initial_user_message: str = ""
    #: SessionStart/CwdChanged/FileChanged `watchPaths`.
    watch_paths: tuple[str, ...] = ()
    #: SessionStart `reloadSkills`.
    reload_skills: bool = False
    #: Evrensel `terminalSequence` (izinli OSC/BEL dizisi; etkileşimli arayüz basar).
    terminal_sequences: tuple[str, ...] = ()

    @property
    def context_text(self) -> str:
        return "\n\n".join(part for part in self.additional_context if part)
