"""Ses nesli sahipliği: eski neslin hazır sesi yeni konuşmayı ne bekletir ne ezer."""

from __future__ import annotations

import threading
import time

import pytest

from fusion_cli.appserver import voice
from fusion_cli.appserver.prepared_voice import PreparedVoiceStore, StaleVoiceGenerationError


def _write(path):
    path.write_bytes(b"wav")


def test_yavas_sentez_baska_kaydin_alinmasini_ve_silinmesini_bekletmez(tmp_path):
    """Ölçüldü (29 Ekim): `prepare` sentez boyunca RLock tutuyor; kesme isteği (`take`/`discard`)
    saniyeler süren eski sentezin arkasında kuyruğa giriyordu."""
    store = PreparedVoiceStore(directory=tmp_path)
    ready = store.prepare(_write)
    release = threading.Event()
    started = threading.Event()

    def slow(path):
        started.set()
        release.wait(5)
        _write(path)

    worker = threading.Thread(target=lambda: store.prepare(slow), daemon=True)
    worker.start()
    assert started.wait(2)
    done = threading.Event()

    def interrupt():
        store.discard(ready)
        done.set()

    threading.Thread(target=interrupt, daemon=True).start()
    try:
        assert done.wait(1.0), "discard yavaş sentezin arkasında takıldı"
    finally:
        release.set()
        worker.join(5)


def test_yavas_sentez_sirasinda_kapasite_asilmaz(tmp_path):
    store = PreparedVoiceStore(directory=tmp_path)
    release = threading.Event()
    started = threading.Event()

    def slow(path):
        started.set()
        release.wait(5)
        _write(path)

    first = threading.Thread(target=lambda: store.prepare(slow), daemon=True)
    first.start()
    assert started.wait(2)
    store.prepare(_write)
    with pytest.raises(RuntimeError):
        store.prepare(_write)
    release.set()
    first.join(5)


def test_yeni_nesil_eski_nesil_hazir_dosyalarini_dusurur(tmp_path):
    store = PreparedVoiceStore(directory=tmp_path)
    old_a = store.prepare(_write, generation=1)
    old_b = store.prepare(_write, generation=1)
    new = store.prepare(_write, generation=2)  # kapasite eski nesille dolu olsa da girer
    assert store.take(old_a, generation=1) is None
    assert store.take(old_b, generation=1) is None
    path = store.take(new, generation=2)
    assert path is not None and path.exists()
    assert len(list(tmp_path.iterdir())) == 1


def test_eski_nesil_hazirlama_reddedilir_ve_dosya_birakmaz(tmp_path):
    store = PreparedVoiceStore(directory=tmp_path)
    store.prepare(_write, generation=5)
    with pytest.raises(StaleVoiceGenerationError):
        store.prepare(_write, generation=4)
    assert len(list(tmp_path.iterdir())) == 1


def test_sentez_sirasinda_yeni_nesil_gelirse_biten_eski_dosya_atilir(tmp_path):
    store = PreparedVoiceStore(directory=tmp_path)
    release = threading.Event()
    started = threading.Event()
    result: list[object] = []

    def slow(path):
        started.set()
        release.wait(5)
        _write(path)

    def run():
        try:
            result.append(store.prepare(slow, generation=1))
        except StaleVoiceGenerationError as error:
            result.append(error)

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    assert started.wait(2)
    store.prepare(_write, generation=2)
    release.set()
    worker.join(5)
    assert isinstance(result[0], StaleVoiceGenerationError)
    assert len(list(tmp_path.iterdir())) == 1


def test_eski_nesil_oynatma_istegi_yeni_konusmayi_ezmez(tmp_path, monkeypatch):
    """Ölçüldü (29 Ekim): çekirdekte nesil kimliği yoktu; geç gelen eski `haziri_cal`,
    yeni konuşmanın sürecini `_register_speech_process` ile durdurup kendini çalardı."""
    store = PreparedVoiceStore(directory=tmp_path)
    monkeypatch.setattr(voice, "_prepared_store", lambda: store)
    played: list[object] = []
    monkeypatch.setattr(voice, "_play_wav_file", lambda path: played.append(path) or {"ok": True})
    old = store.prepare(_write, generation=1)
    new = store.prepare(_write, generation=2)
    stale = voice.play_prepared_voice(old, generation=1)
    assert stale["ok"] is False and stale["eski_nesil"] is True
    assert played == []
    assert voice.play_prepared_voice(new, generation=2)["ok"] is True
    assert len(played) == 1


def test_nesilsiz_cagri_eski_sozlesmeyle_calisir(tmp_path, monkeypatch):
    store = PreparedVoiceStore(directory=tmp_path)
    monkeypatch.setattr(voice, "_prepared_store", lambda: store)
    monkeypatch.setattr(voice, "_play_wav_file", lambda path: {"ok": True})
    token = store.prepare(_write)
    assert voice.play_prepared_voice(token)["ok"] is True


def test_discard_yavas_olmayan_yolda_hizli(tmp_path):
    store = PreparedVoiceStore(directory=tmp_path)
    token = store.prepare(_write)
    started = time.monotonic()
    store.discard(token)
    assert time.monotonic() - started < 0.5
