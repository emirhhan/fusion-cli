"""Bir görevin tek çalıştırmasından toplanan ham gözlemler.

Bu nesne yürütücü (executor) tarafından üretilir; başarı ölçütü ve metrikler
bunun üzerinden hesaplanır. Ağ/motor bağımlılığı yoktur, saf veridir — bu sayede
metrik ve karşılaştırma mantığı sahte gözlemle ağ olmadan test edilebilir.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class TaskExecution:
    """Tek bir görev çalıştırmasının ölçülebilir sonucu."""

    task_id: str
    #: Çalıştırılan komutun çıkış kodu; komut yoksa None.
    exit_code: int | None = None
    #: Çalıştırma sırasında değişen dosya yolları.
    changed_files: frozenset[str] = field(default_factory=frozenset)
    #: Modelin/araçların ürettiği birleşik çıktı metni.
    output_text: str = ""
    #: Bu görev için yapılan toplam model çağrısı sayısı.
    model_calls: int = 0
    #: İlk denemeden sonra yapılan yeniden deneme sayısı (0 = ilk denemede bitti).
    retries: int = 0
    #: Görevin baştan sona sürdüğü süre (saniye).
    duration_seconds: float = 0.0
