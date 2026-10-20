"""EMA Lightning ONNX sentezi: gerçek model, gerçek ses (ağ yok, PyTorch yok)."""

from __future__ import annotations

import io
import sys
import wave
from pathlib import Path

import numpy as np
import pytest

from fusion_cli.appserver import ema_synthesis as ema
from fusion_cli.appserver.ema_synthesis import EmaVoice, chunk_text, wav_bytes


@pytest.fixture(scope="module")
def voice() -> EmaVoice:
    return EmaVoice()


def test_torch_olmadan_yuklenir() -> None:
    assert "torch" not in sys.modules


def test_cumle_sese_donusur_sessiz_degildir_ve_sure_makuldur(voice: EmaVoice) -> None:
    audio = voice.synthesize("Merhaba, ben Fusion. Bugün size nasıl yardımcı olabilirim?", seed=1)
    seconds = len(audio) / ema.SAMPLE_RATE
    assert audio.dtype == np.float32 and 2.0 < seconds < 6.0
    assert 0.1 < float(np.abs(audio).max()) <= 1.0
    assert float(np.sqrt((audio**2).mean())) > 0.01
    assert not np.isnan(audio).any()


def test_ayni_tohum_ayni_ses_farkli_tohum_farkli_ses(voice: EmaVoice) -> None:
    first = voice.synthesize("Dosyalar kaydedildi.", seed=3)
    again = voice.synthesize("Dosyalar kaydedildi.", seed=3)
    other = voice.synthesize("Dosyalar kaydedildi.", seed=4)
    assert np.array_equal(first, again)
    assert first.shape != other.shape or not np.array_equal(first, other)


def test_hiz_sureyi_ters_orantili_degistirir(voice: EmaVoice) -> None:
    text = "Proje testleri başarıyla tamamlandı ve rapor hazır."
    slow = len(voice.synthesize(text, speed=0.8, seed=1))
    fast = len(voice.synthesize(text, speed=1.5, seed=1))
    assert fast < slow * 0.8


def test_sayilar_ve_tarihler_okunur(voice: EmaVoice) -> None:
    spoken = voice._frontend("5 TL ve 12.10.2026")
    assert "beş türk lirası" in spoken and "ekim" in spoken and not any(c.isdigit() for c in spoken)


def test_bos_metin_sessiz_semboller_okunur(voice: EmaVoice) -> None:
    assert len(voice.synthesize("   ")) == 0
    assert len(voice.synthesize("")) == 0
    assert len(voice.synthesize("---")) == 0  # yalnız noktalama: okunacak harf yok
    # normalizer-tr "fallback" ilkesi: bilinen simgeyi atmaz, adıyla okur.
    assert len(voice.synthesize("*")) > 0


def test_uzun_metin_parcalanir_ve_birlestirilir(voice: EmaVoice) -> None:
    text = "Bu bir deneme cümlesidir. " * 14
    pieces = chunk_text(voice._frontend(text), 1.0)
    assert len(pieces) >= 2 and pieces[-1][1] == 0.0
    assert all(piece.endswith((".", "!", "?")) for piece, _ in pieces)
    audio = voice.synthesize(text, seed=1)
    assert len(audio) / ema.SAMPLE_RATE > 15


def test_wav_gecerli_ve_48khz_mono() -> None:
    data = wav_bytes(np.zeros(4800, dtype=np.float32))
    with wave.open(io.BytesIO(data)) as stream:
        assert (stream.getnchannels(), stream.getsampwidth(), stream.getframerate()) == (
            1,
            2,
            48_000,
        )
        assert stream.getnframes() == 4800


def test_yarim_kurulum_hazir_sayilmaz(tmp_path: Path) -> None:
    for name in ("text.onnx", "meta.json"):
        (tmp_path / name).write_bytes(b"x")
    assert ema.is_installed(tmp_path) is False
    with pytest.raises(ema.EmaUnavailableError):
        EmaVoice(tmp_path)


def test_synthesize_ema_dosyaya_yazar_ve_kisa_cevabi_onbellekler(tmp_path: Path) -> None:
    out = tmp_path / "a.wav"
    ema._short_wav.cache_clear()
    ema.synthesize_ema("Tamamdır.", out, 1.0)
    assert out.stat().st_size > 1000
    ema.synthesize_ema("Tamamdır.", tmp_path / "b.wav", 1.0)
    assert ema._short_wav.cache_info().hits == 1
    assert (tmp_path / "b.wav").read_bytes() == out.read_bytes()


def test_ema_say_komutu_wav_uretir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from fusion_cli.cli.app import ema_say

    monkeypatch.setattr(sys, "stdin", io.StringIO("Merhaba"))
    ema_say(str(tmp_path / "say.wav"))
    with wave.open(str(tmp_path / "say.wav")) as stream:
        assert stream.getnframes() > 10_000
