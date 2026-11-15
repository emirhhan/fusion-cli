"""`SnippetProvider`ın gerçek model uygulaması.

Tek model çağrısıyla birkaç kısa ek madde ister. Çağrı kullanıcının kendi komutuyla
(`fusion prompt-opt calistir`) yapılır; testler bu sınıfı sahte `LlmProvider` ile sınar.
Sağlayıcı hatası sessizce boş sonuca çevrilmez: "aday çıkmadı" ile "model yanıt vermedi"
farklı şeylerdir ve kullanıcı farkı görmelidir.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from fusion_cli.core.errors import EvalError
from fusion_cli.core.protocols import LlmProvider
from fusion_cli.core.types import CompletionRequest, Message

from .additive import FAILURE_REQUEST_CHARS, MAX_ADDITION_CHARS, FailureNote

_TEMPLATE = Path(__file__).parent / "prompts" / "ek_oner.md"
#: Modelin maddeleri ayırdığı satır.
SEPARATOR = "====="


class ModelSnippetProvider:
    """Başarısız görevlere bakıp modelden ek madde isteyen sağlayıcı."""

    def __init__(
        self, provider: LlmProvider, *, temperature: float, max_tokens: int, timeout_s: float
    ) -> None:
        self._provider = provider
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._timeout_s = timeout_s

    async def propose(
        self, base_text: str, failures: Sequence[FailureNote], count: int
    ) -> tuple[str, ...]:
        request = CompletionRequest(
            messages=(Message("user", build_request(base_text, failures, count)),),
            temperature=self._temperature,
            max_tokens=self._max_tokens,
            timeout_s=self._timeout_s,
        )
        result = await self._provider.complete(request)
        if not result.ok:
            raise EvalError(f"ek madde önerisi için model çağrısı başarısız: {result.error}")
        return parse_snippets(result.text)


def build_request(base_text: str, failures: Sequence[FailureNote], count: int) -> str:
    """Modele gidecek isteği kur (şablon + temel istem + başarısız görevler)."""

    notes = "\n".join(
        f"- {note.task_id}: {note.request[:FAILURE_REQUEST_CHARS]}" for note in failures
    )
    template = _TEMPLATE.read_text(encoding="utf-8")
    return (
        template.replace("{SAYI}", str(count))
        .replace("{SINIR}", str(MAX_ADDITION_CHARS))
        .replace("{GOREVLER}", notes or "(başarısız görev bilgisi yok)")
        .replace("{ISTEM}", base_text)
    )


def parse_snippets(text: str) -> tuple[str, ...]:
    """Model çıktısını ayırıcıdan bölüp boş parçaları at."""

    return tuple(part.strip() for part in text.split(SEPARATOR) if part.strip())
