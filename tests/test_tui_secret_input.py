"""TUI gizli metin istemi: yıldızlı ve girdi geçmişine yazılmaz (eklenti userConfig, #388)."""

from __future__ import annotations

import asyncio

from prompt_toolkit.document import Document

from .test_tui import _tui


async def test_gizli_istem_metni_doner_ve_tamponu_bosaltir():
    tui, _ = _tui()
    task = asyncio.ensure_future(tui.await_secret())
    await asyncio.sleep(0)
    assert tui._secret is True and tui._mode == "ask"

    buffer = tui._input.buffer
    buffer.set_document(Document("gizli-deger", 11), bypass_readonly=True)
    tui._accept(buffer)

    assert await task == "gizli-deger"
    assert buffer.text == "" and tui._secret is False
