"""Başarı ölçütü değerlendirmesi — saf fonksiyon.

Bir görevin başarı ölçütünü, o görevin çalıştırma gözlemleriyle karşılaştırır.
Ağ/dosya erişimi yoktur; yalnızca verilen `TaskExecution` üzerinden karar verir.
"""

from __future__ import annotations

from evals.execution import TaskExecution
from evals.tasks import CriterionKind, SuccessCriterion


def evaluate_criterion(criterion: SuccessCriterion, execution: TaskExecution) -> bool:
    """Ölçüt, çalıştırma gözlemlerine göre karşılandı mı."""

    if criterion.kind is CriterionKind.EXIT_CODE:
        return execution.exit_code == criterion.expected_exit_code

    if criterion.kind is CriterionKind.FILE_CHANGED:
        return criterion.expected_path in execution.changed_files

    if criterion.kind is CriterionKind.KEYWORD:
        # Büyük/küçük harf ayrımı DAVRANIŞ ölçmez: canlı koşuda cevap cümleye
        # "Erişilemeyen kaynağın..." diye başladı ve küçük harfli anahtar tutmadı.
        metin = execution.output_text.lower()
        aranan = (criterion.keyword or "", *criterion.alternatives)
        return any(kelime.lower() in metin for kelime in aranan if kelime)

    # Enum kapsamı yukarıda tükendi; buraya düşmek imkânsız olmalı.
    raise AssertionError(f"bilinmeyen ölçüt türü: {criterion.kind!r}")
