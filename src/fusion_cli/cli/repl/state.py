"""REPL oturum durumu.

Tek bir yerde tutulur ve komut işleyicilerine geçirilir; modüller arası global
değişken yoktur. Oturum boyunca değişen her şey buradadır.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from dataclasses import dataclass, field, fields, replace
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from ...config.live import ConfigRevision, reload_checked, revision
from ...config.models import Config
from ...config.permission_rules import PermissionRuleSet, load_permission_rules
from ...config.permissions import load_allowed_commands
from ...core.changeset import ChangeSet
from ...core.errors import ConfigError
from ...core.health import HealthRegistry
from ...core.pull_request import PullRequestLink
from ...core.remotion_browser import RemotionBrowser
from ...core.session_cron import SessionCron
from ...core.session_goal import SessionGoal
from ...core.turn_checkpoints import TurnCheckpointLedger
from ...core.types import FusionResult, Message
from ...core.worktree import Worktree, WorktreeSwitch
from ...engines.agent.approval import ApprovalMemory, ApprovalMode, next_mode
from ...engines.agent.child_runs import ChildRuns
from ...engines.agent.remotion_bridge import FrameTransport
from ...engines.agent.skill_turn import TurnModelChoice
from ...engines.agent.team import Persona
from ...engines.hooks.session import HookSession, open_hook_session
from ...memory.factory import Memory
from ...memory.plain_memory import PlainMemory, build_plain_memory
from ...observability.cost import CostTracker
from ...observability.usage_log import UsageLog
from ...tools.capabilities import Capability, CapabilityRegistry
from ...tools.capability_overrides import registry_from_config
from ..rule_notices import attach_rule_writer
from .macros import Mode

if TYPE_CHECKING:  # pragma: no cover - yalnızca tip denetimi
    from ...remote.host import RemoteControlHost
    from ...tools.browser_shared import SharedBrowser
    from .agent_link import AgentLink


def rebase_session_changes(baseline: Config, session: Config, loaded: Config) -> Config:
    """Dosyadan yeniden yüklenen yapılandırmanın üstüne OTURUM değişikliklerini bindir.

    Üç yönlü birleşim, `Config` alan düzeyinde: oturumun `baseline`'a göre değiştirdiği
    alan (`/effort`, `/model agent x`, `/profiles edit`…) korunur; oturumun dokunmadığı
    alan dosyadan (`loaded`) gelir. Böylece kontrol paneli değişikliği alınırken
    kullanıcının oturumluk seçimleri sessizce silinmez (L2-08).
    """
    merged = {
        item.name: getattr(session, item.name)
        if getattr(session, item.name) != getattr(baseline, item.name)
        else getattr(loaded, item.name)
        for item in fields(Config)
        if item.name != "source"
    }
    return replace(loaded, **merged)


@dataclass(frozen=True, slots=True)
class Reminder:
    """Kullanıcının kurduğu, süresi dolunca gösterilecek hatırlatma."""

    due_in_seconds: int
    text: str


class Engine(Enum):
    """Bir mesajın hangi motora gideceği. Onay modundan BAĞIMSIZDIR."""

    AGENT = "agent"
    FUSION = "fusion"


#: Fusion görev tipleri — `task_model_map` anahtarlarıyla aynı.
TASK_TYPES = ("general", "code", "reasoning", "agent")


#: `run_agent`/`run_forked_turn` imzalı tur çalıştırıcısı (bkz. `PendingExtras.fork_runner`).
# Any: tur çalıştırıcılarının imzası geniş anahtar sözcüklüdür; yalnız sarmalanır.
TurnRunner = Callable[..., Any]


@dataclass(frozen=True, slots=True)
class PendingExtras:
    """`/beceri` komutunun sıradaki tura taşıdığı ekler (bkz. `ReplState.take_pending_extras`)."""

    context: str = ""
    tools: frozenset[str] | None = None
    #: Becerinin `model`/`effort` alanı: yalnız bu turun yapılandırmasını değiştirir (P-020).
    model_choice: TurnModelChoice = field(default_factory=TurnModelChoice)
    #: Becerinin `disallowed-tools` alanı (Fusion adları).
    denied: frozenset[str] = frozenset()
    #: `context: fork` + `agent:` → fork turunu bu alt ajan tanımı koşar.
    fork_agent: str = ""

    def merged_tools(self, base: set[str] | None) -> set[str] | None:
        """Yüzeyin kendi kısıtıyla kesişim; ikisi de yoksa None (kısıt yok)."""
        if self.tools is None:
            return base
        return set(self.tools) if base is None else set(self.tools) & base

    def merged_denied(self, base: frozenset[str]) -> frozenset[str]:
        """Kişiliğin yasaklarıyla birleşim: beceri yasak ekler, kaldıramaz."""
        return frozenset(base) | self.denied

    def turn_config(self, config: Config) -> Config:
        """Bu turun yapılandırması (becerinin modeli/eforu); seçim yoksa aynı nesne."""
        return self.model_choice.apply(config)

    def fork_runner(self, runner: TurnRunner) -> TurnRunner:
        """Fork turu çalıştırıcısı; `agent:` varsa o tanımla koşar."""
        return functools.partial(runner, persona=self.fork_agent) if self.fork_agent else runner


@dataclass(slots=True)
class ReplState:
    """Oturumun tüm değişken durumu."""

    config: Config
    memory: Memory
    root: Path
    #: Geçmiş, yetenek ve dış bellek kökü. Composition root tarafından enjekte edilir.
    home: Path
    #: Transcript ve checkpoint aynı sohbet sahibini kullanır; yeni REPL ayrı kapsamdır.
    conversation_id: str = field(default_factory=lambda: f"session-{uuid4().hex}", kw_only=True)
    #: Kanca oturumu (P-009); ilk `hooks()` çağrısında kurulur.
    hook_session: HookSession | None = field(default=None, kw_only=True)
    #: Bir sonraki SessionStart'ın zorunlu kaynağı (`/branch`, `--fork-session` → `fork`).
    hook_start_source: str = field(default="", kw_only=True)
    #: Kullanıcının sohbete verdiği ad (`--name`, `/rename`); yoksa boş.
    conversation_name: str = field(default="", kw_only=True)
    #: Oturum bir git çalışma ağacındaysa künyesi (`--worktree`, `/worktree`); `root` o ağaçtır.
    worktree: Worktree | None = field(default=None, kw_only=True)
    #: Proje kökünün YANINDA erişime açılan dizinler (`--add-dir`).
    #
    # Tek-atış `fusion agent` bunu destekliyordu ama interaktif oturum
    # desteklemiyordu: iki projeye birden dokunan bir görevde model ikinci projeye
    # erişemiyor, `run_shell(ls -la ..)` ile dolaşmaya çalışıp tur bütçesini
    # yakıyordu.
    extra_roots: tuple[Path, ...] = ()
    #: Yalnız host enjekte eder; model/scaffold tarayıcı seçemez.
    remotion_transport: FrameTransport | None = field(default=None, kw_only=True)
    remotion_browser: RemotionBrowser | None = field(default=None, kw_only=True)
    engine: Engine = Engine.AGENT
    approval: ApprovalMode = ApprovalMode.AUTO
    task_type: str = "general"
    #: `/mode auto` açık mı? Açıkken her tur görevi sınıflandırıp kademe seçilir.
    auto_profile: bool = False
    show_all_answers: bool = False
    #: `/thinking` açık mı? Açıkken model düşünmesi (`<think>…`) gizlenmez, Claude Code
    #: gibi sönük bir blok olarak akıtılır. Varsayılan kapalı — sade akış korunur.
    show_thinking: bool = False
    #: `/zil` açık mı? Açıkken tur bitince terminal zili çalar (başka pencerede çalışan
    #: kullanıcıya haber). Varsayılan kapalı — boruda ve CI'da zaten yazılmaz.
    bell: bool = False
    #: Açılış dolgusu hâlâ ekranda mı? İlk mesajda ekran dolgusuz yeniden çizilir.
    welcome_padded: bool = True
    synthesis: bool | None = None
    #: Agent motorunun çok-turlu sohbet geçmişi.
    history: list[Message] = field(default_factory=list)
    #: Son fusion sonucu — geri bildirim komutları buna uygulanır.
    last_fusion: FusionResult | None = None
    #: Oturum boyunca biriken token ve maliyet. Her tur aynı toplayıcıyı besler.
    cost: CostTracker = field(default_factory=CostTracker)
    #: Kalıcı kullanım günlüğü (`/usage` pencereleri; P-056). Ayar kapalıysa None.
    usage_log: UsageLog | None = None
    #: Son agent turunun dosya değişiklikleri — `/undo` bunu geri alır.
    #: Yalnızca SON tur tutulur: daha derin bir geçmiş, kullanıcının aradan yaptığı
    #: elle değişiklikleri sessizce ezme riski taşır.
    last_changes: ChangeSet | None = None
    #: Tur başına kod + konuşma checkpoint'leri (`/rewind`). Her agent turu `begin` ile
    #: açılır; turun `ChangeSet`'i buradan gelir ve `last_changes` ile aynı nesnedir.
    checkpoints: TurnCheckpointLedger = field(default_factory=TurnCheckpointLedger)
    #: Skill/agent kütüphanesi. Tarama oturumda bir kez yapılır.
    capabilities: CapabilityRegistry | None = None
    #: --agents tanımları yalnız bu oturumun katalog bileşimindedir.
    session_agents: tuple[Capability, ...] = field(default=(), kw_only=True)
    #: Aynı asenkron sohbetin turlarından uzun yaşayan, kapanışta beklenen görev sahibi.
    child_runs: ChildRuns = field(
        default_factory=lambda: ChildRuns(persistent=True), kw_only=True, repr=False
    )

    #: Düz metin otomatik bellek (P-036); `runtime.auto_memory` kapalıysa None.
    plain_memory: PlainMemory | None = None
    #: Oturum kişiliği (P-053; `--agent <ad>` / `/persona`): tanımın gövdesi her turun
    #: sistem istemine girer, araç kümesi daralır. None = varsayılan Fusion.
    persona: Persona | None = field(default=None, kw_only=True)
    #: initialPrompt yalnız ana oturumun ilk kullanıcı turunda tüketilir.
    persona_initial_prompt_applied: bool = field(default=False, kw_only=True)
    #: `/persona` kullanımdan kalkma uyarısı bu oturumda basıldı mı (#34).
    persona_command_warned: bool = field(default=False, kw_only=True)
    main_config_applied: bool = field(default=False, kw_only=True)
    _configured_persona: Persona | None = field(default=None, init=False, repr=False)
    _persona_base_config: Config | None = field(default=None, init=False, repr=False)
    _persona_applied_config: Config | None = field(default=None, init=False, repr=False)

    #: Oturum boyunca paylaşılan sağlayıcı sağlığı (circuit breaker + güvenilirlik).
    #: Tur ötesi durum burada yaşar; her agent turu aynı kaydı besler ve okur.
    health: HealthRegistry | None = None
    #: Etkin yapılandırma dosyasının sürümü; turlar arasında kontrol paneli
    #: değişikliklerini yakalamak için kullanılır.
    config_revision: ConfigRevision = field(init=False)
    #: Dosyadan en son yüklenen yapılandırma: oturum değişikliklerinin kıyas tabanı.
    config_baseline: Config = field(init=False)
    #: Bir makronun hazırladığı, çalıştırılmayı bekleyen görev.
    pending_task: str = ""
    #: Bekleyen görevin davranış kipi (hedef, mülakat…).
    pending_mode: Mode = Mode.NONE
    #: Plan kipinde biten turun plan dosyası; kabul kartı gösterilince temizlenir.
    pending_plan: Path | None = None
    #: Sıradaki satır ajanın zamanladığı görevdir: slash ile başlasa da KOMUT değil, tur
    #: olarak çalışır (bkz. `core.session_cron.Source`). Satır işlenince sıfırlanır.
    scheduled_turn_only: bool = False
    #: `/rc` ile bu süreçte açılan uzaktan kontrol sunucusu; kapalıyken `None` (P-039).
    remote_control: RemoteControlHost | None = field(default=None, kw_only=True)
    #: `/voice` dikte metni: bir sonraki istem bununla dolu açılır (P-072); alınınca temizlenir.
    pending_input: str = ""
    #: Arka plan görevleri + oturumlar arası mesaj bağlantısı (P-048/P-060); `agent_link.start`.
    agent_link: AgentLink | None = field(default=None, kw_only=True)
    #: `/tarayici ac` ile açılan, ajanla paylaşılan görünür tarayıcı (P-045); kapalıyken None.
    shared_browser: SharedBrowser | None = field(default=None, kw_only=True)
    #: `/tarayici kapat` sonrası kapanışı süren paylaşımlar; REPL çıkışında beklenir.
    closing_browsers: list[SharedBrowser] = field(default_factory=list, kw_only=True)
    #: `/beceri` ile hazırlanan ve sıradaki turun sistem bağlamına eklenecek beceri gövdesi.
    pending_context: str = ""
    #: `allowed-tools` kısıtı: sıradaki turda sunulacak Fusion araç adları; None = kısıt yok.
    pending_tools: frozenset[str] | None = None
    #: Becerinin `model`/`effort`, `disallowed-tools` ve fork `agent` alanları (P-020).
    pending_model_choice: TurnModelChoice = field(default_factory=TurnModelChoice)
    pending_denied_tools: frozenset[str] = frozenset()
    pending_fork_agent: str = ""
    #: Oturumun bağlı olduğu PR (P-057): son turda açılan/okunan PR; durum satırında görünür.
    linked_pr: PullRequestLink | None = None

    def bind_pull_request(self, link: PullRequestLink | None) -> None:
        """Turun kanıtından gelen PR künyesini bağla; yoksa öncekini koru."""
        if link is not None:
            self.linked_pr = link

    @classmethod
    def from_runtime_config(cls, config: Config, **kwargs: object) -> ReplState:
        """Kayıtlı motor ve izin modunu alarak oturum durumu kur.

        Bozuk ya da tanınmayan kayıt sessizce varsayılana düşer: elle düzenlenmiş
        bir yapılandırma yüzünden uygulamanın açılmaması kabul edilemez.
        """
        try:
            engine = Engine(config.runtime.engine)
        except ValueError:
            engine = Engine.AGENT
        try:
            approval = ApprovalMode(config.runtime.approval_mode)
        except ValueError:
            approval = ApprovalMode.AUTO
        if approval is ApprovalMode.BYPASS:
            approval = ApprovalMode.AUTO
        return cls(config=config, engine=engine, approval=approval, **kwargs)  # type: ignore[arg-type]

    async def reset_child_runs(self) -> None:
        """Sohbet/kök değişiminde önce eski görevleri kapat, sonra yeni sahibi kur."""
        await self.child_runs.close()
        self.child_runs = ChildRuns(persistent=True)
        self.persona_initial_prompt_applied = bool(self.history)

    async def apply_worktree_switch(self, switch: WorktreeSwitch | None) -> str:
        """Kök değişmeden eski görevleri bekle; aynı kökte sürekliliği koru."""
        from .worktrees import apply_switch_request

        if switch is None:
            return ""
        target = switch.requested.path if switch.requested is not None else self.root
        if switch.exit_requested and self.worktree is not None:
            target = self.worktree.origin
        if target != self.root:
            await self.reset_child_runs()
        return apply_switch_request(self, switch)

    def select_persona(self, persona: Persona | None) -> None:
        """Ayarları seçim anında uygula; ardından kullanıcı tercihi ilk turda da korunur."""
        previous = self.persona
        self.persona = persona
        try:
            self.prepare_persona_config()
        except ConfigError:
            self.persona = previous
            raise
        from . import session_agent

        session_agent.save(
            self.config.memory_dir, self.conversation_id, persona.name if persona else ""
        )

    def prepare_persona_config(self) -> None:
        """Kişilik ayarlarını seçimde uygula; sonraki model/efor/MCP tercihini koru."""
        if self.persona is self._configured_persona:
            return
        from ...engines.agent.team_settings import main_agent_config, main_approval_mode

        base = self.config
        if self._persona_base_config is not None and self._persona_applied_config is not None:
            base = rebase_session_changes(
                self._persona_applied_config, base, self._persona_base_config
            )
        updated = (
            main_agent_config(base, self.persona, root=self.root, home=self.home)
            if self.persona is not None
            else base
        )
        if self.persona is not None:
            self.approval = main_approval_mode(updated, self.persona, self.approval)
        self._persona_base_config, self._persona_applied_config = base, updated
        self.config = updated
        self._configured_persona = self.persona
        self.main_config_applied = self.persona is not None

    def take_persona_initial(self, task: str) -> str:
        """Devam/resume turunda başlangıç görevini yeniden ekleme."""
        from .persona_commands import initial_persona_task

        if self.persona_initial_prompt_applied or self.persona is None:
            return task
        self.persona_initial_prompt_applied = True
        return task if self.history else initial_persona_task(self.persona, task)

    def take_pending(self) -> tuple[str, Mode]:
        """Bekleyen görevi al ve temizle."""
        task, mode = self.pending_task, self.pending_mode
        self.pending_task, self.pending_mode = "", Mode.NONE
        return task, mode

    def take_pending_input(self) -> str:
        """`/voice` ön dolgusunu bir kez al ve temizle."""
        text, self.pending_input = self.pending_input, ""
        return text

    def take_scheduled_turn_only(self) -> bool:
        """Zamanlanmış satır 'yalnız tur' işaretini bir kez al ve temizle."""
        value, self.scheduled_turn_only = self.scheduled_turn_only, False
        return value

    def refresh_capability_roots(self) -> None:
        """`/add-dir` sonrası beceri kataloğunu ek köklerle yeniden kur (P-052)."""
        if self.capabilities is not None:
            self.capabilities = self.capabilities.with_extra_roots(self.extra_roots)

    def take_pending_extras(self) -> PendingExtras:
        """Beceri bağlamı ve araç kısıtını BİR KEZ al; sonraki turlara sızmasın."""
        extras = PendingExtras(
            self.pending_context,
            self.pending_tools,
            self.pending_model_choice,
            self.pending_denied_tools,
            self.pending_fork_agent,
        )
        self.pending_context, self.pending_tools = "", None
        self.pending_model_choice = TurnModelChoice()
        self.pending_denied_tools, self.pending_fork_agent = frozenset(), ""
        return extras

    #: `.claude/settings.local.json` içindeki onaysız komutlar.
    allowed_commands: frozenset[str] = frozenset()
    #: "Oturum boyunca" verilen onay izinleri. Politika her tur yeniden kurulur;
    #: izinler turla birlikte kaybolmasın diye sohbet durumunda yaşar.
    approval_memory: ApprovalMemory = field(default_factory=ApprovalMemory)
    #: Kurulmuş ama henüz gösterilmemiş hatırlatmalar.
    reminders: list[Reminder] = field(default_factory=list)
    #: Oturum zamanlayıcısı: `/loop` ve `cron_*` araçlarının görevleri (P-038).
    cron: SessionCron = field(default_factory=SessionCron)
    #: `/goal <koşul>` ile kurulan turlar arası hedef (P-058); yoksa None.
    goal: SessionGoal | None = None
    #: Devralınan oturumun künyesi. Bir sonraki turda sistem bağlamına eklenir.
    pending_digest: str | None = None

    #: `!` kabuk çıktısı ve `@dosya` içerikleri (P-022): bir sonraki turun sistem
    #: bağlamına girer, sonra temizlenir. Devralma künyesiyle aynı yoldan taşınır.
    pending_blocks: list[str] = field(default_factory=list)

    def take_pending_digest(self) -> str:
        """Devralma künyesi + bekleyen bağlam bloklarını bir kez al; sonraki turlardan temizle."""
        parts = [self.pending_digest or "", *self.pending_blocks]
        self.pending_digest = None
        self.pending_blocks = []
        return "\n\n".join(part for part in parts if part)

    def restore_pending_digest(self, digest: str) -> None:
        """İptal/hata ile biten turun tükettiği bağlamı geri koy (L2-24; iki REPL yüzeyi).

        Ölçüldü (31 Ekim): satır-içi REPL'de tur iptal olunca `@dosya` blokları ve `!`
        çıktısı kayboluyordu (yalnız tam ekran geri koyuyordu). Arada yeni künye
        geldiyse eskisi onun ÖNÜNE eklenir; ezilmez.
        """
        if not digest:
            return
        current = self.pending_digest or ""
        self.pending_digest = f"{digest}\n\n{current}" if current else digest

    def __post_init__(self) -> None:
        self._bind_root_services()
        # Onay kartındaki "bir daha sorma" kalıcı kurala dönüşür (P-003); kök çağrı anında
        # okunur, böylece proje değişince yeni projeye yazılır.
        attach_rule_writer(self.approval_memory, lambda: self.root)
        # Denetçi engel eşiğini aşınca (P-011) oturum Manuel kipe düşer; kalıcı ayar değişmez.
        self.approval_memory.auto_review.on_fallback = self._fall_back_to_manual
        self.config_revision = revision(self.config)
        self.config_baseline = self.config

    def _bind_root_services(self) -> None:
        """Köke bağlı yardımcılar (beceri kataloğu, düz bellek, onaysız komutlar); eksikse kur."""
        if self.capabilities is None:
            # `capabilities.disabled` ve `overrides` her oturumda uygulanır (P-051).
            self.capabilities = registry_from_config(
                self.config,
                self.home,
                self.root,
                extra_roots=self.extra_roots,
                session_agents=self.session_agents,
            )
        if self.plain_memory is None:
            self.plain_memory = build_plain_memory(self.config, self.root)
        if not self.allowed_commands:
            self.allowed_commands = load_allowed_commands(self.root)

    def rebind_root(self, root: Path) -> None:
        """Oturum kökünü değiştir ve köke bağlı her şeyi yeni köke kur (`/cd`, P-072).

        Eski projenin ek klasörleri (`/add-dir`) ve "oturum boyunca izin ver" kararları
        yeni köke TAŞINMAZ — masaüstü `_apply_root` ile aynı kural.
        """
        self.root = root
        self.extra_roots = ()
        self.approval_memory.revoke()
        self.capabilities = None
        self.plain_memory = None
        self.allowed_commands = frozenset()
        self._bind_root_services()

    def hooks(self) -> HookSession:
        """Oturumun kanca yürütücüsü (P-009); yaşam döngüsü `engines/hooks/session.py`.

        Kök değişimi (worktree) aynı oturumu sürdürür; sohbet kimliği değişirse (`/resume`,
        `/branch`, masaüstünde başka sohbet) eski oturum kapanır, yenisi `resume` ile açılır.
        Ölçüldü (31 Ekim): kök değişince yeni oturum kuruluyor, SessionStart ikinci kez
        tetikleniyor ve ilk oturumun SessionEnd'i hiç gelmiyordu.
        """
        session = self.hook_session
        source = self.hook_start_source or ("resume" if self.history else "startup")
        self.hook_start_source = ""
        if session is None:
            session = open_hook_session(
                self.root,
                lambda: self.config,
                session_id=self.conversation_id,
                permission_mode=lambda: self.approval.value,
                source=source,
            )
            session.skills_reloader = self._reload_skills
            session.context_chars = lambda: sum(len(m.content or "") for m in self.history)
            self.hook_session = session
        session.root = self.root
        if session.conversation_id != self.conversation_id:
            session.restart(
                source,
                # Claude: etkileşimli /resume ile oturum değişimi `resume` nedenidir.
                reason="resume",
                session_id=self.conversation_id,
                conversation_id=self.conversation_id,
            )
        return session

    def _reload_skills(self) -> None:
        """SessionStart `reloadSkills` (#111): kanca kurduğu beceriler hemen görünsün."""
        if self.capabilities is not None:
            self.capabilities.invalidate()

    def _fall_back_to_manual(self) -> None:
        if self.approval is ApprovalMode.AUTO:
            self.approval = ApprovalMode.SECURITY

    def permission_rules(self) -> PermissionRuleSet:
        """İzin kuralları her turda dosyadan taze okunur (P-001).

        `/permissions add` ve onay kartındaki "bir daha sorma" sonraki turda etkili olur;
        dosyalar küçük, okuma ucuzdur.
        """
        return load_permission_rules(
            self.root,
            block_reads_outside_root=self.config.runtime.block_reads_outside_root,
            block_writes_outside_root=self.config.runtime.block_writes_outside_root,
        )

    def refresh_config(self) -> bool:
        """Bir sonraki turdan önce kontrol paneli yapılandırma değişikliklerini uygula.

        Etkin turlar başladıkları anlık görüntüyle devam eder; bu metot yalnızca
        giriş/HTTP istek sınırlarında çağrılır.
        """
        outcome = reload_checked(self.config, self.config_revision)
        loaded, rev, reloaded = outcome.config, outcome.revision, outcome.reloaded
        self.config_revision = rev
        # Okunamayan dosya SESSİZ kalmaz: kullanıcı değişikliğinin uygulanmadığını
        # `take_config_error()` ile görür (L2-20).
        self.config_error = outcome.error
        if not reloaded:
            return False
        updated = rebase_session_changes(self.config_baseline, self.config, loaded)
        # Oturumun kendi yazması da dosya sürümünü değiştirir; içerik aynıysa "ayarlar
        # yüklendi" demek ve efor gibi oturum seçimlerini sıfırlamak yanlıştır.
        changed = updated != self.config
        self.config_baseline = loaded
        self.config = updated
        if changed:
            self.plain_memory = build_plain_memory(self.config, self.root)
        return changed

    #: Son yeniden yüklemede dosya değişti ama okunamadıysa nedeni (bir kez gösterilir).
    config_error: str = ""

    def take_config_error(self) -> str:
        """Bekleyen yapılandırma okuma hatasını döndür ve temizle (tekrar gösterilmesin)."""
        error, self.config_error = self.config_error, ""
        return error

    running: bool = True

    def cycle_approval(self) -> ApprovalMode:
        """Onay modunu sırayla döndür (shift-tab davranışı)."""
        self.approval = next_mode(self.approval)
        return self.approval

    def reset_history(self) -> int:
        """Agent sohbet geçmişini temizle; silinen mesaj sayısını döndür."""
        from . import linked_pr

        removed = len(self.history)
        self.history = []
        if self.hook_session is not None:
            # Claude `/clear` gibi: SessionEnd(clear) + yeni kimlikle SessionStart(source: clear).
            self.hook_session.restart("clear", reason="clear")
        # Temizlenen sohbetin PR künyesi de gider (Claude Code `/clear` ile aynı).
        linked_pr.forget(self)
        return removed
