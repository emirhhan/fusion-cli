"""Masaüstünde proje kökü değişince .claude/settings.json ajan ayarları yeniden okunur."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fusion_cli.appserver.protocol import Request
from fusion_cli.appserver.session import AppSession
from fusion_cli.config import trust


@pytest.fixture
def ev(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "ev"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setenv("FUSION_KEYCHAIN", "off")
    for name in ("CLAUDE_CODE_FORK_SUBAGENT", "CLAUDE_CODE_SUBAGENT_MODEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(trust, "trust_store_file", lambda: tmp_path / "trust.json")
    return home


async def test_kok_degisince_proje_ajan_ayarlari_yeniden_okunur(tmp_path: Path, ev: Path):
    eski, yeni = tmp_path / "a", tmp_path / "b"
    eski.mkdir()
    (yeni / ".claude").mkdir(parents=True)
    (yeni / ".claude" / "settings.json").write_text(
        json.dumps({"env": {"CLAUDE_CODE_FORK_SUBAGENT": "0"}}), encoding="utf-8"
    )
    trust.trust_project(yeni)
    oturum = AppSession([].append, root=eski, home=ev)
    assert oturum._state.config.agent_launch.fork_enabled is True

    await oturum.handle(Request(id="1", name="oturum.baslat", data={"kok": str(yeni)}))
    assert oturum._state.config.agent_launch.fork_enabled is False

    await oturum.handle(Request(id="2", name="oturum.baslat", data={"kok": str(eski)}))
    assert oturum._state.config.agent_launch.fork_enabled is True
