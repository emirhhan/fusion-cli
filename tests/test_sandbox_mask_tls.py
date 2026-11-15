"""Claude `credentials.envVars` mode: mask + `network.tlsTerminate` + `allowPlaintextInject`.

Komut gerçek değer yerine aynı uzunlukta bir yer tutucu görür; sandbox proxy'si izinli adlara
giden istekte gerçek değeri koyar, yanıtta geri çevirir (#350, #368).
"""

from __future__ import annotations

import datetime
import http.server
import ipaddress
import json
import shutil
import ssl
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path
from typing import ClassVar

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from fusion_cli.config.sandbox_config import SandboxConfig, sandbox_policy
from fusion_cli.core.sandbox_policy import SandboxPolicy
from fusion_cli.core.sandbox_proxy import DomainProxy
from fusion_cli.core.sandbox_tls import Injection, StreamReplacer, injections_for
from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import sandbox_ca, sandbox_runtime
from fusion_cli.tools.sandbox_mask import apply_masks

_SANDBOX = Path("/usr/bin/sandbox-exec")
TOKEN = "ghp_GERCEKdeger1234567890abcdef"


def test_akista_bolunen_yer_tutucu_degisir_yarim_eslesme_bekletilir():
    replacer = StreamReplacer([(b"SENTINEL", b"gercek!!")])
    out = replacer.feed(b"Authorization: Bearer SENT")
    assert out == b"Authorization: Bearer " and replacer.holding
    out += replacer.feed(b"INEL\r\n\r\n")
    assert out == b"Authorization: Bearer gercek!!\r\n\r\n" and not replacer.holding
    assert replacer.feed(b"son S") == b"son " and replacer.flush() == b"S"


def test_yer_tutucu_ayni_bayt_uzunlugunda_kararli_ve_hedefler_izinli_adlarla_sinirli():
    policy = SandboxPolicy(
        allowed_domains=("api.github.com", "*.npmjs.org"),
        mask_env=("GH_TOKEN=api.github.com,kotu.example", "NPM_TOKEN", "YOK"),
    )
    env = {"GH_TOKEN": TOKEN, "NPM_TOKEN": "çok-gizli", "PATH": "/bin"}

    masked, injections = apply_masks(env, policy)
    again, _ = apply_masks(env, policy)

    assert masked["GH_TOKEN"] != TOKEN and len(masked["GH_TOKEN"]) == len(TOKEN)
    assert masked["GH_TOKEN"].startswith("FUSIONMASK") and again == masked
    assert len(masked["NPM_TOKEN"].encode()) == len("çok-gizli".encode())
    assert masked["PATH"] == "/bin" and "YOK" not in masked
    gh, npm = injections
    assert gh.hosts == ("api.github.com",) and npm.hosts == policy.allowed_domains
    assert injections_for("api.github.com", injections) == (gh, npm)
    assert injections_for("registry.npmjs.org", injections) == (npm,)
    assert injections_for("kotu.example", injections) == ()


def test_ayni_ad_deny_ve_maskte_ise_deny_uygulanir(tmp_path):
    config = SandboxConfig(credential_env=("GH_TOKEN",), credential_mask=("GH_TOKEN", "B"))
    policy = sandbox_policy(config, home=tmp_path, root=tmp_path)
    assert policy.mask_env == ("B",) and policy.deny_env == ("GH_TOKEN",)


def _self_signed(folder: Path) -> tuple[Path, Path]:
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1")])
    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(hours=1))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    cert_path, key_path = folder / "up.pem", folder / "up.key"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return cert_path, key_path


class _Echo(http.server.BaseHTTPRequestHandler):
    seen: ClassVar[list[str]] = []

    def do_GET(self) -> None:
        auth = self.headers.get("Authorization", "")
        type(self).seen.append(auth)
        body = json.dumps({"auth": auth}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        return


def _upstream(tls: tuple[Path, Path] | None) -> http.server.ThreadingHTTPServer:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Echo)
    if tls is not None:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(*tls)
        server.socket = context.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _trusting(ca: sandbox_ca.SessionCa, upstream_cert: Path) -> None:
    def upstream_context() -> ssl.SSLContext:
        context = ssl.create_default_context(cafile=str(upstream_cert))
        context.set_alpn_protocols(["http/1.1"])
        return context

    ca.upstream_context = upstream_context  # type: ignore[method-assign]


