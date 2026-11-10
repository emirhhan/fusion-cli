"""Masaüstü ekran görüntüsü çerçevesi: görüntü pikseli ↔ ekran noktası eşlemesi (P-030).

Model, son ekran görüntüsünün PİKSELİNDE tıklar; macOS olayları ise ekran NOKTASI ister.
Retina'da bir nokta iki pikseldir ve görüntü ayrıca modele gitmeden küçültülür; iki
dönüşüm tek yerde, bu çerçevede toplanır. `DesktopView`, `ToolContext` içinde turun son
çerçevesini taşır (frozen bağlamda taşıyıcı nesne deseni; bkz. `PendingWrite`).

Ölçüldü (31 Ekim): `desktop_click` CG noktası bekliyordu, `desktop_screenshot` ise ham
Retina pikseli veriyordu; model 2x kaymış noktaya tıklıyordu.
"""

from __future__ import annotations

import hashlib
import os
import stat
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .desktop_ref_handles import Scope

#: Eski `runtime.desktop_screenshot_max_width` varsayılanı (kullanımdan kalktı, #448).
DESKTOP_SCREENSHOT_MAX_WIDTH = 1568
#: Claude Code: "A 16-inch MacBook Pro at native Retina resolution captures at 3456×2234 and
#: downscales to roughly 1372×887, preserving aspect ratio. There is no setting to change the
#: target size." (#453). Hedef: en-boy oranı korunur, alan bu piksel bütçesini aşmaz.
SCREENSHOT_TARGET_PIXELS = 1_218_000
MAX_BACKGROUND_IMAGE_BYTES = 5 * 1024 * 1024
_BACKGROUND_READ_ERROR = "Arka plan gözlemi değişti veya erişilemiyor."


def screenshot_target_width(width: float, height: float) -> int:
    """Görüntünün en-boy oranından sabit hedef genişlik (3456x2234 → 1372; ayarlanamaz)."""
    if width <= 0 or height <= 0:
        return DESKTOP_SCREENSHOT_MAX_WIDTH
    target = int((SCREENSHOT_TARGET_PIXELS * width / height) ** 0.5)
    return max(1, min(DESKTOP_SCREENSHOT_MAX_WIDTH, target))


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


@dataclass(frozen=True, slots=True)
class DesktopCapture:
    """Trusted captured bytes and their full-screen coordinate rectangle."""

    generation: int
    path: Path
    payload_digest: str
    file_digest: str
    byte_size: int
    frame: DesktopFrame | None
    bounds: tuple[float, float, float, float]
    focus: tuple[object, ...]


class ObservationArtifact(Protocol):
    """Sunum için yalnız dosya kimliğini taşıyan ortak sözleşme."""

    @property
    def path(self) -> Path: ...
    @property
    def file_digest(self) -> str: ...
    @property
    def byte_size(self) -> int: ...


def capture_file_generation(info: os.stat_result) -> tuple[int, int, int, int]:
    """Atomik yayından önce açık dosyadan alınan değişmez nesil alanları."""
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


@dataclass(frozen=True, slots=True)
class BackgroundCapture:
    """Pencere pikseli gözlemi; ekran koordinatı veya odak yetkisi taşımaz."""

    root: Path
    scope: Scope
    path: Path
    file_digest: str
    byte_size: int
    pid: int
    window_id: int
    image_width: int
    image_height: int
    file_generation: tuple[int, int, int, int]

    def read_bytes(self) -> bytes:
        """Sunum ve görsel yardımcı aynı sınırlı, bağlantısız fiş okumasını kullanır."""
        if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
            raise OSError(_BACKGROUND_READ_ERROR)
        relative = self.path.relative_to(self.root)
        if ".." in relative.parts or not 0 < self.byte_size <= MAX_BACKGROUND_IMAGE_BYTES:
            raise ValueError(_BACKGROUND_READ_ERROR)
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        directories = [os.open(self.root, flags)]
        try:
            for part in relative.parts[:-1]:
                directories.append(os.open(part, flags, dir_fd=directories[-1]))
            descriptor = os.open(
                relative.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directories[-1]
            )
            with os.fdopen(descriptor, "rb") as handle:
                before = os.fstat(handle.fileno())
                if (
                    not stat.S_ISREG(before.st_mode)
                    or stat.S_IMODE(before.st_mode) != 0o600
                    or before.st_uid != os.getuid()
                    or capture_file_generation(before) != self.file_generation
                ):
                    raise ValueError(_BACKGROUND_READ_ERROR)
                payload = handle.read(self.byte_size + 1)
                after = os.stat(relative.name, dir_fd=directories[-1], follow_symlinks=False)
                if (
                    capture_file_generation(os.fstat(handle.fileno())) != self.file_generation
                    or capture_file_generation(after) != self.file_generation
                    or hashlib.sha256(payload).hexdigest() != self.file_digest
                ):
                    raise ValueError(_BACKGROUND_READ_ERROR)
            return payload
        finally:
            for descriptor in reversed(directories):
                os.close(descriptor)


