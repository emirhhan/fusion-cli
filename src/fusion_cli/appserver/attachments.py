"""Bounded attachment admission shared by metadata and image loading."""

from __future__ import annotations

import base64
import json
from pathlib import Path

from ..core.image_input import IMAGE_MIMES, MAX_IMAGE_BYTES, MAX_IMAGES

MAX_ATTACHMENTS = 20


def attachment_context(value: object) -> tuple[str, str | None]:
    if value is None:
        return "", None
    if not isinstance(value, list):
        return "", "Ekler bir liste olmalıdır."
    if len(value) > MAX_ATTACHMENTS:
        return "", f"Bir turda en fazla {MAX_ATTACHMENTS} dosya eklenebilir."
    if sum(isinstance(raw, dict) and raw.get("kind") == "image" for raw in value) > MAX_IMAGES:
        return "", f"Bir turda en fazla {MAX_IMAGES} görsel eklenebilir."
    items = []
    for raw in value:
        if not isinstance(raw, dict):
            return "", "Geçersiz ek kaydı."
        path = raw.get("path")
        if not isinstance(path, str) or not path.strip() or len(path) > 4096:
            return "", "Geçersiz ek dosyası yolu."
        try:
            local = Path(path).expanduser()
            if not local.is_absolute() or not local.is_file():
                return "", f"Ek açılamadı veya artık mevcut değil: {local.name[:200]}"
            if raw.get("kind") == "image":
                if local.suffix.casefold() not in IMAGE_MIMES:
                    return "", "Desteklenmeyen görsel türü."
                if local.stat().st_size > MAX_IMAGE_BYTES:
                    return "", "Görsel en fazla 5 MiB olabilir."
        except (OSError, RuntimeError):
            return "", "Ek dosyası yolu çözülemedi veya dosya okunamadı."
        items.append(
            {
                "path": str(local),
                "name": str(raw.get("name", ""))[:512],
                "kind": "image" if raw.get("kind") == "image" else "file",
            }
        )
    if not items:
        return "", None
    return (
        "<kullanici_ekleri>\nBu yolları kullanıcı bu tur için açıkça ekledi. "
        "İçerikleri yalnız görev gerektiriyorsa standart izin ve araç kurallarıyla oku.\n"
        + json.dumps(items, ensure_ascii=False)
        + "\n</kullanici_ekleri>",
        None,
    )


def attachment_images(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    _, error = attachment_context(value)
    if error:
        raise ValueError(error)  # Revalidation can detect a race after metadata admission.
    images = []
    for raw in value:
        if raw.get("kind") != "image":
            continue
        try:
            path = Path(raw["path"]).expanduser()
            with path.open("rb") as stream:
                data = stream.read(MAX_IMAGE_BYTES + 1)
            if len(data) > MAX_IMAGE_BYTES:
                raise ValueError("Görsel okuma sırasında büyüdü; yeniden ekleyin.")
        except (OSError, RuntimeError) as read_error:
            raise ValueError("Görsel okunamadı; yeniden ekleyin.") from read_error
        images.append(
            f"data:{IMAGE_MIMES[path.suffix.casefold()]};base64,"
            + base64.b64encode(data).decode("ascii")
        )
    return tuple(images)
