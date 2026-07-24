"""Araç sözleşmeleri.

Bir araç üç parçadan oluşur ve üçü tek yerde, kayıt defterinde birleşir:
şema (modele ne söyleneceği), executor (işi yapan saf fonksiyon) ve `mutating`
bayrağı (onay gerekip gerekmediği).

Executor SAF tutulur: konsola yazmaz, kullanıcıya sormaz, modül seviyesinde durum
tutmaz. Onay, önizleme ve gösterim aracın dışındadır. Tur bazlı durum (görev listesi
gibi) `ToolContext` üzerinden taşınır — eski projede bu modül-global bir liste olduğu
için alt-ajanlar ana ajanla aynı listeyi paylaşıyordu.

Sonuçlar metin değil `ToolResult` döner: "bu çıktı hata mı?" sorusu string aramasıyla
dağınık biçimde değil, tek bir bayrakla cevaplanır.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Protocol

#: Modelin araca verdiği ham argümanlar. JSON'dan geldiği için tipsizdir;
#: `tools.args` yardımcıları bunları doğrulayarak okur.
ToolArgs = Mapping[str, object]


@dataclass(frozen=True, slots=True)
class ToolResult:
    """Bir araç çalıştırmasının sonucu."""

    output: str
    ok: bool = True

    @classmethod
    def failure(cls, message: str) -> ToolResult:
        """Aracın kendi tespit ettiği, modele düzeltme şansı veren hata."""
        return cls(output=message, ok=False)


class TodoStatus(Enum):
    """Bir görev maddesinin durumu."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"

    @property
    def icon(self) -> str:
        return {"pending": "☐", "in_progress": "▶", "completed": "☒"}[self.value]


@dataclass(frozen=True, slots=True)
class TodoItem:
    """Görev listesindeki tek madde."""

    content: str
    status: TodoStatus


class TodoList:
    """Tur bazlı görev listesi.

    Modül-global DEĞİLDİR: her tur (ve her alt-ajan) kendi listesine sahiptir.
    """

    def __init__(self) -> None:
        self._items: tuple[TodoItem, ...] = ()

    def replace(self, items: tuple[TodoItem, ...]) -> None:
        self._items = items

    @property
    def items(self) -> tuple[TodoItem, ...]:
        return self._items

    @property
    def has_pending(self) -> bool:
        """Tamamlanmamış madde var mı? (İşin yarım kalıp kalmadığı sezgiseli için.)"""
        return any(item.status is not TodoStatus.COMPLETED for item in self._items)

    def render(self) -> str:
        return "\n".join(f"{item.status.icon} {item.content}" for item in self._items)


@dataclass(frozen=True, slots=True)
class ToolContext:
    """Araçların çalıştığı ortam. Executor'lar dış dünyaya buradan erişir."""

    #: Göreli yolların çözümleneceği kök dizin.
    root: Path
    #: Bu tura ait görev listesi.
    todos: TodoList = field(default_factory=TodoList)
    #: True ise dosya araçları yalnızca `root` altında çalışır; kök dışına çıkan
    #: yol, `..` ile dışarı taşan yol ve köke sızdıran symlink reddedilir. Varsayılan
    #: kapalıdır: eski davranış (kök dışına da yazma) korunur, kısıtlama opt-in'dir.
    restrict_to_root: bool = False


#: Bir aracın işini yapan fonksiyon. Saf tutulur; yan etkisi yalnızca dosya
#: sistemi / kabuk / ağ üzerindedir, terminale ya da kullanıcıya değil.
#:
#: Asenkron da olabilir: alt-ajan devri ya da çoklu-model danışma gibi araçlar doğası
#: gereği bekler. Kayıt defteri ikisini de aynı şekilde çalıştırır, çağıran taraf farkı
#: bilmez — bu sayede motorda "şu araç özel" diye bir dal açılmaz.
ToolExecutor = Callable[[ToolArgs, ToolContext], ToolResult | Awaitable[ToolResult]]


@dataclass(frozen=True, slots=True)
class Tool:
    """Şema + executor + onay bayrağı."""

    name: str
    description: str
    #: Modele verilecek JSON Schema (OpenAI function-calling biçimi).
    parameters: Mapping[str, object]
    run: ToolExecutor
    #: True ise araç dosya/sistem durumunu değiştirir ve onay akışına girer.
    mutating: bool = False

    def schema(self) -> dict[str, object]:
        """Model çağrısına eklenecek function-calling şeması."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": dict(self.parameters),
            },
        }


class ToolPreviewer(Protocol):
    """Değiştirici bir araç ÇALIŞMADAN önce ne yapacağını anlatan önizleme üretir."""

    def __call__(self, args: ToolArgs, context: ToolContext) -> str | None: ...
