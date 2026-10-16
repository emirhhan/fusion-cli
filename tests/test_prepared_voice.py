"""Hazır ses dosyası sahipliği, sınırı ve iptal temizliği."""

from __future__ import annotations

import pytest

from fusion_cli.appserver.prepared_voice import PreparedVoiceStore


def test_take_and_discard_own_files_only(tmp_path):
    store = PreparedVoiceStore(directory=tmp_path)
    token = store.prepare(lambda path: path.write_bytes(b"wav"))
    assert store.take("unknown") is None
    path = store.take(token)
    assert path and path.read_bytes() == b"wav"
    assert store.take(token) is None
    path.unlink()
    token = store.prepare(lambda path: path.write_bytes(b"wav"))
    store.discard(token)
    assert not list(tmp_path.iterdir())


def test_bounded_and_failed_render_leaves_no_file(tmp_path):
    store = PreparedVoiceStore(directory=tmp_path)
    first = store.prepare(lambda path: path.write_bytes(b"wav"))
    second = store.prepare(lambda path: path.write_bytes(b"wav"))
    with pytest.raises(RuntimeError):
        store.prepare(lambda path: path.write_bytes(b"wav"))
    store.close()
    assert store.take(first) is None and store.take(second) is None

    def fail(path):
        path.write_bytes(b"partial")
        raise ValueError("test")

    with pytest.raises(ValueError):
        store.prepare(fail)
    assert not list(tmp_path.iterdir())
