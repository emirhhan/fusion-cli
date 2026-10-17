"""EMA Lightning (Türkçe, ~34 MB) ONNX ile sentez: PyTorch gerekmez.

Hat: metin ön yüzü → harf süreleri (text.onnx) → kare zaman çizelgesi → akış-eşleme
adımları (sound.onnx) → pencere pencere ses (decoder.onnx). Ağırlıklar ve mantık Canberk
Aslan'ın Apache-2.0 `ema-lightning` projesinden uyarlanmıştır (bkz. `data/ema/NOTICE`).
"""

from __future__ import annotations

import io
import itertools
import re
import threading
import unicodedata
import wave
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

DATA_DIRECTORY = Path(__file__).parent / "data" / "ema"
MODEL_FILES = ("text.onnx", "sound.onnx", "decoder.onnx", "meta.json")

SAMPLE_RATE = 48_000
FRAMES_PER_SECOND = 25
FIRST_WINDOW = 25  # ilk pencere 1 sn: ilk ses çabuk gelsin
WINDOW = 100  # sonraki pencereler 4 sn
CONTEXT = 8  # pencerenin iki yanında kod çözülen ek kare
MAX_WORD_FRAMES = 250
MAX_FRAMES = 3000
SPEED_RANGE = (0.25, 4.0)

# Parçalama: ~10 sn'lik konuşma tek parça kalır; uzun metin cümle/yan cümle sınırında bölünür.
LETTERS_PER_SECOND = 18.0
MAX_SECONDS = 10.0
MAX_LETTERS = 250
SENTENCE_PAUSE = 0.25
CLAUSE_PAUSE = 0.12
_CUTS = (
    (re.compile(r"[.!?]+[\"')]*(?= )"), SENTENCE_PAUSE),
    (re.compile(r"[,;:](?= )"), CLAUSE_PAUSE),
    (re.compile(r"\S(?= )"), CLAUSE_PAUSE),
)
_LETTER = re.compile(r"[^\W\d_]")

_TURKISH = frozenset("çğıöşüÇĞİÖŞÜ")
_TYPOGRAPHY = str.maketrans(
    {
        "’": "'", "‘": "'", "ʼ": "'", "´": "'", "`": "'",
        "“": '"', "”": '"', "„": '"', "«": '"', "»": '"',
        "–": "-", "—": "-", "−": "-", "…": "...",
    }
)  # fmt: skip
_UNSAFE = re.compile("[\x00-\x08\x0b-\x1f\x7f-\x9f؜‎‏‪-‮⁦-⁩]")
_BLOCK_BYTES = 8 * 1024
_NORMALIZER_POLICY = "fallback"


class EmaUnavailableError(RuntimeError):
    """Model dosyaları ya da çalışma bağımlılıkları eksik; mesaj kullanıcıya gösterilebilir."""


def model_directory() -> Path:
    return DATA_DIRECTORY


def is_installed(directory: Path | None = None) -> bool:
    """Üç ONNX dosyası ve meta birlikte varsa kurulu sayılır (yarım kurulum kurulu değildir)."""
    root = directory or DATA_DIRECTORY
    return all((root / name).is_file() for name in MODEL_FILES)


@dataclass(frozen=True, slots=True)
class _Meta:
    vocab: tuple[str, ...]
    times: tuple[float, ...]
    latent_dim: int
    hop: int


class TurkishFrontend:
    """Yazılı Türkçe → modelin kendi alfabesi. Metin üzerinde asla istisna fırlatmaz."""

    def __init__(self, vocab: tuple[str, ...]) -> None:
        self._vocab = frozenset(vocab)
        try:
            from normalizer_tr import Normalizer
        except ImportError as error:
            raise EmaUnavailableError(
                "Sayı/tarih okuma bileşeni (normalizer-tr) kurulu değil."
            ) from error
        self._normalizer = Normalizer()

    def __call__(self, text: str) -> str:
        text = _UNSAFE.sub(" ", text.encode("utf-8", "ignore").decode("utf-8"))
        if not text.strip():
            return ""
        return self._alphabet(" ".join(self._spoken(block) for block in _blocks(text)))

    def _spoken(self, text: str) -> str:
        try:
            return str(
                self._normalizer.normalize(
                    text, ambiguity_policy=_NORMALIZER_POLICY
                ).normalized_text
            )
        except Exception:
            return text

    def _alphabet(self, text: str) -> str:
        text = text.translate(_TYPOGRAPHY).replace("İ", "i").replace("I", "ı").lower()
        out: list[str] = []
        for char in text:
            if char not in _TURKISH:
                char = "".join(
                    c for c in unicodedata.normalize("NFKD", char) if not unicodedata.combining(c)
                )
            out.append(char if char and all(c in self._vocab for c in char) else " ")
        return re.sub(r"\s+", " ", "".join(out)).strip()


