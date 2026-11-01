"""Terminal oturumunda Chrome: --chrome, /chrome, başlangıç ve kurulum soruları (#421)."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest
from rich.console import Console

from fusion_cli.cli.repl import chrome_cli, chrome_command
from fusion_cli.cli.repl.commands import ASYNC_COMMANDS, build_registry
from fusion_cli.config import chrome_cli_prefs
from fusion_cli.ui import chrome_messages as text


class FakeBridge:
    def __init__(self, installer: Any, installed: Any) -> None:
        self.installer = installer
        self.installed = installed
        self.starts = 0
        self.closes = 0
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    def status(self, *, reveal_token: bool = False) -> dict[str, Any]:
        return {"calisiyor": self._running, "bagli": False}

    async def start(self) -> dict[str, Any]:
        self.starts += 1
        self._running = True
        return self.status()

    async def close(self) -> None:
        self.closes += 1
        self._running = False

    async def invoke(self, operation: str, args: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "veri": {}}


@pytest.fixture
def prefs_path(tmp_path, monkeypatch) -> Path:
    path = tmp_path / "ayar" / chrome_cli_prefs.STORE_NAME
    monkeypatch.setattr(chrome_cli_prefs, "store_path", lambda: path)
    return path


def _console() -> tuple[Console, io.StringIO]:
    buffer = io.StringIO()
    return Console(file=buffer, width=200, force_terminal=False), buffer


async def _open(tmp_path: Path, **kwargs: Any) -> tuple[chrome_cli.ChromeSession | None, str]:
    console, buffer = _console()
    root = kwargs.pop("root", tmp_path / "proje")
    root.mkdir(exist_ok=True)
    defaults: dict[str, Any] = {
        "root": root,
        "home": tmp_path / "ev",
        "flag": None,
        "interactive": False,
        "environ": {},
        "bridge_factory": FakeBridge,
        "extension_installed": lambda: True,
        "wait_enter": lambda: None,
    }
    defaults.update(kwargs)
    session = await chrome_cli.open_for_session(console, **defaults)
    return session, buffer.getvalue()


async def test_bayraksiz_ve_tercihsiz_chrome_kapali(tmp_path, prefs_path):
    session, _ = await _open(tmp_path)
    assert session is None
    assert chrome_cli.bridge_of(session) is None


async def test_chrome_bayragi_kopruyu_baslatir_ve_tanitim_bir_kez(tmp_path, prefs_path):
    session, out = await _open(tmp_path, flag=True, interactive=True)
    assert session is not None and session.bridge.running
    assert text.INTRO_TITLE in out
    await chrome_cli.close_session(session)
    _, again = await _open(tmp_path, flag=True, interactive=True)
    assert text.INTRO_TITLE not in again


async def test_no_chrome_varsayilani_ezer(tmp_path, prefs_path):
    chrome_cli_prefs.update(enabled_by_default=True)
    session, _ = await _open(tmp_path, flag=False)
    assert session is None
    session, _ = await _open(tmp_path)
    assert session is not None


async def test_proje_ayari_chromeu_acamaz_ve_uyarir(tmp_path, prefs_path):
    root = tmp_path / "proje"
    (root / ".claude").mkdir(parents=True)
    (root / ".claude" / "settings.json").write_text(
        json.dumps({"env": {"CLAUDE_CODE_ENABLE_CFC": "1"}}), encoding="utf-8"
    )
    session, out = await _open(tmp_path, root=root)
    assert session is None
    assert "CLAUDE_CODE_ENABLE_CFC" in out


async def test_kullanici_ortami_chromeu_acar(tmp_path, prefs_path):
    session, _ = await _open(tmp_path, environ={"CLAUDE_CODE_ENABLE_CFC": "1"})
    assert session is not None


async def test_eklenti_bulundu_sorusu_evet_ayari_acar(tmp_path, prefs_path):
    session, _ = await _open(tmp_path, interactive=True, picker=lambda choices, title: "yes")
    assert session is not None
    assert chrome_cli_prefs.load().enabled_by_default is True


async def test_eklenti_bulundu_sorusu_hayir_ayari_kapatir_ve_sormaz(tmp_path, prefs_path):
    asked: list[str] = []

    def picker(choices, title):
        asked.append(title)
        return None

    session, _ = await _open(tmp_path, interactive=True, picker=picker)
    assert session is None and asked == [text.DETECTED_TITLE]
    prefs = chrome_cli_prefs.load()
    assert prefs.enabled_by_default is False and prefs.dont_ask_install is True
    await _open(tmp_path, interactive=True, picker=picker)
    assert len(asked) == 1


async def test_kurulum_istemi_oturumda_bir_kez(tmp_path, prefs_path):
    session, _ = await _open(tmp_path, flag=True)
    assert session is not None
    seen: list[list[str]] = []

    async def choose(title, choices):
        seen.append([choice.label for choice in choices])
        return "later"

    session.choose = choose
    first = await session.install()
    second = await session.install()
    assert first["asama"] == "izin_gerekli" and second["asama"] == "izin_gerekli"
    assert seen == [[text.INSTALL_YES, text.INSTALL_LATER, text.INSTALL_NEVER]]


async def test_kurulum_istemi_bir_daha_sorma_kalici(tmp_path, prefs_path):
    session, _ = await _open(tmp_path, flag=True)
    assert session is not None

    async def choose(title, choices):
        return "never"

    session.choose = choose
    await session.install()
    assert chrome_cli_prefs.load().dont_ask_install is True


async def test_kurulum_secilirse_kilavuzlu_kurulum_calisir(tmp_path, prefs_path):
    session, _ = await _open(tmp_path, flag=True)
    assert session is not None
    calls: list[int] = []

    async def installer():
        calls.append(1)
        return {"asama": "kuruldu"}

    async def choose(title, choices):
        return "install"

    session.choose = choose
    session.installer = installer
    assert (await session.install())["asama"] == "kuruldu" and calls == [1]


async def test_chrome_komutu_durum_reconnect_default(tmp_path, prefs_path):
    session, _ = await _open(tmp_path, flag=True)
    assert session is not None
    console, buffer = _console()
    await chrome_command.run(session, "", console)
    out = buffer.getvalue()
    assert "Status: Enabled" in out and "Extension: Installed" in out
    await chrome_command.run(session, "reconnect", console)
    assert isinstance(session.bridge, FakeBridge)
    assert session.bridge.closes == 1 and session.bridge.starts == 2
    await chrome_command.run(session, "default on", console)
    assert chrome_cli_prefs.load().enabled_by_default is True
    await chrome_command.run(None, "", console)
    assert "Status: Disabled" in buffer.getvalue()


def test_chrome_komutu_kayitli_ve_asenkron():
    registry = build_registry()
    assert registry.get("chrome") is not None and "chrome" in ASYNC_COMMANDS
