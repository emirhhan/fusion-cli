"""Gerçek çözümleme sözleşmesini karşılayan küçük çevrimdışı görsel örnekleri."""

from io import BytesIO

from PIL import Image


def image_bytes(image_format: str, size: tuple[int, int] = (1, 1)) -> bytes:
    stream = BytesIO()
    with Image.new("RGB", size, color="red") as image:
        image.save(stream, format=image_format)
    return stream.getvalue()