def test_tls_sonlandirilir_istekte_gercek_deger_yanitta_yer_tutucu(tmp_path):
    _Echo.seen = []
    upstream_tls = _self_signed(tmp_path)
    server = _upstream(upstream_tls)
    ca = sandbox_ca.SessionCa()
    _trusting(ca, upstream_tls[0])
    sentinel = "S" * len(TOKEN)
    proxy = DomainProxy(SandboxPolicy(allowed_domains=("127.0.0.1",)), tls=ca)
    proxy.set_injections((Injection(sentinel.encode(), TOKEN.encode(), ("127.0.0.1",)),))
    proxy.start()
    try:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"https": f"http://127.0.0.1:{proxy.port}"}),
            urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile=ca.cert_path)),
        )
        request = urllib.request.Request(
            f"https://127.0.0.1:{server.server_address[1]}/",
            headers={"Authorization": f"Bearer {sentinel}"},
        )
        body = json.loads(opener.open(request, timeout=15).read())
    finally:
        proxy.close()
        server.shutdown()
    assert _Echo.seen == [f"Bearer {TOKEN}"]
    assert body == {"auth": f"Bearer {sentinel}"}


@pytest.mark.parametrize(("plaintext", "expected"), [(True, TOKEN), (False, "P" * len(TOKEN))])
def test_duz_httpde_yalniz_allow_plaintext_inject_ile_yerine_konur(plaintext, expected):
    _Echo.seen = []
    server = _upstream(None)
    sentinel = "P" * len(TOKEN)
    proxy = DomainProxy(SandboxPolicy(allowed_domains=("127.0.0.1",)), plaintext_inject=plaintext)
    proxy.set_injections((Injection(sentinel.encode(), TOKEN.encode(), ("127.0.0.1",)),))
    proxy.start()
    try:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": f"http://127.0.0.1:{proxy.port}"})
        )
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_address[1]}/",
            headers={"Authorization": f"Bearer {sentinel}"},
        )
        body = json.loads(opener.open(request, timeout=15).read())
    finally:
        proxy.close()
        server.shutdown()
    assert _Echo.seen == [f"Bearer {expected}"]
    assert body["auth"] == f"Bearer {sentinel}"


def test_sandbox_ortami_yer_tutucu_ve_ca_guveni_alir_anahtar_dizini_okunamaz(tmp_path, monkeypatch):
    monkeypatch.setattr(sandbox_runtime, "_uses_unix_proxy", lambda: False)
    policy = SandboxPolicy(
        allowed_domains=("api.github.com",), mask_env=("GH_TOKEN",), tls_terminate=True
    )
    context = ToolContext(root=tmp_path, shell_sandbox="write_root", sandbox_policy=policy)
    run = sandbox_runtime.prepare_sandbox("gh api user", {"command": "gh api user"}, context)
    try:
        if not run.plan.is_active:
            pytest.skip("sandbox bu platformda kurulamıyor")
        env = sandbox_runtime.sandbox_env({"GH_TOKEN": TOKEN, "PATH": "/bin"}, run)
        assert env["GH_TOKEN"] != TOKEN and len(env["GH_TOKEN"]) == len(TOKEN)
        assert run.tls is not None and env["SSL_CERT_FILE"] == str(run.tls.bundle_path)
        assert env["NODE_EXTRA_CA_CERTS"] == str(run.tls.cert_path)
        assert run.tls.private_dir in run.policy.locked_read
    finally:
        sandbox_runtime.release_sandbox(run)


