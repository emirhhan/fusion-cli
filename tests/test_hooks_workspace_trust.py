"""Kancalar çalışma alanı güvenine bağlı (#108) — Claude Code `hooks#workspace-trust`.

Etkileşimli oturumda kullanıcı ayarındakiler dahil kancalar klasöre güvenilene dek çalışmaz;
`-p`/etkileşimsiz oturumda klasör güvenilir sayılır. Açılış sorusu ve masaüstü şeridi
güveni verir; yönetilen (managed) politika kancaları beklemez.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fusion_cli.cli.hook_trust_prompt import offer_hook_trust
from fusion_cli.config import hooks as hooks_config
from fusion_cli.config import trust
from fusion_cli.config.hook_trust import REASON_WORKSPACE_UNTRUSTED, is_workspace_trusted


@pytest.fixture
def ev(tmp_path, monkeypatch):
    ev = tmp_path / "ev"
    ev.mkdir()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(ev / ".config"))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: ev))
    monkeypatch.setattr(trust, "trust_store_file", lambda: ev / "guven.json")
    monkeypatch.setattr(hooks_config, "plugin_hooks", lambda timeout: ((), ()))
    monkeypatch.delenv("FUSION_HOOKS", raising=False)
    return ev


def _ayar(path: Path, hooks: dict, **extra) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"hooks": hooks, **extra}), encoding="utf-8")


def _grup(command: str) -> list[dict]:
    return [{"matcher": "", "hooks": [{"type": "command", "command": command}]}]


def _proje(tmp_path: Path) -> Path:
    proje = tmp_path / "proje"
    proje.mkdir()
    return proje


def _komutlar(root: Path, **kwargs) -> set[str]:
    return {command.command for command in hooks_config.load_hooks(root, **kwargs).commands}


def test_etkilesimli_oturumda_kullanici_kancasi_guvene_dek_calismaz(tmp_path, ev):
    proje = _proje(tmp_path)
    _ayar(ev / ".claude" / "settings.json", {"Stop": _grup("kullanici-kancasi")})
    hooks = hooks_config.load_hooks(proje)
    assert hooks.commands == ()
    assert any(
        s.detail == "kullanici-kancasi" and s.reason == REASON_WORKSPACE_UNTRUSTED
        for s in hooks.skipped
    )
    assert hooks.untrusted_layers
    trust.trust_project(proje)
    assert _komutlar(proje) == {"kullanici-kancasi"}


def test_etkilesimsiz_oturumda_klasor_guvenilir_sayilir(tmp_path, ev):
    proje = _proje(tmp_path)
    _ayar(ev / ".claude" / "settings.json", {"Stop": _grup("kullanici-kancasi")})
    _ayar(proje / ".claude" / "settings.json", {"Stop": _grup("depo-kancasi")})
    assert _komutlar(proje, interactive=False) == {"kullanici-kancasi", "depo-kancasi"}


def test_ust_klasor_guveni_alt_klasore_gecer(tmp_path, ev):
    proje = _proje(tmp_path)
    alt = proje / ".fusion" / "worktrees" / "a"
    alt.mkdir(parents=True)
    assert not is_workspace_trusted(alt)
    trust.trust_project(proje)
    assert is_workspace_trusted(alt)


def test_yonetilen_politika_kancasi_beklemez(tmp_path, ev, monkeypatch):
    proje = _proje(tmp_path)
    yonetilen = tmp_path / "managed-settings.json"
    _ayar(yonetilen, {"PreToolUse": _grup("politika")})
    monkeypatch.setattr(hooks_config, "managed_settings_file", lambda: yonetilen)
    assert _komutlar(proje) == {"politika"}


def test_guvenilmeyen_klasorde_disable_all_hooks_yine_uygulanir(tmp_path, ev):
    # Kapatma gevşetme değildir: güven beklenirken kullanıcının kapatma kararı geçerli kalır.
    proje = _proje(tmp_path)
    _ayar(ev / ".claude" / "settings.json", {"Stop": _grup("x")}, disableAllHooks=True)
    hooks = hooks_config.load_hooks(proje)
    assert hooks.disabled_reason is not None and "disableAllHooks" in hooks.disabled_reason


def test_bekleyen_kullanici_dosyasi_guven_seridinde_listelenir(tmp_path, ev):
    proje = _proje(tmp_path)
    _ayar(ev / ".claude" / "settings.json", {"Stop": _grup("x")})
    assert hooks_config.untrusted_hook_files(proje) == ("~/.claude/settings.json",)
    trust.trust_project(proje)
    assert hooks_config.untrusted_hook_files(proje) == ()


def test_acilis_sorusu_evet_klasore_guvenir(tmp_path, ev):
    proje = _proje(tmp_path)
    _ayar(ev / ".claude" / "settings.json", {"Stop": _grup("x")})
    satirlar: list[str] = []
    assert offer_hook_trust(proje, satirlar.append, lambda _: "e", interactive=True) is True
    assert "~/.claude/settings.json" in "\n".join(satirlar)
    assert is_workspace_trusted(proje)
    assert offer_hook_trust(proje, satirlar.append, lambda _: "e", interactive=True) is None


def test_acilis_sorusu_hayir_guven_yazmaz_kancasizda_sorulmaz(tmp_path, ev):
    proje = _proje(tmp_path)
    assert offer_hook_trust(proje, print, lambda _: "e", interactive=True) is None
    _ayar(ev / ".claude" / "settings.json", {"Stop": _grup("x")})
    assert offer_hook_trust(proje, lambda _: None, lambda _: "", interactive=True) is False
    assert not is_workspace_trusted(proje)
    assert offer_hook_trust(proje, lambda _: None, lambda _: "e", interactive=False) is None


def test_fusionin_yazdigi_dosya_onayi_klasore_guven_vermez(tmp_path, ev):
    # forge / preview_launch / mcp_json `approve_file` ile kendi dosyasını onaylar; bu,
    # kullanıcının vermediği klasör güvenini (ve kancaları) açmamalı.
    proje = _proje(tmp_path)
    _ayar(ev / ".claude" / "settings.json", {"Stop": _grup("kullanici-kancasi")})
    arac = proje / ".fusion" / "tools" / "x.py"
    arac.parent.mkdir(parents=True)
    arac.write_text("print(1)\n", encoding="utf-8")
    trust.approve_file(proje, arac)
    assert trust.is_file_trusted(proje, arac)
    assert not is_workspace_trusted(proje)
    assert not trust.resolve_project_trust(proje).trusted
    assert _komutlar(proje) == set()


def test_guvenilen_klasorde_dosya_onayi_guveni_korur(tmp_path, ev):
    proje = _proje(tmp_path)
    trust.trust_project(proje)
    arac = proje / "x.py"
    arac.write_text("print(1)\n", encoding="utf-8")
    trust.approve_file(proje, arac)
    assert is_workspace_trusted(proje)
    assert trust.resolve_project_trust(proje).trusted
