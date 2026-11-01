"""Kullanımdan kalkan `runtime.hook_http_allow_private` ve `runtime.hook_timeout_s` (#105, #106).

Brif kuralı: eski ad bir sürüm okunur, bir kez uyarılır, kullanıcının mevcut ayarı bozulmaz.
Varsayılan değerleri (true / 600) Claude davranışıdır; açıkça başka değer yazılmışsa uygulanır.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fusion_cli.config import hooks as hooks_config
from fusion_cli.core.hooks.events import HookEvent
from fusion_cli.engines.hooks.session import open_hook_session

from .fakes import make_config


@pytest.fixture(autouse=True)
def _izole(monkeypatch, tmp_path):
    monkeypatch.delenv("FUSION_HOOKS", raising=False)
    monkeypatch.setattr(hooks_config, "managed_settings_file", lambda: tmp_path / "yok.json")
    monkeypatch.setattr(hooks_config, "user_config_dir", lambda: tmp_path / "fusion-ayar")


def _session(tmp_path: Path, **runtime: object):
    settings = tmp_path / "ev" / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True, exist_ok=True)
    handler = {"type": "command", "command": "denetle"}
    settings.write_text(
        json.dumps({"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [handler]}]}}),
        encoding="utf-8",
    )
    config = make_config(runtime=runtime)
    return open_hook_session(tmp_path, config, home=tmp_path / "ev", interactive=False)


def test_varsayilan_degerlerde_uyari_yok_ve_yerel_adres_izinli(tmp_path):
    session = _session(tmp_path)
    assert session.http_allow_private is None or session.http_allow_private() is True
    assert not [n for n in session.current().notices if "hook_" in n]


def test_acik_false_yerel_adres_kisitini_korur_ve_bir_kez_uyarir(tmp_path):
    session = _session(tmp_path, hook_http_allow_private=False)
    assert session.http_allow_private is not None
    assert session.http_allow_private() is False
    notices = session.take_notices()
    assert any("hook_http_allow_private" in n and "allowedHttpHookUrls" in n for n in notices)
    assert session.take_notices() == ()


def test_eski_sure_tanimda_sure_yoksa_uygulanir_ve_uyarir(tmp_path):
    session = _session(tmp_path, hook_timeout_s=30.0)
    (command,) = session.current().for_event(HookEvent.PRE_TOOL_USE, ("Bash",))
    assert command.timeout_s == 30.0
    assert any("hook_timeout_s" in n for n in session.current().notices)
