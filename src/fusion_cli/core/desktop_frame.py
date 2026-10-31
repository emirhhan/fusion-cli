"""Masaüstü ekran görüntüsü çerçevesi: görüntü pikseli ↔ ekran noktası eşlemesi (P-030).

Model, son ekran görüntüsünün PİKSELİNDE tıklar; macOS olayları ise ekran NOKTASI ister.
Retina'da bir nokta iki pikseldir ve görüntü ayrıca modele gitmeden küçültülür; iki
dönüşüm tek yerde, bu çerçevede toplanır. `DesktopView`, `ToolContext` içinde turun son
çerçevesini taşır (frozen bağlamda taşıyıcı nesne deseni; bkz. `PendingWrite`).

Ölçüldü (31 Ekim): `desktop_click` CG noktası bekliyordu, `desktop_screenshot` ise ham
Retina pikseli veriyordu; model 2x kaymış noktaya tıklıyordu.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

#: Modele gönderilen ekran görüntüsünün en fazla genişliği (piksel). Claude computer-use
#: 3456x2234'ü ~1372 genişliğe indirir; 1568 vision modellerinin kayıpsız kenarıdır.
DESKTOP_SCREENSHOT_MAX_WIDTH = 1568


@dataclass(frozen=True, slots=True)
class DesktopFrame:
    """Bir ekran görüntüsünün geometrisi: görüntü boyutu + kapladığı ekran dikdörtgeni."""

    image_width: int
    image_height: int
    #: Görüntünün sol üst köşesinin ekran noktası (çoklu ekranda sıfır olmayabilir).
    origin_x: float
    origin_y: float
    #: Görüntünün kapladığı alan, ekran noktası cinsinden.
    point_width: float
    point_height: float
    #: 1 tabanlı ekran sırası (1 = ana ekran); bölge görüntüsünde kaynak ekran.
    display: int = 1

    @property
    def scale(self) -> float:
        """Bir görüntü pikselinin kaç ekran noktası olduğu (küçültülmüş Retina'da ~0.9)."""
        return self.point_width / self.image_width if self.image_width else 1.0

    def to_point(self, x: float, y: float) -> tuple[float, float]:
        """Görüntü pikselini ekran noktasına çevir."""
        return (
            round(self.origin_x + x * self.scale, 1),
            round(self.origin_y + y * self.scale, 1),
        )

    def contains_pixel(self, x: float, y: float) -> bool:
        """Kenar dahil: model sık sık tam kenar değerini (ör. 1568) verir."""
        return 0 <= x <= self.image_width and 0 <= y <= self.image_height

    def describe(self) -> str:
        """Modele giden tek satırlık çerçeve bilgisi."""
        return (
            f"Görüntü {self.image_width}x{self.image_height} px; ekran {self.display}: "
            f"{self.point_width:.0f}x{self.point_height:.0f} nokta, sol üst "
            f"({self.origin_x:.0f},{self.origin_y:.0f}); "
            f"1 görüntü pikseli = {self.scale:.2f} nokta."
        )


class DesktopTurnHooks(Protocol):
    """Turun masaüstü oturumu (P-033): ilk ön plan eyleminde Esc dinleyicisi + gizleme."""

    def foreground_action(self, keep: Sequence[int] = ()) -> None: ...


class DesktopView:
    """Turun son tam ekran çerçevesi; fare araçları koordinatı buna göre çevirir.

    `turn`, turu süren yüzeyin (`tools.desktop_turn.begin`) bağladığı oturumdur; bağlanmamışsa
    (MCP köprüsü, testler) ön plan eylemi yalnız eylemin kendisidir.
    """

    def __init__(self) -> None:
        self.frame: DesktopFrame | None = None
        self.turn: DesktopTurnHooks | None = None
        #: Son masaüstü çağrısının politika hedefi (pid); gizlemede görünür kalır (P-033).
        self.target_pid = 0

    def to_point(self, x: float, y: float) -> tuple[float, float]:
        """Çerçeve yoksa (henüz görüntü alınmadı) koordinat ekran noktası sayılır."""
        if self.frame is None:
            return (float(x), float(y))
        return self.frame.to_point(x, y)
