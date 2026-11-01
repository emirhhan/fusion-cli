"""Ekran görüntüsü kimlikleri ve Claude `upload_image` karşılığı (#431).

Claude in Chrome ekran görüntüsüne kimlik verir; `upload_image` o görüntüyü dosya alanına
(`ref`) ya da sürükle-bırak hedefine (`coordinate`) koyar. Fusion son görüntüleri köprü
başına bellekte tutar (diske yazılmaz); yükleme eklentinin `upload` işlemiyle yapılır.
"""

from __future__ import annotations

import itertools
import re
import weakref
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from typing import Any

from ..core.tools import ToolContext, ToolResult

#: Köprü başına tutulan en fazla görüntü.
MAX_IMAGES = 10

Call = Callable[[ToolContext, str, dict[str, Any]], Awaitable[ToolResult]]
PointParser = Callable[[object, ToolContext | None], tuple[float, float] | None]

_STORE: weakref.WeakKeyDictionary[object, OrderedDict[str, str]] = weakref.WeakKeyDictionary()
_COUNTER = itertools.count(1)


def remember(chrome: object, encoded: str) -> str | None:
    """Base64 JPEG'i sakla, kimliğini (`ss_N`) döndür; köprü saklanamıyorsa `None`."""
    image_id = f"ss_{next(_COUNTER)}"
    try:
        images = _STORE.setdefault(chrome, OrderedDict())
    except TypeError:
        return None
    images[image_id] = encoded
    while len(images) > MAX_IMAGES:
        images.popitem(last=False)
    return image_id


def recall(chrome: object, image_id: str) -> str | None:
    try:
        images = _STORE.get(chrome)
    except TypeError:
        return None
    return None if images is None else images.get(image_id)


def _file_name(filename: object, image_id: str) -> str:
    raw = filename if isinstance(filename, str) else ""
    base = re.sub(r"[\\/]", "", raw).strip().strip(".")
    return base or f"{image_id}.jpg"


async def upload_image(
    args: dict[str, Any], context: ToolContext, call: Call, point: PointParser
) -> ToolResult:
    """`upload_image`: `value`=görüntü kimliği; `ref` dosya alanı ya da `point` 'x,y'."""
    image_id = args.get("value")
    if not isinstance(image_id, str) or not image_id.strip():
        return ToolResult.failure("upload_image için imageId gerekli (screenshot çıktısında).")
    encoded = recall(context.chrome, image_id.strip())
    if encoded is None:
        return ToolResult.failure(
            f"Görüntü bulunamadı: {image_id}. Yeni screenshot al; son {MAX_IMAGES} görüntü tutulur."
        )
    files = [
        {"name": _file_name(args.get("filename"), image_id), "mime": "image/jpeg", "data": encoded}
    ]
    ref = args.get("ref")
    if isinstance(ref, str) and ref:
        return await call(context, "upload", {"ref": ref, "files": files})
    spot = point(args.get("point"), context)
    if spot is None:
        return ToolResult.failure("upload_image için ref ya da coordinate [x, y] gerekli.")
    return await call(context, "upload", {"x": spot[0], "y": spot[1], "files": files})
