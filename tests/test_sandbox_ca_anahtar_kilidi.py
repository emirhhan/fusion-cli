"""`tlsTerminate` kullanıcı CA'sının özel anahtarı sandbox'a okunamaz (#350, #368).

Claude: `caCertPath`/`caKeyPath` ile verilen CA anahtarı proxy'nin sırrıdır; sandbox içindeki
komut onu okuyup izinli bir ana makineye gönderebilseydi bu CA'ya güvenen her istemci için
sertifika üretebilirdi. Anahtar dosyası `locked_read`'e (hiçbir `allowRead` açamaz) eklenir.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from fusion_cli.core.sandbox_policy import SandboxPolicy
from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import sandbox_runtime
from fusion_cli.tools.sandbox_mask import prepare_tls
from tests.test_sandbox_mask_tls import _self_signed

_SANDBOX = Path("/usr/bin/sandbox-exec")


def _user_ca(tmp_path: Path) -> tuple[Path, Path]:
    folder = tmp_path / "kullanici-ca"
    folder.mkdir()
    return _self_signed(folder)


def _policy(cert: Path, key: Path, **extra: object) -> SandboxPolicy:
    values: dict[str, object] = {
        "allowed_domains": ("127.0.0.1",),
        "tls_terminate": True,
        "tls_ca_cert": str(cert),
        "tls_ca_key": str(key),
        **extra,
    }
    return SandboxPolicy(**values)  # type: ignore[arg-type]


def test_kullanici_ca_anahtari_locked_read_ve_deny_reade_eklenir(tmp_path):
    cert, key = _user_ca(tmp_path)
    notices: list[str] = []

    policy, ca = prepare_tls(_policy(cert, key), notices)

    assert ca is not None and notices == []
    assert key.resolve() in {path.resolve() for path in policy.locked_read}
    assert key.resolve() in {path.resolve() for path in policy.deny_read}
    assert ca.private_dir in policy.locked_read


def test_ca_yuklenemese_de_anahtar_dosyasi_kilitlenir(tmp_path):
    _, key = _user_ca(tmp_path)
    notices: list[str] = []

    policy, ca = prepare_tls(_policy(tmp_path / "yok.pem", key), notices)

    assert ca is None and any("kullanılamıyor" in item for item in notices)
    assert key.resolve() in {path.resolve() for path in policy.locked_read}


def test_ag_kisitsiz_ya_da_dis_proxyde_de_anahtar_kilitli(tmp_path):
    cert, key = _user_ca(tmp_path)
    for policy in (
        _policy(cert, key, network="open"),
        _policy(cert, key, http_proxy_port=8080),
    ):
        locked, ca = prepare_tls(policy, [])
        assert ca is None
        assert key.resolve() in {path.resolve() for path in locked.locked_read}


@pytest.mark.skipif(sys.platform != "darwin" or not _SANDBOX.exists(), reason="Seatbelt yok")
def test_gercek_sandboxta_kullanici_ca_anahtari_okunamaz(tmp_path, monkeypatch):
    monkeypatch.setattr(sandbox_runtime, "_uses_unix_proxy", lambda: False)
    cert, key = _user_ca(tmp_path)
    root = tmp_path / "proje"
    root.mkdir()
    context = ToolContext(root=root, shell_sandbox="write_root", sandbox_policy=_policy(cert, key))
    run = sandbox_runtime.prepare_sandbox("cat", {"command": "cat"}, context)
    try:
        assert run.plan.is_active and run.tls is not None
        cert_read = subprocess.run(
            [*run.plan.prefix, "/bin/cat", str(cert)], capture_output=True, timeout=30
        )
        key_read = subprocess.run(
            [*run.plan.prefix, "/bin/cat", str(key)], capture_output=True, timeout=30
        )
    finally:
        sandbox_runtime.release_sandbox(run)
    assert cert_read.returncode == 0, cert_read.stderr
    assert key_read.returncode != 0 and b"PRIVATE KEY" not in key_read.stdout
    assert b"not permitted" in key_read.stderr


def _artiklar(folder: Path) -> list[str]:
    return sorted(item.name for item in folder.iterdir() if item.name.startswith("fusion-sbx-ca"))


def test_ca_dizinleri_surec_sonunda_silinir_hatali_ca_dizin_birakmaz(tmp_path, monkeypatch):
    """İnceleme bulgusu 6: anahtar içeren geçici dizinler /tmp altında kalmaz."""
    import tempfile

    from fusion_cli.core.errors import ConfigError
    from fusion_cli.tools import sandbox_ca

    temp = tmp_path / "tmp"
    temp.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(temp))
    with pytest.raises(ConfigError):
        sandbox_ca.SessionCa(str(tmp_path / "yok.pem"), str(tmp_path / "yok.key"))
    assert _artiklar(temp) == []

    ca = sandbox_ca.SessionCa()
    ca.server_context("127.0.0.1")
    assert len(_artiklar(temp)) == 2
    sandbox_ca._cleanup_all()
    assert _artiklar(temp) == []


def test_doctor_ca_denetimi_gecici_dizin_acmaz(tmp_path, monkeypatch):
    import tempfile
    from dataclasses import replace

    from fusion_cli.cli.doctor import tls_terminate_check
    from fusion_cli.config.loader import load_config
    from fusion_cli.config.sandbox_config import SandboxConfig

    temp = tmp_path / "tmp"
    temp.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(temp))
    path = tmp_path / "config.yaml"
    path.write_text("{}\n", encoding="utf-8")
    config = load_config(path)
    cert, key = _user_ca(tmp_path)
    for sandbox in (
        SandboxConfig(tls_terminate=True),
        SandboxConfig(tls_terminate=True, tls_ca_cert=str(cert), tls_ca_key=str(key)),
    ):
        (check,) = tls_terminate_check(replace(config, sandbox=sandbox))
        assert check.ok is True
    assert _artiklar(temp) == []