def test_tls_ve_ca_yoksa_mask_yine_yer_tutucu_verir(tmp_path, monkeypatch):
    monkeypatch.setattr(sandbox_runtime, "_uses_unix_proxy", lambda: False)
    policy = SandboxPolicy(
        allowed_domains=("api.github.com",),
        mask_env=("GH_TOKEN",),
        tls_terminate=True,
        tls_ca_cert=str(tmp_path / "yok.pem"),
        tls_ca_key=str(tmp_path / "yok.key"),
    )
    context = ToolContext(root=tmp_path, shell_sandbox="write_root", sandbox_policy=policy)
    run = sandbox_runtime.prepare_sandbox("true", {"command": "true"}, context)
    try:
        if not run.plan.is_active:
            pytest.skip("sandbox bu platformda kurulamıyor")
        env = sandbox_runtime.sandbox_env({"GH_TOKEN": TOKEN}, run)
        assert env["GH_TOKEN"] != TOKEN and run.tls is None
        assert any("TLS sonlandırma kullanılamıyor" in item for item in run.notices)
    finally:
        sandbox_runtime.release_sandbox(run)


@pytest.mark.skipif(sys.platform != "darwin" or not _SANDBOX.exists(), reason="Seatbelt yok")
def test_gercek_sandboxta_komut_yer_tutucuyla_kimlik_dogrular(tmp_path, monkeypatch):
    _Echo.seen = []
    upstream_tls = _self_signed(tmp_path)
    server = _upstream(upstream_tls)
    original = sandbox_ca.SessionCa.upstream_context

    def upstream_context(self: sandbox_ca.SessionCa) -> ssl.SSLContext:
        context = ssl.create_default_context(cafile=str(upstream_tls[0]))
        context.set_alpn_protocols(["http/1.1"])
        return context

    monkeypatch.setattr(sandbox_ca.SessionCa, "upstream_context", upstream_context)
    policy = SandboxPolicy(
        allowed_domains=("127.0.0.1",),
        allow_localhost=False,
        mask_env=("GH_TOKEN",),
        tls_terminate=True,
    )
    context = ToolContext(root=tmp_path, shell_sandbox="write_root", sandbox_policy=policy)
    run = sandbox_runtime.prepare_sandbox("python", {"command": "python"}, context)
    python = shutil.which("python3") or sys.executable
    port = server.server_address[1]
    code = (
        f"import os,urllib.request as u;r=u.Request('https://127.0.0.1:{port}/',headers={{"
        "'Authorization':'Bearer '+os.environ['GH_TOKEN']});print(u.urlopen(r,timeout=15)"
        ".read().decode());print('ENV',os.environ['GH_TOKEN'])"
    )
    try:
        env = sandbox_runtime.sandbox_env({"GH_TOKEN": TOKEN, "PATH": "/usr/bin:/bin"}, run)
        result = subprocess.run(
            [*run.plan.prefix, python, "-c", code],
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )
    finally:
        sandbox_runtime.release_sandbox(run)
        server.shutdown()
        monkeypatch.setattr(sandbox_ca.SessionCa, "upstream_context", original)
    assert _Echo.seen == [f"Bearer {TOKEN}"], result.stderr
    assert TOKEN not in result.stdout and env["GH_TOKEN"] in result.stdout


def test_doctor_tls_sonlandirma_kurulamiyorsa_uyarir(tmp_path):
    from dataclasses import replace

    from fusion_cli.cli.doctor import tls_terminate_check
    from fusion_cli.config.loader import load_config

    path = tmp_path / "config.yaml"
    path.write_text("{}\n", encoding="utf-8")
    config = load_config(path)
    assert tls_terminate_check(config) == []

    broken = SandboxConfig(
        tls_terminate=True, tls_ca_cert=str(tmp_path / "yok.pem"), tls_ca_key=str(tmp_path / "k")
    )
    (check,) = tls_terminate_check(replace(config, sandbox=broken))
    assert check.ok is False and "kullanılamıyor" in check.value and check.remedy

    (ready,) = tls_terminate_check(replace(config, sandbox=SandboxConfig(tls_terminate=True)))
    assert ready.ok is True
