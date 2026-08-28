"""Kurulu geçmiş kaynaklarının tespiti."""

from __future__ import annotations

import json

from fusion_cli.history.registry import available_sources, recent_sessions, source_by_name


def _claude_kur(home, slug="-x", session_id="s1", metin="merhaba", mtime=None):
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
