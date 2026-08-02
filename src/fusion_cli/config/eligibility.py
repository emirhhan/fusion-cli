"""Model uygunluğu — bir modelin hangi profillerde önerildiğini hesaplar.

Yetenek UYDURULMAZ, var olan sinyallerden TÜRETİLİR:

- `agent` etiketi → `NATIVE`. Fusion bu modelleri bugün agent turunda gerçek
  (LiteLLM) araç çağrılarıyla çalıştırıyor; yani araç desteği pratikte doğrulanmış.
- `agent` etiketi olmayan model → `UNKNOWN`. Yalnızca council adayı olarak
  kullanılıyor, araç yolu hiç sınanmadı; "yok" değil "bilinmiyor".
- `reasoning` etiketi → reasoning beyanı.
- Bağlam penceresi dışarıdan (canlı katalog) gelir; etiketten türetilmez.

Uygunluk kararı yalnızca BİLİNEN-kötü modeli eler (araçsız model mutation profiline
giremez, bağlamı bilinen ve eşiğin altındaki model elenir). Bilinmeyen yetenek
gizlenmez — çağıran taraf "uyumsuzları göster" ile yine de seçebilir.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core.model_capability import ModelCapability, ToolSupport
from ..core.reasoning import ReasoningEffort, provider_value
from ..core.types import ModelSpec
from .models import ProfileEligibility

#: `NATIVE` araç desteğini beyan eden etiket. Bu etiketli modeller agent turunda
#: araçlarla çalıştırılıyor; başka bir etiket araç desteğini DOĞRULAMAZ.
_NATIVE_TOOL_TAG = "agent"
#: Araç desteği OLMADIĞINI açıkça beyan eden etiket (opak/web/arena modelleri).
#: `NONE`, mutation agent olmayı yapısal olarak engeller (bkz. `tool_policy`).
_NO_TOOL_TAG = "no-tools"
#: Araç çağrısının taklit (emulated) edildiğini beyan eden etiket. Eval eşiğinden
#: geçmeden mutation görevine giremez.
_EMULATED_TOOL_TAG = "emulated-tools"
#: Reasoning beyan eden etiket.
_REASONING_TAG = "reasoning"


def _tool_support_of(spec: ModelSpec) -> ToolSupport:
    """Model etiketlerinden araç desteğini türet. Açık beyan örtük çıkarımı ezer:
    `no-tools`/`emulated-tools` yazılmışsa o kazanır, yoksa `agent` → native, o da
    yoksa doğrulanmamış (`UNKNOWN`)."""
    if _NO_TOOL_TAG in spec.tags:
        return ToolSupport.NONE
    if _EMULATED_TOOL_TAG in spec.tags:
        return ToolSupport.EMULATED
    if _NATIVE_TOOL_TAG in spec.tags:
        return ToolSupport.NATIVE
    return ToolSupport.UNKNOWN


def capability_from_spec(spec: ModelSpec, context_window: int = 0) -> ModelCapability:
    """Model etiketlerinden ve (varsa) bağlam penceresinden yeteneği türet."""
    return ModelCapability(
        tool_support=_tool_support_of(spec),
        context_window=context_window,
        reasoning=_REASONING_TAG in spec.tags,
    )


def effort_for_spec(spec: ModelSpec, effort: ReasoningEffort) -> str | None:
    """Seçilen modele gönderilecek `reasoning_effort` değerini belirle.

    Model reasoning DESTEKLEMİYORSA `None`: parametre gönderilmez, hatalı istek
    kurulmaz (master prompt §7.1). Destekliyorsa effort sağlayıcının kabul ettiği
    değere eşlenir (`auto`→None, `xhigh`/`max`→`high`). Hem agent hem fusion yolu
    bu tek fonksiyondan geçer; ikinci bir eşleme kopyası açılmaz."""
    if not capability_from_spec(spec).reasoning:
        return None
    return provider_value(effort)


@dataclass(frozen=True, slots=True)
class EligibilityResult:
    """Bir modelin bir profile uygunluğu ve (uygun değilse) Türkçe gerekçe."""

    ok: bool
    reason: str = ""


def is_eligible(capability: ModelCapability, requirement: ProfileEligibility) -> EligibilityResult:
    """Yetenek, profil eşiklerini karşılıyor mu?

    Yalnızca bilinen-kötüyü eler: araçsız (`NONE`) model mutation profiline giremez;
    bağlamı BİLİNEN (>0) ve eşiğin altındaki model elenir. Bilinmeyen bağlam (0)
    ya da bilinmeyen araç desteği (`UNKNOWN`) elenmez.
    """
    if not requirement.allow_no_tools and capability.tool_support is ToolSupport.NONE:
        return EligibilityResult(False, "araç desteği yok (mutation profiline giremez)")
    known_context = capability.context_window > 0
    below_min = known_context and capability.context_window < requirement.min_context
    if requirement.min_context > 0 and below_min:
        return EligibilityResult(
            False,
            f"bağlam penceresi {capability.context_window} < gereken {requirement.min_context}",
        )
    return EligibilityResult(True)


def eligible_profiles(
    capability: ModelCapability,
    eligibility: dict[str, ProfileEligibility],
) -> tuple[str, ...]:
    """Yeteneğin uygun olduğu profil adları (eşik sözlüğündeki sırayı korur)."""
    return tuple(
        profile
        for profile, requirement in eligibility.items()
        if is_eligible(capability, requirement).ok
    )
