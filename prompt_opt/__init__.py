"""Offline prompt optimizasyonu — promptları elle değil, ölçerek iyileştir.

GEPA/DSPy ruhunda ama OFFLINE: planner/critic/localizer promptları Faz 0 eval setinde
çalıştırılır, skoru ölçülür, varyant üretilir ve kazanan sürümlenir. Canlı akışta
ONLINE optimizasyon YOKTUR — bu paket ürünün çalışma zamanına dahil değildir, bir
araçtır (`evals` gibi).

Güvenlik ilkesi: yeni sürüm ancak eski sürüme göre REGRESYON YOKSA ve ölçülebilir
iyileşme varsa yayımlanır; her yayım sürümlenir ve geri alınabilir.
"""

from __future__ import annotations

from .selection import Candidate, Selection, select_winner
from .variants import PromptVariant

__all__ = ["Candidate", "PromptVariant", "Selection", "select_winner"]
