"""Masaüstünde İzinleri atla kipi ayar/kurum politikasıyla kapatılır (#442).

Claude Code: `permissions.disableBypassPermissionsMode: "disable"` herhangi bir ayar
dosyasında (kullanıcı, proje, yerel, yönetilen) bypass kipini kapatır; Desktop'ta Team ve
Enterprise için kurum politikası Bypass'ı belirler.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fusion_cli.appserver.bypass_policy import bypass_policy_disabled
from fusion_cli.appserver.protocol import Request
from fusion_cli.appserver.session import AppSession
from fusion_cli.engines.agent.approval import ApprovalMode

_DISABLED = {"permissions": {"disableBypassPermissionsMode": "disable"}}


def _write(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


@pytest.fixture(autouse=True)
def _yonetilen_dizin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    managed = tmp_path / "managed"
    monkeypatch.setenv("FUSION_CLAUDE_MANAGED_DIR", str(managed))
    return managed


@pytest.mark.parametrize(
    "relative",
    [
        "ev/.claude/settings.json",
        "proje/.claude/settings.json",
        "proje/.claude/settings.local.json",
    ],
)
def test_herhangi_bir_kapsam_bypassi_kapatir(tmp_path: Path, relative: str) -> None:
    root, home = tmp_path / "proje", tmp_path / "ev"
    root.mkdir()
    assert bypass_policy_disabled(root, home) is False
    _write(tmp_path / relative, _DISABLED)
    assert bypass_policy_disabled(root, home) is True


def test_yonetilen_ayar_bypassi_kapatir(tmp_path: Path, _yonetilen_dizin: Path) -> None:
    root = tmp_path / "proje"
    root.mkdir()
    _write(_yonetilen_dizin / "managed-settings.json", _DISABLED)
    assert bypass_policy_disabled(root, tmp_path / "ev") is True


def test_bozuk_ya_da_baska_deger_kapatmaz(tmp_path: Path) -> None:
    root, home = tmp_path / "proje", tmp_path / "ev"
    _write(
        root / ".claude" / "settings.json", {"permissions": {"disableBypassPermissionsMode": "x"}}
    )
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / "settings.json").write_text("{bozuk", encoding="utf-8")
    assert bypass_policy_disabled(root, home) is False


def _session(tmp_path: Path) -> tuple[AppSession, list[str]]:
    lines: list[str] = []
    root = tmp_path / "proje"
    root.mkdir(exist_ok=True)
    return AppSession(lines.append, root=root, home=tmp_path / "ev"), lines


async def _ask(session: AppSession, lines: list[str], name: str, data: dict) -> dict:
    await session.handle(Request(id=str(len(lines)), name=name, data=data))
    return json.loads(lines[-1])["veri"]


@pytest.mark.asyncio
async def test_politika_kapaliyken_masaustu_bypassa_gecemez(tmp_path: Path) -> None:
    _write(tmp_path / "proje" / ".claude" / "settings.json", _DISABLED)
    session, lines = _session(tmp_path)

    durum = await _ask(session, lines, "oturum.durum", {})
    assert durum["bypass_kapali"] is True
    result = await _ask(session, lines, "oturum.baslat", {"mod": "bypass"})

    assert result["ok"] is False
    assert "disableBypassPermissionsMode" in result["metin"]
    assert session._state.approval is not ApprovalMode.BYPASS


@pytest.mark.asyncio
async def test_politika_yokken_bypass_secilebilir(tmp_path: Path) -> None:
    session, lines = _session(tmp_path)

    durum = await _ask(session, lines, "oturum.durum", {})
    assert durum["bypass_kapali"] is False
    result = await _ask(session, lines, "oturum.baslat", {"mod": "bypass"})

    assert result["ok"] is True
    assert session._state.approval is ApprovalMode.BYPASS


@pytest.mark.asyncio
async def test_politika_kapaliyken_bypass_komutu_reddedilir(tmp_path: Path) -> None:
    _write(tmp_path / "proje" / ".claude" / "settings.local.json", _DISABLED)
    session, lines = _session(tmp_path)

    result = await _ask(session, lines, "komut.calistir", {"ad": "bypass", "arguman": ""})

    assert result["ok"] is False
    assert session._state.approval is not ApprovalMode.BYPASS
