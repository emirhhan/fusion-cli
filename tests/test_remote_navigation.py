"""Telefon dock yönlendirmesi ana masaüstüne, açık kapsam ve hedeflere bağlıdır."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from fusion_cli.appserver import session as session_module
from fusion_cli.appserver.desktop_dock import DesktopDock
from fusion_cli.appserver.session import AppSession
from fusion_cli.remote.controller import RemoteController
from tests.test_desktop_dock import Chrome, Native
from tests.test_remote_controller import MemorySecrets
from tests.test_remote_service import FakeClock


@pytest.fixture
async def navigation(tmp_path: Path) -> Any:
    native, chrome = Native(), Chrome()
    controller = RemoteController(
        home=tmp_path,
        root=tmp_path,
        secrets=MemorySecrets(),
        session_factory=lambda writer: object(),
        clock=FakeClock(),
        navigation=DesktopDock(native=native, chrome=chrome),
    )
    yield controller, native, chrome
    await controller.aclose()


async def test_telefon_ana_oturumun_dockunu_kullanir_isci_oturumu_degismez(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    native, chrome = Native(), Chrome()
    owner = AppSession.__new__(AppSession)
    owner._root = tmp_path
    owner._home = tmp_path
    owner._secret_store = MemorySecrets()
    owner._remote = None
    owner._desktop_dock = DesktopDock(native=native, chrome=chrome)

    class Worker:
        def __init__(self, writer: Any, **kwargs: Any) -> None:
            self.requests: list[object] = []

        async def handle(self, request: object) -> None:
            self.requests.append(request)
            raise AssertionError("Telefon dock'u işçi oturuma gönderilmemeli.")

    monkeypatch.setattr(session_module, "AppSession", Worker)
    controller = owner._remote_controller()
    try:
        phone = controller._registry.add(
            "Tel", "signed", frozenset({"desktop.observe", "agent.run"})
        )
        before = controller._registry._path.read_bytes()
        listed = await controller._service.call(phone, "desktop.targets", {})
        assert listed.ok and len(listed.data["windows"]) == 2
        assert listed.data["tabs"] == [{"kind": "tab", "id": 9, "title": "Sekme"}]
        target = {"kind": "window", "id": 2, "pid": 20}
        assert (await controller._service.call(phone, "desktop.focus", {"target": target})).ok
        assert native.calls == [("list", {}), ("focus", target)]
        assert chrome.calls == [("tabs", {})]
        assert not controller._backend._session.requests
        assert controller._registry._path.read_bytes() == before
    finally:
        await controller.aclose()


async def test_liste_ve_odak_farkli_kapsamlari_adapterden_once_dogrular(navigation: Any) -> None:
    controller, native, chrome = navigation
    reader = controller._registry.add("Okur", "signed", frozenset({"desktop.observe"}))
    runner = controller._registry.add("Görev", "signed", frozenset({"agent.run"}))
    target = {"kind": "window", "id": 1, "pid": 20}
    assert (await controller._service.call(runner, "desktop.targets", {})).error == "yetki_yok"
    assert (
        await controller._service.call(reader, "desktop.focus", {"target": target})
    ).error == "yetki_yok"
    assert native.calls == chrome.calls == []
    assert (await controller._service.call(reader, "desktop.targets", {})).ok
    assert (await controller._service.call(runner, "desktop.focus", {"target": target})).ok


@pytest.mark.parametrize(
    "target",
    [
        None,
        "window:1",
        {"kind": "window", "id": True, "pid": 20},
        {"kind": "shell", "command": "open"},
    ],
)
async def test_gecersiz_dock_hedefi_komut_calistirmaz(navigation: Any, target: object) -> None:
    controller, native, chrome = navigation
    phone = controller._registry.add("Tel", "signed", frozenset({"agent.run"}))
    result = await controller._service.call(phone, "desktop.focus", {"target": target})
    assert not result.ok and result.error in {"gecersiz_istek", "hedef_yok"}
    assert native.calls == chrome.calls == []


async def test_kapanmis_pencere_durust_hata_dondurur(navigation: Any) -> None:
    controller, native, _chrome = navigation
    phone = controller._registry.add("Tel", "signed", frozenset({"agent.run"}))
    target = {"kind": "window", "id": 99, "pid": 20}
    result = await controller._service.call(phone, "desktop.focus", {"target": target})
    assert not result.ok and result.error == "hedef_yok"
    assert native.calls == [("focus", target)]


@pytest.mark.parametrize(
    "method", ["desktop.snapshot", "desktop.inspect", "desktop.action", "masaustu.onizleme"]
)
async def test_telefon_docku_ekran_onayini_baypas_eden_uc_acmaz(
    navigation: Any, method: str
) -> None:
    controller, native, chrome = navigation
    phone = controller._registry.add(
        "Tel", "signed", frozenset({"desktop.observe", "desktop.control", "agent.run"})
    )
    result = await controller._service.call(
        phone, method, {"target": {"kind": "window", "id": 1, "pid": 20}}
    )
    assert not result.ok and result.error == "yontem_yok"
    assert native.calls == chrome.calls == []


async def test_tum_hedef_saglayicilari_kapaliyken_rpc_basari_bildirmez(
    navigation: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    controller, native, chrome = navigation

    async def unavailable(operation: str, target: dict[str, object]) -> dict[str, object]:
        return {"ok": False, "windows": [], "metin": "Yerel pencere servisi kullanılamıyor."}

    monkeypatch.setattr(native, "invoke", unavailable)
    monkeypatch.setattr(chrome, "status", lambda: {"bagli": False})
    phone = controller._registry.add("Tel", "signed", frozenset({"desktop.observe"}))
    result = await controller._service.call(phone, "desktop.targets", {})
    assert not result.ok
    assert "kullanılamıyor" in result.message


async def test_yerel_hata_varken_chrome_hedefleri_ve_hata_ipucu_korunur(
    navigation: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    controller, native, _chrome = navigation

    async def unavailable(operation: str, target: dict[str, object]) -> dict[str, object]:
        return {"ok": False, "windows": [], "metin": "Yerel pencere servisi kullanılamıyor."}

    monkeypatch.setattr(native, "invoke", unavailable)
    phone = controller._registry.add("Tel", "signed", frozenset({"desktop.observe"}))
    result = await controller._service.call(phone, "desktop.targets", {})
    assert result.ok and result.data["tabs"]
    assert result.data["native_error"] == "Yerel pencere servisi kullanılamıyor."
