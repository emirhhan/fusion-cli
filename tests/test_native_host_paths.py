"""Yerel mesajlaşma bildirimi Chrome dışındaki Chromium tarayıcılarına da yazılır (#433)."""

from __future__ import annotations

import json

import pytest

from fusion_cli.appserver import chrome_host
from fusion_cli.appserver.native_host_paths import host_dirs, windows_host_keys


def test_macos_ve_linux_dizinleri_edge_brave_arc_vivaldi_opera_icerir(tmp_path):
    mac = {str(path) for path in host_dirs(tmp_path, "darwin")}
    for data in (
        "Microsoft Edge",
        "BraveSoftware/Brave-Browser",
        "Arc/User Data",
        "Vivaldi",
        "com.operasoftware.Opera",
        "Google/Chrome",
    ):
        assert str(tmp_path / "Library/Application Support" / data / "NativeMessagingHosts") in mac
    linux = {str(path) for path in host_dirs(tmp_path, "linux")}
    assert str(tmp_path / ".config/microsoft-edge/NativeMessagingHosts") in linux
    assert host_dirs(tmp_path, "win32") == []


def test_windows_anahtarlari_edge_ve_brave_icerir():
    keys = windows_host_keys("com.fusion.browser")
    assert r"Software\Microsoft\Edge\NativeMessagingHosts\com.fusion.browser" in keys
    assert r"Software\BraveSoftware\Brave-Browser\NativeMessagingHosts\com.fusion.browser" in keys


@pytest.mark.parametrize("platform", ["darwin", "linux"])
def test_yalniz_kurulu_tarayicilara_yazilir(tmp_path, monkeypatch, platform):
    monkeypatch.delenv("FUSION_NO_NATIVE_HOST", raising=False)
    monkeypatch.setattr(chrome_host.sys, "platform", platform)
    monkeypatch.setattr(chrome_host, "base_config_dir", lambda: tmp_path / "fusion")
    edge = host_dirs(tmp_path, platform)[2]
    edge.parent.mkdir(parents=True)
    written = chrome_host.install_native_host({"abc"}, home=tmp_path)
    assert written == [edge / f"{chrome_host.HOST_NAME}.json"]
    body = json.loads(written[0].read_text(encoding="utf-8"))
    assert body["allowed_origins"] == ["chrome-extension://abc/"]
