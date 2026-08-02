"""Slash komut kayıt defteri.

Komutlar bir SÖZLÜKTE tutulur, uzun bir `elif` zincirinde değil. Yeni komut eklemek
bir `@command(...)` dekoratörü yazmaktır: yardım metni, takma adlar ve tamamlama
listesi kendiliğinden güncellenir.

İşleyiciler ince tutulur: durumu değiştirir ve tek satırlık bir sonuç döndürür.
Basma işi çağırana aittir.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace

from ...config import model_select, profile
from ...config.models import Config
from ...core.errors import ConfigError
from ...core.memory import Feedback, Lesson, LessonKind, LessonSource
from ...core.reasoning import ReasoningEffort, is_downgraded, provider_value
from ...engines.agent.approval import ApprovalMode
from ...memory.seed import SEED_LESSONS, seed
from ...ui import messages
from . import macros, model_flows, provider_flow, verify_flow
from .state import TASK_TYPES, Engine, Reminder, ReplState

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


def _model(state: ReplState, argument: str) -> str:
    """`/model` — oturum içinde model değiştir.

    Alt komutlar: agent <id> | judge <id> | cand <ad|no> <id> | add <ad> <id> [etiket…]
    | rm <ad>. Argümansız çağrı etkin modelleri listeler.
    """
    parts = argument.split()
    if not parts:
        return model_select.format_models(state.config)
    try:
        state.config, message = _apply_model_command(state, parts)
    except ConfigError as error:
        return str(error)
    return message


def _apply_model_command(state: ReplState, parts: list[str]) -> tuple[Config, str]:
    action, arguments = parts[0].lower(), parts[1:]
    config = state.config

    if action == "agent" and len(arguments) == 1:
        return model_select.set_agent_model(config, arguments[0]), messages.REPL_MODEL_SET.format(
            role="agent", model=arguments[0]
        )
    if action == "judge" and len(arguments) == 1:
        return model_select.set_judge_model(config, arguments[0]), messages.REPL_MODEL_SET.format(
            role="hakem", model=arguments[0]
        )
    if action == "cand" and len(arguments) == 2:
        updated = model_select.set_candidate_model(config, arguments[0], arguments[1])
        return updated, messages.REPL_MODEL_SET.format(
            role=f"aday {arguments[0]}", model=arguments[1]
        )
    if action == "add" and len(arguments) >= 2:
        updated = model_select.add_candidate(
            config, arguments[0], arguments[1], tuple(arguments[2:])
        )
        return updated, messages.REPL_MODEL_ADDED.format(name=arguments[0], model=arguments[1])
    if action == "rm" and len(arguments) == 1:
        return model_select.remove_candidate(
            config, arguments[0]
        ), messages.REPL_MODEL_REMOVED.format(name=arguments[0])
    return config, messages.REPL_MODEL_USAGE


def _level(state: ReplState, argument: str) -> str:
    """`/level` — model kademesi seç (low → premium).

    Argüman verilirse seçim ekranı hiç açılmaz: `/level premium` betiklenebilir yol.
    """
    wanted = argument.strip().lower()
    if not wanted:
        result = model_flows.choose_level(state.config)
    else:
        try:
            updated = model_select.apply_tier(state.config, wanted)
        except ConfigError as error:
            return str(error)
        result = model_flows.applied_result(updated, wanted)
    state.config = result.config
    return result.message


def _mode(state: ReplState, argument: str) -> str:
    """`/mode` — çalışma profili seç: auto · low · medium · high · max.

    Kademe seçmenin PROFİL cephesidir; aynı `apply_tier` çekirdeğini kullanır (ikinci
    yol değildir). `auto` bir kademe değil oturum kipidir: her tur görevi sınıflandırıp
    kademeyi kendisi seçer. Argümansız çağrı seçim ekranını açar.
    """
    wanted = argument.strip()
    if not wanted:
        picked = model_flows.choose_mode(state.config)
        if picked is None:
            return messages.PICKER_CANCELLED
    else:
        picked = wanted
    if picked.strip().casefold() == model_flows.AUTO_CHOICE:
        state.auto_profile = True
        return messages.MODE_AUTO_ON
    tier_name = profile.resolve_tier_name(state.config, picked)
    if tier_name is None:
        known = ", ".join(item.name for item in state.config.tiers)
        return messages.MODE_UNKNOWN.format(name=picked, known=known)
    result = model_flows.applied_result(model_select.apply_tier(state.config, tier_name), tier_name)
    state.config = result.config
    # Elle profil seçmek auto kipini kapatır: kullanıcı belirli bir kademe istedi.
    state.auto_profile = False
    return result.message


def _effort(state: ReplState, argument: str) -> str:
    """`/effort` — reasoning yoğunluğu seç (mode'dan AYRI).

    Yalnızca oturum boyunca yaşar (onay modu gibi; kalıcılaştırılmaz). Seçilen model
    reasoning desteklemiyorsa değer sessizce göz ardı edilir; `xhigh`/`max` desteklenen
    en yakına (`high`) iner ve bu kullanıcıya bildirilir.
    """
    wanted = argument.strip()
    if not wanted:
        picked = model_flows.choose_effort()
        if picked is None:
            return messages.PICKER_CANCELLED
    else:
        picked = wanted
    try:
        effort = ReasoningEffort(picked.strip().lower())
    except ValueError:
        known = ", ".join(item.value for item in ReasoningEffort)
        return messages.EFFORT_UNKNOWN.format(name=picked, known=known)
    state.config = replace(
        state.config, runtime=replace(state.config.runtime, reasoning_effort=effort)
    )
    if is_downgraded(effort):
        return messages.EFFORT_APPLIED_DOWNGRADED.format(
            effort=effort.value, mapped=provider_value(effort)
        )
    return messages.EFFORT_APPLIED.format(effort=effort.value)


def _undo(state: ReplState, argument: str) -> str:
    """`/undo` — son agent turunun dosya değişikliklerini geri al."""
    kayit = state.last_changes
    if kayit is None or not kayit:
        return messages.UNDO_NOTHING
    beklenen = len(kayit.paths)
    geri_alinan = kayit.restore()
    state.last_changes = None
    if len(geri_alinan) < beklenen:
        return messages.UNDO_PARTIAL.format(
            count=len(geri_alinan), failed=beklenen - len(geri_alinan)
        )
    yollar = "\n".join(f"  {yol}" for yol in geri_alinan)
    return messages.UNDO_DONE.format(count=len(geri_alinan), paths=yollar)


def _provider(state: ReplState, argument: str) -> str:
    """`/provider` — hangi sağlayıcının kullanılacağını seç."""
    result = provider_flow.choose_provider(state.config)
    state.config = result.config
    return result.message


def _verify(state: ReplState, argument: str) -> str:
    """`/verify` — projeden doğrulama planı çıkar, onaylat, kalıcılaştır."""
    result = verify_flow.choose_verification(state.config, state.root)
    state.config = result.config
    return result.message


def _development(state: ReplState, argument: str) -> str:
    """`/development` — kaynak seç, sonra model seç."""
    result = model_flows.choose_development(state.config, ask_text=_ask_line)
    state.config = result.config
    return result.message


def _ask_line(prompt: str) -> str | None:
    """Özel model alias'ı için tek satır al. Vazgeçilirse None."""
    try:
        return input(prompt)
    except (EOFError, KeyboardInterrupt):
        return None


def _macro(name: str) -> Handler:
    """Makroyu çalıştırılacak göreve çevir ve durumda beklet.

    Makrolar model çağırır; komut işleyicileri ise saftır ve senkrondur. Bu yüzden
    işleyici yalnızca görevi HAZIRLAR, çalıştırmayı REPL döngüsü üstlenir.
    """

    def _handler(state: ReplState, argument: str) -> str:
        macro = macros.get(name)
        if macro is None:  # pragma: no cover - kayıt defteri ile senkron
            return ""
        if macro.argument_required and not argument.strip():
            return messages.REPL_MACRO_NEEDS_ARGUMENT.format(name=name)
        state.engine = Engine.AGENT
        state.pending_task = macro.build(argument)
        state.pending_mode = macro.mode
        return messages.REPL_MACRO_STARTED.format(name=name)

    return _handler


def _schedule(state: ReplState, argument: str) -> str:
    """`/schedule <saniye>` — belirtilen süre sonra hatırlatma kur.

    Hatırlatma doğrudan konsola YAZMAZ: bekleyen hatırlatma listesine düşer ve
    REPL döngüsü bir sonraki uygun anda gösterir. Eski projede ayrı bir thread
    doğrudan yazdığı için uyarı giriş satırının ortasına biniyordu.
    """
    try:
        seconds = int(argument.strip())
    except ValueError:
        return messages.REPL_SCHEDULE_USAGE
    if seconds <= 0:
        return messages.REPL_SCHEDULE_USAGE
    state.reminders.append(Reminder(due_in_seconds=seconds, text=messages.REPL_SCHEDULE_FIRED))
    return messages.REPL_SCHEDULE_SET.format(seconds=seconds)


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
    SlashCommand("tips", messages.CMD_TIPS, lambda state, argument: "", group="Bilgi"),
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
    SlashCommand("model", messages.CMD_MODEL, _model, group="Bilgi", usage="[alt-komut]"),
    SlashCommand("mode", messages.CMD_MODE, _mode, group="Model", usage="[profil]"),
    SlashCommand("effort", messages.CMD_EFFORT, _effort, group="Model", usage="[seviye]"),
    SlashCommand("level", messages.CMD_LEVEL, _level, group="Model", usage="[kademe]"),
    SlashCommand("provider", messages.CMD_PROVIDER, _provider, group="Model"),
    SlashCommand(
        "development", messages.CMD_DEVELOPMENT, _development, group="Model", aliases=("dev",)
    ),
    SlashCommand("verify", messages.CMD_VERIFY, _verify, group="Agent"),
    SlashCommand("undo", messages.CMD_UNDO, _undo, group="Agent"),
    SlashCommand("cost", messages.CMD_COST, lambda state, argument: "", group="Bilgi"),
    *(
        SlashCommand(
            name,
            summary,
            _macro(name),
            group="Makro",
            usage="<görev>" if macros.MACROS[name].argument_required else "[görev]",
        )
        for name, summary in (
            ("goal", messages.CMD_GOAL),
            ("grill-me", messages.CMD_GRILL),
            ("bug", messages.CMD_BUG),
            ("commit", messages.CMD_COMMIT),
            ("review", messages.CMD_REVIEW),
            ("browser", messages.CMD_BROWSER),
        )
    ),
    SlashCommand("schedule", messages.CMD_SCHEDULE, _schedule, group="Makro", usage="<saniye>"),
)

#: Kendi çıktısını basan komutlar (tablo, panel, ekran temizleme). REPL döngüsü
#: bunları özel olarak ele alır; işleyicileri boş metin döndürür.
RENDERED_COMMANDS = frozenset(
    {"help", "tips", "clear", "stats", "lessons", "models", "compact", "cost"}
)


def parse(line: str) -> tuple[str, str]:
    """`/komut argüman` satırını (komut, argüman) olarak ayır."""
    stripped = line[1:].strip()
    if not stripped:
        return "", ""
    name, _, argument = stripped.partition(" ")
    return name.lower(), argument.strip()
