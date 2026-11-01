"""Sandbox'ın belgede "bilinen sınır" olarak kalan dört maddesi (P-010, 1 Kasım).

Ölçüldü (1 Kasım, eca48854):
- `sandbox.deny_read` yazan kullanıcının listesi varsayılanın YERİNE geçiyordu: tek bir yol
  ekleyen `~/.ssh`, `~/.aws`… korumasını sessizce kaybediyordu.
- Ağ proxy'si politika başına süreç boyunca paylaşılıyordu: eşzamanlı iki komutun
  engellenen adları birbirinin notuna düşüyor, politika değişince eski proxy kapanmıyordu.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest

from fusion_cli.cli.sandbox_view import format_status
from fusion_cli.config.sandbox_admin import sandbox_status
from fusion_cli.config.sandbox_config import (
    DEFAULT_DENY_READ,
    SandboxConfig,
    sandbox_policy,
    validate_sandbox,
)
from fusion_cli.core import shell_sandbox
from fusion_cli.core.errors import ConfigError
from fusion_cli.core.sandbox_policy import SandboxPolicy
from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import sandbox_runtime, shell
from fusion_cli.tools.jobs import job_status
from tests.fakes import make_config

# --- inceleme-8: okuma engeli varsayılanı her zaman uygulanır --------------- #


def test_kullanicinin_okuma_engeli_varsayilani_ezmez_eklenir(tmp_path):
    ev = tmp_path / "ev"
    config = validate_sandbox(SandboxConfig(deny_read=("~/ozel",)))

    policy = sandbox_policy(config, home=ev, root=tmp_path)

    assert ev / "ozel" in policy.deny_read
    assert ev / ".ssh" in policy.deny_read and ev / ".aws" in policy.deny_read


def test_allow_read_varsayilandan_yolu_bilerek_cikarir(tmp_path):
    ev = tmp_path / "ev"
    config = validate_sandbox(SandboxConfig(allow_read=("~/.kube/",)))

    policy = sandbox_policy(config, home=ev, root=tmp_path, extra_deny=(tmp_path / "kasa",))

    assert ev / ".kube" not in policy.deny_read
    assert ev / ".ssh" in policy.deny_read and tmp_path / "kasa" in policy.deny_read


def test_allow_read_listede_olmayan_yolu_reddeder():
    with pytest.raises(ConfigError, match=r"sandbox\.allow_read"):
        validate_sandbox(SandboxConfig(allow_read=("~/.sshh",)))


def test_allow_read_kullanicinin_ekledigi_yolu_da_cikarabilir(tmp_path):
    config = validate_sandbox(SandboxConfig(deny_read=("~/ozel",), allow_read=("$HOME/ozel",)))
    policy = sandbox_policy(config, home=tmp_path, root=tmp_path)
    assert tmp_path / "ozel" not in policy.deny_read


def test_durum_etkin_okuma_engelini_ve_cikarilanlari_gosterir(tmp_path):
    sandbox = validate_sandbox(SandboxConfig(deny_read=("~/ozel",), allow_read=("~/.kube",)))
    status = sandbox_status(replace(make_config(), sandbox=sandbox), tmp_path, platform="win32")

    assert "~/ozel" in status.deny_read and "~/.ssh" in status.deny_read
    assert "~/.kube" not in status.deny_read
    assert status.allow_read == ("~/.kube",)
    assert status.as_dict()["okuma_izni"] == ["~/.kube"]
    assert "Okuma izni   : ~/.kube" in format_status(status)


def test_varsayilan_okuma_engeli_tek_kaynakta_ve_eski_yollari_kapsar():
    for yol in ("~/.ssh", "~/.aws", "~/.config/gh", "~/.pypirc", "~/Library/Keychains"):
        assert yol in DEFAULT_DENY_READ
    assert SandboxConfig().deny_read == () and SandboxConfig().allow_read == ()


def _yukle(tmp_path: Path, metin: str):
    from fusion_cli.config.loader import load_config

    yol = tmp_path / "config.yaml"
    yol.write_text(metin, encoding="utf-8")
    return load_config(yol)


def test_eski_tam_liste_yazan_yapilandirma_ayni_engeli_uretir(tmp_path):
    satirlar = "".join(f"    - '{yol}'\n" for yol in DEFAULT_DENY_READ)
    config = _yukle(tmp_path, f"sandbox:\n  deny_read:\n{satirlar}")
    policy = sandbox_policy(config.sandbox, home=tmp_path, root=tmp_path)
    assert len(policy.deny_read) == len(DEFAULT_DENY_READ)


# --- inceleme-11: proxy komut başına; sahibi bitince kapanır ------------------ #

_ALLOWLIST = SandboxPolicy(network="allowlist", allowed_domains=("izinli.test",))


def _ctx(root: Path, policy: SandboxPolicy = _ALLOWLIST) -> ToolContext:
    return ToolContext(root=root, shell_sandbox="write_root", sandbox_policy=policy)


def _connect_reddi(proxy, host: str) -> None:
    """Proxy'ye izinsiz bir ad için CONNECT gönder (yalnız TCP uçlu proxy)."""
    with socket.create_connection(("127.0.0.1", proxy.port), timeout=5) as baglanti:
        baglanti.sendall(f"CONNECT {host}:443 HTTP/1.1\r\nHost: {host}\r\n\r\n".encode())
        baglanti.recv(4096)


