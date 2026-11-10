"""Yalnız açıkça istenmiş, tek hedefli görsel koordinat sözleşmesi."""

from __future__ import annotations

import base64
import io
import re
from dataclasses import dataclass
from enum import Enum
from math import isfinite

OMNI_COORDINATE_MODEL = "nvidia_nim/nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"
MAX_COORDINATE_IMAGE_BYTES = 5 * 1024 * 1024
MAX_COORDINATE_IMAGE_PIXELS = 32_000_000
COORDINATE_ERROR = (
    "Görsel koordinat yanıtı tek hedefli doğrulanmış sözleşmeye uymuyor; "
    "yeni bir ekran görüntüsü al ve view_image(mode=locate) ile yalnız tek bir kontrolü sor. "
    "Bu yanıttan konum veya tıklama yetkisi çıkarma."
)
OBSERVATION_LABEL = "Görsel modelinin gözlemi; bağımsız doğrulama değildir: "
_SINGLE_POINT = re.compile(r"<point>\s*\(\s*([0-9]{1,4})\s*,\s*([0-9]{1,4})\s*\)\s*</point>")
_COORDINATE_HINT = re.compile(
    r"\bcoordinates?\s*:\s*[-+]?(?:\d|\.\d)|</?(?:points?|coordinates?)\b|[\[(]\s*[-+]?\d+(?:\.\d+)?(?:\s*,\s*[-+]?\d+(?:\.\d+)?)+\s*[\])]",
    re.IGNORECASE | re.DOTALL,
)
_AXIS_DECLARATION = re.compile(
    r"(?<!\w)[\"']?([xy])[\"']?\s*[:=]\s*[\"']?[-+]?(?:\d|\.\d)",
    re.IGNORECASE,
)
_PLAIN_PAIR = re.compile(r"\s*[-+]?\d+(?:\.\d+)?\s*,\s*[-+]?\d+(?:\.\d+)?\s*")


class CoordinateStatus(Enum):
    ABSENT = "absent"
    IMAGE_PIXELS = "image_pixels"
    REJECTED = "rejected"


@dataclass(frozen=True)
class ImageDimensions:
    width: int
    height: int


@dataclass(frozen=True)
class ImagePoint:
    x: float
    y: float
    dimensions: ImageDimensions


@dataclass(frozen=True)
class ImageObservation:
    text: str
    error: str | None = None
    coordinates: CoordinateStatus = CoordinateStatus.ABSENT
    point: ImagePoint | None = None

    @property
    def usable(self) -> bool:
        return self.error is None and self.coordinates is not CoordinateStatus.REJECTED

    @property
    def can_ground(self) -> bool:
        """Yalnız geçerli piksel noktası fare konumu kanıtıdır; OCR metni ayrı kalır."""
        point = self.point
        return (
            self.usable
            and bool(self.text.strip())
            and self.coordinates is CoordinateStatus.IMAGE_PIXELS
            and point is not None
            and isfinite(point.x)
            and isfinite(point.y)
            and 0 < point.dimensions.width * point.dimensions.height <= MAX_COORDINATE_IMAGE_PIXELS
            and 0 <= point.x < point.dimensions.width
            and 0 <= point.y < point.dimensions.height
        )


def image_dimensions(data_uri: str) -> ImageDimensions | None:
    """Sorudan değil, sınırlandırılmış değişmez görsel baytlarından boyut al."""
    from PIL import Image

    header, separator, encoded = data_uri.partition(",")
    if (
        not separator
        or not header.startswith("data:image/")
        or not header.endswith(";base64")
        or len(encoded) > 4 * ((MAX_COORDINATE_IMAGE_BYTES + 2) // 3)
    ):
        return None
    try:
        payload = base64.b64decode(encoded, validate=True)
        if len(payload) > MAX_COORDINATE_IMAGE_BYTES:
            return None
        with Image.open(io.BytesIO(payload)) as parsed:
            width, height = parsed.size
            if not 0 < width * height <= MAX_COORDINATE_IMAGE_PIXELS:
                return None
            parsed.verify()
        with Image.open(io.BytesIO(payload)) as parsed:
            parsed.load()
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        return None
    return ImageDimensions(width, height)


def coordinate_request(dimensions: ImageDimensions) -> str:
    """Yerel yüksek öncelikli istek; modelin kendi birim iddiasına güvenmez."""
    return (
        f" Image dimensions decoded by the caller: {dimensions.width}x{dimensions.height} pixels. "
        "This is an explicit locate request. Locate exactly ONE control per request. "
        "Respond ONLY as <point>(x,y)</point> with integer x,y in 0..1000, "
        "in thousandths of the image width and height (NVIDIA GUI-coordinate convention). "
        "Never return a list, multiple points or screen coordinates. If unsure, return uncertainty "
        "without coordinates."
    )


def normalize_coordinates(
    text: str, *, configured_model: str, response_model: str, contract: ImageDimensions | None
) -> ImageObservation:
    """Bilinmeyen koordinatları sayısal aralığından hareketle yorumlama."""
    declared_axes = {match[1].lower() for match in _AXIS_DECLARATION.finditer(text)}
    has_coordinates = bool(
        _COORDINATE_HINT.search(text) or _PLAIN_PAIR.fullmatch(text) or declared_axes == {"x", "y"}
    )
    if not has_coordinates:
        return ImageObservation(OBSERVATION_LABEL + text)
    match = _SINGLE_POINT.fullmatch(text.strip())
    if (
        match is None
        or contract is None
        or configured_model != OMNI_COORDINATE_MODEL
        or response_model != OMNI_COORDINATE_MODEL
    ):
        return ImageObservation("", COORDINATE_ERROR, CoordinateStatus.REJECTED)
    x, y = int(match[1]), int(match[2])
    if not 0 <= x < 1000 or not 0 <= y < 1000:
        return ImageObservation("", COORDINATE_ERROR, CoordinateStatus.REJECTED)
    point = ImagePoint(x * contract.width / 1000, y * contract.height / 1000, contract)
    return ImageObservation(
        OBSERVATION_LABEL + f"image_pixels; image_width={contract.width}; "
        f"image_height={contract.height}; "
        f"point=({point.x:g},{point.y:g}). Tek kontrolün görsel konum gözlemidir.",
        coordinates=CoordinateStatus.IMAGE_PIXELS,
        point=point,
    )
