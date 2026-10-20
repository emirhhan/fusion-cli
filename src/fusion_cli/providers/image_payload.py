"""Sağlayıcılardan gelen görsel baytlarını tam çözerek ortak doğrulama yapar."""

from __future__ import annotations

import base64
import warnings
from dataclasses import dataclass
from io import BytesIO

from PIL import Image


@dataclass(frozen=True, slots=True)
class ValidatedImage:
    data: bytes
    suffix: str
    width: int
    height: int


def decode_image_payload(encoded: str) -> ValidatedImage | None:
    """PNG/JPEG'yi doğrula; ölçüleri DOM veya istekten değil gerçek dosyadan al."""
    try:
        data = base64.b64decode(encoded, validate=True)
    except ValueError:
        return None
    return validate_image_bytes(data)


def validate_image_bytes(data: bytes) -> ValidatedImage | None:
    """Aynı tam çözümleme kuralını disk makbuzlarında base64 kopyası olmadan kullan."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                image_format = image.format
                image.verify()
            if image_format not in {"PNG", "JPEG"}:
                return None
            with Image.open(BytesIO(data)) as image:
                image.load()
                width, height = image.size
        return ValidatedImage(data, ".png" if image_format == "PNG" else ".jpg", width, height)
    except (
        OSError,
        ValueError,
        SyntaxError,
        OverflowError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        return None
