"""Reprodüksiyon kanıtı: önce kırmızı, sonra yeşil.

Agentless ve ReProAgent'ın ölçtüğü şey şu: bir düzeltmenin doğruluğu, hatayı
gösteren testin ÖNCE başarısız SONRA başarılı olmasıyla kanıtlanır. Yalnız "şimdi
geçiyor" demek, testin hatayı hiç yakalamadığı durumu (fail-to-fail) gizler ve bu,
yanlış başarının en yaygın kaynağıdır.

Bu modül yeni komut ÇALIŞTIRMAZ: turda gerçekten yapılmış araç çağrılarının
kaydına bakar (`ToolUse`). Doğrulayıcının kendi komut çalıştırması, kanıtı ölçmek
yerine üretmek olurdu.
"""

from __future__ import annotations

import re
import shlex
from collections.abc import Sequence
from dataclasses import replace

from ...core.evidence import CriterionEvidence, EvidenceEnvironment, EvidenceStatus, ToolUse
from ...core.execution_plan import VerificationCheck

#: Kanıt metni tek yerde tutulur: durum değişse de sözleşme aynı cümleyle anlatılır.
_KIRMIZI_YOK = "önce kırmızı görülmedi; testin hatayı yakaladığı kanıtlanmadı"
_KIRMIZI_SONRA_YESIL = "önce kırmızı, sonra yeşil: düzeltme kanıtlandı"
_HALA_KIRMIZI = "test hâlâ kırmızı"
_HIC_CALISMADI = "reprodüksiyon testi bu turda hiç çalıştırılmadı"


def evaluate_reproduction(
    check: VerificationCheck,
    *,
    tool_uses: Sequence[ToolUse],
) -> CriterionEvidence:
    """Reprodüksiyon kontrolünü turun gerçek komut kayıtlarından değerlendir."""
    uses = [use for use in tool_uses if _ayni_komut(use, check.target)]
    if not uses:
        return _kanit(check, EvidenceStatus.UNVERIFIED, _HIC_CALISMADI)
    green = uses[-1]
    if not _has_identity(green):
        return _kanit(check, EvidenceStatus.UNVERIFIED, "kaynak veya ortam kimliği ölçülmedi")
    if not green.ok:
        return _kanit(check, EvidenceStatus.FAILED, _HALA_KIRMIZI)
    if uses[0].ok:
        return _kanit(check, EvidenceStatus.UNVERIFIED, _KIRMIZI_YOK)
    for red in uses[:-1]:
        if (
            not red.ok
            and _has_identity(red)
            and is_same_environment(red.environment, green.environment)
            and red.source_digest != green.source_digest
            and red.call_id != green.call_id
            and not _RUNNER_UNAVAILABLE.search(red.output)
        ):
            return replace(
                _kanit(check, EvidenceStatus.PASSED, _KIRMIZI_SONRA_YESIL),
                source_digest=green.source_digest,
                source_after_digest=green.source_after_digest,
                environment=green.environment,
                call_id=green.call_id,
            )
    return _kanit(check, EvidenceStatus.UNVERIFIED, _KIRMIZI_YOK)


_RUNNER_UNAVAILABLE = re.compile(
    r"No module named|command not found|komut bulunamadı|çıkış kodu: 127|timed out|zaman aşımı",
    re.IGNORECASE,
)


def _has_identity(use: ToolUse) -> bool:
    """Koşu boyunca sabit kaynak ve ölçülmüş ortam olmadan kanıt üretme."""
    return bool(
        use.source_digest
        and use.source_digest == use.source_after_digest
        and use.environment is not None
        and is_same_command(use.environment.command, str(use.arguments.get("command", "")))
        and use.call_id
    )


def is_same_command(first: str, second: str) -> bool:
    """Boş veya kabuk anlamı farklı komutları aynı kanıt kimliği sayma."""
    return bool(first and second) and _normalize(first) == _normalize(second)


def is_same_environment(
    first: EvidenceEnvironment | None,
    second: EvidenceEnvironment | None,
) -> bool:
    """Kaydedilmiş iki ortamı, komut anlamını koruyarak karşılaştır."""
    if first is None or second is None:
        return False
    return replace(first, command=_normalize(first.command)) == replace(
        second, command=_normalize(second.command)
    )


def _ayni_komut(use: ToolUse, target: str) -> bool:
    """Araç kaydı bu kontrolün komutunu mu çalıştırmış?"""
    komut = use.arguments.get("command")
    return isinstance(komut, str) and is_same_command(komut, target)


# Genişletme, kaçış, atama veya kabuk dilbilgisi varsa yazım kimliğini koru.
_SHELL_SEMANTIC_MARKERS = frozenset("*?[]{}~$`\\;&|()<>#!=\n\r")
_SHELL_RESERVED_WORDS = frozenset(
    {
        "if",
        "then",
        "else",
        "elif",
        "fi",
        "for",
        "while",
        "until",
        "do",
        "done",
        "case",
        "esac",
        "in",
        "function",
        "select",
        "time",
        "coproc",
    }
)


def _normalize(komut: str) -> str:
    """Yalnız kanıtlanabilir basit argv yazımını eşitle; kabuk anlamını silme."""
    if any(marker in komut for marker in _SHELL_SEMANTIC_MARKERS):
        return komut
    try:
        tokens = shlex.split(komut)
        if tokens and tokens[0] in _SHELL_RESERVED_WORDS:
            return komut
        return shlex.join(tokens)
    except ValueError:
        return komut


def _kanit(check: VerificationCheck, status: EvidenceStatus, ozet: str) -> CriterionEvidence:
    return CriterionEvidence(
        criterion_id=check.criterion_id,
        kind=check.kind,
        status=status,
        summary=ozet,
        command=check.target,
    )
