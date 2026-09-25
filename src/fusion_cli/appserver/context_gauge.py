"""Kalan bağlam göstergesi — kullanıcı sıkıştırmanın yaklaştığını görsün.

Neden var — ölçüldü (17 Eylül denetimi): uzun bir turda geçmiş 91 mesajdan 13'e
sıkıştırıldı ve kullanıcı bunu ancak modelin daha önce konuşulanı unutmasından
anladı. Arayüzde kalan bağlam görünürse, kullanıcı ya konuyu böler ya da yeni
sohbet açar; sürpriz olmaz.

Saftır: geçmişe ve seçilen zincirin özetleme bütçesine bakar. Yüzde, modelin
tam token penceresi değildir; bu iki kavram tel üstünde ayrı alanlarda kalır.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..core.types import Message
from ..engines.agent.context_budget import ContextBudget
from ..engines.agent.history import COMPRESS_THRESHOLD_CHARS, WEB_COMPRESS_THRESHOLD_CHARS

__all__ = ["baglam_olcusu"]


def baglam_olcusu(
    messages: Sequence[Message],
    *,
    web: bool = False,
    budget: ContextBudget | None = None,
    last_prompt_tokens: int | None = None,
    last_prompt_model: str | None = None,
) -> dict[str, int | str | None]:
    """Geçmişin özetleme eşiğine yaklaşmasını göster; model sınırını ayrı bildir.

    Eşik seçilen bütçeden gelir. Eski çağıranlar için ``web`` yolu korunur.
    """
    sinir = (
        budget.compression_chars
        if budget is not None
        else WEB_COMPRESS_THRESHOLD_CHARS
        if web
        else COMPRESS_THRESHOLD_CHARS
    )
    kullanilan = sum(len(message.content) for message in messages)
    yuzde = min(100, round(kullanilan * 100 / sinir)) if sinir else 0
    return {
        "kullanilan": kullanilan,
        "sinir": sinir,
        "yuzde": yuzde,
        "model": budget.model if budget is not None else None,
        "model_siniri_token": budget.window_tokens if budget is not None else None,
        "son_girdi_token": last_prompt_tokens,
        "son_girdi_model": last_prompt_model,
    }
