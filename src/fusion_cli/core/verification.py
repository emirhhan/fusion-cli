"""Doğrulama sözleşmesi.

Bir turdan sonra projenin kalite kapısının (ya da alt kümesinin) çalıştırılıp
sonucunun taşındığı ince protokol. Motor concrete doğrulayıcıyı tanımaz; yalnızca
bu protokolü görür — testte sahte verilebilir, yapılandırılmamışsa hiç verilmez.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .evidence import CriterionEvidence

#: Zaman aşımına uğrayan kapı bulgusunun ortak öneki — TEK KAYNAK.
#
# Bulgu metnini hem üreten (`engines/agent/verification.py`) hem de baseline ile
# karşılaştıran (`engines/agent/step_verification.py`) taraf aynı biçimi bilmek
# zorunda; iki yerde yazılsaydı biri değiştiğinde karşılaştırma sessizce kör
# kalırdı.
TIMEOUT_FINDING_PREFIX = "komut zaman aşımına uğradı"


@dataclass(frozen=True, slots=True)
class VerificationResult:
    """Doğrulama sonucunu önem derecesiyle taşır.

    `findings` geriye uyumluluk için BLOCKING bulguların adıdır. Yalnızca bunlar
    `ok=False` yapar, correction agent açar ve öğrenme sinyalini başarısız sayar.

    `warnings` nesnel ama işi kırmayan kalite/erişilebilirlik eksikleridir.
    `advisories` ise stil, semantic tercih ve tasarım tutarlılığı önerileridir.
    """

    ok: bool
    #: İlk başarısız komut / kısa özet. Non-blocking notlarda boş olabilir.
    summary: str = ""
    #: BLOCKING ihlaller. Mevcut API adı korunur.
    findings: tuple[str, ...] = ()
    #: İşi kırmayan fakat düzeltilmesi değerli kalite/erişilebilirlik bulguları.
    warnings: tuple[str, ...] = ()
    #: Tercih/kalite seviyesindeki öneriler; correction agent açmaz.
    advisories: tuple[str, ...] = ()
    #: Gerçekten çalıştırılmış kontrol ve sınırlı çıktısı.
    evidence: tuple[CriterionEvidence, ...] = ()

    @property
    def has_notes(self) -> bool:
        return bool(self.warnings or self.advisories)


@dataclass(frozen=True, slots=True)
class SyntaxCheckResult:
    """Bir kaynak metnin ayrıştırılabilir olup olmadığını taşır."""

    ok: bool
    detail: str = ""


class JavaScriptSyntaxChecker(Protocol):
    """JavaScript kaynağını çalıştırmadan ayrıştıran dış araç sözleşmesi."""

    async def check(self, source: str, *, is_module: bool) -> SyntaxCheckResult: ...


class Verifier(Protocol):
    """Bir turdan sonra projenin doğrulama kapısını çalıştıran taraf."""

    async def verify(self) -> VerificationResult: ...
