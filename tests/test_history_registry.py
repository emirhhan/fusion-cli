"""Kurulu geçmiş kaynaklarının tespiti."""

from __future__ import annotations

import json

from fusion_cli.history.registry import available_sources, recent_sessions, source_by_name


def _claude_kur(home, slug=None, session_id="s1", metin="merhaba", mtime=None):
    if slug is None:
        slug = str(home / "proje").replace("/", "-")
    hedef = home / ".claude" / "projects" / slug
    hedef.mkdir(parents=True, exist_ok=True)
    yol = hedef / f"{session_id}.jsonl"
    yol.write_text(
        json.dumps({"type": "user", "message": {"role": "user", "content": metin}}),
        encoding="utf-8",
    )
    if mtime is not None:
        import os

        os.utime(yol, (mtime, mtime))
    return yol


def test_hicbir_arac_yoksa_kaynak_yok(tmp_path):
    assert available_sources(tmp_path) == ()


def test_yalniz_kurulu_kaynak_donder(tmp_path):
    _claude_kur(tmp_path)

    adlar = [s.name for s in available_sources(tmp_path)]

    assert adlar == ["claude"]


def test_ada_gore_cozer(tmp_path):
    _claude_kur(tmp_path)

    assert source_by_name(tmp_path, "claude") is not None
    assert source_by_name(tmp_path, "hermes") is None


def test_son_oturumlar_limitle_kirpilir(tmp_path):
    for i in range(7):
        _claude_kur(tmp_path, session_id=f"s{i}", metin=f"m{i}", mtime=1000 + i)

    refs = recent_sessions(tmp_path, tmp_path / "proje", limit=5)

    assert len(refs) == 5


def test_son_oturumlar_yeniden_eskiye_sirali(tmp_path):
    _claude_kur(tmp_path, session_id="eski", metin="eski", mtime=1000)
    _claude_kur(tmp_path, session_id="yeni", metin="yeni", mtime=2000)

    refs = recent_sessions(tmp_path, tmp_path / "proje")

    assert refs[0].session_id == "yeni"


def test_recent_sessions_limiti_adaptore_gecirir(tmp_path, monkeypatch):
    """`recent_sessions`, `limit`'i her kaynağın `list()` çağrısına GEÇİRMELİ —
    yalnızca harmanlanmış sonucu kırpmamalı. Bu, adapter'ların gereksiz
    ayrıştırmadan kaçınabilmesi için gereken sözleşmedir."""
    for i in range(7):
        _claude_kur(tmp_path, session_id=f"s{i}", metin=f"m{i}", mtime=1000 + i)

    from fusion_cli.history.claude_source import ClaudeSource

    seen_limits: list[int | None] = []
    original_list = ClaudeSource.list_for_root

    def _kaydeden_list(self, root=None, limit=None):
        seen_limits.append(limit)
        return original_list(self, root, limit)

    monkeypatch.setattr(ClaudeSource, "list_for_root", _kaydeden_list)

    recent_sessions(tmp_path, tmp_path / "proje", limit=3)

    assert seen_limits == [3]


def test_recent_sessions_birden_fazla_kaynak_harmanlaninca_dogru_sirali(tmp_path):
    """Birden fazla kaynak varken her kaynaktan `limit` kadar istenmeli; aksi
    halde bir kaynağın gerçekte en yeni oturumlarından biri harmanlanmış
    sonuçtan haksız yere dışlanabilir."""
    import sqlite3

    _claude_kur(tmp_path, session_id="claude-eski", metin="c-eski", mtime=100)

    # Hermes kaynağını kur: en yeni oturum onda.
    kok = tmp_path / ".hermes"
    kok.mkdir(parents=True, exist_ok=True)
    baglanti = sqlite3.connect(kok / "state.db")
    baglanti.executescript(
        "CREATE TABLE sessions (id TEXT PRIMARY KEY, source TEXT, title TEXT, cwd TEXT, "
        "started_at REAL NOT NULL, message_count INTEGER DEFAULT 0);"
        "CREATE TABLE messages (id TEXT PRIMARY KEY, session_id TEXT, role TEXT, "
        "content TEXT, timestamp REAL);"
    )
    baglanti.execute(
        "INSERT INTO sessions VALUES (?,?,?,?,?,?)",
        ("hermes-yeni", "cli", "h-yeni", str(tmp_path / "proje"), 999.0, 0),
    )
    baglanti.commit()
    baglanti.close()

    refs = recent_sessions(tmp_path, tmp_path / "proje", limit=1)

    assert [r.session_id for r in refs] == ["hermes-yeni"]


def test_recent_sessions_isolates_a_corrupt_source(tmp_path, monkeypatch) -> None:
    from fusion_cli.history import registry
    from fusion_cli.history.models import SessionRef

    class BrokenSource:
        name = "broken"

        def list_for_root(self, root, limit=None):
            raise ValueError("bozuk kaynak")

    class HealthySource:
        name = "healthy"

        def list_for_root(self, root, limit=None):
            return (SessionRef("healthy", "h1", "sağlam", 10.0),)

    monkeypatch.setattr(
        registry,
        "available_sources",
        lambda _home: (BrokenSource(), HealthySource()),
    )

    refs = recent_sessions(tmp_path, tmp_path / "proje")

    assert [ref.session_id for ref in refs] == ["h1"]
