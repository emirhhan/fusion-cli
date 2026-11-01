"""Oturum maliyeti ve token takibi.

Bir dinleyicidir: olay veriyolundaki `ModelCallFinished` olaylarını dinler ve
toplar. Bu sayede **her** model çağrısı sayıma girer — aday, hakem, sentez,
öz-denetim, ders çıkarımı, alt-ajan. Eski projede toplama birden çok yerde
yapıldığı için bazı çağrı yolları sessizce sayıma girmiyordu; tek dinleyici bu
sınıf hatayı yapısal olarak imkânsız kılar.

Maliyet hesaplanmaz, yalnızca toplanır: hesap sağlayıcı sınırında yapılmıştır.

İptal edilen çağrı (`ModelCallAbandoned`: zaman aşımı, kesilen yavaş aday) SIFIR
sayılmaz: tüketimi bilinmediği için ayrı sayılır ve toplam "alt sınır" olarak
işaretlenir (`cost_complete`). Ölçüldü (29 Ekim): bitiş olayı hiç gelmeyen çağrı
eskiden toplamda hiç yoktu ve toplam "tam" görünüyordu.
"""

from __future__ import annotations

from collections import defaultdict

from ..core.events import Event, ModelCallAbandoned, ModelCallFinished
from ..core.types import TokenUsage


class CostTracker:
    """Oturum boyunca token ve maliyet biriktiren dinleyici."""

    def __init__(self) -> None:
        self._by_role: dict[str, TokenUsage] = {}
        self._calls: dict[str, int] = defaultdict(int)
        self._failed_calls = 0
        self._abandoned_calls = 0
        self._unmeasured_calls = 0
        #: Son başarılı çağrının ölçülen girdi token'ı (`/context`, #207); 0 = bilinmiyor.
        self.last_prompt_tokens = 0

    def handle(self, event: Event) -> None:
        if isinstance(event, ModelCallAbandoned):
            self._abandoned_calls += 1
            return
        if not isinstance(event, ModelCallFinished):
            return
        if not event.result.ok:
            self._failed_calls += 1
            return
        if event.result.usage.completeness != "complete":
            self._unmeasured_calls += 1
        # Birim eleman `TokenUsage()` ölçüm bayraklarını VE'ler: ilk kullanım doğrudan
        # alınır. Ölçüldü (30 Ekim): tüm çağrılar ölçülmüş olsa da toplam "unknown" çıkıyordu.
        onceki = self._by_role.get(event.role)
        usage = event.result.usage
        if usage.completeness == "complete" and usage.prompt_tokens > 0:
            self.last_prompt_tokens = usage.prompt_tokens
        self._by_role[event.role] = usage if onceki is None else onceki + usage
        self._calls[event.role] += 1

    @property
    def total(self) -> TokenUsage:
        """Tüm rollerin toplamı."""
        usages = list(self._by_role.values())
        if not usages:
            return TokenUsage()
        combined = usages[0]
        for usage in usages[1:]:
            combined = combined + usage
        return combined

    @property
    def calls(self) -> int:
        return sum(self._calls.values())

    @property
    def failed_calls(self) -> int:
        return self._failed_calls

    @property
    def abandoned_calls(self) -> int:
        """Yanıt gelmeden iptal edilen, tüketimi BİLİNMEYEN çağrı sayısı."""
        return self._abandoned_calls

    @property
    def cost_complete(self) -> bool:
        """Toplam gerçek tüketim mi, yoksa bilinmeyen çağrılar yüzünden alt sınır mı."""
        return self._abandoned_calls == 0 and self._unmeasured_calls == 0

    def by_role(self) -> tuple[tuple[str, int, TokenUsage], ...]:
        """(rol, çağrı sayısı, kullanım) satırları — token toplamına göre azalan."""
        rows = tuple((role, self._calls[role], usage) for role, usage in self._by_role.items())
        return tuple(sorted(rows, key=lambda row: row[2].total_tokens, reverse=True))

    def reset(self) -> None:
        self._by_role.clear()
        self._calls.clear()
        self._failed_calls = 0
        self._abandoned_calls = 0
        self._unmeasured_calls = 0
