"""Sandbox'ın belgede "bilinen sınır" olarak kalan dört maddesi (P-010, 1 Kasım).

Ölçüldü (1 Kasım, eca48854):
- `sandbox.deny_read` yazan kullanıcının listesi varsayılanın YERİNE geçiyordu: tek bir yol
  ekleyen `~/.ssh`, `~/.aws`… korumasını sessizce kaybediyordu.
"""

from __future__ import annotations

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
from fusion_cli.core.errors import ConfigError
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
