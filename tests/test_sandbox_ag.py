"""Sandbox ağ allowlist'i (P-010): alan adı proxy'si ve macOS'ta uçtan uca `run_shell`.

Ölçüldü (31 Ekim, e30d57a0): `write_root` açıkken komut her adrese bağlanabiliyordu;
ağ kısıtı yoktu. Testler gerçek internete çıkmaz: yerel HTTP sunucusu ve sahte çözücü.
"""

from __future__ import annotations

import http.server
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from fusion_cli.core import sandbox_proxy, shell_sandbox
from fusion_cli.core.sandbox_policy import SandboxPolicy
from fusion_cli.core.sandbox_proxy import DomainProxy
from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import shell

_SANDBOX_EXEC = Path("/usr/bin/sandbox-exec")


def _sandbox_calisir() -> bool:
    if sys.platform != "darwin" or not _SANDBOX_EXEC.exists() or shutil.which("curl") is None:
        return False
    probe = subprocess.run(
        [str(_SANDBOX_EXEC), "-p", "(version 1)(allow default)", "/usr/bin/true"],
        capture_output=True,
        check=False,
    )
    return probe.returncode == 0


macos_sandbox = pytest.mark.skipif(not _sandbox_calisir(), reason="sandbox-exec/curl yok")


class _Cevap(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = b"yerel-sunucu"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


@pytest.fixture
def sunucu() -> Iterator[int]:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Cevap)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield int(server.server_address[1])
    server.shutdown()
    server.server_close()


def _proxy(policy: SandboxPolicy, resolver=None) -> DomainProxy:
    proxy = DomainProxy(policy, resolver=resolver or (lambda host, port: ["127.0.0.1"]))
    proxy.start()
    return proxy


def _istek(port: int, text: str) -> bytes:
    with socket.create_connection(("127.0.0.1", port), timeout=5) as baglanti:
        baglanti.sendall(text.encode())
        parcalar = []
        while True:
            parca = baglanti.recv(65536)
            if not parca:
                break
            parcalar.append(parca)
    return b"".join(parcalar)


# --- proxy ------------------------------------------------------------------- #


def test_izinsiz_alan_adi_403_ve_ret_kaydi(sunucu):
    proxy = _proxy(SandboxPolicy(network="allowlist", allowed_domains=("izinli.test",)))
    try:
        isaret = proxy.mark()
        cevap = _istek(proxy.port, "CONNECT kotu.test:443 HTTP/1.1\r\nHost: kotu.test\r\n\r\n")
        assert cevap.startswith(b"HTTP/1.1 403") and b"kotu.test" in cevap
        assert [item.host for item in proxy.denials_since(isaret)] == ["kotu.test"]
        assert proxy.denials_since(proxy.mark()) == []
    finally:
        proxy.close()


def test_izinli_ad_ic_aga_cozulurse_reddedilir(sunucu):
    """DNS yeniden bağlama: allowlist'teki ad 127.0.0.1'e çözülürse iç ağa sızılmaz."""
    proxy = _proxy(SandboxPolicy(network="allowlist", allowed_domains=("izinli.test",)))
    try:
        cevap = _istek(
            proxy.port, f"GET http://izinli.test:{sunucu}/ HTTP/1.1\r\nHost: izinli.test\r\n\r\n"
        )
        assert cevap.startswith(b"HTTP/1.1 403") and "iç ağ".encode() in cevap
    finally:
        proxy.close()


def test_acikca_yazilmis_ip_ic_aga_gidebilir_duz_http(sunucu):
    proxy = _proxy(SandboxPolicy(network="allowlist", allowed_domains=("127.0.0.1",)))
    try:
        cevap = _istek(
            proxy.port,
            f"GET http://127.0.0.1:{sunucu}/yol HTTP/1.1\r\nHost: x\r\n"
            "Proxy-Authorization: gizli\r\nConnection: close\r\n\r\n",
        )
        assert cevap.startswith(b"HTTP/1.0 200") and cevap.endswith(b"yerel-sunucu")
    finally:
        proxy.close()


def test_genel_adrese_cozulen_izinli_ad_connect_ile_tunellenir(sunucu, monkeypatch):
    """Genel IP'ye çözülen ad: bağlantı DENETLENEN adrese yapılır (ad yeniden çözülmez)."""
    hedefler: list[tuple[str, int]] = []
    gercek = socket.create_connection

    def yonlendir(address, timeout=None):
        hedefler.append(address)
        return gercek(("127.0.0.1", sunucu), timeout=timeout)

    monkeypatch.setattr(sandbox_proxy.socket, "create_connection", yonlendir)
    proxy = _proxy(
        SandboxPolicy(network="allowlist", allowed_domains=("*.ornek.test",)),
        resolver=lambda host, port: ["93.184.216.34"],
    )
    try:
        with gercek(("127.0.0.1", proxy.port), timeout=5) as baglanti:
            baglanti.sendall(b"CONNECT api.ornek.test:443 HTTP/1.1\r\n\r\n")
            assert baglanti.recv(1024).startswith(b"HTTP/1.1 200")
            baglanti.sendall(b"GET / HTTP/1.1\r\nHost: a\r\nConnection: close\r\n\r\n")
            veri = b""
            while chunk := baglanti.recv(65536):
                veri += chunk
        assert veri.endswith(b"yerel-sunucu")
        assert hedefler == [("93.184.216.34", 443)]
    finally:
        proxy.close()


