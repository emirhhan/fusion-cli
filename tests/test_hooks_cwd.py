"""`CwdChanged` kancası (P-072 + P-009): `/cd` REPL'de ve masaüstünde olayı tetikler.

Ölçüldü (1 Kasım): `CwdChanged` `CLAUDE_ONLY_EVENTS` listesindeydi; tanım "Fusion bu olayı
tetiklemiyor" diye atlanıyor, `/cd` hiçbir kanca çalıştırmıyordu.
"""

from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

import pytest

from fusion_cli.cli.repl import hook_events
from fusion_cli.cli.repl.commands import build_registry
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.config.hooks import parse_hooks_block
from fusion_cli.core.hooks.events import HookCommand, HookEvent, HookSet
from fusion_cli.engines.hooks.session import HookSession
from fusion_cli.memory.factory import null_memory

from .fakes import make_config


@pytest.fixture
def ev(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "ev"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("FUSION_HOOKS", raising=False)
    return home


def _kayit_kancasi(tmp_path: Path, kayit: Path, cikti: str = "") -> HookCommand:
    script = tmp_path / "cwd_kanca.py"
    script.write_text(
        "import json, sys\n"
        f"open({str(kayit)!r}, 'a', encoding='utf-8').write(sys.stdin.read().strip() + '\\n')\n"
        + (f"print({cikti!r})\n" if cikti else ""),
        encoding="utf-8",
    )
    command = f"{shlex.quote(sys.executable)} {shlex.quote(str(script))}"
    return HookCommand(HookEvent.CWD_CHANGED, "", command, 20.0, "test", "")


def _durum(root: Path, home: Path, *commands: HookCommand) -> ReplState:
    state = ReplState(config=make_config(), memory=null_memory(), root=root, home=home)
    state.hook_session = HookSession(root=root, loader=lambda: HookSet(tuple(commands)))
    return state


def _satirlar(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_cwdchanged_tanimi_artik_atlanmaz():
    commands, skipped = parse_hooks_block(
        {"CwdChanged": [{"hooks": [{"type": "command", "command": "echo x"}]}]},
        source="fusion",
        path=Path("hooks.json"),
        default_timeout_s=60.0,
    )
    assert [c.event for c in commands] == [HookEvent.CWD_CHANGED] and skipped == ()


async def test_cd_cwdchanged_kancasini_eski_ve_yeni_dizinle_tetikler(tmp_path: Path, ev: Path):
    eski, yeni = tmp_path / "a", tmp_path / "b"
    eski.mkdir()
    yeni.mkdir()
    kayit = tmp_path / "kayit.jsonl"
    state = _durum(eski, ev, _kayit_kancasi(tmp_path, kayit, '{"systemMessage": "dizin izlendi"}'))
    command = build_registry().get("cd")
    assert command is not None

    command.handler(state, str(yeni))
    satirlar = await hook_events.flush(state)

    olay = _satirlar(kayit)[0]
    assert olay["hook_event_name"] == "CwdChanged"
    assert (olay["old_cwd"], olay["new_cwd"], olay["cwd"]) == (
        str(eski.resolve()),
        str(yeni.resolve()),
        str(yeni.resolve()),
    )
    assert satirlar == ("Kanca: dizin izlendi",)
    # Kuyruk boşaldı: ikinci gönderim kancayı yeniden çalıştırmaz.
    assert await hook_events.flush(state) == ()
    assert len(_satirlar(kayit)) == 1


async def test_reddedilen_cd_kanca_tetiklemez(tmp_path: Path, ev: Path):
    kayit = tmp_path / "kayit.jsonl"
    state = _durum(tmp_path, ev, _kayit_kancasi(tmp_path, kayit))
    command = build_registry().get("cd")
    assert command is not None

    command.handler(state, str(tmp_path / "yok"))
    await hook_events.flush(state)

    assert _satirlar(kayit) == []


async def test_masaustu_cd_cwdchanged_tetikler_ve_sistem_mesajini_dondurur(
    tmp_path: Path, ev: Path
):
    from fusion_cli.appserver.protocol import Request
    from fusion_cli.appserver.session import AppSession

    eski, yeni = tmp_path / "a", tmp_path / "b"
    eski.mkdir()
    yeni.mkdir()
    kayit = tmp_path / "kayit.jsonl"
    satirlar: list[str] = []
    oturum = AppSession(satirlar.append, root=eski, home=ev)
    hook = _kayit_kancasi(tmp_path, kayit, '{"systemMessage": "yeni projeye geçildi"}')
    oturum._state.hook_session = HookSession(root=eski, loader=lambda: HookSet((hook,)))

    await oturum.handle(
        Request(id="1", name="komut.calistir", data={"ad": "cd", "arguman": str(yeni)})
    )

    sonuc = next(
        json.loads(satir)["veri"]
        for satir in reversed(satirlar)
        if json.loads(satir).get("tip") == "sonuc" and json.loads(satir).get("id") == "1"
    )
    assert sonuc["kok"] == str(yeni.resolve())
    assert "Kanca: yeni projeye geçildi" in sonuc["metin"]
    olay = _satirlar(kayit)[0]
    assert (olay["old_cwd"], olay["new_cwd"]) == (str(eski.resolve()), str(yeni.resolve()))
