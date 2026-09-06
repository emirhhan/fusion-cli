"""Koşan işe araya girme (steering).

Codex/Claude Code paritesi yalnız başarı oranı değildir: kullanıcı uzun bir işi
izlerken "şunu da yap", "oraya dokunma" diyebilmeli ve iş kaldığı yerden doğru
biçimde sürmeli. Fusion'da duraklatma ve devam vardı; ARAYA GİRME yoktu — tek yol
turu öldürüp baştan başlamaktı ve o ana kadarki iş çöpe gidiyordu.

Yönlendirme mesajı bir sonraki alt tura HARNESS NOTU olarak girer: modelin kendi
cevabına karışmaz, kullanıcının sözü olarak taşınır ve tur bittiğinde kaybolmaz.

Saf ve iş parçacığından bağımsızdır: kuyruk yalnız veri tutar, kim ne zaman
boşaltacağını çağıran belirler.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .types import Message

#: Kullanıcı yönergesinin modele nasıl görüneceği.
#
# Etiket açıktır: model bunu kendi ürettiği bir düşünce ya da araç çıktısı sanmamalı;
# kullanıcı SONRADAN söylemiştir ve önceki talimatı günceller.
_PREFIX = "[kullanıcı araya girdi]"


@dataclass
class SteeringQueue:
    """Koşan işe iletilecek kullanıcı yönergeleri."""

    _pending: list[str] = field(default_factory=list)

    @property
    def pending(self) -> bool:
        """Bekleyen yönerge var mı?"""
        return bool(self._pending)

    def push(self, message: str) -> None:
        """Yönergeyi kuyruğa al; boş mesaj yok sayılır."""
        text = message.strip()
        if text:
            self._pending.append(text)

    def drain(self) -> tuple[Message, ...]:
        """Bekleyen yönergeleri sırasıyla al ve kuyruğu boşalt.

        Boşaltma tek seferliktir: aynı yönergeyi her turda yeniden göndermek,
        kullanıcının bir kez söylediğini sonsuz tekrar eden bir talimata çevirirdi.
        """
        notlar = tuple(
            Message("user", f"{_PREFIX} {text}", harness_note=True) for text in self._pending
        )
        self._pending.clear()
        return notlar
