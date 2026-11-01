"""Claude sandbox anahtarları: httpProxyPort, socksProxyPort, filesystem.disabled,
enableWeakerNestedSandbox, allowNestedUserNamespaces, ripgrep, tlsTerminate, mask (#350, #368)."""

from __future__ import annotations

import json
import logging
import os
import shutil
import socket
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from fusion_cli.config import claude_sandbox_settings, sandbox_claude_keys, sandbox_scopes, trust
from fusion_cli.config.claude_sandbox_settings import read_claude_sandbox
from fusion_cli.core import shell_sandbox
from fusion_cli.core.errors import ConfigError
from fusion_cli.core.linux_sandbox_tools import LinuxTools, nested_protected
from fusion_cli.core.sandbox_policy import SandboxPolicy
from fusion_cli.core.shell_sandbox_linux import LINUX_SOCKS_BRIDGE_PORT, linux_sandbox_argv
from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import sandbox_runtime

_SANDBOX = Path("/usr/bin/sandbox-exec")
_SEATBELT = pytest.mark.skipif(
    sys.platform != "darwin" or not _SANDBOX.exists(), reason="Seatbelt yok"
)


@pytest.fixture(autouse=True)
def _uyarilar_sifir(monkeypatch):
    monkeypatch.setattr(sandbox_claude_keys, "_WARNED", set())
    monkeypatch.setattr(claude_sandbox_settings, "_WARNED", set())
    monkeypatch.setattr(sandbox_scopes, "_WARNED", set())


def test_claude_adlari_ic_alanlara_uyarisiz_cevrilir(caplog):
    caplog.set_level(logging.WARNING)
    section, _ = sandbox_claude_keys.normalize_claude_sandbox(
        {
            "enableWeakerNestedSandbox": True,
            "allowNestedUserNamespaces": True,
            "ripgrep": {"command": "/opt/rg", "args": ["--threads", "1"]},
            "filesystem": {"disabled": True},
            "network": {"httpProxyPort": 8080, "socksProxyPort": 1081, "tlsTerminate": {}},
            "credentials": {
                "envVars": [
                    {"name": "GH_TOKEN", "mode": "mask", "injectHosts": ["api.github.com"]},
                    {"name": "NPM_TOKEN", "mode": "mask"},
                    {"name": "AWS_SECRET", "mode": "deny"},
                ],
                "allowPlaintextInject": True,
            },
        }
    )
    assert section["enable_weaker_nested_sandbox"] and section["allow_nested_user_namespaces"]
    assert section["ripgrep_command"] == "/opt/rg" and section["ripgrep_args"] == ["--threads", "1"]
    assert section["filesystem_disabled"] is True
    assert section["http_proxy_port"] == 8080 and section["socks_proxy_port"] == 1081
    assert section["tls_terminate"] is True and section["tls_ca_cert"] == ""
    assert section["credential_mask"] == ["GH_TOKEN=api.github.com", "NPM_TOKEN"]
    assert section["credential_env"] == ["AWS_SECRET"]
    assert section["allow_plaintext_inject"] is True
    assert not [r for r in caplog.records if "desteklenmiyor" in r.getMessage()]


def test_tls_ca_yollari_birlikte_verilmeli():
    with pytest.raises(ConfigError):
        sandbox_claude_keys.normalize_claude_sandbox(
            {"network": {"tlsTerminate": {"caCertPath": "/ca.pem"}}}
        )
    section, _ = sandbox_claude_keys.normalize_claude_sandbox(
        {"network": {"tlsTerminate": {"caCertPath": "/ca.pem", "caKeyPath": "/ca.key"}}}
    )
    assert (section["tls_ca_cert"], section["tls_ca_key"]) == ("/ca.pem", "/ca.key")


def test_proje_ayari_yalitimi_gevsetemez_ve_mask_acamaz(tmp_path, monkeypatch, caplog):
    proje = tmp_path / "proje"
    (proje / ".claude").mkdir(parents=True)
    monkeypatch.chdir(proje)
    sandbox = {
        "allowNestedUserNamespaces": True,
        "ripgrep": {"command": "/kotu/rg"},
        "filesystem": {"disabled": True, "allowWrite": ["/derleme"]},
        "network": {"tlsTerminate": {}, "httpProxyPort": 9000},
        "credentials": {
            "envVars": [{"name": "GH_TOKEN", "mode": "mask"}],
            "allowPlaintextInject": True,
        },
    }
    (proje / ".claude" / "settings.local.json").write_text(
        json.dumps({"sandbox": sandbox}), encoding="utf-8"
    )
    trust.record_permissions_digest(proje)
    caplog.set_level(logging.WARNING)

    section = read_claude_sandbox(proje).section

    for key in (
        "allow_nested_user_namespaces",
        "ripgrep_command",
        "filesystem_disabled",
        "tls_terminate",
        "credential_mask",
        "allow_plaintext_inject",
    ):
        assert key not in section, key
    assert section["allow_write"] == ["/derleme"] and section["http_proxy_port"] == 9000
    assert any("proje ayarında yok sayıldı" in r.getMessage() for r in caplog.records)

    user = Path(os.environ["CLAUDE_CONFIG_DIR"]) / "settings.json"
    user.parent.mkdir(parents=True, exist_ok=True)
    user.write_text(json.dumps({"sandbox": {"filesystem": {"disabled": True}}}), encoding="utf-8")
    assert read_claude_sandbox(proje).section["filesystem_disabled"] is True


