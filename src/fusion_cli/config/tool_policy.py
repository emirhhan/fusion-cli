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
from typing import TYPE_CHECKING

from ..core.model_capability import ModelCapability, ToolSupport

if TYPE_CHECKING:  # pragma: no cover - yalnızca tip denetimi
    from .models import Config


@dataclass(frozen=True, slots=True)
class MutationPolicy:
    """Bir modelin mutation agent olup olamayacağı ve (olamıyorsa) gerekçe."""

    ok: bool
    reason: str = ""


def can_be_mutation_agent(
    capability: ModelCapability, *, emulated_verified: bool = False
) -> MutationPolicy:
    """Bu yetenekteki model dosya değiştiren ana agent olabilir mi?

    `emulated_verified`, taklit araç modelinin eval eşiğini GEÇTİĞİNİ söyler (bkz.
    `tools.emulation_eval`). Doğrulama config katmanında yapılamaz (jsonschema
    üçüncü partidir, `core`/`config` onu import etmez); bu yüzden sonuç bir bayrak
    olarak dışarıdan geçirilir — config saf kalır.
    """
    if capability.tool_support is ToolSupport.NONE:
        return MutationPolicy(
            False, "araç desteği yok: yalnızca sohbet/council rollerinde kullanılabilir"
        )
    if capability.tool_support is ToolSupport.EMULATED and not emulated_verified:
        return MutationPolicy(
            False, "taklit araç desteği henüz eval eşiğinden geçmedi: mutation'a giremez"
        )
    return MutationPolicy(True)


def mutation_policy_for_model(config: Config, model: str) -> MutationPolicy:
    """Bu model kimliği dosya değiştiren agent olabilir mi?

    Yetenek iki kaynaktan gelir ve WEB OTURUMU ÖNCELİKLİDİR: `ModelSpec` etiketleri
    kullanıcının yazdığı serbest metindir, web oturumunun `tool_support` alanı ise
    Fusion'ın kendi kaydıdır. Etikete bakmak, panelden bağlanmış bir ChatGPT/Claude
    oturumunu `UNKNOWN` sayıp doğrulanmamış taklit araçla dosya yazmasına izin
    veriyordu — belge "hayır" derken kod "evet" yapıyordu.
    """
    session = next(
        (item for item in config.web_sessions if item.model == model and item.enabled),
        None,
    )
    if session is None:
        return MutationPolicy(True)
    support = _WEB_TOOL_SUPPORT.get(session.tool_support, ToolSupport.NONE)
    return can_be_mutation_agent(
        ModelCapability(tool_support=support),
        emulated_verified=session.tool_eval_passed,
    )


#: Web oturumu `tool_support` metninin yetenek karşılığı.
_WEB_TOOL_SUPPORT = {"none": ToolSupport.NONE, "emulated": ToolSupport.EMULATED}
