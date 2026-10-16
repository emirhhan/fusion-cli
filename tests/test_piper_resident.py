"""Ardışık cümlelerde model yüklemesi tekrarlanmaz."""

from __future__ import annotations

import os
import sys
import types
from unittest.mock import Mock

import pytest

from fusion_cli.appserver.piper_synthesis import synthesize_piper


def install_fake_piper(monkeypatch):
    engine = Mock()

    def write_audio(text, stream, syn_config):
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(22050)
        stream.writeframes(b"\0\0")

    engine.synthesize_wav.side_effect = write_audio
    load = Mock(return_value=engine)
    monkeypatch.setitem(
        sys.modules,
        "piper",
        types.SimpleNamespace(
            PiperVoice=types.SimpleNamespace(load=load),
            SynthesisConfig=lambda **kwargs: kwargs,
        ),
    )
    return load, engine


def create_model(tmp_path):
    model = tmp_path / "voice.onnx"
    model.write_bytes(b"model")
    model.with_suffix(".onnx.json").write_text("{}")
    return model


def test_reuses_loaded_model_and_applies_new_settings(tmp_path, monkeypatch):
    model = create_model(tmp_path)
    load, engine = install_fake_piper(monkeypatch)
    for speed in [1.0, 0.736]:
        synthesize_piper(
            "Merhaba",
            model,
            tmp_path / "out.wav",
            {
                "length_scale": speed,
                "noise_w_scale": 0.9,
            },
        )
    assert load.call_count == 1
    assert engine.synthesize_wav.call_count == 2
    assert engine.synthesize_wav.call_args.kwargs["syn_config"]["length_scale"] == 0.736


@pytest.mark.parametrize("changed", ["model", "config"])
def test_reloads_when_model_or_config_changes(tmp_path, monkeypatch, changed):
    model = create_model(tmp_path)
    load, _engine = install_fake_piper(monkeypatch)
    settings = {"length_scale": 0.736, "noise_w_scale": 0.9}
    synthesize_piper("Merhaba", model, tmp_path / "out.wav", settings)
    target = model if changed == "model" else model.with_suffix(".onnx.json")
    stamp = target.stat()
    os.utime(target, ns=(stamp.st_atime_ns, stamp.st_mtime_ns + 1_000_000))
    synthesize_piper("Merhaba", model, tmp_path / "out.wav", settings)
    assert load.call_count == 2


def test_synthesis_failure_removes_partial_wav(tmp_path, monkeypatch):
    from fusion_cli.appserver import piper_synthesis, voice

    generated = []

    def fail(text, model, output, settings):
        generated.append(output)
        output.write_bytes(b"partial")
        raise RuntimeError("test")

    monkeypatch.setattr(piper_synthesis, "synthesize_piper", fail)
    result = voice._speak_with_piper("Merhaba", tmp_path / "model.onnx")
    assert result["ok"] is False
    assert generated and not generated[0].exists()


def test_identical_short_reply_reuses_audio_with_owned_output_files(tmp_path, monkeypatch):
    model = create_model(tmp_path)
    _load, engine = install_fake_piper(monkeypatch)
    settings = {"length_scale": 0.92, "noise_w_scale": 0.9}
    first, second = tmp_path / "first.wav", tmp_path / "second.wav"
    synthesize_piper("Buradayım, seni dinliyorum.", model, first, settings)
    synthesize_piper("Buradayım, seni dinliyorum.", model, second, settings)
    assert engine.synthesize_wav.call_count == 1
    assert first.read_bytes() == second.read_bytes()
    first.unlink()
    assert second.is_file()


def test_voice_warmup_prepares_catalog_without_starting_player(tmp_path, monkeypatch):
    from fusion_cli.appserver import piper_synthesis, voice

    model = create_model(tmp_path)
    monkeypatch.setattr(voice, "active_model_path", lambda: model)
    monkeypatch.setattr(
        voice, "load_settings", lambda: {"length_scale": 0.92, "noise_w_scale": 0.9}
    )
    rendered = []

    def synthesize(text, model, output, settings):
        rendered.append(text)
        output.write_bytes(b"wave")

    monkeypatch.setattr(piper_synthesis, "synthesize_piper", synthesize)
    monkeypatch.setattr(
        voice, "_spawn_speech_process", Mock(side_effect=AssertionError("Isıtma ses çalamaz"))
    )
    result = voice.warm_voice(None)
    assert result["ok"] is True and len(set(rendered)) >= 4
