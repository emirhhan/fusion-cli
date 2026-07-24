"""Çalıştırılabilir beceri (playbook) kütüphanesi — opt-in deterministik akışlar.

Tekrarlayan çok-adımlı işler (biçimlendir + lint düzelt, testleri koştur…) serbest
bir ReAct döngüsü yerine deterministik bir akışla yapılabilir: daha az model çağrısı,
öngörülebilir sonuç. Bir playbook ön-koşulu eşleşince önerilir/çalıştırılır; `checks`
başarısızsa yapılan adımlar geri alınır.

Opt-in'dir: yapılandırmada `playbooks` açık değilse (varsayılan) devreye hiç girmez
ve mevcut agent akışı birebir korunur.
"""

from __future__ import annotations

from .model import Playbook, PlaybookResult, PlaybookStep
from .runner import StepRunner, run_playbook

__all__ = ["Playbook", "PlaybookResult", "PlaybookStep", "StepRunner", "run_playbook"]