def test_unix_soketli_proxy_dinler_ve_kapaninca_soketi_siler():
    # macOS AF_UNIX yol sınırı ~104 bayt: pytest'in tmp_path'i fazla uzun.
    klasor = Path(tempfile.mkdtemp(prefix="sbx", dir="/tmp"))
    yol = klasor / "p.sock"
    proxy = DomainProxy(SandboxPolicy(network="allowlist"), unix_path=yol)
    proxy.start()
    assert yol.exists() and proxy.port == 0
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as baglanti:
        baglanti.connect(str(yol))
        baglanti.sendall(b"CONNECT x.test:443 HTTP/1.1\r\n\r\n")
        assert baglanti.recv(1024).startswith(b"HTTP/1.1 403")
    proxy.close()
    assert not yol.exists()
    klasor.rmdir()


# --- uçtan uca (macOS) ------------------------------------------------------- #


def _context(root: Path, policy: SandboxPolicy) -> ToolContext:
    return ToolContext(root=root, shell_sandbox="write_root", sandbox_policy=policy)


@macos_sandbox
def test_allowlist_proxy_uzerinden_izinliye_gider_dogrudan_baglanti_engellenir(
    tmp_path, sunucu, monkeypatch
):
    monkeypatch.setattr(shell_sandbox, "_temporary_directories", lambda: ())
    policy = SandboxPolicy(
        network="allowlist", allowed_domains=("127.0.0.1",), allow_localhost=False
    )
    context = _context(tmp_path, policy)
    adres = f"http://127.0.0.1:{sunucu}/"

    proxyli = shell.run_shell({"command": f"curl -sS -m 5 {adres}"}, context)
    dogrudan = shell.run_shell({"command": f"curl -sS -m 5 --noproxy '*' {adres}"}, context)
    izinsiz = shell.run_shell({"command": "curl -sS -m 5 -f http://kotu.invalid/"}, context)

    assert proxyli.ok and "yerel-sunucu" in proxyli.output
    assert not dogrudan.ok
    assert not izinsiz.ok and "Sandbox ağı engelledi: kotu.invalid" in izinsiz.output
    assert "/sandbox izin kotu.invalid" in izinsiz.output


@macos_sandbox
def test_bos_allowlistte_localhost_acik_dis_ag_kapali(tmp_path, sunucu, monkeypatch):
    monkeypatch.setattr(shell_sandbox, "_temporary_directories", lambda: ())
    context = _context(tmp_path, SandboxPolicy(network="allowlist"))

    yerel = shell.run_shell({"command": f"curl -sS -m 5 http://127.0.0.1:{sunucu}/"}, context)
    dis = shell.run_shell({"command": "curl -sS -m 5 http://93.184.216.34/"}, context)

    assert yerel.ok and "yerel-sunucu" in yerel.output
    assert not dis.ok and "Sandbox ağı kapalı" in dis.output


@macos_sandbox
@pytest.mark.parametrize("ag", ["open", "allowlist"])
def test_fusion_chrome_cdp_portu_sandboxtan_erisilemez_dev_sunucusu_erisilir(
    tmp_path, sunucu, monkeypatch, ag
):
    """Ölçüldü (1 Kasım): ağ open iken `curl 127.0.0.1:<CDP>` sandbox içinden yanıt alıyordu."""
    monkeypatch.setattr(shell_sandbox, "_temporary_directories", lambda: ())
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "veri"))
    monkeypatch.delenv("FUSION_WORKSPACE_ISOLATION", raising=False)
    cdp = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Cevap)
    threading.Thread(target=cdp.serve_forever, daemon=True).start()
    profil = tmp_path / "veri" / "fusion-cli" / "web_profiles" / "gemini_web" / "main"
    profil.mkdir(parents=True)
    (profil / "DevToolsActivePort").write_text(f"{cdp.server_address[1]}\n/devtools/browser/x\n")
    proje = tmp_path / "proje"
    proje.mkdir()
    context = _context(proje, SandboxPolicy(network=ag))
    try:
        tarayici = shell.run_shell(
            {"command": f"curl -sS -m 5 --noproxy '*' http://127.0.0.1:{cdp.server_address[1]}/"},
            context,
        )
        gelistirme = shell.run_shell(
            {"command": f"curl -sS -m 5 --noproxy '*' http://127.0.0.1:{sunucu}/"}, context
        )
    finally:
        cdp.shutdown()
        cdp.server_close()
    assert not tarayici.ok and "yerel-sunucu" not in tarayici.output
    assert gelistirme.ok and "yerel-sunucu" in gelistirme.output
