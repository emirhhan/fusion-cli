"""`transcript_path` (#129): oturumun kalıcı dökümü; kanca sonradan eklense de eksiksiz."""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

from fusion_cli.core.hooks.events import HookCommand, HookEvent, HookSet
from fusion_cli.engines.hooks.session import HookSession
from fusion_cli.engines.retention import purge_local_state


def _session(tmp_path: Path, hooks: list[HookCommand]) -> HookSession:
    return HookSession(
        root=tmp_path, loader=lambda: HookSet(tuple(hooks)), transcript_dir=tmp_path / "dokum"
    )


def test_kanca_yokken_de_yazilir_sonradan_eklenen_kanca_tum_dokumu_gorur(tmp_path):
    hooks: list[HookCommand] = []
    session = _session(tmp_path, hooks)
    session.record("user", "ilk istem")
    session.record("assistant", "ilk cevap")
    transcript = session.transcript()
    assert transcript is not None
    text = transcript.path.read_text(encoding="utf-8")
    assert "ilk istem" in text and "ilk cevap" in text


def test_session_end_sonrasi_dokum_silinmez(tmp_path):
    session = _session(tmp_path, [HookCommand(HookEvent.SESSION_END, "", "true", 5.0)])

    async def run() -> None:
        await session.start()
        session.record("user", "merhaba")
        await session.end("other")

    asyncio.run(run())
    transcript = session.transcript()
    assert transcript is not None and transcript.path.exists()


def test_reset_eski_oturumun_dokumu_kalir(tmp_path):
    session = _session(tmp_path, [HookCommand(HookEvent.SESSION_END, "", "true", 5.0)])

    async def run() -> None:
        await session.start()
        session.record("user", "eski")
        old = session.transcript()
        session.restart("clear", reason="clear")
        await session.start()
        assert old is not None and old.path.exists()

    asyncio.run(run())


def test_otuz_gunden_eski_dokum_temizlenir(tmp_path):
    folder = tmp_path / "hook-transcripts"
    folder.mkdir()
    old, new = folder / "eski.jsonl", folder / "yeni.jsonl"
    old.write_text("{}\n", encoding="utf-8")
    new.write_text("{}\n", encoding="utf-8")
    past = time.time() - 31 * 86_400
    os.utime(old, (past, past))

    purge_local_state(tmp_path, now=time.time())

    assert not old.exists() and new.exists()
