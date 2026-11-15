"""SessionStart oturum AÇILIRKEN (#111): Claude gibi ilk istem beklenmez; bağlam ilk isteme."""

from __future__ import annotations

import io

import pytest
from rich.console import Console

from fusion_cli.cli.repl.hook_open import open_hooks

from .test_hooks_surfaces import _izole_ev, _kaydeden_kancalar, _olaylar, _repl_durumu

#: Kanca yükleme testleri güvenilmiş klasörde (#108; kapı: test_hooks_workspace_trust).
pytestmark = pytest.mark.usefixtures("guvenilir_klasor")

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


def test_sessionstart_girdisi_model_agent_type_ve_baslik(tmp_path):
    """Claude SessionStart girdisi: model, agent_type, session_title; /clear'da model yok."""
    import asyncio

    from fusion_cli.core.hooks.events import HookSet
    from fusion_cli.engines.hooks.session import HookSession

    session = HookSession(root=tmp_path, loader=HookSet, model=lambda: "anthropic/claude-x")
    session.agent_type = "inceleyici"
    session.session_title = "hata avı"
    assert asyncio.run(session._start_fields("startup")) == {
        "source": "startup",
        "model": "anthropic/claude-x",
        "agent_type": "inceleyici",
        "session_title": "hata avı",
    }
    assert "model" not in asyncio.run(session._start_fields("clear"))
    asyncio.run(session.start("fork"))
    assert session.started


def test_branch_sonrasi_sessionstart_kaynagi_fork(tmp_path):
    import contextlib

    from fusion_cli.cli.repl import session_resume

    state = type("S", (), {})()
    state.hook_start_source = ""
    # Oturum alanı (#189, #205) apply_target'ın ilk satırında açılmış sohbetleri işaretler; sahte
    # durum bunu taşımazsa kaynak atanmadan AttributeError ile çıkılıyordu.
    state.opened_conversations = frozenset()
    state.conversation_id = "eski"
    target = session_resume.ResumeTarget("yeni", (), "başlık", forked_from="eski")
    # Sahte durum yalnız kaynağı taşır; sonraki adımlar (PR künyesi) burada önemsiz.
    with contextlib.suppress(AttributeError):
        session_resume.apply_target(state, target)
    assert state.hook_start_source == "fork"
