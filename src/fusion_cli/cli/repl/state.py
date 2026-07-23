"""REPL oturum durumu.

Tek bir yerde tutulur ve komut işleyicilerine geçirilir; modüller arası global
değişken yoktur. Oturum boyunca değişen her şey buradadır.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from ...config.models import Config
from ...core.types import FusionResult, Message
from ...engines.agent.approval import ApprovalMode
from ...memory.factory import Memory
from ...observability.cost import CostTracker


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
    show_all_answers: bool = False
    synthesis: bool | None = None
    #: Agent motorunun çok-turlu sohbet geçmişi.
    history: list[Message] = field(default_factory=list)
    #: Son fusion sonucu — geri bildirim komutları buna uygulanır.
    last_fusion: FusionResult | None = None
    #: Oturum boyunca biriken token ve maliyet. Her tur aynı toplayıcıyı besler.
    cost: CostTracker = field(default_factory=CostTracker)
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