@pytest.fixture
def tcp_proxy(monkeypatch):
    """Proxy'yi platformdan bağımsız TCP uçla kur (Linux'ta da port üzerinden sınanır)."""
    monkeypatch.setattr(sandbox_runtime, "_uses_unix_proxy", lambda: False)
    monkeypatch.setattr(shell_sandbox, "_temporary_directories", lambda: ())


def test_eszamanli_komutlarin_ag_retleri_birbirine_karismaz(tmp_path, tcp_proxy):
    birinci = sandbox_runtime.prepare_sandbox("curl a", {}, _ctx(tmp_path))
    ikinci = sandbox_runtime.prepare_sandbox("curl b", {}, _ctx(tmp_path))
    try:
        assert birinci.proxy is not None and ikinci.proxy is not None
        assert birinci.proxy is not ikinci.proxy
        _connect_reddi(birinci.proxy, "kotu.test")

        assert any("kotu.test" in not_ for not_ in sandbox_runtime.sandbox_notes(birinci, 1, ""))
        assert not any("kotu.test" in not_ for not_ in sandbox_runtime.sandbox_notes(ikinci, 1, ""))
    finally:
        sandbox_runtime.release_sandbox(birinci)
        sandbox_runtime.release_sandbox(ikinci)


def test_birakilan_proxy_kapanir_ve_ikinci_birakma_zararsiz(tmp_path, tcp_proxy):
    run = sandbox_runtime.prepare_sandbox("curl a", {}, _ctx(tmp_path))
    assert run.proxy is not None and run.proxy.is_running
    port = run.proxy.port

    sandbox_runtime.release_sandbox(run)
    sandbox_runtime.release_sandbox(run)

    assert not run.proxy.is_running
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", port), timeout=1).close()


def test_unix_soketli_proxy_birakilinca_gecici_dizini_de_siler(tmp_path, monkeypatch):
    monkeypatch.setattr(sandbox_runtime, "_uses_unix_proxy", lambda: True)
    run = sandbox_runtime.prepare_sandbox("curl a", {}, _ctx(tmp_path))
    assert run.proxy is not None and run.proxy.unix_path is not None
    klasor = run.proxy.unix_path.parent
    assert klasor.is_dir()

    sandbox_runtime.release_sandbox(run)

    assert not klasor.exists()


class _Casus:
    """`shell.prepare_sandbox` çağrılarını kaydeden sarmal."""

    def __init__(self) -> None:
        self.runs: list[sandbox_runtime.SandboxRun] = []

    def __call__(self, command, args, context):
        run = sandbox_runtime.prepare_sandbox(command, args, context)
        self.runs.append(run)
        return run


def _bekle(kosul, sure_s: float = 10.0) -> bool:
    bitis = time.monotonic() + sure_s
    while time.monotonic() < bitis:
        if kosul():
            return True
        time.sleep(0.05)
    return kosul()


def test_on_plan_komutunun_proxysi_komut_bitince_kapanir(tmp_path, tcp_proxy, monkeypatch):
    casus = _Casus()
    monkeypatch.setattr(shell, "prepare_sandbox", casus)

    sonuc = shell.run_shell({"command": "echo merhaba"}, _ctx(tmp_path))

    assert "merhaba" in sonuc.output
    (run,) = casus.runs
    assert run.proxy is not None and not run.proxy.is_running


