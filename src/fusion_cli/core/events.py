"""Olay sözlüğü — motor katmanının dış dünyayla tek konuşma biçimi.

Eski projede motorlar doğrudan konsola yazıyordu; bu yüzden alt-ajan çıktısı ana
ajanınkine karışıyor, ham log satırları akışın ortasına düşüyordu. Burada motorlar
konsolu hiç tanımaz: tiplenmiş olay yayınlar, olayları tek bir veriyolu SIRAYLA
dinleyicilere dağıtır. Çakışma yapısal olarak imkânsız hale gelir.

`Channel` alanı ikinci güvenceyi verir: ana ajan, alt-ajan ve council farklı
kanallarda akar; dinleyici her kanalı ayrı tamponlar, satırlar birbirini bölmez.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

from .types import ModelResult


class Channel(Enum):
    """Metin akışının hangi konuşmaya ait olduğu."""

    MAIN = "main"
    SUBAGENT = "subagent"
    COUNCIL = "council"


@dataclass(frozen=True, slots=True)
class Event:
    """Tüm olayların kökü."""


@dataclass(frozen=True, slots=True)
class StatusChanged(Event):
    """Kullanıcıya gösterilecek kısa ilerleme bilgisi."""

    message: str


@dataclass(frozen=True, slots=True)
class ModelCallStarted(Event):
    """Bir model çağrısı başlatıldı."""

    role: str
    model: str


@dataclass(frozen=True, slots=True)
class ModelCallFinished(Event):
    """Bir model çağrısı bitti (başarılı ya da değil)."""

    role: str
    result: ModelResult


@dataclass(frozen=True, slots=True)
class TokenReceived(Event):
    """Akıştan metin parçası geldi."""

    channel: Channel
    text: str


@dataclass(frozen=True, slots=True)
class ErrorOccurred(Event):
    """Kullanıcıya gösterilecek hata. `fatal` ise tur devam edemez."""

    message: str
    fatal: bool = False


@dataclass(frozen=True, slots=True)
class TurnFinished(Event):
    """Tur bitti; dinleyiciler tamponlarını boşaltabilir."""


@runtime_checkable
class EventSink(Protocol):
    """Olayları tüketen taraf (terminal render'ı, JSON çıktısı, dosya log'u…).

    `handle` senkrondur ve hızlı dönmelidir; veriyolu olayları sırayla dağıtır.
    """

    def handle(self, event: Event) -> None: ...


class EventPublisher(Protocol):
    """Olay yayınlayan taraf. Motorlar yalnızca bunu görür, veriyolunu tanımaz.

    `publish` asla bloklamaz ve asla hata fırlatmaz.
    """

    def publish(self, event: Event) -> None: ...
