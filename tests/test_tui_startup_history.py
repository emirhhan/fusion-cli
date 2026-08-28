"""TUI açılışında son oturum listesinin basılması.

`history_view.render_recent` düz konsol REPL'inde zaten test edilmişti
(`tests/test_history_startup.py`), ama TUI yüzeyi (`tui_loop.run_tui_repl`)
banner'ı ayrı basıyor ve listeyi hiç çağırmıyordu — yani varsayılan yüzeyde
özellik görünmüyordu. Bu test `_print_startup` üzerinden gerçek TUI oturumunu
(`_TuiSession`) kurup konuşma transkriptini doğrudan denetler; sahte bir
konsol nesnesine değil, gerçek `FusionTui` akışına dayanır.
"""

from __future__ import annotations

import json
import os

from fusion_cli.cli.repl.state import ReplState
from fusion_cli.cli.repl.tui_loop import _print_startup, _TuiSession
from fusion_cli.memory.factory import null_memory

from .fakes import make_config


def _claude_kur(home, session_id, metin, mtime):
    hedef = home / ".claude" / "projects" / "-x"
    hedef.mkdir(parents=True, exist_ok=True)
    yol = hedef / f"{session_id}.jsonl"
    yol.write_text(
        json.dumps({"type": "user", "message": {"role": "user", "content": metin}}),
        encoding="utf-8",
    )
    os.utime(yol, (mtime, mtime))


def _state(tmp_path, home) -> ReplState:
    return ReplState(config=make_config(), memory=null_memory(), root=tmp_path, home=home)


def test_tui_acilisinda_oturum_varsa_liste_basilir(tmp_path):
    home = tmp_path / "home"
    root = tmp_path / "proje"
    root.mkdir()
    _claude_kur(home, "s1", "ilk iş", 1000)
    state = _state(root, home)
    session = _TuiSession(state)

    _print_startup(session, state)

    assert "ilk iş" in session.tui.transcript
    assert "son oturumlar" in session.tui.transcript


def test_tui_acilisinda_oturum_yoksa_hicbir_sey_basilmaz(tmp_path):
    home = tmp_path / "home"
    root = tmp_path / "proje"
    root.mkdir()
    home.mkdir()
    state = _state(root, home)
    session = _TuiSession(state)

    _print_startup(session, state)

    assert "son oturumlar" not in session.tui.transcript
