"""Ölçüm iskeleti — fusion-cli değişikliklerinin işe yarayıp yaramadığını A/B ölçer.

Bu paket ürünün çalışma zamanına dahil değildir; bir araçtır. Bir görev seti
(istek + başarı ölçütü) tanımlar, seti çalıştırıp metrik toplar ve iki çalıştırmayı
karşılaştırır. Amaç: sonraki her zekâ fazının etkisini eski/yeni diff'iyle görmek.

Katmanlar bilinçle ayrıdır ve saf tutulur:

- `tasks` / `execution` — veri modelleri (frozen dataclass).
- `criteria` — bir çalıştırmanın başarı ölçütünü değerlendiren saf fonksiyon.
- `metrics` — görev sonuçlarını çalıştırma raporuna toplayan saf toplama.
- `compare` — iki raporu diff'leyen saf karşılaştırma.
- `report` — raporu tek JSON'a yazan/okuyan serileştirme.
- `loader` — görev setini YAML/JSON dosyasından okuyan doğrulayıcı.
- `runner` — bir yürütücü (executor) protokolü üzerinden seti koşturan ince orkestra.
"""

from __future__ import annotations
