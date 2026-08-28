"""Geçmiş kaynaklarının ortak veri modeli ve protokolü.

Her araç (Claude Code, Codex, Hermes) geçmişini başka bir biçimde saklar. Bu modül
o biçimlerin TEK ortak görünümünü tanımlar: listelenebilir bir oturum künyesi ve
imleçle çekilebilen turlar. Yeni bir araç desteği eklemek, bu protokolü uygulayan
tek bir dosya yazmaktır.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SessionRef:
    """Listede gösterilen tek bir oturum. İçeriği DEĞİL, künyesi."""

    #: Kaynak etiketi: claude | codex | hermes
    source: str
    #: Kaynağın kendi kimliği. Aynı kaynak içinde benzersizdir.
    session_id: str
    #: Gösterilecek başlık. Çözüm sırası kaynağa göre değişir, boş olmaz.
    title: str
    #: Son değişiklik zamanı (unix saniye). Sıralama bunun üzerinden yapılır.
    updated_at: float
    #: Turdaki mesaj sayısı. Bilinmiyorsa 0.
    turn_count: int = 0


@dataclass(frozen=True, slots=True)
class Turn:
    """Bir oturumdaki tek bir mesaj."""

    #: user | assistant | system
    role: str
    text: str
    timestamp: float = 0.0


class HistorySource(Protocol):
    """Bir aracın geçmişini okuyabilen taraf.

    `list` ve `read` ASLA istisna fırlatmaz: bozuk kayıt atlanır, okunamayan kaynak
    boş döner. Tek bir bozuk dosya tüm keşfi düşürmemelidir.
    """

    #: Komut adında kullanılan kısa ad: /resume<name>
    name: str

    def is_installed(self) -> bool:
        """Bu aracın izi makinede var mı? Yalnızca varlık kontrolü, dosya açılmaz."""
        ...

    def list(self, root: Path | None = None) -> tuple[SessionRef, ...]:
        """Oturumları yeniden eskiye sıralı döndür. `root` verilirse o projeye ait
        olanlar önce gelir; kaynak proje bilgisi tutmuyorsa `root` yok sayılır."""
        ...

    def read(self, session_id: str, cursor: int = 0, limit: int = 50) -> tuple[Turn, ...]:
        """`cursor`'dan başlayarak en fazla `limit` tur döndür."""
        ...
