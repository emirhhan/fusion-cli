"""Bir görevin tek çalıştırmasından toplanan ham gözlemler.

Bu nesne yürütücü (executor) tarafından üretilir; başarı ölçütü ve metrikler
bunun üzerinden hesaplanır. Ağ/motor bağımlılığı yoktur, saf veridir — bu sayede
metrik ve karşılaştırma mantığı sahte gözlemle ağ olmadan test edilebilir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from evals.interactions import InteractionMetrics
from fusion_cli.core.events import Event
from fusion_cli.core.evidence import EvidenceEnvironment

if TYPE_CHECKING:
    from evals.research_runtime import RuntimeReceipt


@dataclass(frozen=True, slots=True)
class ModelCallIdentity:
    """İstenen kimliği gözlenenden ayır; ölçülmeyen kullanım None kalır."""

    call_id: str
    role: str
    requested_model: str | None
    served_model: str | None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    outcome: str = "unknown"
    cost_usd: float | None = None


@dataclass(frozen=True, slots=True)
class TaskExecution:
    """Tek bir görev çalıştırmasının ölçülebilir sonucu."""

    task_id: str
    #: Çalıştırılan komutun çıkış kodu; komut yoksa None.
    exit_code: int | None = None
    #: Çalıştırma sırasında değişen dosya yolları.
    changed_files: frozenset[str] = field(default_factory=frozenset)
    #: Modelin/araçların ürettiği birleşik çıktı metni.
    output_text: str = ""
    #: Bu görev için yapılan toplam model çağrısı sayısı.
    model_calls: int = 0
    #: İlk denemeden sonra yapılan yeniden deneme sayısı (0 = ilk denemede bitti).
    retries: int = 0
    #: Sağlayıcı kota/hız sınırı yüzünden mi başarısız oldu?
    #:
    #: Kota hatası görev başarısızlığı DEĞİLDİR: agent'ın yeteneği hiç ölçülmemiştir.
    #: Ayırt edilmediğinde ölçüm sessizce bozulur — nitekim bozuldu ve düşüş bir
    #: kod değişikliğine bağlandı.
    rate_limited: bool = False
    #: Kota hatasının HAM metni. Günlük kota mı geçici sınır mı ayrımı buradan
    #: yapılır; sağlayıcılar bunu farklı söyler ve tepkiler zıttır.
    rate_limit_detail: str = ""
    #: Agent turu BİTTİĞİNİ beyan etti mi? (bkz. `AgentRunObservation.claimed_success`)
    claimed_success: bool = True
    #: Görevin baştan sona sürdüğü süre (saniye).
    duration_seconds: float = 0.0
    calls: tuple[ModelCallIdentity, ...] = ()
    trace_events: tuple[Event, ...] = ()
    runtime_receipt: RuntimeReceipt | None = None
    environments: tuple[EvidenceEnvironment, ...] = ()
    effective_config_digest: str | None = None
    sample_index: int | None = None
    interactions: InteractionMetrics | None = None
