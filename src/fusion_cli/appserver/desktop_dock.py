"""Yerel pencere ve Chrome hedeflerini ayrı kimliklerle yöneten küçük dock."""

from __future__ import annotations

from typing import Protocol

from ..tools.native_desktop import SwiftDesktop


class DockChrome(Protocol):
    """Var olan Chrome köprüsünün gereken küçük yüzeyi."""

    async def invoke(self, operation: str, args: dict[str, object]) -> dict[str, object]: ...

    def status(self) -> dict[str, object]: ...


class NativeDesktop(Protocol):
    """İşletim sistemi hedeflerini açık kimliklerle işle."""

    async def invoke(self, operation: str, target: dict[str, object]) -> dict[str, object]: ...


def _failure(message: str) -> dict[str, object]:
    return {"ok": False, "status": "unavailable", "metin": message}


def _positive(value: object) -> bool:
    return type(value) is int and value > 0


def _window_target(target: dict[str, object]) -> bool:
    return (
        target.get("kind") == "window"
        and _positive(target.get("id"))
        and _positive(target.get("pid"))
    )


class DesktopDock:
    """Kullanıcı odağı ajan sekme bağından ve salt ekran gözleminden ayrıdır."""

    def __init__(
        self, chrome: DockChrome | None = None, native: NativeDesktop | None = None
    ) -> None:
        self._chrome = chrome
        self._native = native if native is not None else SwiftDesktop()

    async def list(self) -> dict[str, object]:
        """Pencereleri ve bağlı Chrome'un sekmelerini getir; kısmi hatayı göster."""
        native = await self._native.invoke("list", {})
        tabs: list[object] = []
        chrome_error = ""
        if self._chrome is not None and self._chrome.status().get("bagli"):
            try:
                response = await self._chrome.invoke("tabs", {})
                payload = response.get("veri", response)
                if response.get("ok", True) and isinstance(payload, dict):
                    items = payload.get("tabs")
                    if isinstance(items, list):
                        tabs = [{**item, "kind": "tab"} for item in items if isinstance(item, dict)]
                else:
                    chrome_error = "Chrome sekmeleri alınamadı."
            except (ConnectionError, TimeoutError, OSError):
                chrome_error = "Chrome eklentisi bağlı değil."
        return {
            "ok": bool(native.get("ok")) or bool(tabs),
            "windows": native.get("windows", []),
            "tabs": tabs,
            "native_error": native.get("metin", ""),
            "chrome_error": chrome_error,
        }

    async def focus(self, target: dict[str, object]) -> dict[str, object]:
        """Yalnız kullanıcı seçtiğinde gerçek pencereyi öne getir."""
        if _window_target(target):
            return await self._native.invoke("focus", target)
        if target.get("kind") == "tab" and _positive(target.get("id")) and self._chrome:
            try:
                return await self._chrome.invoke("tab_focus", {"id": target["id"]})
            except (ConnectionError, TimeoutError, OSError):
                return _failure("Chrome sekmesi öne getirilemedi.")
        return _failure("Dock hedefi geçersiz veya bağlı değil.")

    async def snapshot(self, target: dict[str, object]) -> dict[str, object]:
        """Yalnız seçilmiş pencereyi yakala; tüm ekranı veya etkin sekmeyi açma."""
        if not _window_target(target):
            return _failure("Bu hedef için odağı değiştirmeyen görüntü desteklenmiyor.")
        return await self._native.invoke("snapshot", target)

    async def inspect(self, target: dict[str, object]) -> dict[str, object]:
        """Arka plandaki hedef pencerenin erişilebilir öğelerini oku."""
        if not _window_target(target):
            return _failure("Erişilebilirlik hedefi geçersiz.")
        return await self._native.invoke("inspect", target)

    async def action(
        self, target: dict[str, object], request: dict[str, object]
    ) -> dict[str, object]:
        """İncelenmiş hedef öğeye sınırlı AX eylemi uygula."""
        if not _window_target(target):
            return _failure("Erişilebilirlik hedefi geçersiz.")
        if request.get("action") not in {"press", "set_value"}:
            return _failure("Erişilebilirlik eylemi desteklenmiyor.")
        return await self._native.invoke("action", {**target, "request": request})