def test_seatbelt_dis_proxy_portlari_ve_socks_ortami(tmp_path):
    policy = SandboxPolicy(allow_localhost=False, http_proxy_port=8080, socks_proxy_port=1081)
    endpoint = shell_sandbox.ProxyEndpoint(port=8080, socks_port=1081)

    plan = shell_sandbox.plan_shell_sandbox(
        "write_root", (tmp_path,), policy=policy, platform="darwin", proxy=endpoint
    )

    profile = plan.prefix[-1]
    assert '(allow network-outbound (remote ip "localhost:8080"))' in profile
    assert '(allow network-outbound (remote ip "localhost:1081"))' in profile
    env = dict(plan.env)
    assert env["HTTPS_PROXY"] == "http://127.0.0.1:8080"
    assert env["ALL_PROXY"] == "socks5h://127.0.0.1:1081"

    only_socks = shell_sandbox.plan_shell_sandbox(
        "write_root",
        (tmp_path,),
        policy=SandboxPolicy(socks_proxy_port=1081),
        platform="darwin",
        proxy=shell_sandbox.ProxyEndpoint(socks_port=1081),
    )
    assert dict(only_socks.env)["HTTPS_PROXY"] == "socks5h://127.0.0.1:1081"


def test_dis_proxy_verilince_fusion_proxysi_baslamaz(tmp_path, monkeypatch):
    monkeypatch.setattr(sandbox_runtime, "_uses_unix_proxy", lambda: False)
    policy = SandboxPolicy(allowed_domains=("github.com",), http_proxy_port=8080)
    context = ToolContext(root=tmp_path, shell_sandbox="write_root", sandbox_policy=policy)

    run = sandbox_runtime.prepare_sandbox("curl x", {"command": "curl x"}, context)
    try:
        assert run.proxy is None
        if run.plan.is_active:
            assert dict(run.plan.env)["HTTP_PROXY"] == "http://127.0.0.1:8080"
    finally:
        sandbox_runtime.release_sandbox(run)


def test_linuxta_dis_proxy_unix_aktariciyla_tasinir(tmp_path, monkeypatch):
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]

    def accept() -> None:
        conn, _ = listener.accept()
        conn.sendall(b"proxy")
        conn.close()

    threading.Thread(target=accept, daemon=True).start()
    monkeypatch.setattr(sandbox_runtime, "_uses_unix_proxy", lambda: True)
    run = sandbox_runtime.SandboxRun(plan=shell_sandbox.SandboxPlan(), policy=SandboxPolicy())
    endpoint = sandbox_runtime._external_endpoint(SandboxPolicy(socks_proxy_port=port), run)
    try:
        assert endpoint is not None and endpoint.unix_path is None
        client = socket.socket(socket.AF_UNIX)
        client.connect(str(endpoint.socks_unix_path))
        assert client.recv(5) == b"proxy"
        client.close()
    finally:
        sandbox_runtime.release_sandbox(run)
        listener.close()
    assert not endpoint.socks_unix_path.exists()


@_SEATBELT
def test_gercek_sandboxta_filesystem_disabled_yazar_sirlar_kapali(tmp_path):
    # Geçici dizinler sandbox'ta hep yazılabilir; dış hedef depo içinde açılıp silinir.
    import tempfile

    outside = Path(tempfile.mkdtemp(prefix=".fs-disabled-", dir=Path(__file__).parent))
    try:
        _filesystem_disabled_case(tmp_path, outside)
    finally:
        shutil.rmtree(outside, ignore_errors=True)


def _filesystem_disabled_case(tmp_path: Path, outside: Path) -> None:
    secret = tmp_path / "gizli.txt"
    secret.write_text("x", encoding="utf-8")
    root = tmp_path / "kok"
    (root / ".git").mkdir(parents=True)
    (root / ".git" / "config").write_text("", encoding="utf-8")
    command = (
        f"echo a > {outside}/y && cat {secret} >/dev/null 2>&1; echo okuma=$?;"
        f" echo x >> {root}/.git/config 2>/dev/null; echo git=$?"
    )
    for disabled, expected_write in ((False, False), (True, True)):
        policy = SandboxPolicy(filesystem_disabled=disabled, locked_read=(secret,))
        plan = shell_sandbox.plan_shell_sandbox("write_root", (root,), policy=policy)
        result = subprocess.run(
            [*plan.prefix, "/bin/sh", "-c", command], capture_output=True, text=True, timeout=30
        )
        assert (outside / "y").exists() is expected_write, result.stderr
        assert "okuma=1" in result.stdout and "git=1" in result.stdout


