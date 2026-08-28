"""Kurulu kaynaklara göre eklenen /resume komutları."""

from __future__ import annotations

import json

from fusion_cli.cli.repl.commands import build_registry
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.cli.repl.tui_loop import _TuiSession
from fusion_cli.memory.factory import null_memory

from .fakes import make_config


def _claude_kur(home):
    hedef = home / ".claude" / "projects" / "-x"
    hedef.mkdir(parents=True, exist_ok=True)
    (hedef / "s1.jsonl").write_text(
        json.dumps({"type": "user", "message": {"role": "user", "content": "merhaba"}}),
        encoding="utf-8",
    )


def _state(tmp_path) -> ReplState:
    return ReplState(config=make_config(), memory=null_memory(), root=tmp_path, home=tmp_path)


def test_home_verilmezse_resume_komutu_yok():
    registry = build_registry()

    assert registry.get("resumeclaude") is None


def test_kurulu_kaynak_icin_komut_eklenir(tmp_path):
    _claude_kur(tmp_path)

    registry = build_registry(tmp_path)

    assert registry.get("resumeclaude") is not None


def test_kurulmamis_kaynak_icin_komut_hic_yok(tmp_path):
    _claude_kur(tmp_path)

    registry = build_registry(tmp_path)

    assert registry.get("resumehermes") is None
    assert "/resumehermes" not in registry.completion_words()


def test_komut_tamamlamada_gorunur(tmp_path):
    _claude_kur(tmp_path)

    registry = build_registry(tmp_path)

    assert "/resumeclaude" in registry.completion_words()


def test_komut_gecmis_grubunda(tmp_path):
    _claude_kur(tmp_path)

    komut = build_registry(tmp_path).get("resumeclaude")

    assert komut is not None
    assert komut.group == "Geçmiş"


def test_argumanla_cagrilinca_secici_acmadan_devralir(tmp_path):
    """Argüman (session_id) doluysa seçici AÇILMAZ — betiklenebilir/TUI yolu."""
    _claude_kur(tmp_path)
    registry = build_registry(tmp_path)
    komut = registry.get("resumeclaude")
    assert komut is not None
    state = _state(tmp_path)

    sonuc = komut.handler(state, "s1")

    assert state.pending_digest is not None
    assert "merhaba" in state.pending_digest
    assert "devral" in sonuc.lower()


def test_bilinmeyen_session_id_devralmaz(tmp_path):
    _claude_kur(tmp_path)
    registry = build_registry(tmp_path)
    komut = registry.get("resumeclaude")
    assert komut is not None
    state = _state(tmp_path)

    sonuc = komut.handler(state, "olmayan-oturum")

    assert state.pending_digest is None
    assert sonuc == messages_history_empty()


def messages_history_empty() -> str:
    from fusion_cli.ui import messages

    return messages.HISTORY_EMPTY


def test_bos_argumanla_ve_tty_yokken_vazgecilir(tmp_path, monkeypatch):
    """Argümansız çağrı (düz konsol yolu) TTY yokken düz listeye düşer; boş cevap
    vazgeçme sayılır ve devralma OLMAZ."""
    _claude_kur(tmp_path)
    registry = build_registry(tmp_path)
    komut = registry.get("resumeclaude")
    assert komut is not None
    state = _state(tmp_path)

    from fusion_cli.ui import picker

    monkeypatch.setattr(picker.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr("builtins.input", lambda: "")

    sonuc = komut.handler(state, "")

    assert state.pending_digest is None
    assert sonuc == ""


async def test_tui_resume_komutu_modalda_secilen_session_id_argumana_gecer(tmp_path):
    """TUI'de argümansız /resumeclaude modal açar (nested picker DEĞİL); modaldan
    dönen session_id gerçekten işleyiciye argüman olarak geçer ve devralma olur."""
    import asyncio

    _claude_kur(tmp_path)
    state = _state(tmp_path)
    session = _TuiSession(state)

    task = asyncio.ensure_future(session._command("/resumeclaude"))
    await asyncio.sleep(0)
    assert session.tui._mode == "choice"  # uygulama-içi modal, nested picker değil
    session.tui._resolve("s1")
    await task

    assert state.pending_digest is not None
    assert "merhaba" in state.pending_digest


async def test_tui_resume_komutunda_vazgecilirse_devralma_olmaz(tmp_path):
    import asyncio

    _claude_kur(tmp_path)
    state = _state(tmp_path)
    session = _TuiSession(state)

    task = asyncio.ensure_future(session._command("/resumeclaude"))
    await asyncio.sleep(0)
    assert session.tui._mode == "choice"
    session.tui._resolve(None)
    await task

    assert state.pending_digest is None


def test_duz_repl_yuzeyi_de_ev_dizinini_gecirir():
    """Her kullanıcı yüzeyi kayıt defterini ev dizini ile kurmalı.

    Regresyon: düz konsol REPL (`FUSION_INLINE=1`) `build_registry()`'yi
    argümansız çağırıyordu; kurulu araç olsa bile o yüzeyde `/resume<kaynak>`
    komutları hiç kaydolmuyordu. Hata tek bir çağrı yerindeydi ve testler
    `build_registry`'yi doğrudan çağırdığı için görünmüyordu.
    """
    import inspect

    from fusion_cli.cli.repl import loop

    kaynak = inspect.getsource(loop)

    # Değişmez: bu modülde ARGÜMANSIZ çağrı kalmamalı. Hangi ifadeyle geçirildiği
    # serbesttir; asıl kural ev dizininin geçiriliyor olmasıdır.
    assert "build_registry()" not in kaynak, "kayıt defteri ev dizinsiz kuruluyor"
