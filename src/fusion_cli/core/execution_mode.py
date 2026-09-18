"""Agent görevlerinin profesyonel yürütme modları."""

from __future__ import annotations

from enum import Enum


class ExecutionMode(Enum):
    """Kök görevin tek döngü ile plan motoru arasında nasıl seçileceği.

    Varsayılan `OFF`'tur: tek ReAct döngüsü çalışır, çok adımlı işte plan tutmaya
    model `todo_write` ile kendisi karar verir. `ALWAYS` her kök turu plan
    motoruna sokar; kullanıcı tek bir tur için `/plan-yurut` makrosunu da seçebilir.
    """

    ALWAYS = "always"
    OFF = "off"

    @classmethod
    def _missing_(cls, value: object) -> ExecutionMode | None:
        """Eski ayarları güvenli yeni davranışa taşı.

        `auto` görev metnindeki kelimelerle plan motorunu seçiyordu ve kısa bir
        onay mesajını ("Tamam yaz") bile plan koşusuna sokuyordu; artık yok,
        eski değer tek döngüye (`OFF`) eşlenir. Boolean ayarlar da aynı mantıkla
        taşınır.
        """
        if value == "auto" or value is False:
            return cls.OFF
        if value is True:
            return cls.ALWAYS
        return None
