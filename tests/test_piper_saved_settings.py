"""Paketli Piper alt komutu kayıtlı tercihi gerçekten uygular."""

from __future__ import annotations

import io
import sys
import types

from fusion_cli.appserver import voice
from fusion_cli.cli.app import piper_say


def test_packaged_piper_uses_saved_speed_and_timbre(tmp_path, monkeypatch):
    monkeypatch.setattr(voice, "_data_home", lambda: tmp_path)
    voice.save_settings({"hiz": 1.25, "robotik": 0.25})
    captured = {}

    class FakeVoice:
        @classmethod
        def load(cls, model):
            return cls()

        def synthesize_wav(self, text, stream, syn_config):
            captured.update(syn_config)
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(22050)
            stream.writeframes(b"\0\0")

    monkeypatch.setitem(
        sys.modules,
        "piper",
        types.SimpleNamespace(
            PiperVoice=FakeVoice,
            SynthesisConfig=lambda **kwargs: kwargs,
        ),
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO("Merhaba"))
    piper_say("model.onnx", str(tmp_path / "voice.wav"))
    expected = voice.load_settings()
    assert captured["length_scale"] == expected["length_scale"]
    assert captured["noise_w_scale"] == expected["noise_w_scale"]
