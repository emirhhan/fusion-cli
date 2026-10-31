"""launch.json `autoPort` ve `${port}` yer tutucusu (P-041 kalanı).

Ölçüldü (31 Ekim): `autoPort` uyarıyla yok sayılıyordu; port doluyken komut aynı porta
bağlanıp düşüyor ya da o portta yanıt veren BAŞKA sunucu önizlemede görünüyordu.
"""

from __future__ import annotations

import socket
import sys
from pathlib import Path

import pytest

from fusion_cli.config import trust
from fusion_cli.tools import preview_launch, preview_ports, preview_server
from fusion_cli.tools.preview_launch import LaunchConfig, load_launch_configs
from fusion_cli.tools.preview_server import PreviewError


@pytest.fixture(autouse=True)
def _sunuculari_kapat(tmp_path, monkeypatch):
    monkeypatch.setattr(trust, "trust_store_file", lambda: tmp_path / "guven-kaydi.json")
    yield
    preview_launch.stop_all_launches()
    preview_server.stop_all()


@pytest.fixture
def dolu_port():
    """Dinlemede tutulan bir port (başka bir sunucunun açık olduğu durum)."""
    # Geçici (ephemeral) aralık dışından: orada komşu portlar giden bağlantılarca tutulabilir.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", preview_server.free_port()))
    sock.listen(1)
    yield int(sock.getsockname()[1])
    sock.close()


def _http_sunucu(port_arg: str, port: int, **kw) -> LaunchConfig:
    return LaunchConfig(
        "web",
        sys.executable,
        ("-m", "http.server", port_arg, "--bind", "127.0.0.1"),
        port,
        None,
        trusted=True,
        **kw,
    )


def _sayfa(root: Path) -> None:
    (root / "index.html").write_text("<!doctype html><title>ok</title><p>merhaba</p>", "utf-8")


def test_autoport_alani_okunur_ve_uyari_uretmez(tmp_path):
    (tmp_path / ".fusion").mkdir()
    (tmp_path / ".fusion" / "launch.json").write_text(
        '{"configurations": [{"name": "web", "runtimeExecutable": "npm", "port": 5173,'
        ' "autoPort": false}, {"name": "api", "runtimeExecutable": "npm", "port": 8000}]}',
        "utf-8",
    )
    loaded = load_launch_configs(tmp_path)
    assert loaded.warnings == ()
    assert loaded.get("web").auto_port is False
    assert loaded.get("api").auto_port is None


def test_autoport_mantiksal_degilse_kayit_atlanir(tmp_path):
    (tmp_path / ".fusion").mkdir()
    (tmp_path / ".fusion" / "launch.json").write_text(
        '{"configurations": [{"name": "web", "runtimeExecutable": "npm", "port": 1,'
        ' "autoPort": "evet"}]}',
        "utf-8",
    )
    loaded = load_launch_configs(tmp_path)
    assert loaded.configs == () and "autoPort" in loaded.warnings[0]


def test_dolu_port_sonraki_bos_porta_kayar(dolu_port):
    secim = preview_ports.choose_port(dolu_port, auto_port=None)
    assert secim is not None and secim.moved and secim.port > dolu_port
    assert preview_ports.choose_port(dolu_port, auto_port=False) is None


def test_yer_tutucu_ve_adres_portu_degisir():
    assert preview_ports.expand_port(("--port", "${port}", "x"), 5174) == ("--port", "5174", "x")
    assert preview_ports.with_port("http://localhost:5173/app?x=1", 5174) == (
        "http://localhost:5174/app?x=1"
    )


async def test_port_doluysa_komut_yeni_portta_baslar_ve_port_ortamda(tmp_path, dolu_port):
    _sayfa(tmp_path)
    config = _http_sunucu("${port}", dolu_port)

    preview = await preview_launch.start_launch(tmp_path, config)

    assert preview.url != f"http://127.0.0.1:{dolu_port}/"
    assert preview_server.responds(preview.url)
    assert preview_launch.port_note(config, preview)


async def test_autoport_false_ve_dolu_port_baslatmaz(tmp_path, dolu_port):
    config = _http_sunucu("${port}", dolu_port, auto_port=False)
    with pytest.raises(PreviewError, match="autoPort"):
        await preview_launch.start_launch(tmp_path, config)


async def test_port_bossa_istenen_portta_kalir(tmp_path):
    _sayfa(tmp_path)
    port = preview_server.free_port()
    config = _http_sunucu("${port}", port)
    preview = await preview_launch.start_launch(tmp_path, config)
    assert preview.url == f"http://127.0.0.1:{port}/"
    assert preview_launch.port_note(config, preview) == ""


async def test_panel_rpc_kaydirilan_portu_not_olarak_doner(tmp_path, dolu_port):
    import json

    from fusion_cli.appserver.preview_rpc import start_config

    _sayfa(tmp_path)
    dosya = tmp_path / ".fusion" / "launch.json"
    dosya.parent.mkdir()
    komut = ["-m", "http.server", "${port}", "--bind", "127.0.0.1"]
    dosya.write_text(
        json.dumps(
            {
                "configurations": [
                    {
                        "name": "web",
                        "runtimeExecutable": sys.executable,
                        "runtimeArgs": komut,
                        "port": dolu_port,
                    }
                ]
            }
        ),
        "utf-8",
    )
    trust.approve_file(tmp_path, dosya)

    sonuc = await start_config(tmp_path, {"ad": "web"})

    assert sonuc["ok"] is True and str(dolu_port) not in sonuc["url"]
    assert f"{dolu_port} portu doluydu" in sonuc["not"]
