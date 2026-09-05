"""Hızlı agent turunu çalışma kanıtıyla profesyonel akışa yükselt."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from ...core.tools import ToolFamily, tool_family


@dataclass(frozen=True, slots=True)
class ExecutionSignals:
    """Bir görevin tek güvenli tura sığmadığını gösteren sayaç ve bayraklar."""

    pending_todos: int = 0
    touched_components: int = 0
    tool_families: int = 0
    has_dependency: bool = False
    needs_repair: bool = False
    needs_verification: bool = False
    budget_pressure: bool = False


@dataclass(frozen=True, slots=True)
class PromotionDecision:
    """Workflow'a geçiş kararı ve gözlenebilir gerekçeleri."""

    should_promote: bool
    reasons: tuple[str, ...] = ()


def should_promote(signals: ExecutionSignals) -> PromotionDecision:
    """Hızlı yolun büyüyen işi workflow'a bırakması gerekip gerekmediğini seç."""
    reasons: list[str] = []
    if signals.pending_todos >= 3:
        reasons.append("üç veya daha fazla bekleyen iş")
    if signals.touched_components >= 2:
        reasons.append("birden fazla bileşen")
    if signals.tool_families >= 2:
        reasons.append("birden fazla araç ailesi")
    if signals.has_dependency:
        reasons.append("araç çıktısına bağlı sonraki iş")
    if signals.needs_repair:
        reasons.append("teşhis ve onarım gerektiren hata")
    if signals.needs_verification:
        reasons.append("ayrı doğrulama gereksinimi")
    if signals.budget_pressure:
        reasons.append("hızlı yol bütçesi yetersiz")
    return PromotionDecision(should_promote=bool(reasons), reasons=tuple(reasons))


#: Bir plan isteminde en fazla kaç kanıt satırı taşınır.
#:
#: Yükseltme bağlamı ham geçmişin yerine geçer; sınırsız bırakılırsa yirmi dosyalık
#: bir turun tamamı isteme kopyalanır ve tam olarak kaçındığımız şeye dönüşür.
MAX_EVIDENCE_ITEMS = 12

#: Ayrı kanıtla doğrulanması gereken etkiler. Kabuk komutu ve VCS işlemi dış dünyada
#: gerçekleşir; modelin "çalıştı" demesi sonucun kanıtı değildir.
_PROOF_FAMILIES = frozenset({ToolFamily.SHELL, ToolFamily.VCS})


@dataclass(frozen=True, slots=True)
class ToolUse:
    """Turda denenen tek araç çağrısı."""

    name: str
    ok: bool = True
    mutating: bool = False
    arguments: Mapping[str, object] = field(default_factory=dict)
    output: str = ""


@dataclass(frozen=True, slots=True)
class TurnObservation:
    """Hızlı turun bıraktığı ham kanıt.

    Saf veridir: motor nesnesi taşımaz, bu yüzden karar mantığı motoru ayağa
    kaldırmadan test edilebilir.
    """

    #: Denenen araç çağrıları, ÇALIŞMA SIRASIYLA. Sıra bağımlılık kanıtını üretir.
    tool_uses: tuple[ToolUse, ...] = ()
    pending_todos: int = 0
    touched_paths: tuple[str, ...] = ()
    hit_step_limit: bool = False
    budget_stopped: bool = False
    #: Çağıranın zaten bildiği, araç kanıtından çıkarılamayan doğrulama zorunluluğu.
    verification_required: bool = False


@dataclass(frozen=True, slots=True)
class PromotionContext:
    """Yükseltilen görevin plan üretimine taşınan tipli başlangıç bağlamı.

    Mesaj geçmişi KOPYALANMAZ (tasarım: "Bağlam aktarımı"). Plan üreten alt tur
    yalnız görev özetini, yükseltme gerekçesini ve gözlenmiş kanıtı görür.
    """

    task_summary: str
    reasons: tuple[str, ...] = ()
    touched_paths: tuple[str, ...] = ()
    pending_todos: tuple[str, ...] = ()
    tool_evidence: tuple[str, ...] = ()

    def render(self) -> str:
        """Plan istemine eklenecek okunabilir kanıt bloğunu üret."""
        return "\n".join(
            (
                "YÜKSELTME BAĞLAMI",
                "Bu görev hızlı yolda başladı ve çalışma sırasında büyüdüğü için planlı",
                "yürütmeye alındı. Aşağıdaki iş ZATEN yapıldı; tekrar etme, kalanı planla.",
                f"- Görev: {self.task_summary}",
                f"- Yükseltme gerekçesi: {_satir(self.reasons)}",
                f"- Dokunulan dosyalar: {_satir(self.touched_paths)}",
                f"- Bekleyen işler: {_satir(self.pending_todos)}",
                f"- Araç kanıtı: {_satir(self.tool_evidence)}",
            )
        )


def _satir(items: tuple[str, ...]) -> str:
    """Kanıt listesini sınırlı, tek satırlık okunabilir metne çevir."""
    if not items:
        return "Yok"
    kirpik = items[:MAX_EVIDENCE_ITEMS]
    metin = "; ".join(kirpik)
    if len(items) > len(kirpik):
        metin = f"{metin}; (+{len(items) - len(kirpik)} kayıt daha)"
    return metin


def signals_from_turn(observation: TurnObservation) -> ExecutionSignals:
    """Tur kanıtını yükseltme sinyallerine çevir."""
    families = {
        tool_family(use.name)
        for use in observation.tool_uses
        if tool_family(use.name) is not ToolFamily.META
    }
    return ExecutionSignals(
        pending_todos=observation.pending_todos,
        touched_components=len(set(observation.touched_paths)),
        tool_families=len(families),
        has_dependency=_has_dependency(observation.tool_uses),
        needs_repair=any(not use.ok for use in observation.tool_uses),
        needs_verification=(
            observation.verification_required or _needs_proof(observation.tool_uses)
        ),
        budget_pressure=observation.hit_step_limit or observation.budget_stopped,
    )


def _has_dependency(uses: tuple[ToolUse, ...]) -> bool:
    """Bir araç ÇIKTISINA dayanan sonraki eylem var mı?

    Kanıt sıradan okunur: değiştirici bir çağrı, BAŞARILI bir gözlem çağrısından
    sonra geldiyse o gözlemin çıktısına dayanıyordur. Düşen bir okuma çıktı
    üretmediği için zincir kurmaz.
    """
    observed = False
    for use in uses:
        if use.mutating and observed:
            return True
        if use.ok and not use.mutating:
            observed = True
    return False


def _needs_proof(uses: tuple[ToolUse, ...]) -> bool:
    """Sonucu ayrı kanıt isteyen bir dış etki çalıştırıldı mı?"""
    return any(use.mutating and tool_family(use.name) in _PROOF_FAMILIES for use in uses)