def _blocks(text: str) -> list[str]:
    blocks: list[str] = []
    current: list[str] = []
    size = 0
    for word in text.split():
        weight = len(word.encode("utf-8")) + 1
        if current and size + weight > _BLOCK_BYTES:
            blocks.append(" ".join(current))
            current, size = [], 0
        current.append(word)
        size += weight
    if current:
        blocks.append(" ".join(current))
    return blocks


def _finish(piece: str) -> str:
    """Her parçayı eğitimdeki gibi cümle sonuyla bitir."""
    if piece.rstrip("\"')")[-1:] in (".", "!", "?"):
        return piece
    return piece.rstrip(",;:- ") + "."


def chunk_text(text: str, speed: float) -> list[tuple[str, float]]:
    """[(parça, sonrasındaki sessizlik sn)]."""
    limit = int(min(MAX_LETTERS, LETTERS_PER_SECOND * MAX_SECONDS * speed))
    pieces: list[tuple[str, float]] = []
    rest = text.strip()
    while rest:
        cut, pause = len(rest), 0.0
        if len(rest) > limit:
            cut = limit
            for pattern, gap in _CUTS:
                ends = [m.end() for m in pattern.finditer(rest, 0, limit + 1)]
                if ends:
                    cut, pause = ends[-1], gap
                    break
        piece, rest = rest[:cut].strip(), rest[cut:].strip()
        if _LETTER.search(piece):
            pieces.append((_finish(piece), pause))
    if pieces:
        pieces[-1] = (pieces[-1][0], 0.0)
    return pieces


def _timeline(text: str, durations: np.ndarray) -> tuple[Any, ...]:
    """Harf süreleri → her karenin sözcüğü ve sözcük içi konumu (motorla aynı mantık)."""
    starts = [i for i, ch in enumerate(text) if ch != " " and (i == 0 or text[i - 1] == " ")] or [0]
    bounds = [0, *starts[1:], len(text)]
    letter_word = np.zeros(len(text), dtype=np.int64)
    word_start = np.zeros(len(text), dtype=np.int64)
    for index, (begin, end) in enumerate(itertools.pairwise(bounds)):
        letter_word[begin:end] = index
        word_start[begin:end] = begin
    words = int(letter_word[-1]) + 1
    per_word = np.zeros(words, dtype=np.float64)
    np.add.at(per_word, letter_word, durations[0].astype(np.float64))
    counts = np.clip(np.rint(per_word), 1, MAX_WORD_FRAMES).astype(np.int64)
    frames = min(int(counts.sum()), MAX_FRAMES)
    frame_word = np.repeat(np.arange(words), counts)[:frames]
    first = np.cumsum(counts) - counts
    frame_pos = ((np.arange(frames) - first[frame_word]) / counts[frame_word]).astype(np.float32)
    return letter_word, word_start, frame_word, frame_pos


