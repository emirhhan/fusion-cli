"""Eklemeli aday üretimi — tam yeniden yazma YOK.

ACE'nin "context collapse" uyarısı: model istemi baştan yazdırılınca özenle biriken
ayrıntı sessizce silinir. Burada sağlayıcıdan yalnız KISA EK maddeler istenir; aday,
temel metnin birebir korunmuş hâlinin SONUNA bu maddenin eklenmesiyle kurulur. Yani
bir adayın temeli bozması yapı gereği imkânsızdır; sağlayıcı ne dönerse dönsün temel
metin aynen kalır.

Sağlayıcı (gerçek model ya da test sahtesi) `SnippetProvider` protokolünün arkasındadır.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

#: Tek bir ek maddenin üst sınırı (karakter). Temel istem birkaç bin karakterdir;
#: bundan uzun bir "ek" fiilen yeniden yazımdır ve reddedilir.
MAX_ADDITION_CHARS = 600
#: Temelin yüzde kaçından uzun ek reddedilir (kısa istemlerde mutlak sınır yetmez).
MAX_ADDITION_RATIO = 0.25
#: Modele gösterilecek başarısız görev sayısı ve görev metninin uzunluğu.
MAX_FAILURE_NOTES = 8
FAILURE_REQUEST_CHARS = 240
_FENCE = re.compile(r"^```[A-Za-z]*\n|\n```\s*$")


@dataclass(frozen=True, slots=True)
class FailureNote:
    """Temel istemin başarısız olduğu bir görev (ipucu olarak sağlayıcıya gider)."""

    task_id: str
    request: str


class SnippetProvider(Protocol):
    """Başarısız görevlere bakıp temel isteme eklenecek kısa maddeler öneren taraf."""

    async def propose(
        self, base_text: str, failures: Sequence[FailureNote], count: int
    ) -> tuple[str, ...]: ...


class AdditiveGenerator:
    """`VariantGenerator` uygulaması: sağlayıcının eklerini temelin sonuna iliştirir."""

    def __init__(
        self,
        provider: SnippetProvider,
        *,
        failures: Sequence[FailureNote] = (),
        max_chars: int = MAX_ADDITION_CHARS,
        max_ratio: float = MAX_ADDITION_RATIO,
    ) -> None:
        self._provider = provider
        self._failures = tuple(failures)[:MAX_FAILURE_NOTES]
        self._max_chars = max_chars
        self._max_ratio = max_ratio

    async def generate(self, base_text: str, count: int) -> tuple[str, ...]:
        raw = await self._provider.propose(base_text, self._failures, count)
        limit = min(self._max_chars, int(len(base_text) * self._max_ratio))
        variants: list[str] = []
        for snippet in raw:
            clean = _clean(snippet)
            if not clean or len(clean) > limit or clean in base_text:
                continue
            variant = append_snippet(base_text, clean)
            if variant not in variants:
                variants.append(variant)
        return tuple(variants[:count])


def append_snippet(base_text: str, snippet: str) -> str:
    """Temeli BİREBİR koruyup sonuna ek maddeyi ekle; sonuç daima `base_text` ile başlar."""

    ayirac = "\n" if base_text.endswith("\n") else "\n\n"
    return f"{base_text}{ayirac}{snippet}\n"


def addition_of(base_text: str, variant: str) -> str:
    """Adayın temele eklediği kısım (öneri kaydında gösterilir)."""

    return variant[len(base_text) :].strip() if variant.startswith(base_text) else ""


def _clean(snippet: str) -> str:
    return _FENCE.sub("", snippet.strip()).strip()
