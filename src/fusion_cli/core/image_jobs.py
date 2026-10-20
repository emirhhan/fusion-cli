"""Görsel işi için sır ve istem içermeyen kabul/çıktı makbuzları."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .errors import FusionError
from .submission import SubmissionReceipt

_DIGEST = re.compile(r"[0-9a-f]{64}")
IMAGE_JOB_REQUEST_PREFIX = "image:"


class ImageJobConflictError(FusionError):
    """İş kimliği, girdi veya çıktı kaydı başka bir kabul ile çakışıyor."""


def valid_digest(value: object) -> bool:
    """Parmak izi ham kullanıcı içeriği taşıyamaz."""
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None


@dataclass(frozen=True, slots=True)
class ImageOutputReceipt:
    """Gerçek dosya doğrulaması servis sınırında; depo yalnız typed makbuz tutar."""

    path: str
    width: int
    height: int
    digest: str
    provider: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.path, str)
            or len(self.path) > 4096
            or not Path(self.path).is_absolute()
        ):
            raise ValueError("Görsel makbuzunun mutlak dosya yolu geçersiz.")
        if any(type(value) is not int or value < 1 for value in (self.width, self.height)):
            raise ValueError("Görsel makbuzunun piksel ölçüsü geçersiz.")
        if not valid_digest(self.digest):
            raise ValueError("Görsel makbuzunun içerik parmak izi geçersiz.")
        if not isinstance(self.provider, str) or len(self.provider) > 120:
            raise ValueError("Görsel makbuzunun sağlayıcısı geçersiz.")


@dataclass(frozen=True, slots=True)
class ImageJobRecord:
    receipt: SubmissionReceipt
    input_fingerprint: str
    outputs: tuple[ImageOutputReceipt, ...] = ()


@dataclass(frozen=True, slots=True)
class ImageJobClaim:
    is_owner: bool
    record: ImageJobRecord
