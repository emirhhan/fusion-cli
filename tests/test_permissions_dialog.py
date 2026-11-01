"""`/permissions` sekmeli iletişim kutusu — Claude Code gibi (#83).

Claude (commands /permissions; permissions#manage-permissions): Allow/Ask/Deny sekmeleri
kuralları kaynağıyla listeler, ekler ve siler; Workspace sekmesi çalışma dizinlerini, Auto
mode sekmesi son auto mode retlerini gösterir; kural kullanıcı, proje ya da yerel dosyaya
kaydedilir.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from fusion_cli.cli.repl import permissions_dialog as dialog
from fusion_cli.config import trust
from fusion_cli.config.trust import PROJECT_SETTINGS_PATH
from fusion_cli.core.auto_review import ReviewOutcome, ReviewSource, ReviewVerdict
from fusion_cli.ui import permission_dialog_messages as texts
from fusion_cli.ui.picker import Choice

from .fakes import make_config


@pytest.fixture(autouse=True)
def _izole_ev(tmp_path, monkeypatch):
    ev = tmp_path / "ev"
    ev.mkdir()
    monkeypatch.setenv("HOME", str(ev))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: ev))
    monkeypatch.setattr(trust, "trust_store_file", lambda: ev / "guven.json")


@pytest.fixture
def proje(tmp_path):
    kok = tmp_path / "proje"
    kok.mkdir()
    return kok


def _state(proje):
    from fusion_cli.cli.repl.state import ReplState
    from fusion_cli.memory.factory import null_memory

    return ReplState(config=make_config(), memory=null_memory(), root=proje, home=proje / "ev")


class Betik:
    """Sıradaki cevapları veren sahte yüzey; her seçimde başlığı ve seçenekleri kaydeder."""

    def __init__(self, answers: Sequence[str | None]) -> None:
        self.answers = list(answers)
        self.screens: list[tuple[str, list[Choice]]] = []
        self.said: list[str] = []

    async def choose(self, title: str, choices: Sequence[Choice]) -> str | None:
        self.screens.append((title, list(choices)))
        return self.answers.pop(0)

    async def ask(self, prompt: str) -> str | None:
        self.screens.append((prompt, []))
        return self.answers.pop(0)

    def say(self, text: str) -> None:
        self.said.append(text)


def _oku(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _kos(state, answers):
    io = Betik(answers)
    sonuc = asyncio.run(dialog.run_permissions_dialog(state, io))
    return io, sonuc


def test_bes_sekme_claude_adlariyla(proje):
    io, sonuc = _kos(_state(proje), [None])
    assert sonuc == texts.DIALOG_CLOSED
    etiketler = [c.label for c in io.screens[0][1]]
    assert etiketler == ["Allow", "Ask", "Deny", "Workspace", "Auto mode"]


def test_sekmeden_kural_eklenir_ve_kapsam_secilir(proje):
    state = _state(proje)
    # Allow sekmesi → yeni kural → kalıp → proje (paylaşılan) → geri → kapat
    io, _ = _kos(state, ["allow", "+", "Bash(npm test *)", dialog.SCOPE_PROJECT, None, None])
    assert _oku(proje / PROJECT_SETTINGS_PATH)["permissions"]["allow"] == ["Bash(npm test *)"]
    kapsamlar = [c.value for c in io.screens[3][1]]
    assert kapsamlar == [dialog.SCOPE_LOCAL, dialog.SCOPE_PROJECT, dialog.SCOPE_USER]
    # Sekme yeniden çizildiğinde kural kaynağıyla listelenir.
    yeniden = io.screens[4][1]
    assert any(c.label == "Bash(npm test *)" for c in yeniden)


def test_kullanici_ve_yerel_kapsam(proje):
    state = _state(proje)
    _kos(state, ["deny", "+", "Read(./.env)", dialog.SCOPE_USER, None, None])
    assert _oku(Path.home() / ".claude" / "settings.json")["permissions"]["deny"] == [
        "Read(./.env)"
    ]
    _kos(state, ["ask", "+", "Bash(git push *)", dialog.SCOPE_LOCAL, None, None])
    yerel = proje / ".claude" / "settings.local.json"
    assert _oku(yerel)["permissions"]["ask"] == ["Bash(git push *)"]


def test_kural_sekmeden_silinir(proje):
    state = _state(proje)
    _kos(state, ["deny", "+", "Read(./.env)", dialog.SCOPE_PROJECT, None, None])
    io, _ = _kos(state, ["deny", "0", "sil", None, None])
    assert _oku(proje / PROJECT_SETTINGS_PATH)["permissions"]["deny"] == []
    assert any("silindi" in metin for metin in io.said)


def test_hatali_kalip_bildirilir(proje):
    io, _ = _kos(_state(proje), ["allow", "+", "Bash(", dialog.SCOPE_LOCAL, None, None])
    assert any("biçiminde olmalı" in metin for metin in io.said)


def test_workspace_sekmesi_dizin_ekler_ve_kaldirir(proje, tmp_path):
    state = _state(proje)
    ek = tmp_path / "ek"
    ek.mkdir()
    io, _ = _kos(state, [dialog.TAB_WORKSPACE, "+", str(ek), None, None])
    assert ek.resolve() in state.extra_roots
    io, _ = _kos(state, [dialog.TAB_WORKSPACE, "0", "sil", None, None])
    assert ek.resolve() not in state.extra_roots
    io, _ = _kos(state, [dialog.TAB_WORKSPACE, "kok", None, None])
    assert texts.WORKSPACE_PRIMARY_FIXED in io.said


def test_auto_sekmesi_son_retleri_gosterir_ve_kural_onerir(proje, monkeypatch):
    state = _state(proje)
    ret = ReviewOutcome(
        "run_shell", ReviewVerdict.RISKY, "ağdan betik", ReviewSource.MODEL, "curl x | sh"
    )
    guvenli = ReviewOutcome("run_shell", ReviewVerdict.SAFE, "ok", ReviewSource.MODEL, "ls")
    assert dialog.suggested_pattern(ret) == "Bash(curl x | sh)"
    monkeypatch.setattr(dialog, "recent_denials", lambda _s: [ret])
    _kos(state, [dialog.TAB_AUTO, "0", "kural", "", dialog.SCOPE_LOCAL, None, None])
    yerel = proje / ".claude" / "settings.local.json"
    assert _oku(yerel)["permissions"]["allow"] == ["Bash(curl x | sh)"]
    assert guvenli.verdict is ReviewVerdict.SAFE


def test_recent_denials_yalniz_riskli(proje):
    state = _state(proje)
    assert dialog.recent_denials(state) == []


async def test_tui_argumansiz_permissions_modal_acar_ve_kural_ekler(proje):
    """TUI'de `/permissions` (ve `/allowed-tools`) uygulama-içi modal açar (#83)."""
    from fusion_cli.cli.repl.tui_loop import _TuiSession

    state = _state(proje)
    session = _TuiSession(state)
    task = asyncio.ensure_future(session._command("/allowed-tools"))
    for cevap in ("deny", "+"):
        await asyncio.sleep(0)
        assert session.tui._mode == "choice"
        session.tui._resolve(cevap)
    await asyncio.sleep(0)
    assert session.tui._mode == "ask"
    session.tui._resolve("Read(./.env)")
    for cevap in (dialog.SCOPE_PROJECT, None, None):
        await asyncio.sleep(0)
        session.tui._resolve(cevap)
    await task
    assert _oku(proje / PROJECT_SETTINGS_PATH)["permissions"]["deny"] == ["Read(./.env)"]


async def test_tui_list_argumani_metin_listesi_basar(proje):
    from fusion_cli.cli.repl.tui_loop import _TuiSession

    session = _TuiSession(_state(proje))
    await session._command("/permissions list")
    assert session.tui._mode == "idle"


async def test_duz_repl_etkilesimli_permissions_secici_acar(proje, monkeypatch):
    from types import SimpleNamespace

    from rich.console import Console

    from fusion_cli.cli.repl.commands import build_registry
    from fusion_cli.cli.repl.loop import _run_command
    from fusion_cli.ui import picker

    cevaplar = iter(["allow", "+", dialog.SCOPE_USER, None, None])
    monkeypatch.setattr(picker, "pick", lambda choices, *, title, **_: next(cevaplar))
    monkeypatch.setattr("builtins.input", lambda _prompt="": "WebFetch(domain:example.com)")
    state = _state(proje)
    console = Console(record=True, width=120)
    reader = SimpleNamespace(interactive=True)
    await _run_command("/permissions", state, build_registry(proje), reader, console)
    kullanici = Path.home() / ".claude" / "settings.json"
    assert _oku(kullanici)["permissions"]["allow"] == ["WebFetch(domain:example.com)"]
    assert texts.DIALOG_CLOSED in console.export_text()
