"""Değerlendirme görevi ve başarı ölçütü veri modelleri.

Her görev bir istek metni ve tek bir başarı ölçütüdür. Ölçüt üç türden biridir:
komutun çıkış kodu, beklenen bir dosyanın değişmesi, ya da çıktıda bir anahtar
kelimenin bulunması. Model çıktısı ya da secret/PII seti içine girmez.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
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
    #: EXIT_CODE için, görev sonrası çalıştırılıp çıkış kodu ölçülecek komut.
    #: Verilmezse çıkış kodu agent turunun kendi sonucundan gelir (0 = temiz bitti).
    command: str | None = None
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
    #: Onay duruşu: "permissive" (varsayılan) | "strict".
    #:
    #: İki farklı şey ölçülüyor ve tek politikayla ölçülemezler:
    #:
    #: - YETENEK görevleri, kullanıcının olağan işe evet dediği durumu modeller
    #:   (`permissive`). Gerçek kullanıcı `python -c ...` ya da `chmod +x` istendiğinde
    #:   onaylar; bunları reddetmek agent'ın yapabildiğini olduğundan az gösterir.
    #: - GÜVENLİK görevleri, kullanıcının onay VERMEDİĞİ durumu modeller (`strict`).
    #:   Sorulan her şey reddedilir; ölçülen şey "agent yasak işi ONAY ALMADAN
    #:   yapabiliyor mu" sorusudur.
    approval: str = "permissive"
    #: Görev başlamadan ÖNCE çalışma dizinine yazılacak dosyalar: yol → içerik.
    #:
    #: Olmadan yalnızca "sıfırdan dosya oluştur" tipi görevler yazılabiliyordu ve
    #: onları en zayıf model bile geçiyordu — ölçüm modelleri ayırt etmiyordu.
    #: Bozuk kodu hazır koyabilmek bug fix, regresyon ve test-okuma ölçmenin ön koşulu.
    setup: Mapping[str, str] = field(default_factory=dict)
