"""REPL oturum durumu.

Tek bir yerde tutulur ve komut işleyicilerine geçirilir; modüller arası global
değişken yoktur. Oturum boyunca değişen her şey buradadır.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields, replace
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from ...config.live import ConfigRevision, reload_checked, revision
from ...config.models import Config
from ...config.permission_rules import PermissionRuleSet, load_permission_rules
from ...config.permissions import load_allowed_commands
from ...core.changeset import ChangeSet
from ...core.health import HealthRegistry
from ...core.remotion_browser import RemotionBrowser
from ...core.session_cron import SessionCron
from ...core.turn_checkpoints import TurnCheckpointLedger
from ...core.types import FusionResult, Message
from ...core.worktree import Worktree
from ...engines.agent.approval import ApprovalMemory, ApprovalMode, next_mode
from ...engines.agent.remotion_bridge import FrameTransport
from ...engines.agent.team import Persona
from ...engines.hooks.session import HookSession, open_hook_session
from ...memory.factory import Memory
from ...memory.plain_memory import PlainMemory, build_plain_memory
from ...observability.cost import CostTracker
from ...observability.usage_log import UsageLog
from ...tools.capabilities import CapabilityRegistry
from ..rule_notices import attach_rule_writer
from .macros import Mode

if TYPE_CHECKING:  # pragma: no cover - yalnızca tip denetimi
    from ...remote.host import RemoteControlHost


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


@dataclass(frozen=True, slots=True)
class PendingExtras:
    """`/beceri` komutunun sıradaki tura taşıdığı ekler (bkz. `ReplState.take_pending_extras`)."""

    context: str = ""
    tools: frozenset[str] | None = None

    def merged_tools(self, base: set[str] | None) -> set[str] | None:
        """Yüzeyin kendi kısıtıyla kesişim; ikisi de yoksa None (kısıt yok)."""
        if self.tools is None:
            return base
        return set(self.tools) if base is None else set(self.tools) & base


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
    #: Düz metin otomatik bellek (P-036); `runtime.auto_memory` kapalıysa None.
    plain_memory: PlainMemory | None = None
    #: Oturum kişiliği (P-053; `--agent <ad>` / `/persona`): tanımın gövdesi her turun
    #: sistem istemine girer, araç kümesi daralır. None = varsayılan Fusion.
    persona: Persona | None = field(default=None, kw_only=True)
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
    #: `/beceri` ile hazırlanan ve sıradaki turun sistem bağlamına eklenecek beceri gövdesi.
    pending_context: str = ""
    #: `allowed-tools` kısıtı: sıradaki turda sunulacak Fusion araç adları; None = kısıt yok.
    pending_tools: frozenset[str] | None = None

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

    def take_pending(self) -> tuple[str, Mode]:
        """Bekleyen görevi al ve temizle."""
        task, mode = self.pending_task, self.pending_mode
        self.pending_task, self.pending_mode = "", Mode.NONE
        return task, mode

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
        extras = PendingExtras(self.pending_context, self.pending_tools)
        self.pending_context, self.pending_tools = "", None
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
        if self.capabilities is None:
            # `capabilities.disabled` kalıcı kapatma listesi her oturumda uygulanır (P-051).
            disabled = frozenset(getattr(self.config.capabilities, "disabled", ()))
            self.capabilities = CapabilityRegistry(
                self.home,
                self.root,
                disabled_skills=disabled,
                disabled_agents=disabled,
                extra_roots=self.extra_roots,
            )
        if self.plain_memory is None:
            self.plain_memory = build_plain_memory(self.config, self.root)
        if not self.allowed_commands:
            self.allowed_commands = load_allowed_commands(self.root)
        # Onay kartındaki "bir daha sorma" kalıcı kurala dönüşür (P-003); kök çağrı anında
        # okunur, böylece proje değişince yeni projeye yazılır.
        attach_rule_writer(self.approval_memory, lambda: self.root)
        self.config_revision = revision(self.config)
        self.config_baseline = self.config

    def hooks(self) -> HookSession:
        """Oturumun kanca yürütücüsü (P-009); kök değişirse (worktree) yeniden kurulur."""
        if self.hook_session is None or self.hook_session.root != self.root:
            self.hook_session = open_hook_session(
                self.root,
                self.config,
                session_id=self.conversation_id,
                permission_mode=lambda: self.approval.value,
            )
        return self.hook_session

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
        removed = len(self.history)
        self.history = []
        return removed
