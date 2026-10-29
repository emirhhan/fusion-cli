"""Bir sonraki cümlenin hazır ses dosyalarını sınırlı ve sahipli tutar."""

from __future__ import annotations

import tempfile
import threading
import uuid
from collections.abc import Callable
from pathlib import Path

# Çalan cümle dışında tek ön yükleme ve onun geçişi için iki yuva yeterlidir.
MAX_PREPARED_VOICE_FILES = 2


class StaleVoiceGenerationError(RuntimeError):
    """Daha yeni bir konuşma nesli başladı; bu neslin sesi çalınmamalı."""


class PreparedVoiceStore:
    """Dosya yolu istemciden alınmaz; yalnız tek kullanımlık kimlik paylaşılır.

    NESİL: istemci her yeni konuşmaya artan bir `generation` verir. Daha yeni
    nesil geldiği an eski neslin hazır dosyaları düşer, eski neslin hazırlama
    ve oynatma istekleri reddedilir. İptal ACK'i gecikse bile eski ses yeni
    konuşmayı ne ezer ne de kapasitesini tutar. Nesil verilmezse davranış eskisi gibidir.

    Ölçüldü (29 Ekim): sentez kilit altında yapılıyordu; kesme isteği (`take`/`discard`)
    saniyeler süren sentezin arkasında bekliyordu. Kilit artık yalnız defter tutar.
    """

    def __init__(self, directory: Path | None = None) -> None:
        self._directory = directory
        self._files: dict[str, tuple[Path, int | None]] = {}
        self._reserved = 0
        self._newest = 0
        self._lock = threading.RLock()

    def is_stale(self, generation: int | None) -> bool:
        with self._lock:
            return generation is not None and generation < self._newest

    def _advance(self, generation: int | None) -> None:
        """Kilit altında çağrılır: yeni nesil eski neslin dosyalarını düşürür."""
        if generation is None:
            return
        if generation < self._newest:
            raise StaleVoiceGenerationError("Daha yeni bir konuşma başladı.")
        if generation > self._newest:
            self._newest = generation
            for token, (path, owner) in list(self._files.items()):
                if owner is not None and owner < generation:
                    del self._files[token]
                    path.unlink(missing_ok=True)

    def prepare(self, render: Callable[[Path], object], generation: int | None = None) -> str:
        """Dosyayı üret; başarısız üretim, eski nesil ve kapasite taşması kalıntı bırakmaz."""
        with self._lock:
            self._advance(generation)
            if len(self._files) + self._reserved >= MAX_PREPARED_VOICE_FILES:
                raise RuntimeError("Hazır ses kuyruğu dolu.")
            self._reserved += 1
        path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                suffix=".wav", dir=self._directory, delete=False
            ) as file:
                path = Path(file.name)
            render(path)
            with self._lock:
                self._advance(generation)  # Sentez sürerken yeni nesil gelmiş olabilir.
                token = uuid.uuid4().hex
                self._files[token] = (path, generation)
                return token
        except BaseException:
            if path is not None:
                path.unlink(missing_ok=True)
            raise
        finally:
            with self._lock:
                self._reserved -= 1

    def take(self, token: str, generation: int | None = None) -> Path | None:
        """Oynatıcı dosyanın sahipliğini bir kez devralır; eski nesil devralamaz."""
        with self._lock:
            entry = self._files.pop(token, None)
            if entry is None:
                return None
            path, owner = entry
            effective = generation if generation is not None else owner
            if effective is not None and effective < self._newest:
                path.unlink(missing_ok=True)
                return None
            return path

    def discard(self, token: str) -> None:
        """İptal, yalnız bu kaydın ürettiği dosyayı siler."""
        path = self.take(token)
        if path is not None:
            path.unlink(missing_ok=True)

    def close(self) -> None:
        """Oturum kapanırken oynatılmamış dosyaları bırakma."""
        with self._lock:
            for path, _owner in self._files.values():
                path.unlink(missing_ok=True)
            self._files.clear()
