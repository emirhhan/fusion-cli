"""Model yeteneği — bir modelin ne yapabildiğine dair NORMALİZE edilmiş bilgi.

Bu tipler saftır ve üçüncü partiye bağımlı değildir (`core` sözleşmesi). Değerler
UYDURULMAZ: yalnızca elde gerçekten var olan sinyallerden türetilir (model
etiketleri, canlı katalogdan gelen bağlam penceresi). Bilinmeyen bir yetenek
`UNKNOWN`/0/`False` ile temsil edilir — "bilmiyoruz" ayrı bir durumdur ve
uygunluk kararında asla "kesinlikle var" gibi davranılmaz.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ToolSupport(Enum):
    """Bir modelin araç (function/tool) çağırma yeteneği.

    Ayrım davranışsaldır (master prompt §5.3): yalnızca `NATIVE` ve doğrulanmış
    `EMULATED` modeller dosya değiştiren/shell çalıştıran ana agent olabilir;
    `NONE` olan model mutation görevine giremez. `UNKNOWN`, "sağlayıcı söylemedi"
    demektir — gizlenmez ama doğrulanmış da sayılmaz.
    """

    #: Sağlayıcının gerçek function/tool-calling API'si. Fusion bu modeli agent
    #: turunda araçlarla çalıştırır.
    NATIVE = "native"
    #: Araç tanımları prompt'a kontrollü biçimde eklenir; yapılandırılmış çıktı
    #: ayrıştırılır. Eval eşiğini geçmeden mutation görevine giremez.
    EMULATED = "emulated"
    #: Araç desteği yok. Yalnızca sohbet/council/özet rollerinde kullanılabilir.
    NONE = "none"
    #: Doğrulanmamış. Ne var ne yok bilinmiyor; karar ihtiyatlı verilir.
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class CapabilityEvidence:
    """Provenance for a provider capability declaration."""
    capability: str
    source: str
    measured_at: str | None = None
    model_revision: str | None = None
    adapter_revision: str | None = None
    account_scope: str | None = None


@dataclass(frozen=True, slots=True)
class ModelCapability:
    """Bir modelin uygunluk kararı için gereken normalize yeteneği.

    Alanlar bilinçle azdır: her biri gerçek bir sinyalden türetilebilir ve gerçek
    bir filtreleme kararını besler. Maliyet/gecikme/güvenilirlik burada YOKTUR —
    onlar telemetriden gelir ve router katmanının işidir.
    """

    #: Araç çağırma yeteneği.
    tool_support: ToolSupport = ToolSupport.UNKNOWN
    #: Bağlam penceresi (token). 0 = bilinmiyor.
    context_window: int = 0
    #: Model reasoning/thinking yeteneğini beyan ediyor mu?
    reasoning: bool = False
    #: Görüntü girdisi kabul ediyor mu? Yalnız CANLI ölçümle doğrulanmış `vision`
    #: etiketinden türetilir (bkz. `config/eligibility.py::capability_from_spec`);
    #: etiket yoksa ihtiyatlı `False` kalır — "muhtemelen görür" varsayılmaz.
    vision: bool = False

    # Unknown (unverified) differs from verified-unsupported (empty list).
    supported_reasoning_efforts: tuple[str, ...] = ()
    reasoning_efforts_verified: bool = False
    evidence: tuple[CapabilityEvidence, ...] = ()
