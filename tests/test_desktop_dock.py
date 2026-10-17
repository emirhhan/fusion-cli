from __future__ import annotations

from fusion_cli.appserver.desktop_dock import DesktopDock


class Native:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def invoke(self, operation: str, target: dict[str, object]) -> dict[str, object]:
        self.calls.append((operation, target))
        if operation == "list":
            return {
                "ok": True,
                "windows": [
                    {"kind": "window", "id": 1, "pid": 20, "title": "Aynı"},
                    {"kind": "window", "id": 2, "pid": 20, "title": "Aynı"},
                ],
            }
        return {"ok": target.get("id") in {1, 2}, "id": target.get("id")}


class Chrome:
    def status(self) -> dict[str, object]:
        return {"bagli": True}

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def invoke(self, operation: str, args: dict[str, object]) -> dict[str, object]:
        self.calls.append((operation, args))
        return {"ok": True, "veri": {"tabs": [{"id": 9, "title": "Sekme"}]}}


async def test_ayni_baslikli_pencereler_kimlikle_ayrilir() -> None:
    native = Native()
    dock = DesktopDock(native=native)
    result = await dock.list()
    windows = result["windows"]
    assert isinstance(windows, list)
    assert len(windows) == 2
    await dock.focus({"kind": "window", "id": 2, "pid": 20})
    assert native.calls[-1] == ("focus", {"kind": "window", "id": 2, "pid": 20})


async def test_eski_hedef_ve_gecersiz_kimlik_odağı_degistirmez() -> None:
    native = Native()
    dock = DesktopDock(native=native)
    assert not (await dock.focus({"kind": "window", "id": 99, "pid": 20}))["ok"]
    count = len(native.calls)
    assert not (await dock.focus({"kind": "window", "id": True, "pid": 20}))["ok"]
    assert len(native.calls) == count


async def test_sekme_odagi_baglama_isleminden_ayridir() -> None:
    chrome = Chrome()
    dock = DesktopDock(chrome=chrome, native=Native())
    result = await dock.list()
    assert result["tabs"] == [{"kind": "tab", "id": 9, "title": "Sekme"}]
    await dock.focus({"kind": "tab", "id": 9})
    assert chrome.calls == [("tabs", {}), ("tab_focus", {"id": 9})]
    assert not (await dock.snapshot({"kind": "tab", "id": 9}))["ok"]
    assert len(chrome.calls) == 2


async def test_snapshot_tum_ekran_yerine_hedefe_baglidir() -> None:
    native = Native()
    dock = DesktopDock(native=native)
    target = {"kind": "window", "id": 2, "pid": 20}
    await dock.snapshot(target)
    assert native.calls == [("snapshot", target)]


async def test_kopuk_chrome_listeleme_tarayıciyi_baslatmaz() -> None:
    class Disconnected(Chrome):
        def status(self) -> dict[str, object]:
            return {"bagli": False}

    chrome = Disconnected()
    await DesktopDock(chrome=chrome, native=Native()).list()
    assert not chrome.calls


async def test_ax_eylemi_tam_pencere_ve_basvuruya_baglanir() -> None:
    native = Native()
    dock = DesktopDock(native=native)
    request: dict[str, object] = {"ref": "inceleme-basvurusu", "action": "press"}
    target = {"kind": "window", "id": 2, "pid": 20}
    await dock.action(target, request)
    assert native.calls == [("action", {**target, "request": request})]
    assert not (await dock.action(target, {"action": "global_click"}))["ok"]
