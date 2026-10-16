"""Piper modelini süreçte sıcak tutan, sınırlı ve sıralı sentez sınırı."""

from __future__ import annotations

import io
import threading
import wave
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from piper import PiperVoice


@lru_cache(maxsize=1)
def _loaded_voice(model: str, model_stamp: int, config_stamp: int) -> PiperVoice:
    """Tek model tutulur; dosya güncellenirse eski örnek bırakılır."""
    # Üçüncü taraf Piper'ın tip stubları yoktur; Any yalnız bu sınırdadır.
    from piper import PiperVoice

    return PiperVoice.load(model)


@lru_cache(maxsize=1)
def _synthesis_lock() -> threading.RLock:
    """Fonemleyici ve model aynı süreçte eşzamanlı kullanılmaz."""
    return threading.RLock()


# Kısa konuşma cevapları bellekte sınırlı tutulur; WAV dosyası paylaşılmaz.
SHORT_REPLY_CHARS = 160
SHORT_REPLY_CACHE_SIZE = 16


@lru_cache(maxsize=SHORT_REPLY_CACHE_SIZE)
def _short_audio(
    text: str,
    model: str,
    model_stamp: int,
    config_stamp: int,
    length_scale: float,
    noise_w_scale: float,
) -> bytes:
    from piper import SynthesisConfig

    voice = _loaded_voice(model, model_stamp, config_stamp)
    config = SynthesisConfig(length_scale=length_scale, noise_w_scale=noise_w_scale)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as stream:
        voice.synthesize_wav(text, stream, syn_config=config)
    return buffer.getvalue()


def synthesize_piper(text: str, model: Path, output: Path, settings: dict[str, Any]) -> None:
    """Yeni CLI açmadan üret; aynı kısa cevabın sesini ayar/model değişene kadar koru."""
    with _synthesis_lock():
        render = _short_audio if len(text) <= SHORT_REPLY_CHARS else _short_audio.__wrapped__
        audio = render(
            text,
            str(model),
            model.stat().st_mtime_ns,
            model.with_suffix(".onnx.json").stat().st_mtime_ns,
            settings["length_scale"],
            settings["noise_w_scale"],
        )
    output.write_bytes(audio)