class EmaVoice:
    """ONNX oturumlarını sıcak tutar; sentez tek iş parçacığında sıralıdır."""

    def __init__(self, directory: Path | None = None) -> None:
        root = directory or DATA_DIRECTORY
        if not is_installed(root):
            raise EmaUnavailableError("Ses modeli dosyaları eksik; uygulamayı yeniden kur.")
        try:
            # onnxruntime tip stub'ı yayımlamaz; Any yalnız bu sınırda kalır.
            import onnxruntime as ort  # type: ignore[import-untyped]
        except ImportError as error:
            raise EmaUnavailableError("onnxruntime kurulu değil.") from error
        import json

        raw = json.loads((root / "meta.json").read_text(encoding="utf-8"))
        self._meta = _Meta(
            vocab=tuple(raw["vocab"]),
            times=tuple(float(t) for t in raw["times"]),
            latent_dim=int(raw["latent_dim"]),
            hop=int(raw["hop"]),
        )
        options = ort.SessionOptions()
        options.intra_op_num_threads = 4
        options.log_severity_level = 3
        providers = ["CPUExecutionProvider"]
        self._text = ort.InferenceSession(str(root / "text.onnx"), options, providers=providers)
        self._sound = ort.InferenceSession(str(root / "sound.onnx"), options, providers=providers)
        self._decoder = ort.InferenceSession(
            str(root / "decoder.onnx"), options, providers=providers
        )
        self._stoi = {ch: i for i, ch in enumerate(self._meta.vocab)}
        self._frontend = TurkishFrontend(self._meta.vocab)
        self._lock = threading.RLock()

    def synthesize(self, text: str, speed: float = 1.0, seed: int | None = None) -> np.ndarray:
        """48 kHz mono float32 ses. Okunacak harf yoksa boş dizi döner."""
        low, high = SPEED_RANGE
        speed = max(low, min(high, float(speed)))
        base_seed = 0 if seed is None else int(seed)
        pieces = chunk_text(self._frontend(text), speed)
        parts: list[np.ndarray] = []
        with self._lock:
            for index, (piece, pause) in enumerate(pieces):
                parts.append(self._piece_audio(piece, speed, (base_seed * 1_000_003 + index)))
                if pause > 0:
                    parts.append(np.zeros(round(pause * SAMPLE_RATE), dtype=np.float32))
        return np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)

    def _piece_audio(self, text: str, speed: float, seed: int) -> np.ndarray:
        ids = np.array([[self._stoi.get(ch, 1) for ch in text]], dtype=np.int64)
        hidden, durations = self._text.run(None, {"ids": ids})
        durations = durations / speed
        letter_word, word_start, frame_word, frame_pos = _timeline(text, durations)
        frames = frame_word.shape[0]
        rng = np.random.default_rng(seed % 2**63)
        noise = rng.standard_normal((1, len(self._meta.times), frames, self._meta.latent_dim))
        (latents,) = self._sound.run(
            None,
            {
                "h": hidden,
                "dur": durations.astype(np.float32),
                "cw": letter_word[None],
                "wstart": word_start[None],
                "fw": frame_word[None].astype(np.int64),
                "fp": frame_pos[None],
                "noise": noise.astype(np.float32),
            },
        )
        return self._decode(latents[0])

    def _decode(self, latents: np.ndarray) -> np.ndarray:
        frames = latents.shape[0]
        hop = self._meta.hop
        chunks: list[np.ndarray] = []
        start = 0
        while start < frames:
            end = min(frames, start + (FIRST_WINDOW if start == 0 else WINDOW))
            lo, hi = max(0, start - CONTEXT), min(frames, end + CONTEXT)
            (audio,) = self._decoder.run(None, {"z": latents[None, lo:hi]})
            chunks.append(audio[0, (start - lo) * hop : (end - lo) * hop])
            start = end
        return np.concatenate(chunks).astype(np.float32)


@lru_cache(maxsize=1)
def _shared_voice(stamp: int) -> EmaVoice:
    """Tek örnek; model dosyası değişirse (`stamp`) yenisi yüklenir."""
    return EmaVoice()


def wav_bytes(audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> bytes:
    pcm = (np.clip(audio, -1.0, 1.0) * 32767.0).astype("<i2")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(sample_rate)
        stream.writeframes(pcm.tobytes())
    return buffer.getvalue()


# Kısa cevaplar bellekte sınırlı önbelleğe alınır (aynı selamlama tekrar sentezlenmesin).
SHORT_REPLY_CHARS = 160
SHORT_REPLY_CACHE_SIZE = 16


@lru_cache(maxsize=SHORT_REPLY_CACHE_SIZE)
def _short_wav(text: str, speed: float, stamp: int) -> bytes:
    return wav_bytes(_shared_voice(stamp).synthesize(text, speed))


def synthesize_ema(text: str, output: Path, speed: float) -> None:
    """Metni WAV'a yaz. Model yüklemesi ilk çağrıda, sonrası sıcak."""
    stamp = (DATA_DIRECTORY / "sound.onnx").stat().st_mtime_ns
    if len(text) <= SHORT_REPLY_CHARS:
        data = _short_wav(text, speed, stamp)
    else:
        data = wav_bytes(_shared_voice(stamp).synthesize(text, speed))
    output.write_bytes(data)
