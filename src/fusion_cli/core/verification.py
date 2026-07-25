"""Doğrulama sözleşmesi.

Bir turdan sonra projenin kalite kapısının (ya da alt kümesinin) çalıştırılıp
sonucunun taşındığı ince protokol. Motor concrete doğrulayıcıyı tanımaz; yalnızca
bu protokolü görür — testte sahte verilebilir, yapılandırılmamışsa hiç verilmez.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class VerificationResult:
    """Doğrulama kapısının sonucu."""

    ok: bool
    #: İlk başarısız komut / kısa özet (log ve teşhis için). Başarıda boş olabilir.
    summary: str = ""
    #: Modele geri verilecek SOMUT ihlaller, her biri tek satır.
    #:
    #: Özet insan içindir; bulgular modele düzeltme talimatı olarak gider. Ölçüldü:
    #: model araç sonucuna tepki veriyor, prompt metnine vermiyor — bu yüzden kapının
    #: çıktısı "bir sorun var" değil, "şu satırda şu yanlış" olmalıdır.
    findings: tuple[str, ...] = ()


class Verifier(Protocol):
    """Bir turdan sonra projenin doğrulama kapısını çalıştıran taraf."""

    async def verify(self) -> VerificationResult: ...
