"""Slash komut kayıt defteri.

Komutlar bir SÖZLÜKTE tutulur, uzun bir `elif` zincirinde değil. Yeni komut eklemek
bir `@command(...)` dekoratörü yazmaktır: yardım metni, takma adlar ve tamamlama
listesi kendiliğinden güncellenir.

İşleyiciler ince tutulur: durumu değiştirir ve tek satırlık bir sonuç döndürür.
Basma işi çağırana aittir.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path

from ...config import model_select, profile
from ...config.eligibility import capability_from_spec
from ...config.keys import environ_snapshot
from ...config.models import Config
from ...core.errors import ConfigError
from ...core.memory import Feedback, Lesson, LessonKind, LessonSource
from ...core.reasoning import ReasoningEffort, resolve_reasoning
from ...core.redaction import redact
from ...engines.agent.approval import ApprovalMode
from ...history import SessionRef, available_sources, build_digest, source_by_name
from ...memory.seed import SEED_LESSONS, seed
from ...providers.registry import BUILTIN_PROVIDERS, ProviderKind
from ...tools.capabilities import Capability, CapabilityRegistry
from ...tools.capabilities import search as search_capabilities
from ...ui import background_messages as bg_texts
from ...ui import messages
from ...ui.picker import Choice, pick
from . import (
    auto_mode_command,
    background_commands,
    btw_command,
    code_review,
    config_command,
    doctor_command,
    export_commands,
    fork_command,
    goal_command,
    hooks_command,
    import_command,
    keybinding_commands,
    loop_command,
    macros,
    memory_commands,
    model_flows,
    model_switch,
    output_style_command,
    permissions_command,
    persona_commands,
    plan_card,
    plugin_command,
    profiles_flow,
    provider_flow,
    recap_command,
    rewind,
    session_clear,
    session_resume,
    status_line,
    team_commands,
    terminal_setup,
    verify_flow,
    view_commands,
    voice_command,
    web_session_command,
    workflow_commands,
    workspace_commands,
    worktrees,
)
from .browser_command import browser_command
from .cd_command import cd_command
from .diff_command import diff_command
from .macros import Mode
from .preview_command import preview_command
from .sandbox_command import sandbox_command
from .state import TASK_TYPES, Engine, Reminder, ReplState

#: `/resume<kaynak>` listesinde gösterilecek en fazla oturum. `source.list`'e
#: bu değer `limit` olarak geçirilir; böylece gereksiz oturum ayrıştırılmaz.
RESUME_LIST_LIMIT = 50

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


#: Yerleşik olmayan komutları (beceriler) her çağrıda üreten sağlayıcı.
DynamicCommands = Callable[[], tuple[SlashCommand, ...]]
#: Listede olmayan ad için son çare çözücü (ör. henüz kataloğu gelmemiş `/mcp__…`).
FallbackCommand = Callable[[str], SlashCommand | None]


@dataclass(slots=True)
class CommandRegistry:
    """Ada ve takma ada göre komut çözen defter.

    `dynamic` sağlayıcı (bkz. `skill_commands.skill_slash_commands`) her sorguda yeniden
    üretilir: beceri kataloğu yenilenince (`/skills reload`) defter de yenilenmiş olur.
    Yerleşik komut dinamik olanı her zaman gölgeler.
    """

    _commands: dict[str, SlashCommand] = field(default_factory=dict)
    _by_name: dict[str, SlashCommand] = field(default_factory=dict)
    _dynamic: DynamicCommands | None = None
    _fallback: FallbackCommand | None = None

    def register(self, command: SlashCommand) -> None:
        self._by_name[command.name] = command
        for key in (command.name, *command.aliases):
            self._commands[key] = command

    def set_dynamic(self, provider: DynamicCommands | None) -> None:
        self._dynamic = provider

    def set_fallback(self, resolver: FallbackCommand | None) -> None:
        self._fallback = resolver

    def _dynamic_commands(self) -> tuple[SlashCommand, ...]:
        if self._dynamic is None:
            return ()
        return tuple(c for c in self._dynamic() if c.name.lower() not in self._commands)

    def get(self, name: str) -> SlashCommand | None:
        wanted = name.lower()
        builtin = self._commands.get(wanted)
        if builtin is not None:
            return builtin
        found = next((c for c in self._dynamic_commands() if c.name.lower() == wanted), None)
        if found is None and self._fallback is not None:
            return self._fallback(wanted)
        return found

    def is_dynamic(self, name: str) -> bool:
        """Ad bir beceri/komut dosyasına mı çözülüyor (yerleşik değil)?"""
        return name.lower() not in self._commands and self.get(name) is not None

    def all(self) -> tuple[SlashCommand, ...]:
        return (*self._by_name.values(), *self._dynamic_commands())

    def completion_words(self) -> list[str]:
        """Tamamlama için tüm komut ve takma adlar."""
        words = {f"/{key}" for key in self._commands}
        words.update(f"/{c.name}" for c in self._dynamic_commands())
        return sorted(words)


def build_registry(
    home: Path | None = None,
    *,
    skills: Callable[[], CapabilityRegistry | None] | None = None,
) -> CommandRegistry:
    """Yerleşik komutların tamamını içeren defter.

    `home` verilirse makinede izi bulunan her geçmiş kaynağı için bir
    `/resume<kaynak>` komutu EKLENİR. Kurulu olmayan aracın komutu hiç var olmaz:
    tamamlamada da yardımda da görünmez. `skills` verilirse keşfedilen her beceri/komut
    dosyası `/ad` olarak "Beceri" grubunda sunulur (P-019); sağlayıcı tembel çağrılır ki
    katalog yenilenince defter de yenilensin.
    """
    registry = CommandRegistry()
    for command in _COMMANDS:
        registry.register(command)
    if skills is not None:
        attach_skill_commands(registry, skills)
    if home is not None:
        # Claude Code'da `/resume<kaynak>` yok (#223): dış araç geçmişi `/import history
        # <kaynak>` ile devralınır. Eski adlar bir sürüm boyunca listede görünmeyen,
        # kullanımdan kalkmış takma ad olarak çözülür.
        registry.set_fallback(_with_legacy_resume(home, registry._fallback))
    return registry


def _with_legacy_resume(home: Path, previous: FallbackCommand | None) -> FallbackCommand:
    def _resolve(name: str) -> SlashCommand | None:
        source_name = name.removeprefix("resume")
        known = any(source.name == source_name for source in available_sources(home))
        if name.startswith("resume") and source_name and known:
            return SlashCommand(
                name,
                messages.CMD_RESUME.format(source=source_name),
                _legacy_resume(source_name),
                group="Geçmiş",
            )
        return previous(name) if previous is not None else None

    return _resolve


def _legacy_resume(source_name: str) -> Handler:
    handler = _resume(source_name)

    def _handler(state: ReplState, argument: str) -> str:
        result = handler(state, argument)
        if getattr(state, "legacy_resume_warned", False):
            return result
        state.legacy_resume_warned = True
        note = messages.HISTORY_LEGACY_RESUME.format(source=source_name)
        return f"{note}\n{result}" if result else note

    return _handler


def _import_or_history(state: ReplState, argument: str) -> str:
    """`/import <araç>` ayar içe aktarır; `/import history <kaynak> [oturum]` geçmiş devralır."""
    words = argument.split()
    if not words or words[0] not in ("history", "gecmis"):
        return import_command.import_command(state, argument)
    names = [source.name for source in available_sources(state.home)]
    if len(words) < 2 or words[1] not in names:
        return messages.HISTORY_IMPORT_USAGE.format(sources="|".join(names) or "-")
    return _resume(words[1])(state, " ".join(words[2:]))


def attach_skill_commands(
    registry: CommandRegistry, skills: Callable[[], CapabilityRegistry | None]
) -> None:
    """Keşfedilen beceri/komut dosyalarını deftere dinamik sağlayıcı olarak bağla (P-019).

    `build_registry(home)` imzasını değiştirmeden sonradan bağlamak isteyen yüzeyler
    (masaüstü oturumu) için ayrı tutulur.
    """
    from .mcp_prompt_commands import mcp_prompt_slash_commands, unlisted_prompt_command
    from .skill_commands import skill_slash_commands

    registry.set_dynamic(
        lambda: tuple(
            c
            for c in (*skill_slash_commands(skills()), *mcp_prompt_slash_commands())
            if isinstance(c, SlashCommand)
        )
    )
    registry.set_fallback(unlisted_prompt_command)


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


def _toggle_thinking(state: ReplState, argument: str) -> str:
    state.show_thinking = not state.show_thinking
    return messages.REPL_SHOW_THINKING.format(state=_on_off(state.show_thinking))


def _toggle_bell(state: ReplState, argument: str) -> str:
    state.bell = not state.bell
    return messages.REPL_BELL.format(state=_on_off(state.bell))


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


def parse_lesson_selection(argument: str, total: int) -> tuple[tuple[int, ...], str]:
    """`/forget` argümanını 1-tabanlı ders numaralarına çevir. Saftır.

    Kabul edilen biçimler: `3`, `3 7 9`, `3,7,9`, `2-5` ve karışımları. Sıra
    korunur, tekrar elenir. Geçersiz ya da aralık dışı bir numara SESSİZCE
    atlanmaz: hata metniyle döner — yanlış dersi silmek geri alınamaz.

    Dönüş: (numaralar, hata). Hata doluysa numaralar boştur.
    """
    ham = argument.replace(",", " ").split()
    if not ham:
        return (), messages.REPL_FORGET_USAGE

    secilen: list[int] = []
    for parca in ham:
        alt, ayrac, ust = parca.partition("-")
        try:
            araliklar = range(int(alt), int(ust) + 1) if ayrac else range(int(alt), int(alt) + 1)
        except ValueError:
            return (), messages.REPL_FORGET_INVALID.format(value=parca)
        for numara in araliklar:
            if not 1 <= numara <= total:
                return (), messages.REPL_FORGET_OUT_OF_RANGE.format(value=numara, total=total)
            if numara not in secilen:
                secilen.append(numara)
    return tuple(secilen), ""


def _forget(state: ReplState, argument: str) -> str:
    """`/forget <no…>` — `/lessons` tablosundaki numaralarla ders sil.

    Numara `/lessons` çıktısındaki sıradır; ikisi de `lessons.all()` sırasını
    kullanır, dolayısıyla aynı oturumda tutarlıdır.
    """
    lessons = state.memory.lessons.all()
    if not lessons:
        return messages.MEMORY_EMPTY_LESSONS

    numaralar, hata = parse_lesson_selection(argument, len(lessons))
    if hata:
        return hata

    silinen = state.memory.lessons.forget(tuple(lessons[numara - 1].text for numara in numaralar))
    return messages.REPL_FORGET_DONE.format(count=silinen)


def _model(state: ReplState, argument: str) -> str:
    """`/model` — `/model <ad>` agent modelini değiştirip kaydeder (#211, Claude Code).

    Fusion alt komutları (yalnız oturum): agent <id> | judge <id> | cand <ad|no> <id>
    | add <ad> <id> [etiket…] | rm <ad>. Argümansız çağrı etkin modelleri listeler.
    """
    parts = argument.split()
    if not parts:
        return model_select.format_models(state.config)
    result = model_command_result(state, parts)
    state.config = result.config
    return result.message


@dataclass(frozen=True, slots=True)
class ModelCommandResult:
    """CLI ve App aynı gerçek seçim ret/başarı sonucunu paylaşır."""

    config: Config
    message: str
    ok: bool


def model_command_result(state: ReplState, parts: list[str]) -> ModelCommandResult:
    try:
        config, message = _apply_model_command(state, parts)
    except ConfigError as error:
        return ModelCommandResult(state.config, str(error), False)
    return ModelCommandResult(config, message, config is not state.config)


def _apply_model_command(state: ReplState, parts: list[str]) -> tuple[Config, str]:
    action, arguments = parts[0].lower(), parts[1:]
    config = state.config
    if model_switch.is_direct_model(parts):
        return model_switch.switch_and_save(config, parts[0])

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
        wanted = model_select.normalize_tier_name(wanted)
        try:
            updated = model_select.apply_tier(state.config, wanted)
        except ConfigError as error:
            return str(error)
        result = model_flows.applied_result(updated, wanted)
    state.config = result.config
    return result.message


def _profiles(state: ReplState, argument: str) -> str:
    """`/profiles` — profilleri gör; `/profiles edit <profil> [incompatible]` baş modeli düzenle."""
    parts = argument.split()
    if not parts:
        return profiles_flow.list_profiles(state.config)
    if parts[0].lower() != "edit" or len(parts) < 2:
        return messages.PROFILES_EDIT_USAGE
    tier_name = parts[1]
    show_incompatible = len(parts) > 2 and parts[2].lower() == "incompatible"
    result = profiles_flow.edit_profile_primary(
        state.config, tier_name, show_incompatible=show_incompatible
    )
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
    resolution = resolve_reasoning(effort.value, capability_from_spec(state.config.agent))
    applied = messages.EFFORT_APPLIED.format(effort=effort.value)
    return f"{applied}\n{resolution.reason}" if resolution.reason else applied


def _ask_secret(prompt: str) -> str | None:
    """Gizli girdiyi EKRANA YANSITMADAN al (getpass). TTY yoksa None döner."""
    import getpass

    try:
        value = getpass.getpass(prompt)
    except (EOFError, KeyboardInterrupt):
        return None
    return value or None


def _providers(state: ReplState, argument: str) -> str:
    """`/providers` — sağlayıcıları listele; `/providers add` anahtar ekleme sihirbazı."""
    if argument.strip().lower() == "add":
        from ...config.credentials import FernetSecretStore
        from ...config.keys import secret_key, set_environ_value
        from ...config.paths import credentials_file

        store = FernetSecretStore(credentials_file(), secret_key=secret_key())
        return provider_flow.add_credential(
            store, ask_secret=_ask_secret, on_saved=set_environ_value
        )
    environ = environ_snapshot()
    rows = [messages.PROVIDERS_HEADER]
    for definition in BUILTIN_PROVIDERS:
        if not definition.implemented:
            durum = messages.PROVIDERS_FRAMEWORK
        elif definition.kind is ProviderKind.BROWSER_BACKED:
            durum = (
                messages.PROVIDERS_CONFIGURED
                if any(
                    session.enabled and session.provider == definition.id
                    for session in state.config.web_sessions
                )
                else messages.PROVIDERS_MISSING
            )
        elif definition.kind is ProviderKind.LOCAL:
            durum = messages.PROVIDERS_LOCAL
        elif definition.is_configured(environ):
            durum = messages.PROVIDERS_CONFIGURED
        else:
            durum = messages.PROVIDERS_MISSING
        rows.append(
            messages.PROVIDERS_ROW.format(
                name=definition.name,
                kind=definition.kind.value,
                status=definition.official_status.value,
                risk=definition.risk_level.value,
                state=durum,
            )
        )
    return "\n".join(rows)


def _mcp(state: ReplState, argument: str) -> str:
    """`/mcp` — dış MCP sunucularını listele/ekle/kaldır (`fusion mcp-add` eşdeğeri).

    Kullanıcı sohbette "şu MCP'yi kur" dediğinde model bunu shell aracıyla
    `fusion mcp-add` çalıştırarak da yapabilir; bu komut aynı yazım fonksiyonunu
    (`config.writer.write_mcp_servers`) REPL içinden kullanıcıya açar — tek
    doğruluk kaynağı korunur, iki giriş noktası vardır (RULES.md "UI ve CLI").
    """
    import shlex

    from ...config import writer
    from ...config.models import McpServerConfig

    parcalar = argument.strip().split(maxsplit=1)
    alt_komut = parcalar[0].lower() if parcalar else ""
    kalan = parcalar[1] if len(parcalar) > 1 else ""

    if alt_komut in ("", "list"):
        if not state.config.mcp_servers:
            return messages.MCP_NO_SERVERS
        # Argümanlarda gömülü token olabilir (`--token=…`): listeye ve transcript'e MASKELİ
        # girer (L2-28).
        return "\n".join(
            redact(
                messages.MCP_LIST_ROW.format(
                    name=sunucu.name,
                    scope=messages.MCP_SCOPE_LABELS.get(sunucu.scope.value, sunucu.scope.value),
                    transport=sunucu.transport.value,
                    target=sunucu.url or f"{sunucu.command} {' '.join(sunucu.args)}".rstrip(),
                )
            )
            for sunucu in state.config.mcp_servers
        )

    if alt_komut in ("prompts", "istemler", "resources", "kaynaklar"):
        from .mcp_prompt_commands import listing

        return listing(alt_komut)

    if alt_komut == "reconnect":
        # Claude Code `/mcp reconnect <sunucu>|all` (P-049). İşleyici eşzamansız bekleyemez;
        # havuz düşürmeyi sonraki turun bağlanma adımına erteler.
        from ...mcp_bridge.pool import request_mcp_reconnect

        hedef = kalan.strip()
        if not hedef:
            return messages.MCP_RECONNECT_USAGE
        if hedef == "all":
            for sunucu in state.config.mcp_servers:
                request_mcp_reconnect(sunucu.name)
            return messages.MCP_RECONNECT_ALL_SCHEDULED.format(count=len(state.config.mcp_servers))
        if not any(sunucu.name == hedef for sunucu in state.config.mcp_servers):
            return messages.MCP_NOT_FOUND.format(name=hedef)
        request_mcp_reconnect(hedef)
        return messages.MCP_RECONNECT_SCHEDULED.format(name=hedef)

    if alt_komut in ("remove", "del", "delete"):
        ad = kalan.strip()
        if not ad:
            return messages.MCP_REMOVE_USAGE
        if not any(sunucu.name == ad for sunucu in state.config.mcp_servers):
            return messages.MCP_NOT_FOUND.format(name=ad)
        kalanlar = tuple(sunucu for sunucu in state.config.mcp_servers if sunucu.name != ad)
        guncellenmis = replace(state.config, mcp_servers=kalanlar)
        try:
            writer.write_mcp_servers(guncellenmis)
        except ConfigError as error:
            return messages.MCP_SAVE_FAILED.format(error=error)
        state.config = guncellenmis
        return messages.MCP_REMOVED.format(name=ad)

    if alt_komut == "add":
        try:
            argumanlar_ham = shlex.split(kalan)
        except ValueError:
            return messages.MCP_ADD_USAGE
        if len(argumanlar_ham) < 2:
            return messages.MCP_ADD_USAGE
        ad, komut, *argumanlar = argumanlar_ham
        eskiler = tuple(sunucu for sunucu in state.config.mcp_servers if sunucu.name != ad)
        yeniden_yazildi = len(eskiler) != len(state.config.mcp_servers)
        yeni = McpServerConfig(name=ad, command=komut, args=tuple(argumanlar))
        guncellenmis = replace(state.config, mcp_servers=(*eskiler, yeni))
        try:
            writer.write_mcp_servers(guncellenmis)
        except ConfigError as error:
            return messages.MCP_SAVE_FAILED.format(error=error)
        state.config = guncellenmis
        sablon = messages.MCP_REPLACED if yeniden_yazildi else messages.MCP_ADDED
        return sablon.format(name=ad)

    return messages.MCP_USAGE


def _format_capabilities(items: tuple[Capability, ...], *, empty: str) -> str:
    if not items:
        return empty
    return "\n".join(
        f"· {item.name} [{item.source}]" + (f" — {item.description}" if item.description else "")
        for item in items
    )


def _skills(state: ReplState, argument: str) -> str:
    """`/skills [arama]` listeler; `reload` yeniden tarar; `doctor` teşhis; `new <ad>` üretir."""
    assert state.capabilities is not None
    eylem, _, kalan = argument.strip().partition(" ")
    if eylem in ("reload", "yenile"):
        state.capabilities.invalidate()
        return messages.SKILLS_RELOADED.format(
            skills=len(state.capabilities.skills()), agents=len(state.capabilities.agents())
        )
    if eylem in ("doctor", "teshis", "teşhis"):
        from ...tools.capability_doctor import diagnose, render_report

        return render_report(
            diagnose(state.capabilities),
            skills=len(state.capabilities.skills()),
            agents=len(state.capabilities.agents()),
        )
    if eylem in ("new", "yeni"):
        return _prepare_authoring(state, macros.SKILL_NEW_TASK, kalan)
    items = search_capabilities(state.capabilities.skills(), argument.strip(), limit=50)
    return _format_capabilities(items, empty=messages.SKILLS_EMPTY)


def _agents(state: ReplState, argument: str) -> str:
    """`/agents`: güncel Claude Code gibi yalnız hatırlatma basar (#37).

    Eski Fusion biçimleri (`/agents <arama>`, `/agents new <ad>`) bir sürüm boyunca çalışır.
    """
    assert state.capabilities is not None
    eylem, _, kalan = argument.strip().partition(" ")
    if not eylem:
        return messages.AGENTS_REMINDER
    if eylem in ("new", "yeni"):
        return _prepare_authoring(state, macros.AGENT_NEW_TASK, kalan)
    items = search_capabilities(state.capabilities.agents(), argument.strip(), limit=50)
    return _format_capabilities(items, empty=messages.AGENTS_EMPTY)


def _prepare_authoring(state: ReplState, template: str, name: str) -> str:
    """Beceri/ajan üretme görevini sıradaki tur için hazırla (makrolarla aynı sözleşme)."""
    ad = name.strip() or "<ad>"
    state.engine = Engine.AGENT
    state.pending_task = template.format(name=ad)
    state.pending_mode = Mode.NONE
    return messages.CAPABILITY_AUTHORING_STARTED.format(name=ad)


def resume_choices(refs: Sequence[SessionRef]) -> list[Choice]:
    """Oturum listesini seçim satırlarına çevir.

    Düz REPL bunu `_resume` içinde doğrudan `pick()`'e verir; TUI aynı listeyi
    kendi uygulama-içi modalinde gösterir (bkz. `tui_loop._TuiSession`) — tek
    liste kaynağı, iki sunum yüzeyi.
    """
    return [
        Choice(ref.session_id, ref.title, _when(ref.updated_at)) for ref in refs[:RESUME_LIST_LIMIT]
    ]


def _resume(source_name: str) -> Handler:
    """`/resume<kaynak>` işleyicisi üret. Kaynak adı kapatmada sabitlenir.

    Argüman DOLUYSA (TUI'nin uygulama-içi modalından ya da betikten gelen
    session_id) o oturum doğrudan devralınır — seçici HİÇ AÇILMAZ. Argüman
    BOŞSA (düz konsol REPL yolu) `pick()` ile oturum seçtirilir. TUI bu ikinci
    dalı hiç kullanmaz: nested prompt_toolkit seçicisi tam-ekranı bozar, bu
    yüzden TUI kendi modalını açıp seçilen session_id'yi argüman olarak
    ilk dala geçirir.
    """

    def _handler(state: ReplState, argument: str) -> str:
        source = source_by_name(state.home, source_name)
        if source is None:
            return messages.HISTORY_EMPTY
        refs = source.list(state.root, limit=RESUME_LIST_LIMIT)
        if not refs:
            return messages.HISTORY_EMPTY

        session_id = argument.strip()
        if not session_id:
            chosen = pick(resume_choices(refs), title=messages.HISTORY_PICK_TITLE)
            if chosen is None:
                return ""
            session_id = chosen

        ref = next((candidate for candidate in refs if candidate.session_id == session_id), None)
        if ref is None:
            return messages.HISTORY_EMPTY

        digest = build_digest(source, ref)
        state.pending_digest = digest.text
        line = messages.HISTORY_RESUMED.format(title=ref.title)
        if digest.secret_count:
            line += "\n" + messages.HISTORY_SECRETS_FOUND.format(count=digest.secret_count)
        return line

    return _handler


def _when(epoch: float) -> str:
    """Zaman damgasını listede gösterilecek kısa biçime çevir."""
    from datetime import datetime

    if not epoch:
        return ""
    return datetime.fromtimestamp(epoch).strftime("%d/%m %H:%M")


def _init(state: ReplState, argument: str) -> str:
    """`/init [agents|claude]` — proje talimat dosyasını (AGENTS.md/CLAUDE.md) modele yazdır.

    Görev depodan ölçülen olgularla kurulur (bkz. `instruction_audit.init_task`); çalıştırma
    makrolarla aynı: REPL döngüsü bekleyen görevi sıradaki turda başlatır.
    """
    from ...engines.agent.instruction_audit import DEFAULT_INIT_FORMAT, INIT_TARGETS, init_task

    fmt = argument.strip().lower() or DEFAULT_INIT_FORMAT
    target = INIT_TARGETS.get(fmt, INIT_TARGETS[DEFAULT_INIT_FORMAT])
    state.engine = Engine.AGENT
    state.pending_task = init_task(state.root, state.home, fmt=fmt)
    state.pending_mode = Mode.NONE
    return messages.REPL_INIT_STARTED.format(target=target)


def _health(state: ReplState, argument: str) -> str:
    """`/health` — sağlayıcı güvenilirlik skorlarını ve circuit breaker durumunu göster."""
    registry = state.health
    snapshot = registry.snapshot() if registry is not None else ()
    if not snapshot:
        return messages.HEALTH_EMPTY
    rows = [messages.HEALTH_HEADER]
    for model_id, entry in snapshot:
        phase = messages.HEALTH_PHASE.get(entry.phase.value, entry.phase.value)
        rows.append(messages.HEALTH_ROW.format(model=model_id, score=entry.score, phase=phase))
    return "\n".join(rows)


def _rewind(state: ReplState, argument: str) -> str:
    """`/rewind` (`/checkpoint`, `/undo`) — defter boşken eski son-tur kaydı geri alınır.

    Tur defteri dolmadan kaydedilen değişiklik (dışarıdan verilen `last_changes`) için menüde
    seçilecek tur yoktur; o durumda geri alınacak tek şey o kayıttır.
    """
    if not state.checkpoints.entries() and state.last_changes:
        return _undo(state, argument)
    return rewind.rewind_command(state, argument)


def _undo(state: ReplState, argument: str) -> str:
    """`/undo` — son agent turunun dosya değişikliklerini geri al (= `/rewind <son> kod`).

    Tur checkpoint defteri doluysa oradan geri alınır (kayıt düşer, `/rewind` listesi
    tutarlı kalır). Defter boşken eski `last_changes` yolu korunur: dışarıdan kayıt
    verilen (masaüstü, test) durumlar aynı davranır.
    """
    if state.checkpoints.latest() is not None:
        return rewind.undo_last(state)
    kayit = state.last_changes
    if kayit is None or not kayit:
        return messages.UNDO_NOTHING
    tum_yollar = kayit.restorable_paths
    geri_alinan = kayit.restore()
    # Çakışan ilk hâller, kullanıcı yeniden deneyebilsin diye kayıtta kalır.
    state.last_changes = kayit if kayit.conflicts else None
    if len(geri_alinan) < len(tum_yollar):
        basarisiz = "\n".join(f"  {yol}" for yol in tum_yollar if yol not in geri_alinan)
        return (
            messages.UNDO_PARTIAL.format(
                count=len(geri_alinan), failed=len(tum_yollar) - len(geri_alinan)
            )
            + (
                "\nGeri alma çakışması: mevcut dosyalar ve ilk kayıtları korundu."
                if kayit.conflicts
                else ""
            )
            + f"\n{basarisiz}"
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


def _subtask(state: ReplState, argument: str) -> str:
    """`/subtask <görev>`: görevi fork alt ajan turu olarak HAZIRLA (P-054); döngü koşturur."""
    task = argument.strip()
    if not task:
        return messages.SUBTASK_USAGE
    state.pending_task = task
    state.pending_mode = macros.Mode.SUBTASK
    return messages.SUBTASK_QUEUED


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
        task = macro.build(argument)
        # Claude Code'daki gibi: kullanıcı aynı adlı bir skill tanımladıysa
        # (`.claude/skills/<ad>/SKILL.md`) onun gövdesi yerleşik metnin ÖNÜNE
        # eklenir; yerleşik metin silinmez, kullanıcı kuralı önceliklidir.
        override = macro_skill_override(state, name)
        lines = [messages.REPL_MACRO_STARTED.format(name=name)]
        if override is not None:
            body, path = override
            task = f"{body.strip()}\n\n{task}"
            lines.append(messages.REPL_MACRO_SKILL_PREPENDED.format(name=name, path=path))
        state.pending_task = task
        state.pending_mode = macro.mode
        return "\n".join(lines)

    return _handler


def _code_review(state: ReplState, argument: str) -> str:
    """`/code-review` (takma ad `/review`, #214): seviye/bayrak/hedef ayrıştırılır, inceleme
    ana bağlamı devralan fork alt ajanda koşar."""
    request = code_review.parse(argument)
    if isinstance(request, str):
        return request
    if request.ultra:
        return messages.CODE_REVIEW_ULTRA_UNAVAILABLE
    remembered = code_review.remember(state.config.memory_dir, request)
    lines = [messages.REPL_MACRO_STARTED.format(name="code-review")]
    level = request.level
    if level is None:
        level = remembered.get("level")
        if level is not None:
            lines.append(messages.CODE_REVIEW_REUSING.format(level=level))
        else:
            effort = getattr(state.config.runtime.reasoning_effort, "value", "")
            level = effort if effort in code_review.LEVELS else "medium"
    max_findings = request.max_findings
    if max_findings in (None, "default"):
        max_findings = remembered.get("max_findings")
    task = code_review.build_task(request, level, max_findings)
    override = macro_skill_override(state, "code-review")
    if override is not None:
        body, path = override
        task = f"{body.strip()}\n\n{task}"
        lines.append(messages.REPL_MACRO_SKILL_PREPENDED.format(name="code-review", path=path))
    state.engine = Engine.AGENT
    state.pending_task = task
    state.pending_mode = Mode.SUBTASK
    return "\n".join(lines)


def macro_skill_override(state: ReplState, name: str) -> tuple[str, Path] | None:
    """Makroyla aynı adlı kullanıcı skill'inin gövdesi ve yolu; yoksa None.

    Boş gövde ya da okunamayan dosya "yok" sayılır: bozuk bir skill yerleşik makroyu
    susturmamalı.
    """
    from ...tools.capabilities import load_agent_prompt

    if state.capabilities is None:
        return None
    wanted = name.casefold()
    for skill in state.capabilities.skills():
        if skill.name.casefold() != wanted:
            continue
        body = load_agent_prompt(skill.path)
        if body.strip() and not body.startswith("HATA:"):
            return body, skill.path
    return None


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
    return messages.reindex_summary(state.memory.code_index.reindex())


def _on_off(value: bool) -> str:
    return messages.REPL_ON if value else messages.REPL_OFF


# --------------------------------------------------------------------------- #
# Kayıtlar
# --------------------------------------------------------------------------- #

_COMMANDS: tuple[SlashCommand, ...] = (
    SlashCommand("help", messages.CMD_HELP, lambda state, argument: "", ("h", "?")),
    SlashCommand("tips", messages.CMD_TIPS, lambda state, argument: "", group="Bilgi"),
    SlashCommand("exit", messages.CMD_EXIT, _exit, ("quit", "q")),
    SlashCommand(
        "clear",
        messages.CMD_CLEAR,
        session_clear.clear_command,
        ("reset", "new"),
        usage="[ad]",
    ),
    SlashCommand("agent", messages.CMD_AGENT, _use_agent, group="Motor"),
    SlashCommand("fusion", messages.CMD_FUSION, _use_fusion, group="Motor"),
    SlashCommand("auto", messages.CMD_AUTO, _set_mode(ApprovalMode.AUTO), group="Onay modu"),
    SlashCommand(
        "edits", messages.CMD_EDITS, _set_mode(ApprovalMode.ACCEPT_EDITS), group="Onay modu"
    ),
    SlashCommand(
        "security",
        messages.CMD_SECURITY,
        _set_mode(ApprovalMode.SECURITY),
        ("manual", "manuel"),
        group="Onay modu",
    ),
    SlashCommand(
        "plan", messages.CMD_PLAN, plan_card.command, group="Onay modu", usage="[goster|ac]"
    ),
    SlashCommand("bypass", messages.CMD_BYPASS, _set_mode(ApprovalMode.BYPASS), group="Onay modu"),
    SlashCommand(
        "auto-mode",
        messages.CMD_AUTO_MODE,
        auto_mode_command.auto_mode_command,
        group="Onay modu",
        usage="[durum|devam|off|ask_only|on]",
    ),
    SlashCommand(
        "permissions",
        messages.CMD_PERMISSIONS,
        permissions_command.permissions,
        ("izinler",),
        group="Onay modu",
        usage="[list|add|remove] …",
    ),
    SlashCommand(
        "hooks", messages.CMD_HOOKS, hooks_command.hooks, ("kancalar",), group="Onay modu"
    ),
    SlashCommand(
        "sandbox",
        messages.CMD_SANDBOX,
        sandbox_command,
        group="Onay modu",
        usage="[on|off|izin <alan>|…]",
    ),
    SlashCommand(
        "compact",
        messages.CMD_COMPACT,
        lambda state, argument: "",
        group="Agent",
        usage="[talimat]",
    ),
    SlashCommand("type", messages.CMD_TASK_TYPE, _set_task_type, group="Fusion", usage="<tip>"),
    SlashCommand("all", messages.CMD_SHOW_ALL, _toggle_all, group="Fusion"),
    SlashCommand("thinking", messages.CMD_SHOW_THINKING, _toggle_thinking, group="Agent"),
    SlashCommand("zil", messages.CMD_BELL, _toggle_bell, group="Agent"),
    SlashCommand(
        "onizleme",
        messages.CMD_PREVIEW,
        preview_command,
        aliases=("preview",),
        group="Agent",
        usage="[ad]",
    ),
    SlashCommand(
        "tarayici",
        messages.CMD_TARAYICI,
        browser_command,
        group="Agent",
        usage="[ac|devral|birak|kapat]",
    ),
    SlashCommand(
        "oturum-aktar",
        messages.WEBOTURUM_CMD,
        web_session_command.handler,
        aliases=("import-web-session",),
        group="Agent",
        usage="<sağlayıcı> <profil> <alan>… [--yes]",
    ),
    SlashCommand("synth", messages.CMD_SYNTHESIS, _toggle_synthesis, group="Fusion"),
    SlashCommand("good", messages.CMD_GOOD, _feedback(Feedback.GOOD), group="Bellek"),
    SlashCommand("bad", messages.CMD_BAD, _feedback(Feedback.BAD), group="Bellek"),
    SlashCommand("revise", messages.CMD_REVISE, _feedback(Feedback.REVISE), group="Bellek"),
    SlashCommand("learn", messages.CMD_LEARN, _learn, group="Bellek", usage="<kural>"),
    SlashCommand("seed", messages.CMD_SEED, _seed, group="Bellek"),
    SlashCommand("reindex", messages.CMD_REINDEX, _reindex, group="Bellek"),
    SlashCommand("model-stats", messages.CMD_STATS, lambda state, argument: "", group="Bellek"),
    SlashCommand("lessons", messages.CMD_LESSONS, lambda state, argument: "", group="Bellek"),
    SlashCommand("forget", messages.CMD_FORGET, _forget, group="Bellek", usage="<no…>"),
    SlashCommand(
        "memory",
        messages.CMD_MEMORY,
        memory_commands.memory,
        ("bellek",),
        group="Bellek",
        usage="[on|off|edit|list|import claude|<konu>]",
    ),
    SlashCommand(
        "subtask",
        messages.CMD_SUBTASK,
        _subtask,
        ("altgorev", "altgörev"),
        group="Agent",
        usage="<görev>",
    ),
    SlashCommand(
        "persona",
        messages.CMD_PERSONA,
        persona_commands.persona_command,
        ("kisilik", "kişilik"),
        group="Agent",
        usage="[ad|off]",
    ),
    SlashCommand("models", messages.CMD_MODELS, lambda state, argument: "", group="Model"),
    SlashCommand(
        "model",
        messages.CMD_MODEL,
        _model,
        group="Model",
        usage="[model|agent|judge|cand|add|rm …]",
    ),
    SlashCommand("mode", messages.CMD_MODE, _mode, group="Model", usage="[profil]"),
    SlashCommand(
        "profiles", messages.CMD_PROFILES, _profiles, group="Model", usage="[edit <profil>]"
    ),
    SlashCommand("effort", messages.CMD_EFFORT, _effort, group="Model", usage="[seviye]"),
    SlashCommand("level", messages.CMD_LEVEL, _level, group="Model", usage="[kademe]"),
    SlashCommand(
        "output-style",
        messages.CMD_OUTPUT_STYLE,
        output_style_command.output_style_command,
        group="Model",
        usage="[ad]",
    ),
    SlashCommand("provider", messages.CMD_PROVIDER, _provider, group="Model"),
    SlashCommand("providers", messages.CMD_PROVIDERS, _providers, group="Model", usage="[add]"),
    SlashCommand(
        "development", messages.CMD_DEVELOPMENT, _development, group="Model", aliases=("dev",)
    ),
    SlashCommand("verify", messages.CMD_VERIFY, _verify, group="Agent"),
    # Claude Code: `/checkpoint` ve `/undo` `/rewind` takma adıdır, aynı menüyü açar (#201).
    SlashCommand(
        "rewind",
        messages.CMD_REWIND,
        _rewind,
        ("checkpoint", "undo"),
        group="Agent",
        usage="[no] [kod|konuşma|ikisi]",
    ),
    # Claude Code: `/cost` ve `/stats` `/usage` takma adıdır (#208).
    SlashCommand(
        "usage", messages.CMD_USAGE, lambda state, argument: "", ("cost", "stats"), group="Bilgi"
    ),
    SlashCommand(
        "config",
        messages.CMD_CONFIG,
        config_command.config_command,
        ("settings",),
        group="Bilgi",
        usage="[key=value ...|filtre|yol]",
    ),
    SlashCommand("status", messages.CMD_STATUS, lambda state, argument: "", group="Bilgi"),
    SlashCommand("context", messages.CMD_CONTEXT, lambda state, argument: "", group="Bilgi"),
    SlashCommand("health", messages.CMD_HEALTH, _health, group="Bilgi"),
    # Claude Code (#212): `/doctor [prompt-audit [path]]`, takma adı `/checkup`.
    SlashCommand(
        "doctor",
        messages.CMD_DOCTOR,
        doctor_command.doctor_command,
        ("checkup",),
        group="Bilgi",
        usage="[prompt-audit [yol]]",
    ),
    SlashCommand("init", messages.CMD_INIT, _init, group="Makro", usage="[agents|claude]"),
    SlashCommand("mcp", messages.CMD_MCP, _mcp, group="Bilgi", usage="[add|remove] …"),
    SlashCommand("skills", messages.CMD_SKILLS, _skills, group="Bilgi", usage="[arama]"),
    SlashCommand(
        "skill-doctor",
        messages.CMD_SKILL_DOCTOR,
        lambda state, argument: _skills(state, "doctor"),
        group="Bilgi",
    ),
    SlashCommand("agents", messages.CMD_AGENTS, _agents, group="Bilgi"),
    # `/goal <koşul>` (P-058): ilk turu hedef makrosu hazırlar; turlar arası değerlendirme
    # `goal_flow`'dadır. Argümansız `/goal` durumu söyler (Claude Code ile aynı).
    SlashCommand(
        "goal",
        messages.CMD_GOAL,
        goal_command.goal_handler(_macro("goal")),
        group="Makro",
        usage="<koşul> | durum | devam | clear",
    ),
    *(
        SlashCommand(
            name,
            summary,
            _macro(name),
            aliases=aliases,
            group="Makro",
            usage="<görev>" if macros.MACROS[name].argument_required else "[görev]",
        )
        for name, summary, aliases in (
            ("grill-me", messages.CMD_GRILL, ()),
            ("bug", messages.CMD_BUG, ()),
            ("commit", messages.CMD_COMMIT, ()),
            ("browser", messages.CMD_BROWSER, ()),
            ("plan-yurut", messages.CMD_PLAN_RUN, ()),
            ("simplify", messages.CMD_SIMPLIFY, ()),
            ("security-review", messages.CMD_SECURITY_REVIEW, ()),
            ("debug", messages.CMD_DEBUG, ()),
            ("batch", messages.CMD_BATCH, ()),
            ("pr", messages.CMD_PR, ()),
            ("autofix-pr", messages.CMD_AUTOFIX_PR, ()),
        )
    ),
    SlashCommand(
        "terminal-setup",
        messages.CMD_TERMINAL_SETUP,
        lambda state, _argument: terminal_setup.terminal_setup(state.home),
        group="Görünüm",
    ),
    SlashCommand(
        "code-review",
        messages.CMD_REVIEW,
        _code_review,
        ("review",),
        group="Makro",
        usage="[low|medium|high|xhigh|max|ultra] [--fix] [--comment] "
        "[--max-findings n|all|default] [pr#|branch|path]",
    ),
    SlashCommand(
        "cop",
        messages.CMD_TRASH,
        workspace_commands.trash,
        group="Agent",
        usage="[geri-al <kimlik>]",
    ),
    SlashCommand(
        "trace", messages.CMD_TRACE, workspace_commands.trace, group="Bilgi", usage="[kimlik|liste]"
    ),
    SlashCommand(
        "add-dir",
        messages.CMD_ADD_DIR,
        workspace_commands.add_dir,
        group="Agent",
        usage="[yol|kaldir <yol>]",
    ),
    SlashCommand("cd", messages.CMD_CD, cd_command, group="Agent", usage="[yol]"),
    # REPL'de asenkron (`async_commands`); bu eşzamanlı işleyici masaüstü/uzak yoludur.
    SlashCommand(
        "voice",
        messages.CMD_VOICE,
        voice_command.desktop_handler,
        ("dikte",),
        group="Agent",
        usage="[gonder|durum]",
    ),
    SlashCommand("schedule", messages.CMD_SCHEDULE, _schedule, group="Makro", usage="<saniye>"),
    SlashCommand(
        "loop",
        messages.CMD_LOOP,
        loop_command.command,
        group="Makro",
        usage="[aralık] <görev|/komut> | list | stop [id]",
    ),
    # İşleyici boş: `/rc` asenkron çalışır, döngüler `repl.remote_control.run` ile ele alır.
    SlashCommand(
        "rc",
        messages.CMD_RC,
        lambda state, argument: "",
        ("remote-control",),
        group="Bilgi",
        usage="[kod [telegram]|onayla|durum|telegram|durdur]",
    ),
    SlashCommand(
        "export",
        messages.CMD_EXPORT,
        export_commands.export_transcript,
        group="Agent",
        usage="[yol] [json] [pano]",
    ),
    SlashCommand(
        "copy", messages.CMD_COPY, export_commands.copy_answer, group="Agent", usage="[N]"
    ),
    SlashCommand("diff", messages.CMD_DIFF, diff_command, group="Agent", usage="[tam]"),
    SlashCommand(
        "theme", messages.CMD_THEME, view_commands.theme_command, group="Görünüm", usage="[ad]"
    ),
    SlashCommand(
        "tui",
        messages.CMD_TUI,
        view_commands.tui_command,
        group="Görünüm",
        usage="[default|fullscreen]",
    ),
    SlashCommand(
        "search",
        messages.CMD_SEARCH,
        view_commands.search_command,
        group="Görünüm",
        usage="<metin>",
    ),
    SlashCommand(
        "statusline",
        messages.CMD_STATUSLINE,
        status_line.statusline_command,
        group="Görünüm",
        usage="[istek]",
    ),
    SlashCommand(
        "keybindings",
        messages.CMD_KEYBINDINGS,
        keybinding_commands.keybindings_command,
        group="Görünüm",
    ),
    SlashCommand(
        "vim", messages.CMD_VIM, keybinding_commands.vim_command, group="Görünüm", usage="[on|off]"
    ),
    SlashCommand(
        "resume",
        messages.CMD_RESUME_OWN,
        session_resume.resume_command,
        ("continue",),
        group="Geçmiş",
        usage="[kimlik|ad]",
    ),
    SlashCommand(
        "rename", messages.CMD_RENAME, session_resume.rename_command, group="Geçmiş", usage="[ad]"
    ),
    SlashCommand(
        "branch", messages.CMD_BRANCH, session_resume.branch_command, group="Geçmiş", usage="[ad]"
    ),
    # Claude Code (#221): `/btw` geçmişe girmeyen, araçsız yan soru (help_view basar).
    SlashCommand("btw", messages.CMD_BTW, btw_command.btw_command, group="Agent", usage="[soru]"),
    SlashCommand("recap", messages.CMD_RECAP, recap_command.recap_command, group="Agent"),
    # Claude Code (#229): `/fork [istem]` konuşmayı arka plan kopyasına verir.
    SlashCommand(
        "fork", messages.CMD_FORK, fork_command.fork_command, group="Agent", usage="[istem]"
    ),
    SlashCommand(
        "background",
        bg_texts.CMD_BACKGROUND,
        background_commands.background_command,
        ("bg",),
        group="Agent",
        usage="[görev]",
    ),
    SlashCommand(
        "tasks", bg_texts.CMD_TASKS, background_commands.tasks_command, group="Agent", usage="[…]"
    ),
    SlashCommand(
        "list-agents",
        bg_texts.CMD_LIST_AGENTS,
        background_commands.list_agents_command,
        ("peers",),
        group="Agent",
        usage="[al|reddet <no>|gonder <ad> <mesaj>]",
    ),
    SlashCommand(
        "team",
        messages.EKIP_CMD_TEAM,
        team_commands.team_command,
        group="Agent",
        usage="[goster|sil|mesaj] [ad] | [kur] <hedef>",
    ),
    SlashCommand(
        "workflows",
        messages.AKIS_CMD_WORKFLOWS,
        workflow_commands.workflows_command,
        group="Agent",
        usage="[goster|iptal|sil] [ad|koşu] | <ad> [girdi=değer]",
    ),
    SlashCommand(
        "worktree",
        messages.CMD_WORKTREE,
        worktrees.worktree_command,
        group="Agent",
        usage="[ad|cik|liste]",
    ),
    # Eklenti paketi ve içe aktarma (P-059, P-071); gövdeler kendi modüllerinde.
    SlashCommand(
        "plugin",
        messages.EKLENTI_CMD_PLUGIN,
        plugin_command.plugin_command,
        ("plugins", "eklenti"),
        group="Bilgi",
        usage="[liste|kur|dogrula|ac|kapat|kaldir|kesfet|pazar] …",
    ),
    SlashCommand(
        "import",
        messages.EKLENTI_CMD_IMPORT,
        _import_or_history,
        ("ice-aktar",),
        group="Bilgi",
        usage="<claude|codex|gemini|cursor> [--dry-run|--yes] | history <kaynak> [oturum]",
    ),
    SlashCommand(
        "release-notes",
        messages.EKLENTI_CMD_RELEASE_NOTES,
        import_command.release_notes_command,
        ("surum-notlari",),
        group="Bilgi",
        usage="[sürüm|liste]",
    ),
)

#: Asenkron çalışan ve konsola kendi yazan komutlar: `/rc` (uzaktan kontrol), `/voice` (dikte),
#: `/oturum-aktar` (web model oturumundan profil kopyası).
ASYNC_COMMANDS = frozenset({"rc", "voice", "oturum-aktar"})

#: Kendi çıktısını basan komutlar (tablo, panel, ekran temizleme). REPL döngüsü
#: bunları özel olarak ele alır; işleyicileri boş metin döndürür.
RENDERED_COMMANDS = frozenset(
    {
        "help",
        "tips",
        "model-stats",
        "lessons",
        "models",
        "compact",
        "usage",
        "status",
        "context",
        "doctor",
        "btw",
        "recap",
    }
)

#: Argümansız hâli kendi basan, argümanla işleyiciye düşen komutlar: `/doctor` kurulum
#: tanısını basar (`fusion doctor` ile aynı); `/doctor prompt-audit [yol]` talimat
#: denetimini döndürür.
RENDERED_WHEN_BARE = frozenset({"doctor"})


def renders_itself(name: str, argument: str) -> bool:
    """Komut çıktısını `help_view.render` mı basar, yoksa işleyici mi döndürür?"""
    if name not in RENDERED_COMMANDS:
        return False
    return not (name in RENDERED_WHEN_BARE and argument.strip())


def is_command_line(line: str) -> bool:
    """`/` ile başlayan satır KOMUT mu, yoksa yol ile başlayan sıradan mesaj mı?

    Ölçüldü (30 Ekim): `/` ile başlayan her satır komut sayılıyordu; "/Users/x/proje/main.py
    dosyasını incele" "bilinmeyen komut" hatası verip gönderilemiyordu (L2-16). Komut adı
    düz bir sözcüktür; ilk sözcükte bir `/` daha varsa bu bir yoldur ve mesaj olarak gider.
    """
    if not line.startswith("/"):
        return False
    ilk = line.split(maxsplit=1)[0]
    return "/" not in ilk[1:]


def parse(line: str) -> tuple[str, str]:
    """`/komut argüman` satırını (komut, argüman) olarak ayır."""
    stripped = line[1:].strip()
    if not stripped:
        return "", ""
    name, _, argument = stripped.partition(" ")
    return name.lower(), argument.strip()
