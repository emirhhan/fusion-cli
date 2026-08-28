"""Açılıştaki son oturum listesi."""

from __future__ import annotations

import json
import os
import sqlite3

from fusion_cli.cli.repl.history_view import render_recent


def _claude_kur(home, session_id, metin, mtime):
    hedef = home / ".claude" / "projects" / str(home / "proje").replace("/", "-")
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


def test_startup_excludes_sessions_from_other_roots(tmp_path) -> None:
    _claude_kur(tmp_path, "hedef", "hedef iş", 1_000)
    other = tmp_path / ".claude" / "projects" / str(tmp_path / "başka").replace("/", "-")
    other.mkdir(parents=True)
    path = other / "diger.jsonl"
    path.write_text(
        json.dumps({"type": "user", "message": {"role": "user", "content": "başka iş"}}),
        encoding="utf-8",
    )
    os.utime(path, (2_000, 2_000))

    output = render_recent(tmp_path, tmp_path / "proje")

    assert "hedef iş" in output
    assert "başka iş" not in output


def test_startup_excludes_codex_without_proven_project_ownership(tmp_path) -> None:
    codex = tmp_path / ".codex"
    codex.mkdir(parents=True)
    connection = sqlite3.connect(codex / "thread_history_1.sqlite")
    connection.execute("CREATE TABLE placeholder (id TEXT)")
    connection.close()
    (codex / "session_index.jsonl").write_text(
        json.dumps({"id": "c1", "thread_name": "kanıtsız Codex", "updated_at": "2026-01-01"}),
        encoding="utf-8",
    )

    output = render_recent(tmp_path, tmp_path / "proje")

    assert "kanıtsız Codex" not in output


def test_startup_includes_only_exact_hermes_root(tmp_path) -> None:
    hermes = tmp_path / ".hermes"
    hermes.mkdir(parents=True)
    connection = sqlite3.connect(hermes / "state.db")
    connection.executescript(
        "CREATE TABLE sessions (id TEXT PRIMARY KEY, source TEXT, title TEXT, cwd TEXT, "
        "started_at REAL NOT NULL, message_count INTEGER DEFAULT 0);"
        "CREATE TABLE messages (id TEXT PRIMARY KEY, session_id TEXT, role TEXT, "
        "content TEXT, timestamp REAL);"
    )
    connection.executemany(
        "INSERT INTO sessions VALUES (?,?,?,?,?,?)",
        [
            ("hedef", "cli", "hedef Hermes", str(tmp_path / "proje"), 1_000.0, 0),
            ("diger", "cli", "başka Hermes", str(tmp_path / "başka"), 2_000.0, 0),
        ],
    )
    connection.commit()
    connection.close()

    output = render_recent(tmp_path, tmp_path / "proje")

    assert "hedef Hermes" in output
    assert "başka Hermes" not in output
