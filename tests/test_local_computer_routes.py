"""Gerçek AppSession RPC host bağı olmadan bilgisayar yetkisi üretmez."""

import json

from fusion_cli.appserver.local_computer import LocalComputer, LocalHost
from fusion_cli.appserver.protocol import Request
from fusion_cli.appserver.session import AppSession
from fusion_cli.core.tools import ToolContent, ToolContext, ToolResult


async def test_real_session_rpc_host_snapshot_serialization(tmp_path):
    calls = []

    async def execute(name, args, context):
        calls.append(name)
        return ToolResult(
            "Sonda",
            content=(ToolContent.image("image/png", "fixture"),)
            if name == "desktop_screenshot"
            else (),
        )

    async def clean(*args):
        pass

    computer = LocalComputer(
        LocalHost("native", "thread", "darwin"),
        ToolContext(tmp_path),
        execute,
        lambda: True,
        lambda: 1,
        clean,
    )
    lines = []
    session = AppSession(
        lines.append, root=tmp_path, home=tmp_path / "home", local_computer=computer
    )
    session._conversation_id = "thread"
    await session.handle(Request("1", "bilgisayar.snapshot", {}))
    result = json.loads(lines[-1])["veri"]
    assert result["ok"] and result["status"] == "observed"
    assert result["snapshot_id"] == "thread:1"
    assert result["images"] == ["data:image/png;base64,fixture"]
    assert calls == ["desktop_screenshot", "desktop_accessibility"]


async def test_missing_host_or_wrong_scope_and_json_authority_rejected(tmp_path, monkeypatch):
    async def execute(*args):
        raise AssertionError("Executor çağrılmamalı")

    async def clean(*args):
        pass

    computer = LocalComputer(
        LocalHost("native", "other", "darwin"),
        ToolContext(tmp_path),
        execute,
        lambda: True,
        lambda: 1,
        clean,
    )
    session = AppSession([].append, root=tmp_path, home=tmp_path / "home", local_computer=computer)
    session._conversation_id = "thread"
    assert not (await session._dispatch(Request("1", "bilgisayar.snapshot", {})))["ok"]
    session._conversation_id = "other"
    assert not (await session._dispatch(Request("1", "bilgisayar.snapshot", {"host": "local"})))[
        "ok"
    ]
    # Enjekte edilmemiş oturum kendi yerel gözlemcisini kurar; macOS dışında gözlem yoktur.
    from fusion_cli.appserver import local_computer as modul

    monkeypatch.setattr(modul.sys, "platform", "linux")
    missing = AppSession([].append, root=tmp_path, home=tmp_path / "home2")
    assert not (await missing._dispatch(Request("1", "bilgisayar.durum", {})))["ok"]


async def test_scope_changes_during_probe_reject_output(tmp_path):
    session = None

    async def execute(name, args, context):
        session._conversation_id = "changed"
        return ToolResult("Sonda", content=(ToolContent.image("image/png", "fixture"),))

    async def clean(*args):
        pass

    computer = LocalComputer(
        LocalHost("native", "thread", "darwin"),
        ToolContext(tmp_path),
        execute,
        lambda: True,
        lambda: 1,
        clean,
    )
    session = AppSession([].append, root=tmp_path, home=tmp_path / "home", local_computer=computer)
    session._conversation_id = "thread"
    result = await session._dispatch(Request("1", "bilgisayar.snapshot", {}))
    assert not result["ok"] and "images" not in result


async def test_wrong_root_and_status_without_conversation_fail_closed(tmp_path):
    async def execute(*args):
        raise AssertionError("Executor çağrılmamalı")

    async def clean(*args):
        pass

    computer = LocalComputer(
        LocalHost("native", "thread", "darwin"),
        ToolContext(tmp_path / "other"),
        execute,
        lambda: True,
        lambda: 1,
        clean,
    )
    session = AppSession([].append, root=tmp_path, home=tmp_path / "home", local_computer=computer)
    assert not (await session._dispatch(Request("1", "bilgisayar.durum", {})))["ok"]
    session._conversation_id = "thread"
    assert not (await session._dispatch(Request("1", "bilgisayar.snapshot", {})))["ok"]


async def test_uygulama_oturumu_enjekte_edilmemisse_yerel_macos_gozlemini_kurar(
    tmp_path, monkeypatch
):
    """Codex AppSession'a `local_computer` parametresi ekledi ama hiçbir üretim yolu onu
    kurmuyordu: Kits'ten gelen istek hep "Yerel host bağlı değil" dönerdi."""
    from fusion_cli.appserver import local_computer as modul

    cagrilar = []

    def ekran(args, context):
        cagrilar.append("desktop_screenshot")
        (context.root / args["path"]).parent.mkdir(parents=True, exist_ok=True)
        (context.root / args["path"]).write_bytes(b"png")
        return ToolResult("ekran", content=(ToolContent.image("image/png", "eA=="),))

    def erisilebilirlik(args, context):
        cagrilar.append("desktop_accessibility")
        return ToolResult("Pencere: Finder\n- düğme: Yeni Klasör")

    monkeypatch.setattr(modul, "_native_tools", lambda: {
        "desktop_screenshot": ekran, "desktop_accessibility": erisilebilirlik,
    })  # fmt: skip
    monkeypatch.setattr(modul.sys, "platform", "darwin")
    lines = []
    session = AppSession(lines.append, root=tmp_path, home=tmp_path / "home")

    await session.handle(Request("1", "bilgisayar.snapshot", {}))

    sonuc = json.loads(lines[-1])["veri"]
    assert sonuc["ok"] and sonuc["status"] == "observed"
    assert "Yeni Klasör" in sonuc["text"]
    assert cagrilar == ["desktop_screenshot", "desktop_accessibility"]
    # Geçici ekran dosyası temizlenir; proje kökünde iz kalmaz.
    assert not list((tmp_path / ".fusion" / "local-computer").glob("*.png"))
