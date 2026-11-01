"""Claude `settings.json` sandbox bölümü (#322, #369, #352).

Claude Code (settings-reference › sandbox; sandboxing › Path prefixes): sandbox ayarları
`~/.claude/settings.json`, `.claude/settings.json`, `.claude/settings.local.json`'dan okunur;
diziler kapsamlar arasında birleşir, tekiller son kapsamdan gelir; göreli yol proje ayarında
proje köküne, kullanıcı ayarında `~/.claude`'a göredir. `/sandbox` kip seçimi projenin
`.claude/settings.local.json`'ına yazılır. Fusion yalnız kendi YAML'ını okuyordu.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from fusion_cli.config import claude_sandbox_settings, sandbox_claude_keys, trust
from fusion_cli.config.claude_sandbox_settings import read_claude_sandbox, write_local_sandbox
from fusion_cli.config.loader import load_config
from fusion_cli.config.sandbox_admin import apply_sandbox_action


@pytest.fixture(autouse=True)
def _uyarilar_sifir(monkeypatch):
    monkeypatch.setattr(sandbox_claude_keys, "_WARNED", set())
    monkeypatch.setattr(claude_sandbox_settings, "_WARNED", set())


@pytest.fixture
def proje(tmp_path, monkeypatch) -> Path:
    kok = tmp_path / "proje"
    (kok / ".claude").mkdir(parents=True)
    monkeypatch.chdir(kok)
    return kok


def _yaz(yol: Path, veri: dict) -> None:
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(json.dumps(veri), encoding="utf-8")


def _kullanici() -> Path:
    return Path(os.environ["CLAUDE_CONFIG_DIR"])


def test_kullanici_ayarindaki_sandbox_yuklenir(proje):
    _yaz(
        _kullanici() / "settings.json",
        {
            "sandbox": {
                "enabled": True,
                "autoAllowBashIfSandboxed": False,
                "filesystem": {"allowWrite": ["/tmp/derleme"]},
                "network": {"allowedDomains": ["github.com"]},
            }
        },
    )
    config = load_config()
    assert config.runtime.shell_sandbox == "write_root"
    assert config.sandbox.auto_allow is False
    assert "/tmp/derleme" in config.sandbox.allow_write
    assert config.sandbox.allowed_domains == ("github.com",)


def test_diziler_birlesir_tekiller_son_kapsamdan(proje):
    _yaz(
        _kullanici() / "settings.json",
        {"sandbox": {"enabled": True, "filesystem": {"allowWrite": ["/a"]}}},
    )
    _yaz(
        proje / ".claude" / "settings.local.json",
        {"sandbox": {"enabled": False, "filesystem": {"allowWrite": ["/b"]}}},
    )
    trust.record_permissions_digest(proje)
    sonuc = read_claude_sandbox(proje)
    assert sonuc.enabled is False
    assert sonuc.section["allow_write"] == ["/a", "/b"]


def test_goreli_yol_ayar_dosyasinin_kapsamina_gore(proje):
    _yaz(_kullanici() / "settings.json", {"sandbox": {"filesystem": {"denyRead": ["gizli"]}}})
    _yaz(
        proje / ".claude" / "settings.local.json",
        {"sandbox": {"filesystem": {"allowWrite": ["./cikti", "~/.npm", "/mutlak"]}}},
    )
    trust.record_permissions_digest(proje)
    sonuc = read_claude_sandbox(proje)
    assert sonuc.section["deny_read"] == [str(_kullanici() / "gizli")]
    assert sonuc.section["allow_write"] == [str(proje / "cikti"), "~/.npm", "/mutlak"]


def test_guvenilmeyen_proje_ayari_uygulanmaz(proje):
    _yaz(proje / ".claude" / "settings.json", {"sandbox": {"allowUnsandboxedCommands": True}})
    assert read_claude_sandbox(proje).section == {}


def test_bozuk_ya_da_desteklenmeyen_ayar_yuklemeyi_dusurmez(proje, caplog):
    _yaz(
        _kullanici() / "settings.json",
        {"sandbox": {"enableWeakerNestedSandbox": True, "filesystem": "bozuk"}},
    )
    config = load_config()
    assert config.sandbox.allow_write == ()
    assert "sandbox" in caplog.text


def test_sandbox_kipi_proje_yerel_ayarina_yazilir(proje):
    config = load_config()
    degisim = apply_sandbox_action(config, "oto", "false", root=proje, local=True)
    yerel = proje / ".claude" / "settings.local.json"
    assert degisim.path == yerel
    assert json.loads(yerel.read_text())["sandbox"] == {"autoAllowBashIfSandboxed": False}
    assert degisim.config.sandbox.auto_allow is False
    degisim = apply_sandbox_action(degisim.config, "kapat", root=proje, local=True)
    assert json.loads(yerel.read_text())["sandbox"]["enabled"] is False
    assert degisim.config.runtime.shell_sandbox == "off"
    # Yazılan dosya güvenilir kalır: yeniden yüklemede kip korunur.
    yeniden = load_config()
    assert yeniden.runtime.shell_sandbox == "off" and yeniden.sandbox.auto_allow is False


def test_yerel_yazim_diger_ayarlari_korur(proje):
    yerel = proje / ".claude" / "settings.local.json"
    _yaz(yerel, {"permissions": {"allow": ["Bash(ls *)"]}, "sandbox": {"enabled": True}})
    write_local_sandbox(proje, {"autoAllowBashIfSandboxed": True})
    veri = json.loads(yerel.read_text())
    assert veri["permissions"] == {"allow": ["Bash(ls *)"]}
    assert veri["sandbox"] == {"enabled": True, "autoAllowBashIfSandboxed": True}
