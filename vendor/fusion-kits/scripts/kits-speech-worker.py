"""Ortak yerel ses işçisi: satırlı JSON ile üretir, modeli bellekte tutar."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import signal
import sys
import tempfile
import wave
from collections.abc import Callable
from pathlib import Path
from typing import TextIO

MAX_REQUEST_CHARS = 65_536


class SpeechWorker:
    """Tek üretim kuyruğunun ve henüz teslim alınmayan WAV'ın sahibi."""

    def __init__(
        self, synthesize: Callable[[str, Path], None], output: Path, max_text_chars: int
    ) -> None:
        self.synthesize = synthesize
        self.output = output
        self.max_text_chars = max_text_chars
        self.files: dict[str, Path] = {}

    def handle(self, request: object) -> dict[str, object]:
        """Dosya yollarını istemciden almadan tek bir isteği karşıla."""
        if not isinstance(request, dict):
            return {"id": None, "ok": False, "error": "JSON nesnesi gerekli."}
        identifier = request.get("id")
        if (
            not isinstance(identifier, str)
            or not identifier.strip()
            or len(identifier) > 128
        ):
            return {"id": None, "ok": False, "error": "İstek kimliği gerekli."}
        result: dict[str, object] = {"id": identifier}
        action = request.get("action")
        if action == "release":
            owned = self.files.pop(identifier, None)
            if owned is not None:
                owned.unlink(missing_ok=True)
            return {**result, "ok": True, "released": owned is not None}
        if action != "synthesize":
            return {**result, "ok": False, "error": "Bilinmeyen ses işlemi."}
        text = request.get("text")
        if (
            not isinstance(text, str)
            or not text.strip()
            or len(text) > self.max_text_chars
        ):
            return {
                **result,
                "ok": False,
                "error": "Ses metni boş veya uzunluk sınırını aşıyor.",
            }
        if self.files:
            return {
                **result,
                "ok": False,
                "error": "Önce önceki ses dosyasını serbest bırak.",
            }
        with tempfile.NamedTemporaryFile(
            dir=self.output, suffix=".wav", delete=False
        ) as handle:
            path = Path(handle.name)
        try:
            self.synthesize(text, path)
            if not path.is_file() or path.stat().st_size == 0:
                raise ValueError("Ses motoru boş çıktı üretti.")
        except Exception as error:  # noqa: BLE001, RUF100 — dış motor sınırı.
            # Dış motor sınırı: hata görünür, yarım dosya tutulmaz.
            path.unlink(missing_ok=True)
            return {
                **result,
                "ok": False,
                "error": f"Ses üretilemedi: {type(error).__name__}",
            }
        self.files[identifier] = path
        return {**result, "ok": True, "path": str(path), "format": "wav"}

    def close(self) -> None:
        """Bağlantı kapanınca teslim alınmayan dosyaları kaldır."""
        for path in self.files.values():
            path.unlink(missing_ok=True)
        self.files.clear()


def serve(worker: SpeechWorker, source: TextIO, target: TextIO) -> None:
    """Protokol çıktısını üçüncü parti tanı mesajlarından ayrı tut."""
    try:
        while line := source.readline(MAX_REQUEST_CHARS + 1):
            if len(line) > MAX_REQUEST_CHARS:
                while not line.endswith("\n"):
                    line = source.readline(MAX_REQUEST_CHARS + 1)
                    if not line:
                        break
                target.write(
                    json.dumps(
                        {
                            "id": None,
                            "ok": False,
                            "error": "JSON isteği boyut sınırını aşıyor.",
                        }
                    )
                    + "\n"
                )
                target.flush()
                continue
            response: dict[str, object]
            try:
                request = json.loads(line)
            except (ValueError, RecursionError):
                response = {"id": None, "ok": False, "error": "Geçersiz JSON satırı."}
            else:
                with contextlib.redirect_stdout(sys.stderr):
                    response = worker.handle(request)
            target.write(json.dumps(response, ensure_ascii=False) + "\n")
            target.flush()
    finally:
        worker.close()


def main() -> int:
    """MLX işçi başlangıcında yüklenir; modül testleri hafif kalır."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--max-tokens", type=int, required=True)
    parser.add_argument("--max-text-chars", type=int, required=True)
    parser.add_argument("--memory-limit-mib", type=int, required=True)
    parser.add_argument("--exaggeration", type=float, required=True)
    parser.add_argument("--allow-downloads", action="store_true")
    args = parser.parse_args()
    if not (args.model / "config.json").is_file() or not args.reference.is_file():
        parser.error("Model dizini ve referans ses dosyası mevcut olmalı.")
    if min(args.max_tokens, args.max_text_chars, args.memory_limit_mib) <= 0:
        parser.error("Token, metin ve bellek sınırları pozitif olmalı.")
    if not 0 <= args.exaggeration <= 1:
        parser.error("İfade seviyesi 0 ile 1 arasında olmalı.")
    if not args.allow_downloads:
        os.environ["HF_HUB_OFFLINE"] = "1"
    with contextlib.redirect_stdout(sys.stderr):
        import mlx.core as mx
        import numpy as np
        from mlx_audio.tts.utils import load_model

        mx.set_memory_limit(args.memory_limit_mib * 1024 * 1024)
        model = load_model(str(args.model.resolve()))
        conditions = model.prepare_conditionals(
            str(args.reference.resolve()), 24000, args.exaggeration
        )

    def synthesize(text: str, output: Path) -> None:
        chunks = []
        for result in model.generate(
            text=text,
            lang_code="tr",
            conds=conditions,
            exaggeration=args.exaggeration,
            max_tokens=args.max_tokens,
        ):
            mx.eval(result.audio)
            chunks.append(np.asarray(result.audio).reshape(-1))
        if not chunks:
            raise ValueError("Ses motoru çıktı üretmedi.")
        audio = np.concatenate(chunks)
        if audio.size == 0 or not np.isfinite(audio).all():
            raise ValueError("Ses motoru geçersiz örnek üretti.")
        pcm = np.rint(np.clip(audio, -1, 1) * 32767).astype("<i2")
        with wave.open(str(output), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(model.sample_rate)
            wav.writeframes(pcm.tobytes())

    def terminate(_signal: int, _frame: object) -> None:
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, terminate)
    with tempfile.TemporaryDirectory(prefix="fusion-kits-speech-") as directory:
        worker = SpeechWorker(synthesize, Path(directory), args.max_text_chars)
        sys.stdout.write(
            json.dumps({"ok": True, "event": "ready", "engine": "chatterbox-mlx"})
            + "\n"
        )
        sys.stdout.flush()
        serve(worker, sys.stdin, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
