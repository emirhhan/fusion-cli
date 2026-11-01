"""Claude sandbox ağ/araç anahtarları: allowUnixSockets, allowAllUnixSockets, allowLocalBinding,
bwrapPath, socatPath; Fusion'ın allow-default profilinde zaten açık olanlar (#350)."""

from __future__ import annotations

import logging
import shutil
import socket
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from fusion_cli.config.loader import load_config
from fusion_cli.config.sandbox_config import sandbox_policy
from fusion_cli.core import linux_sandbox_tools, shell_sandbox
from fusion_cli.core.sandbox_policy import SandboxPolicy

_SANDBOX = Path("/usr/bin/sandbox-exec")


def _config(tmp_path: Path, body: str):
    path = tmp_path / "config.yaml"
    path.write_text(body, encoding="utf-8")
    return load_config(path)


def test_claude_adlari_okunur_yollar_cozulur_uyarisiz(tmp_path, caplog):
    caplog.set_level(logging.WARNING)
    config = _config(
        tmp_path,
        "sandbox:\n"
        "  bwrapPath: /opt/bwrap\n"
        "  socatPath: /opt/socat\n"
        "  allowAppleEvents: true\n"
        "  enableWeakerNetworkIsolation: true\n"
        "  network:\n"
        "    allowUnixSockets: ['~/.docker/run/docker.sock', 'run/app.sock']\n"
        "    allowLocalBinding: true\n"
        "    allowMachLookup: ['com.apple.x']\n",
    )
    sandbox = config.sandbox
    assert sandbox.bwrap_path == "/opt/bwrap" and sandbox.socat_path == "/opt/socat"
    assert sandbox.allow_local_binding and not sandbox.allow_all_unix_sockets
    policy = sandbox_policy(sandbox, home=tmp_path / "ev", root=tmp_path / "proje")
    assert policy.allow_unix_sockets == (
        tmp_path / "ev" / ".docker/run/docker.sock",
        tmp_path / "proje" / "run/app.sock",
    )
    assert not [r for r in caplog.records if "desteklenmiyor" in r.getMessage()]


def test_seatbelt_kurallari(tmp_path):
    sock = tmp_path / "a.sock"
    only = SandboxPolicy(
        allow_localhost=False, allow_local_binding=True, allow_unix_sockets=(sock,)
    )
    profile = shell_sandbox._darwin_prefix((tmp_path,), only, str(_SANDBOX), None)[-1]
    assert f'(allow network* (remote unix-socket (path-literal "{sock.resolve()}")))' in profile
    assert '(allow network-bind network-inbound (local ip "localhost:*"))' in profile
    assert '(remote ip "localhost:*")' not in profile
    every = SandboxPolicy(allow_all_unix_sockets=True)
    assert (
        "(allow network* (remote unix-socket))"
        in shell_sandbox._darwin_prefix((tmp_path,), every, str(_SANDBOX), None)[-1]
    )


def test_bwrap_ve_socat_yolu_ayardan(tmp_path, monkeypatch):
    seen: list[str] = []
    monkeypatch.setattr(linux_sandbox_tools.shutil, "which", lambda name: seen.append(name) or None)
    shell_sandbox.plan_shell_sandbox(
        "write_root",
        (tmp_path,),
        policy=SandboxPolicy(bwrap_path="/opt/bwrap", socat_path="/opt/socat"),
        platform="linux",
    )
    assert seen == ["/opt/bwrap", "/opt/socat", "rg"]


def _serve(path: Path) -> socket.socket:
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(path))
    server.listen(4)

    def accept() -> None:
        while True:
            try:
                conn, _ = server.accept()
            except OSError:
                return
            conn.sendall(b"ok")
            conn.close()

    threading.Thread(target=accept, daemon=True).start()
    return server


@pytest.mark.skipif(sys.platform != "darwin" or not _SANDBOX.exists(), reason="Seatbelt yok")
def test_gercek_sandboxta_unix_soket_yalniz_izinliyse_baglanir(tmp_path):
    import tempfile

    folder = Path(tempfile.mkdtemp(prefix="fs", dir="/tmp"))  # AF_UNIX yol uzunluğu sınırı
    sock = folder / "s.sock"
    server = _serve(sock)
    python = shutil.which("python3") or sys.executable
    code = (
        "import socket,sys;s=socket.socket(socket.AF_UNIX);"
        f"s.connect({str(sock)!r});sys.stdout.write(s.recv(2).decode())"
    )
    try:
        for policy, expected in (
            (SandboxPolicy(allow_localhost=False), False),
            (SandboxPolicy(allow_localhost=False, allow_unix_sockets=(sock,)), True),
        ):
            prefix = shell_sandbox._darwin_prefix((tmp_path,), policy, str(_SANDBOX), None)
            result = subprocess.run(
                [*prefix, python, "-c", code], capture_output=True, text=True, timeout=30
            )
            assert (result.stdout == "ok") is expected, result.stderr
    finally:
        server.close()
        shutil.rmtree(folder, ignore_errors=True)