@dataclass(frozen=True, slots=True)
class DesktopMouseAction:
    point: tuple[float, float]
    pressed: int | None = None
    released: tuple[int, ...] = ()


def image_payload_digest(data_uri: str) -> str:
    return hashlib.sha256(data_uri.encode("ascii")).hexdigest()


class DesktopView:
    """Turun son tam ekran çerçevesi; fare araçları koordinatı buna göre çevirir.

    `turn`, turu süren yüzeyin (`tools.desktop_turn.begin`) bağladığı oturumdur; bağlanmamışsa
    (MCP köprüsü, testler) ön plan eylemi yalnız eylemin kendisidir.
    """

    def __init__(self) -> None:
        from .desktop_ref_handles import DesktopRefHandles

        self.ref_handles = DesktopRefHandles()
        self.frame: DesktopFrame | None = None
        self.turn: DesktopTurnHooks | None = None
        #: Son masaüstü çağrısının politika hedefi (pid); gizlemede görünür kalır (P-033).
        self.target_pid = 0
        # Explicit focus binds subsequent coordinates to the observed window.
        self.focused_window: tuple[int, float, float, float, float] | None = None
        self.focus_required = False
        self.focused_window_id = 0
        self.focused_window_title = ""
        self.current_capture: DesktopCapture | None = None
        self._capture_generation = 0
        self._observation_turn_id = ""
        self._observation_artifacts: dict[Path, ObservationArtifact] = {}
        self.background_capture: BackgroundCapture | None = None
        self._explicit_capture_exports: set[Path] = set()

    def begin_observation_turn(self, turn_id: str) -> None:
        """Reset presentation receipts only; grounding/focus authority is unchanged."""
        self._observation_turn_id = turn_id
        self.ref_handles.clear()
        self._observation_artifacts.clear()
        self._explicit_capture_exports.clear()

    @property
    def observation_turn_id(self) -> str:
        return self._observation_turn_id

    def record_observation_artifact(
        self, capture: ObservationArtifact, *, turn_id: str, implicit: bool
    ) -> None:
        """Trusted implicit captures are internal; explicit exports revoke that label."""
        if turn_id and turn_id == self._observation_turn_id:
            if not implicit:
                self._explicit_capture_exports.add(capture.path)
                self._observation_artifacts.pop(capture.path, None)
            elif capture.path not in self._explicit_capture_exports:
                self._observation_artifacts[capture.path] = capture

    def observation_artifact_paths(
        self,
        turn_id: str,
        *,
        background_root: Path | None = None,
        background_scope: Scope | None = None,
    ) -> tuple[Path, ...]:
        """Return this turn's unchanged captured bytes, never filename lookalikes."""
        if not turn_id or turn_id != self._observation_turn_id:
            return ()
        paths: list[Path] = []
        for path, capture in self._observation_artifacts.items():
            try:
                if isinstance(capture, BackgroundCapture):
                    if (
                        capture is not self.background_capture
                        or background_root != capture.root
                        or background_scope != capture.scope
                    ):
                        continue
                    capture.read_bytes()
                    paths.append(path)
                    continue
                info = path.stat()
                if path.is_symlink() or info.st_size != capture.byte_size:
                    continue
                with path.open("rb") as handle:
                    data = handle.read(capture.byte_size + 1)
            except (OSError, ValueError):
                continue
            if hashlib.sha256(data).hexdigest() == capture.file_digest:
                paths.append(path)
        return tuple(paths)

    def focus_identity(self) -> tuple[object, ...]:
        return (
            self.focused_window,
            self.focused_window_id,
            self.focused_window_title,
            self.focus_required,
        )

    def invalidate_capture(self, *, clear_frame: bool = False) -> None:
        """Advance the epoch even if a focus attempt later returns to the same target."""
        self._capture_generation += 1
        self.current_capture = None
        if clear_frame:
            self.frame = None

    def begin_capture(self) -> tuple[int, tuple[object, ...]]:
        """Invalidate old authority and snapshot the focus before acquiring pixels."""
        self.invalidate_capture()
        return self._capture_generation, self.focus_identity()

    def capture_is_current(self, token: tuple[int, tuple[object, ...]]) -> bool:
        return token == (self._capture_generation, self.focus_identity())

    def record_capture(
        self,
        path: Path,
        data_uri: str,
        data: bytes,
        bounds: tuple[float, float, float, float],
        *,
        token: tuple[int, tuple[object, ...]] | None = None,
    ) -> DesktopCapture:
        if token is None:
            self._capture_generation += 1
            token = self._capture_generation, self.focus_identity()
        capture = DesktopCapture(
            token[0],
            path,
            image_payload_digest(data_uri),
            hashlib.sha256(data).hexdigest(),
            len(data),
            self.frame,
            bounds,
            token[1],
        )
        self.current_capture = capture
        return capture

    def to_point(self, x: float, y: float) -> tuple[float, float]:
        """Çerçeve yoksa (henüz görüntü alınmadı) koordinat ekran noktası sayılır."""
        if self.frame is None:
            return (float(x), float(y))
        return self.frame.to_point(x, y)
