"""Slash komut kayıt defteri.

Komutlar bir SÖZLÜKTE tutulur, uzun bir `elif` zincirinde değil. Yeni komut eklemek
bir `@command(...)` dekoratörü yazmaktır: yardım metni, takma adlar ve tamamlama
listesi kendiliğinden güncellenir.

İşleyiciler ince tutulur: durumu değiştirir ve tek satırlık bir sonuç döndürür.
Basma işi çağırana aittir.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from ...core.memory import Feedback, Lesson, LessonKind, LessonSource
from ...engines.agent.approval import ApprovalMode
from ...memory.seed import SEED_LESSONS, seed
from ...ui import messages
from .state import TASK_TYPES, Engine, ReplState

#: Bir komutun döndürdüğü kullanıcıya gösterilecek metin (boşsa bir şey basılmaz).
CommandResult = str

#: İşleyici imzası: (durum, argüman metni) → gösterilecek sonuç.
Handler = Callable[[ReplState, str], CommandResult]


@dataclass(frozen=True, slots=True)
class SlashCommand:
    """Tek bir slash komutu."""

    name: str
    summary: str
    handler: Handler
    aliases: tuple[str, ...] = ()
    #: Yardım ekranında hangi başlık altında görüneceği.
    group: str = "Genel"
    #: Argüman aldığında yardımda gösterilecek biçim.
    usage: str = ""

    @property
    def display(self) -> str:
        return f"/{self.name} {self.usage}".strip()


@dataclass(slots=True)
class CommandRegistry:
    """Ada ve takma ada göre komut çözen defter."""

    _commands: dict[str, SlashCommand] = field(default_factory=dict)
    _by_name: dict[str, SlashCommand] = field(default_factory=dict)

    def register(self, command: SlashCommand) -> None:
        self._by_name[command.name] = command
        for key in (command.name, *command.aliases):
            self._commands[key] = command

    def get(self, name: str) -> SlashCommand | None:
        return self._commands.get(name.lower())

    def all(self) -> tuple[SlashCommand, ...]:
        return tuple(self._by_name.values())

    def completion_words(self) -> list[str]:
        """Tamamlama için tüm komut ve takma adlar."""
        return sorted(f"/{key}" for key in self._commands)


def build_registry() -> CommandRegistry:
    """Yerleşik komutların tamamını içeren defter."""
    registry = CommandRegistry()
    for command in _COMMANDS:
        registry.register(command)
    return registry


# --------------------------------------------------------------------------- #
# İşleyiciler
# --------------------------------------------------------------------------- #


def _exit(state: ReplState, argument: str) -> str:
    # Veda mesajını kapanış basar; buradan da dönmek satırı iki kez gösterirdi.
    state.running = False
    return ""


def _use_agent(state: ReplState, argument: str) -> str:
    state.engine = Engine.AGENT
    return messages.REPL_ENGINE_AGENT


def _use_fusion(state: ReplState, argument: str) -> str:
    state.engine = Engine.FUSION
    return messages.REPL_ENGINE_FUSION


def _set_mode(mode: ApprovalMode) -> Handler:
    def _handler(state: ReplState, argument: str) -> str:
        state.approval = mode
        return messages.REPL_MODE_CHANGED.format(mode=mode.value)

    return _handler


def _reset(state: ReplState, argument: str) -> str:
    return messages.REPL_HISTORY_CLEARED.format(count=state.reset_history())


def _set_task_type(state: ReplState, argument: str) -> str:
    wanted = argument.strip().lower()
    if wanted not in TASK_TYPES:
        return messages.RUN_UNKNOWN_TASK_TYPE.format(
            given=argument or "(boş)", valid=", ".join(TASK_TYPES)
        )
    state.task_type = wanted
    return messages.REPL_TASK_TYPE_CHANGED.format(task_type=wanted)


def _toggle_all(state: ReplState, argument: str) -> str:
    state.show_all_answers = not state.show_all_answers
    return messages.REPL_SHOW_ALL.format(state=_on_off(state.show_all_answers))


def _toggle_synthesis(state: ReplState, argument: str) -> str:
    current = state.config.runtime.synthesis if state.synthesis is None else state.synthesis
    state.synthesis = not current
    return messages.REPL_SYNTHESIS.format(state=_on_off(state.synthesis))


def _feedback(verdict: Feedback) -> Handler:
    def _handler(state: ReplState, argument: str) -> str:
        result = state.last_fusion
        if result is None or not result.winner:
            return messages.REPL_NO_FUSION_YET
        applied = state.memory.performance.apply_feedback(result.task_type, result.winner, verdict)
        if not applied:
            return messages.MEMORY_FEEDBACK_MISSING
        return messages.MEMORY_FEEDBACK_APPLIED.format(
            model=result.winner, verdict=verdict.value, task_type=result.task_type
        )

    return _handler


def _learn(state: ReplState, argument: str) -> str:
    text = argument.strip()
    if not text:
        return messages.REPL_LEARN_USAGE
    lesson = Lesson(
        text=text,
        kind=LessonKind.SUCCESS,
        task=messages.REPL_LEARN_TASK_LABEL,
        source=LessonSource.MANUAL,
    )
    if not state.memory.lessons.add(lesson):
        return messages.REPL_LEARN_DUPLICATE
    return messages.REPL_LEARN_SAVED


def _seed(state: ReplState, argument: str) -> str:
    added = seed(state.memory.lessons)
    return messages.MEMORY_SEEDED.format(count=added, total=len(SEED_LESSONS))


def _reindex(state: ReplState, argument: str) -> str:
    stats = state.memory.code_index.reindex()
    return messages.MEMORY_REINDEXED.format(
        total=stats.total,
        added=stats.added,
        removed=stats.removed,
        unchanged=stats.unchanged,
    )


def _on_off(value: bool) -> str:
    return messages.REPL_ON if value else messages.REPL_OFF


# --------------------------------------------------------------------------- #
# Kayıtlar
# --------------------------------------------------------------------------- #

_COMMANDS: tuple[SlashCommand, ...] = (
    SlashCommand("help", messages.CMD_HELP, lambda state, argument: "", ("h", "?")),
    SlashCommand("exit", messages.CMD_EXIT, _exit, ("quit", "q")),
    SlashCommand("clear", messages.CMD_CLEAR, lambda state, argument: ""),
    SlashCommand("agent", messages.CMD_AGENT, _use_agent, group="Motor"),
    SlashCommand("fusion", messages.CMD_FUSION, _use_fusion, group="Motor"),
    SlashCommand("auto", messages.CMD_AUTO, _set_mode(ApprovalMode.AUTO), group="Onay modu"),
    SlashCommand("plan", messages.CMD_PLAN, _set_mode(ApprovalMode.PLAN), group="Onay modu"),
    SlashCommand(
        "security", messages.CMD_SECURITY, _set_mode(ApprovalMode.SECURITY), group="Onay modu"
    ),
    SlashCommand("reset", messages.CMD_RESET, _reset, group="Agent"),
    SlashCommand("compact", messages.CMD_COMPACT, lambda state, argument: "", group="Agent"),
    SlashCommand("type", messages.CMD_TASK_TYPE, _set_task_type, group="Fusion", usage="<tip>"),
    SlashCommand("all", messages.CMD_SHOW_ALL, _toggle_all, group="Fusion"),
    SlashCommand("synth", messages.CMD_SYNTHESIS, _toggle_synthesis, group="Fusion"),
    SlashCommand("good", messages.CMD_GOOD, _feedback(Feedback.GOOD), group="Bellek"),
    SlashCommand("bad", messages.CMD_BAD, _feedback(Feedback.BAD), group="Bellek"),
    SlashCommand("revise", messages.CMD_REVISE, _feedback(Feedback.REVISE), group="Bellek"),
    SlashCommand("learn", messages.CMD_LEARN, _learn, group="Bellek", usage="<kural>"),
    SlashCommand("seed", messages.CMD_SEED, _seed, group="Bellek"),
    SlashCommand("reindex", messages.CMD_REINDEX, _reindex, group="Bellek"),
    SlashCommand("stats", messages.CMD_STATS, lambda state, argument: "", group="Bellek"),
    SlashCommand("lessons", messages.CMD_LESSONS, lambda state, argument: "", group="Bellek"),
    SlashCommand("models", messages.CMD_MODELS, lambda state, argument: "", group="Bilgi"),
    SlashCommand("cost", messages.CMD_COST, lambda state, argument: "", group="Bilgi"),
)

#: Kendi çıktısını basan komutlar (tablo, panel, ekran temizleme). REPL döngüsü
#: bunları özel olarak ele alır; işleyicileri boş metin döndürür.
RENDERED_COMMANDS = frozenset({"help", "clear", "stats", "lessons", "models", "compact", "cost"})


def parse(line: str) -> tuple[str, str]:
    """`/komut argüman` satırını (komut, argüman) olarak ayır."""
    stripped = line[1:].strip()
    if not stripped:
        return "", ""
    name, _, argument = stripped.partition(" ")
    return name.lower(), argument.strip()
