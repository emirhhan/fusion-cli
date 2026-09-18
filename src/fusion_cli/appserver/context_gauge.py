"""Kalan bağlam göstergesi — kullanıcı sıkıştırmanın yaklaştığını görsün.

Neden var — ölçüldü (17 Eylül denetimi): uzun bir turda geçmiş 91 mesajdan 13'e
sıkıştırıldı ve kullanıcı bunu ancak modelin daha önce konuşulanı unutmasından
anladı. Arayüzde kalan bağlam görünürse, kullanıcı ya konuyu böler ya da yeni
sohbet açar; sürpriz olmaz.

Saftır: yalnız mesajlara ve eşiğe bakar.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..core.types import Message
from ..engines.agent.history import COMPRESS_THRESHOLD_CHARS, WEB_COMPRESS_THRESHOLD_CHARS

__all__ = ["baglam_olcusu"]


def baglam_olcusu(messages: Sequence[Message], *, web: bool) -> dict[str, int]:
    """Kullanılan karakter, sıkıştırma eşiği ve doluluk yüzdesi.

    Eşik sağlayıcıya göre değişir: web oturumunda mesaj kutusu dar olduğu için
    geçmiş çok daha erken özetlenir (bkz. `engines/agent/history`).
    """
    sinir = WEB_COMPRESS_THRESHOLD_CHARS if web else COMPRESS_THRESHOLD_CHARS
    kullanilan = sum(len(message.content) for message in messages)
    yuzde = min(100, round(kullanilan * 100 / sinir)) if sinir else 0
    return {"kullanilan": kullanilan, "sinir": sinir, "yuzde": yuzde}
