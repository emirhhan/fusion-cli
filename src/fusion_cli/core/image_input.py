"""Image admission and journal limits. Never fetch remote image URLs."""

from __future__ import annotations

import base64
import binascii
import io
import warnings

from PIL import Image

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGES = 8
IMAGE_MIMES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def valid_image_uri(value: object) -> bool:
    if not isinstance(value, str) or len(value) > (MAX_IMAGE_BYTES + 2) // 3 * 4 + 64:
        return False
    header, sep, encoded = value.partition(",")
    if not sep or header not in {f"data:{mime};base64" for mime in IMAGE_MIMES.values()}:
        return False
    try:
        data = base64.b64decode(encoded, validate=True)
        if not data or len(data) > MAX_IMAGE_BYTES:
            return False
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if image.width * image.height > 40_000_000:
                    return False
                if Image.MIME.get(image.format or "") != header[5:-7]:
                    return False
                image.verify()
        return True
    except (
        ValueError,
        OSError,
        binascii.Error,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        return False
