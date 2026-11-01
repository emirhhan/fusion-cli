"""Claude Code `sandbox.*` adları (#321, #322): `sandbox.enabled`, iç içe camelCase yapı.

Claude (settings-reference): sandbox.enabled; sandbox.filesystem.{allowWrite, denyRead,
allowRead}; sandbox.network.{allowedDomains, deniedDomains}; autoAllowBashIfSandboxed,
excludedCommands, allowUnsandboxedCommands, failIfUnavailable. Fusion yalnız düz snake_case
adları ve `runtime.shell_sandbox`'ı okuyordu.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from fusion_cli.config import sandbox_claude_keys
from fusion_cli.config.loader import load_config
from fusion_cli.config.sandbox_claude_keys import (
    migrate_to_claude_names,
    normalize_claude_sandbox,
)
from fusion_cli.core.errors import ConfigError


@pytest.fixture(autouse=True)
def _uyarilar_sifir(monkeypatch):
    monkeypatch.setattr(sandbox_claude_keys, "_WARNED", set())


def _yukle(tmp_path: Path, metin: str):
    yol = tmp_path / "config.yaml"
    yol.write_text(metin, encoding="utf-8")
    return load_config(yol)


def test_claude_ic_ice_adlari_okunur(tmp_path):
    config = _yukle(
        tmp_path,
        "sandbox:\n"
        "  enabled: true\n"
        "  autoAllowBashIfSandboxed: true\n"
        "  excludedCommands: ['docker']\n"
        "  allowUnsandboxedCommands: false\n"
        "  failIfUnavailable: true\n"
        "  filesystem:\n"
        "    allowWrite: ['~/.npm']\n"
        "    denyRead: ['~/gizli']\n"
        "  network:\n"
        "    allowedDomains: ['github.com']\n"
        "    deniedDomains: ['kotu.example.com']\n",
    )
    assert config.runtime.shell_sandbox == "write_root"
    kum = config.sandbox
    assert kum.auto_allow and not kum.allow_unsandboxed and kum.fail_if_unavailable
    assert kum.excluded_commands == ("docker",)
    assert kum.allow_write == ("~/.npm",) and kum.deny_read == ("~/gizli",)
    assert kum.allowed_domains == ("github.com",)
    assert kum.denied_domains == ("kotu.example.com",)
    # Claude: sandbox ağı proxy'den geçer; nesne yazıldıysa kısıtsız ağ yok.
    assert kum.network == "allowlist"


def test_sandbox_enabled_false_eski_anahtari_ezer(tmp_path):
    config = _yukle(
        tmp_path, "runtime:\n  shell_sandbox: write_root\nsandbox:\n  enabled: false\n"
    )
    assert config.runtime.shell_sandbox == "off"


def test_eski_adlar_okunur_ve_bir_kez_uyarilir(tmp_path, caplog):
    with caplog.at_level(logging.WARNING):
        config = _yukle(tmp_path, "sandbox:\n  allow_write: ['~/.npm']\n  network: open\n")
        _yukle(tmp_path, "sandbox:\n  allow_write: ['~/.cache']\n")
    assert config.sandbox.allow_write == ("~/.npm",) and config.sandbox.network == "open"
    uyarilar = [r.getMessage() for r in caplog.records if "allow_write" in r.getMessage()]
    assert len(uyarilar) == 1 and "sandbox.filesystem.allowWrite" in uyarilar[0]


def test_claude_adi_eski_adin_ustundedir():
    sonuc, _ = normalize_claude_sandbox(
        {"allow_write": ["eski"], "filesystem": {"allowWrite": ["yeni"]}}
    )
    assert sonuc["allow_write"] == ["yeni"]


def test_desteklenmeyen_claude_anahtari_uyarilir_ve_atilir(caplog):
    with caplog.at_level(logging.WARNING):
        sonuc, _ = normalize_claude_sandbox(
            {"filesystem": {"denyWrite": ["x"]}, "network": {"allowUnixSockets": ["/s"]}}
        )
    assert "denyWrite" not in sonuc and "allowUnixSockets" not in sonuc
    mesaj = " ".join(r.getMessage() for r in caplog.records)
    assert "filesystem.denyWrite" in mesaj and "network.allowUnixSockets" in mesaj


def test_enabled_bool_olmali():
    with pytest.raises(ConfigError):
        normalize_claude_sandbox({"enabled": "evet"})


def test_gecis_eski_adlari_claude_adlarina_tasir():
    eski = {
        "runtime": {"shell_sandbox": "write_root", "max_tokens": 1},
        "sandbox": {"allow_write": ["a"], "allowed_domains": ["g.com"], "network": "open"},
    }
    yeni = migrate_to_claude_names(eski)
    assert yeni["runtime"] == {"max_tokens": 1}
    assert yeni["sandbox"] == {
        "enabled": True,
        "filesystem": {"allowWrite": ["a"]},
        "network": {"mode": "open", "allowedDomains": ["g.com"]},
    }
    assert eski["sandbox"]["allow_write"] == ["a"]  # girdi değişmez


def test_gecis_sonrasi_dosya_ayni_ayarlarla_yuklenir(tmp_path):
    import yaml

    eski = {"runtime": {"shell_sandbox": "write_root"}, "sandbox": {"network": "allowlist"}}
    yol = tmp_path / "config.yaml"
    yol.write_text(yaml.safe_dump(migrate_to_claude_names(eski)), encoding="utf-8")
    config = load_config(yol)
    assert config.runtime.shell_sandbox == "write_root" and config.sandbox.network == "allowlist"