def test_arka_plan_isinin_proxysi_is_bitene_kadar_yasar_sonra_kapanir(
    tmp_path, tcp_proxy, monkeypatch
):
    casus = _Casus()
    monkeypatch.setattr(shell, "prepare_sandbox", casus)
    monkeypatch.setattr(sandbox_runtime, "plan_shell_sandbox", _sandboxsiz_plan)
    context = _ctx(tmp_path)
    tetik = tmp_path / "bitir"

    basladi = shell.run_shell(
        {"command": f"while [ ! -f {tetik} ]; do sleep 0.05; done", "background": True}, context
    )
    (run,) = casus.runs
    kimlik = basladi.output.split("Arka plan işi başladı: ")[1].split()[0]

    assert run.proxy is not None and run.proxy.is_running
    _connect_reddi(run.proxy, "kotu.test")
    tetik.write_text("x")
    job_status({"id": kimlik, "wait_s": 10}, context)

    assert _bekle(lambda: not run.proxy.is_running)
    gunluk = tmp_path / ".fusion" / "is" / f"{kimlik}.log"
    assert _bekle(lambda: "Sandbox ağı engelledi: kotu.test" in gunluk.read_text())


def _sandboxsiz_plan(*args, **kwargs):
    """Gerçek plan + önek boş: komut her platformda sandbox'sız koşar, proxy yine kurulur."""
    plan = shell_sandbox.plan_shell_sandbox(*args, **kwargs)
    return replace(plan, prefix=("env",))


def test_ret_kaydi_ham_ad_tutmaz(tmp_path, tcp_proxy):
    run = sandbox_runtime.prepare_sandbox("curl a", {}, _ctx(tmp_path))
    try:
        assert run.proxy is not None
        _connect_reddi(run.proxy, "Kotu.TEST.")
        _connect_reddi(run.proxy, "talimat:sil")
        assert [item.host for item in run.proxy.denials_since(0)] == ["kotu.test", ""]
    finally:
        sandbox_runtime.release_sandbox(run)


# --- inceleme-6: Fusion tarayıcısının CDP portu sandbox'a kapalı ---------------- #


def _cdp_dosyasi(veri: Path, port: int, saglayici: str = "gemini_web") -> Path:
    profil = veri / "fusion-cli" / "web_profiles" / saglayici / "main"
    profil.mkdir(parents=True)
    dosya = profil / "DevToolsActivePort"
    dosya.write_text(f"{port}\n/devtools/browser/abc\n", encoding="utf-8")
    return dosya


def test_fusion_web_profillerinin_canli_cdp_portlari_okunur(tmp_path, monkeypatch):
    from fusion_cli.tools.sandbox_cdp import fusion_debug_ports

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.delenv("FUSION_WORKSPACE_ISOLATION", raising=False)
    _cdp_dosyasi(tmp_path, 41234)
    _cdp_dosyasi(tmp_path, 41235, "chatgpt_web")
    bozuk = _cdp_dosyasi(tmp_path, 1, "bozuk")
    bozuk.write_text("port-degil\n")

    assert fusion_debug_ports() == (41234, 41235)


@pytest.mark.parametrize("ag", ["open", "allowlist"])
def test_seatbelt_profili_cdp_portunu_localhost_izninden_sonra_kapatir(tmp_path, ag):
    policy = SandboxPolicy(network=ag, denied_local_ports=(41234,))
    plan = shell_sandbox.plan_shell_sandbox(
        "write_root", (tmp_path,), policy=policy, platform="darwin", executable="/bin/sh"
    )
    profil = plan.prefix[-1]
    kural = '(deny network-outbound (remote ip "localhost:41234"))'
    assert kural in profil
    if ag == "allowlist":
        assert profil.index('(allow network* (remote ip "localhost:*"))') < profil.index(kural)


def test_proxy_acikca_izinli_localhostta_bile_cdp_portuna_baglanmaz():
    from fusion_cli.core.sandbox_proxy import DomainProxy

    dinleyici = socket.socket()
    dinleyici.bind(("127.0.0.1", 0))
    dinleyici.listen()
    port = dinleyici.getsockname()[1]
    policy = SandboxPolicy(network="allowlist", allowed_domains=("127.0.0.1",))
    engelli: set[int] = set()
    proxy = DomainProxy(policy, blocked_ports=lambda: engelli)
    proxy.start()
    try:

        def baglan() -> bytes:
            with socket.create_connection(("127.0.0.1", proxy.port), timeout=5) as baglanti:
                baglanti.sendall(f"CONNECT 127.0.0.1:{port} HTTP/1.1\r\n\r\n".encode())
                return baglanti.recv(4096)

        assert b"200" in baglan()
        engelli.add(port)  # tarayıcı komut başladıktan SONRA açıldı: proxy yine görür
        cevap = baglan()
        assert b"403" in cevap and "hata ayıklama".encode() in cevap
    finally:
        proxy.close()
        dinleyici.close()