@_SEATBELT
def test_gercek_sandboxta_yalniz_dis_proxy_portuna_baglanir(tmp_path):
    servers = [socket.socket() for _ in range(2)]
    for server in servers:
        server.bind(("127.0.0.1", 0))
        server.listen(4)
    allowed, other = (server.getsockname()[1] for server in servers)
    policy = SandboxPolicy(allow_localhost=False, http_proxy_port=allowed)
    plan = shell_sandbox.plan_shell_sandbox(
        "write_root", (tmp_path,), policy=policy, proxy=shell_sandbox.ProxyEndpoint(port=allowed)
    )
    python = shutil.which("python3") or sys.executable
    code = (
        "import socket,sys\nfor p in sys.argv[1:]:\n try:\n  socket.create_connection("
        "('127.0.0.1',int(p)),2).close();print(p,'ok')\n except OSError:print(p,'red')"
    )
    try:
        result = subprocess.run(
            [*plan.prefix, python, "-c", code, str(allowed), str(other)],
            capture_output=True,
            text=True,
            timeout=30,
        )
    finally:
        for server in servers:
            server.close()
    assert f"{allowed} ok" in result.stdout and f"{other} red" in result.stdout, result.stderr


def test_linux_argv_zayif_ic_ice_kullanici_ad_alani_ve_disabled(tmp_path):
    tools = LinuxTools("/usr/bin/bwrap", "/usr/bin/socat", disable_userns=True)
    sock = tmp_path / "s" / "socks.sock"

    default = linux_sandbox_argv((tmp_path,), SandboxPolicy(), tools).prefix
    assert "--proc" in default and "--disable-userns" in default
    assert default[default.index("/") - 1] == "--ro-bind"

    weaker = SandboxPolicy(
        enable_weaker_nested_sandbox=True,
        allow_nested_user_namespaces=True,
        filesystem_disabled=True,
        deny_write=(tmp_path,),
    )
    loose = linux_sandbox_argv((tmp_path,), weaker, tools, socks_socket=sock).prefix
    assert "--proc" not in loose and "--disable-userns" not in loose
    assert loose[loose.index("/") - 1] == "--bind"
    script = loose[-2]
    assert f"TCP-LISTEN:{LINUX_SOCKS_BRIDGE_PORT}" in script and str(sock) in script

    old_bwrap = linux_sandbox_argv((tmp_path,), SandboxPolicy(), LinuxTools("/b")).prefix
    assert "--disable-userns" not in old_bwrap


def test_ripgrep_ic_ice_korumali_yollari_bulur_ve_salt_okunur_baglar(tmp_path):
    fake = tmp_path / "rg"
    listing = [
        "alt/.git/config",
        "alt/.git/hooks/pre-commit",
        "alt/derin/.claude/settings.json",
        ".git/config",
        ".mcp.json",
    ]
    fake.write_text("#!/bin/sh\nprintf '%s\\n' " + " ".join(listing) + "\n", encoding="utf-8")
    fake.chmod(0o755)
    root = tmp_path / "kok"
    root.mkdir()

    found = nested_protected((str(fake),), (root,))

    assert found == (
        root / "alt/.git/config",
        root / "alt/.git/hooks",
        root / "alt/derin/.claude/settings.json",
    )
    tools = LinuxTools("/usr/bin/bwrap", ripgrep=(str(fake),))
    argv = linux_sandbox_argv((root,), SandboxPolicy(), tools, protected_roots=(root,)).prefix
    assert ("--ro-bind", str(root / "alt/.git/hooks"), str(root / "alt/.git/hooks")) in zip(
        argv, argv[1:], argv[2:], strict=False
    )
    assert nested_protected((), (root,)) == ()


def test_durum_ekrani_ve_masaustu_ek_ayarlari_gosterir(tmp_path):
    from dataclasses import replace

    from fusion_cli.cli.sandbox_view import format_status
    from fusion_cli.config.loader import load_config
    from fusion_cli.config.sandbox_admin import sandbox_status
    from fusion_cli.config.sandbox_config import SandboxConfig

    sandbox = SandboxConfig(
        http_proxy_port=8080, tls_terminate=True, credential_mask=("GH_TOKEN=api.github.com",)
    )
    path = tmp_path / "config.yaml"
    path.write_text("{}\n", encoding="utf-8")
    status = sandbox_status(replace(load_config(path), sandbox=sandbox), tmp_path)

    text = format_status(status)
    assert "httpProxyPort" in text and "HTTP 8080" in text
    assert "tlsTerminate" in text and "GH_TOKEN" in text
    assert any("mask" in item for item in status.as_dict()["ek_ayarlar"])
