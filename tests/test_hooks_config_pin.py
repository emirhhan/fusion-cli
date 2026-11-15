"""`ConfigChange` engeli dosya başınadır (#121): engellenen dosyanın yeni içeriği çalışan
oturuma uygulanmaz; başka bir izinli değişiklik onu içeri sokmaz; Fusion'ın kendi kapatma
anahtarı (`runtime.hooks_enabled`) engelden etkilenmez.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

from fusion_cli.config import hooks as hook_config
from fusion_cli.core.hooks.events import HookEvent, HookSet
from fusion_cli.engines.hooks import watch
from fusion_cli.engines.hooks.session import HookSession
from fusion_cli.engines.hooks.watch import HookWatcher


@pytest.fixture(autouse=True)
def _kancalar_acik(monkeypatch):
    monkeypatch.delenv("FUSION_HOOKS", raising=False)


def _gate(tmp_path: Path) -> str:
    """project_settings değişikliğini çıkış 2 ile engelleyen ConfigChange kancası."""
    script = tmp_path / "kapi.py"
    script.write_text(
        "import json, sys\n"
        "data = json.load(sys.stdin)\n"
        "sys.exit(2 if data['source'] == 'project_settings' else 0)\n",
        encoding="utf-8",
    )
    return f"{sys.executable} {script}"


def _write(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _setup(monkeypatch, tmp_path: Path) -> tuple[HookSession, dict[str, bool]]:
    managed = tmp_path / "yonetilen" / "managed-settings.json"
    monkeypatch.setattr(hook_config, "managed_settings_file", lambda: managed)
    monkeypatch.setattr(watch, "managed_settings_file", lambda: managed)
    home = tmp_path / "ev"
    gate = {"type": "command", "command": _gate(tmp_path)}
    _write(home / ".claude" / "settings.json", {"hooks": {"ConfigChange": [{"hooks": [gate]}]}})
    root = tmp_path / "proje"
    root.mkdir()
    flags = {"enabled": True}

    def _load() -> HookSet:
        return hook_config.load_hooks(
            root,
            enabled=flags["enabled"],
            home=home,
            interactive=False,
            include_plugins=False,
            pinned=session.pinned_settings,
        )

    session = HookSession(root=root, loader=_load, home=home, interactive=False)
    return session, flags


def _pre_tool(session: HookSession) -> list[str]:
    return [c.command for c in session.current().for_event(HookEvent.PRE_TOOL_USE, ("Bash",))]


def _yeni_kanca() -> dict[str, object]:
    handler = {"type": "command", "command": "yeni-kanca"}
    return {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [handler]}]}}


def test_engellenen_dosya_baska_izinli_degisiklikte_de_uygulanmaz(monkeypatch, tmp_path):
    session, _ = _setup(monkeypatch, tmp_path)
    session.refresh()
    watcher = HookWatcher(session)
    watcher.prime()
    _write(session.root / ".claude" / "settings.json", _yeni_kanca())
    asyncio.run(watcher.check())
    assert _pre_tool(session) == []

    _write(session.root / ".claude" / "settings.local.json", {})  # local_settings: izinli
    asyncio.run(watcher.check())
    session.refresh()

    assert _pre_tool(session) == []
    assert session.hooks_pinned


def test_pin_kalkinca_dosyanin_yeni_icerigi_okunur(monkeypatch, tmp_path):
    session, _ = _setup(monkeypatch, tmp_path)
    session.refresh()
    watcher = HookWatcher(session)
    watcher.prime()
    project = session.root / ".claude" / "settings.json"
    _write(project, _yeni_kanca())
    asyncio.run(watcher.check())
    assert session.hooks_pinned
    session.pinned_settings.clear()  # ör. kapı kancası kaldırıldı; dosya yeniden okunur
    session.refresh()
    assert _pre_tool(session) == ["yeni-kanca"]


def test_kapatma_anahtari_pin_varken_de_etkili(monkeypatch, tmp_path):
    session, flags = _setup(monkeypatch, tmp_path)
    session.refresh()
    watcher = HookWatcher(session)
    watcher.prime()
    _write(session.root / ".claude" / "settings.json", _yeni_kanca())
    asyncio.run(watcher.check())
    assert session.hooks_pinned

    flags["enabled"] = False  # /config set runtime.hooks_enabled false
    session.refresh()

    assert session.current().disabled_reason is not None
