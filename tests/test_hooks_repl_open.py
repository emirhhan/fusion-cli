"""SessionStart oturum AÇILIRKEN (#111): Claude gibi ilk istem beklenmez; bağlam ilk isteme."""

from __future__ import annotations

import io

from rich.console import Console

from fusion_cli.cli.repl.hook_open import open_hooks

from .test_hooks_surfaces import _izole_ev, _kaydeden_kancalar, _olaylar, _repl_durumu

__all__ = ["_izole_ev"]  # otomatik fikstür bu modülde de geçerli


async def test_repl_acilisinda_sessionstart_ilk_istemden_once_calisir(tmp_path):
    kayit = _kaydeden_kancalar(tmp_path)
    state = _repl_durumu(tmp_path)
    console = Console(file=io.StringIO())
    await open_hooks(state, console)
    assert [olay[:2] for olay in _olaylar(kayit)] == [("SessionStart", "startup")]
    # İlk istemde ikinci kez tetiklenmez.
    await state.hooks().start()
    assert len(_olaylar(kayit)) == 1


async def test_sessionstart_kancasi_yoksa_oturum_acik_sayilmaz(tmp_path):
    state = _repl_durumu(tmp_path)
    await open_hooks(state, Console(file=io.StringIO()))
    assert state.hook_session is None or state.hook_session.started is False
