"""REPL oturum durumu.

Tek bir yerde tutulur ve komut işleyicilerine geçirilir; modüller arası global
değişken yoktur. Oturum boyunca değişen her şey buradadır.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from ...config.live import ConfigRevision, reload_if_changed, revision
from ...config.models import Config
from ...config.permissions import load_allowed_commands
from ...core.changeset import ChangeSet
from ...core.health import HealthRegistry
from ...core.types import FusionResult, Message
from ...engines.agent.approval import ApprovalMode
from ...memory.factory import Memory
from ...observability.cost import CostTracker
from ...tools.capabilities import CapabilityRegistry
from .macros import Mode


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


@dataclass(slots=True)
class ReplState:
    """Oturumun tüm değişken durumu."""

    config: Config
    memory: Memory
    root: Path
    engine: Engine = Engine.AGENT
    approval: ApprovalMode = ApprovalMode.AUTO
    task_type: str = "general"
    #: `/mode auto` açık mı? Açıkken her tur görevi sınıflandırıp kademe seçilir.
    auto_profile: bool = False
    show_all_answers: bool = False
    #: Açılış dolgusu hâlâ ekranda mı? İlk mesajda ekran dolgusuz yeniden çizilir.
    welcome_padded: bool = True
    synthesis: bool | None = None
    #: Agent motorunun çok-turlu sohbet geçmişi.
    history: list[Message] = field(default_factory=list)
    #: Son fusion sonucu — geri bildirim komutları buna uygulanır.
    last_fusion: FusionResult | None = None
    #: Oturum boyunca biriken token ve maliyet. Her tur aynı toplayıcıyı besler.
    cost: CostTracker = field(default_factory=CostTracker)
    #: Son agent turunun dosya değişiklikleri — `/undo` bunu geri alır.
    #: Yalnızca SON tur tutulur: daha derin bir geçmiş, kullanıcının aradan yaptığı
    #: elle değişiklikleri sessizce ezme riski taşır.
    last_changes: ChangeSet | None = None
    #: Skill/agent kütüphanesi. Tarama oturumda bir kez yapılır.
    capabilities: CapabilityRegistry | None = None
    #: Oturum boyunca paylaşılan sağlayıcı sağlığı (circuit breaker + güvenilirlik).
    #: Tur ötesi durum burada yaşar; her agent turu aynı kaydı besler ve okur.
    health: HealthRegistry | None = None
    #: Etkin yapılandırma dosyasının sürümü; turlar arasında kontrol paneli
    #: değişikliklerini yakalamak için kullanılır.
    config_revision: ConfigRevision = field(init=False)
    #: Bir makronun hazırladığı, çalıştırılmayı bekleyen görev.
    pending_task: str = ""
    #: Bekleyen görevin davranış kipi (hedef, mülakat…).
    pending_mode: Mode = Mode.NONE

    def take_pending(self) -> tuple[str, Mode]:
        """Bekleyen görevi al ve temizle."""
        task, mode = self.pending_task, self.pending_mode
        self.pending_task, self.pending_mode = "", Mode.NONE
        return task, mode

    #: `.claude/settings.local.json` içindeki onaysız komutlar.
    allowed_commands: frozenset[str] = frozenset()
    #: Kurulmuş ama henüz gösterilmemiş hatırlatmalar.
    reminders: list[Reminder] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.capabilities is None:
            self.capabilities = CapabilityRegistry(Path.home(), self.root)
        if not self.allowed_commands:
            self.allowed_commands = load_allowed_commands(self.root)
        self.config_revision = revision(self.config)

    def refresh_config(self) -> bool:
        """Bir sonraki turdan önce kontrol paneli yapılandırma değişikliklerini uygula.

        Etkin turlar başladıkları anlık görüntüyle devam eder; bu metot yalnızca
        giriş/HTTP istek sınırlarında çağrılır.
        """
        updated, rev, changed = reload_if_changed(self.config, self.config_revision)
        self.config = updated
        self.config_revision = rev
        return changed

    running: bool = True

    def cycle_approval(self) -> ApprovalMode:
        """Onay modunu sırayla döndür (shift-tab davranışı)."""
        modes = tuple(ApprovalMode)
        self.approval = modes[(modes.index(self.approval) + 1) % len(modes)]
        return self.approval

    def reset_history(self) -> int:
        """Agent sohbet geçmişini temizle; silinen mesaj sayısını döndür."""
        removed = len(self.history)
        self.history = []
        return removed
