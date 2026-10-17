"""Yerel dock uçları: yalnız açık, kimliği doğrulanan hedeflere erişilir."""

from __future__ import annotations

from .desktop_activity import DesktopActivity
from .desktop_dock import DesktopDock

DESKTOP_ROUTES = frozenset(
    {"masaustu.hedefler", "masaustu.odakla", "masaustu.onizleme", "masaustu.etkinlik"}
)


async def dispatch_desktop(
    dock: DesktopDock, activity: DesktopActivity, name: str, data: dict[str, object]
) -> dict[str, object]:
    if name == "masaustu.hedefler":
        return await dock.list()
    if name == "masaustu.etkinlik":
        return activity.view()
    target = data.get("target")
    if not isinstance(target, dict):
        return {"ok": False, "metin": "Geçerli hedef gerekli."}
    if name == "masaustu.odakla":
        return await dock.focus(target)
    if name == "masaustu.onizleme":
        current = activity.view()
        if current.get("active") is not True or current.get("target") != target:
            return {"ok": False, "metin": "Bu hedefte etkin bir ajan işlemi yok."}
        result = await dock.snapshot(target)
        latest = activity.view()
        if (
            latest.get("active") is not True
            or latest.get("target") != target
            or latest.get("activityId") != current.get("activityId")
        ):
            return {"ok": False, "metin": "Ajan işlemi değişti; eski görüntü gösterilmedi."}
        image = result.pop("image", None)
        if (
            result.get("ok")
            and isinstance(image, str)
            and image.startswith("data:image/png;base64,")
        ):
            result["pngBase64"] = image.split(",", 1)[1]
        return result
    return {"ok": False, "metin": "Bilinmeyen masaüstü isteği."}
