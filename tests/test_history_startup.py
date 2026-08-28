"""Açılıştaki son oturum listesi."""

from __future__ import annotations

import json
import os

from fusion_cli.cli.repl.history_view import render_recent


def _claude_kur(home, session_id, metin, mtime):
    hedef = home / ".claude" / "projects" / "-x"
    hedef.mkdir(parents=True, exist_ok=True)
    yol = hedef / f"{session_id}.jsonl"
    yol.write_text(
        json.dumps({"type": "user", "message": {"role": "user", "content": metin}}),
        encoding="utf-8",
    )
    os.utime(yol, (mtime, mtime))


def test_oturum_yoksa_bos_doner(tmp_path):
    assert render_recent(tmp_path, tmp_path / "proje") == ""


def test_oturumlar_kaynak_etiketiyle_listelenir(tmp_path):
    _claude_kur(tmp_path, "s1", "ilk iş", 1000)

    cikti = render_recent(tmp_path, tmp_path / "proje")

    assert "ilk iş" in cikti
    assert "claude" in cikti


def test_en_fazla_bes_oturum_gosterilir(tmp_path):
    for i in range(9):
        _claude_kur(tmp_path, f"s{i}", f"iş {i}", 1000 + i)

    cikti = render_recent(tmp_path, tmp_path / "proje")

    assert len([s for s in cikti.splitlines() if s.startswith("  ")]) == 5
