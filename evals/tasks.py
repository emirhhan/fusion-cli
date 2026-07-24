"""Değerlendirme görevi ve başarı ölçütü veri modelleri.

Her görev bir istek metni ve tek bir başarı ölçütüdür. Ölçüt üç türden biridir:
komutun çıkış kodu, beklenen bir dosyanın değişmesi, ya da çıktıda bir anahtar
kelimenin bulunması. Model çıktısı ya da secret/PII seti içine girmez.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CriterionKind(Enum):
    """Bir görevin başarısının nasıl ölçüldüğü."""

    EXIT_CODE = "exit_code"  # çalıştırılan komutun çıkış kodu beklenene eşit mi
    FILE_CHANGED = "file_changed"  # beklenen yol değişen dosyalar arasında mı
    KEYWORD = "keyword"  # anahtar kelime çıktı metninde geçiyor mu


@dataclass(frozen=True, slots=True)
class SuccessCriterion:
    """Bir görevin başarılı sayılması için gereken tek koşul.

    Yalnızca `kind`'a karşılık gelen alan doludur; diğerleri `None` kalır.
    Tutarlılık `loader` tarafından yüklemede doğrulanır.
    """

    kind: CriterionKind
    #: EXIT_CODE için beklenen çıkış kodu.
    expected_exit_code: int | None = None
    #: FILE_CHANGED için değişmesi beklenen dosya yolu.
    expected_path: str | None = None
    #: KEYWORD için çıktıda aranan metin.
    keyword: str | None = None


@dataclass(frozen=True, slots=True)
class EvalTask:
    """Tek bir değerlendirme görevi: istek + başarı ölçütü."""

    id: str
    request: str
    criterion: SuccessCriterion
