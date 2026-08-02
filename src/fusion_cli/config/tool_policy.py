"""Araç desteği politikası — hangi model dosya değiştiren agent olabilir.

Master prompt §5.3'ün en kritik güvenlik kuralı: araç desteği OLMAYAN (`NONE`)
model, dosya değiştiren/shell çalıştıran/git mutasyonu yapan ana agent OLARAK
seçilemez. Böyle bir model sahte araç çağrısı üretir ya da hiç üretmez; ikisi de
sessizce yanlış davranışa yol açar. Bu tür modeller yalnızca sohbet/council/eleştiri/
özet rollerinde kullanılabilir.

`EMULATED` (taklit araç) modeller ancak eval eşiğini geçerse mutation görebilir.
Fusion'da henüz emulated model ve tool-call eval sistemi YOKTUR; dolayısıyla emulated
şimdilik ihtiyatlı biçimde mutation'dan dışlanır (eval sistemi geldiğinde açılır).
`NATIVE` ve `UNKNOWN` mutation yapabilir: native doğrulanmıştır, unknown ise araçlarla
denenir (LiteLLM desteklemeyen parametreyi zaten düşürür).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core.model_capability import ModelCapability, ToolSupport


@dataclass(frozen=True, slots=True)
class MutationPolicy:
    """Bir modelin mutation agent olup olamayacağı ve (olamıyorsa) gerekçe."""

    ok: bool
    reason: str = ""


def can_be_mutation_agent(capability: ModelCapability) -> MutationPolicy:
    """Bu yetenekteki model dosya değiştiren ana agent olabilir mi?"""
    if capability.tool_support is ToolSupport.NONE:
        return MutationPolicy(
            False, "araç desteği yok: yalnızca sohbet/council rollerinde kullanılabilir"
        )
    if capability.tool_support is ToolSupport.EMULATED:
        return MutationPolicy(
            False, "taklit araç desteği henüz eval eşiğinden geçmedi: mutation'a giremez"
        )
    return MutationPolicy(True)