def test_linux_open_kipinde_cdp_korumasi_olmadigini_durum_soyler(tmp_path):
    from fusion_cli.config.sandbox_admin import debug_port_guard

    assert "korunmaz" in debug_port_guard("linux", "open")
    assert "ad alanı" in debug_port_guard("linux", "allowlist")
    assert "her kipte" in debug_port_guard("darwin", "open")
    assert debug_port_guard("win32", "open") == ""
    # Varsayılan ağ proxy'li (Claude, #323): Linux'ta komut ayrı ağ ad alanında.
    durum = sandbox_status(make_config(), tmp_path, platform="linux")
    assert "kapalı (komut ayrı ağ ad alanında" in format_status(durum)
    assert durum.as_dict()["cdp_korumasi"] == durum.debug_ports


# --- inceleme-5: başka süreçlerin ortamı ------------------------------------- #

_PROCARGS_PROBE = """
import ctypes, ctypes.util, sys
libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
mib = (ctypes.c_int * 3)(1, 49, int(sys.argv[1]))  # CTL_KERN, KERN_PROCARGS2, pid
size = ctypes.c_size_t(1 << 20)
buf = ctypes.create_string_buffer(size.value)
if libc.sysctl(mib, 3, buf, ctypes.byref(size), None, 0) != 0:
    print("ENGEL", ctypes.get_errno())
else:
    raw = buf.raw[: size.value]
    print("BASLANGIC" if b"SAHTE_BASLANGIC_" + b"DEGERI" in raw else "-",
          "SONRADAN" if b"SAHTE_SONRADAN_" + b"DEGERI" in raw else "-")
"""


def _seatbelt_calisir() -> bool:
    sandbox_exec = Path("/usr/bin/sandbox-exec")
    if sys.platform != "darwin" or not sandbox_exec.exists():
        return False
    probe = subprocess.run(
        [str(sandbox_exec), "-p", "(version 1)(allow default)", "/usr/bin/true"],
        capture_output=True,
        check=False,
    )
    return probe.returncode == 0


@pytest.mark.skipif(not _seatbelt_calisir(), reason="sandbox-exec kullanılamıyor")
def test_macos_seatbelt_baska_surecin_baslangic_ortamini_kesemez_olcum(tmp_path, monkeypatch):
    """Kanarya ölçüm (1 Kasım, Darwin 27): Fusion profiliyle de okunur; belge bunu söyler.

    Ayrıca denendi, hiçbiri kesmedi: `(deny process-info*)` (+ `target self/same-sandbox`),
    `(deny sysctl-read)`, `(deny sysctl*)`, `sysctl-name "kern.procargs2"`, hatta yalnız
    `process-exec` + `file-read*` izinli `(deny default)`. Bu test düşerse Seatbelt bir
    kanca kazanmıştır: profile kuralı ekleyip docs/SANDBOX.md'yi güncelle. Süreç başladıktan
    sonra ortama eklenen değer (Fusion'ın .env/kasa sırları) görünmez.
    """
    monkeypatch.setattr(shell_sandbox, "_temporary_directories", lambda: ())
    hedef = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import os, time\nos.environ['SAHTE_SONRADAN'] = 'SAHTE_SONRADAN_' + 'DEGERI'\n"
            "print('hazir', flush=True)\ntime.sleep(30)",
        ],
        env={**os.environ, "SAHTE_BASLANGIC": "SAHTE_BASLANGIC_" + "DEGERI"},
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert hedef.stdout is not None and hedef.stdout.readline().strip() == "hazir"
        plan = shell_sandbox.plan_shell_sandbox("write_root", (tmp_path,))
        olcum = subprocess.run(
            [*plan.prefix, sys.executable, "-I", "-c", _PROCARGS_PROBE, str(hedef.pid)],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    finally:
        hedef.kill()
        hedef.wait()
    assert olcum.stdout.split() == ["BASLANGIC", "-"], olcum.stderr


def test_linux_sandbox_kendi_proc_ve_pid_ad_alanini_gorur(tmp_path):
    """Linux'ta kapalı (24382541): yeni PID ad alanı + üstüne bağlanan taze procfs."""
    from fusion_cli.core.shell_sandbox_linux import LinuxTools

    plan = shell_sandbox.plan_shell_sandbox(
        "write_root", (tmp_path,), platform="linux", linux_tools=LinuxTools("/usr/bin/bwrap")
    )
    argv = list(plan.prefix)
    assert "--unshare-pid" in argv
    assert argv[argv.index("--proc") + 1] == "/proc"
    assert argv.index("--ro-bind") < argv.index("--proc")
