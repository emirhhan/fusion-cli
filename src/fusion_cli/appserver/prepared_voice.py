"""Bir sonraki cümlenin hazır ses dosyalarını sınırlı ve sahipli tutar."""

from __future__ import annotations

import tempfile
import threading
import uuid
from collections.abc import Callable
from pathlib import Path

# Çalan cümle dışında tek ön yükleme ve onun geçişi için iki yuva yeterlidir.
MAX_PREPARED_VOICE_FILES = 2


class PreparedVoiceStore:
    """Dosya yolu istemciden alınmaz; yalnız tek kullanımlık kimlik paylaşılır."""

    def __init__(self, directory: Path | None = None) -> None:
        self._directory = directory
        self._files: dict[str, Path] = {}
        self._lock = threading.RLock()

    def prepare(self, render: Callable[[Path], object]) -> str:
        """Dosyayı üret; başarısız üretim ve kapasite taşması kalıntı bırakmaz."""
        with self._lock:
            if len(self._files) >= MAX_PREPARED_VOICE_FILES:
                raise RuntimeError("Hazır ses kuyruğu dolu.")
            with tempfile.NamedTemporaryFile(
                suffix=".wav", dir=self._directory, delete=False
            ) as file:
                path = Path(file.name)
            try:
                render(path)
            except BaseException:
                path.unlink(missing_ok=True)
                raise
            token = uuid.uuid4().hex
            self._files[token] = path
            return token

    def take(self, token: str) -> Path | None:
        """Oynatıcı dosyanın sahipliğini bir kez devralır."""
        with self._lock:
            return self._files.pop(token, None)

    def discard(self, token: str) -> None:
        """İptal, yalnız bu kaydın ürettiği dosyayı siler."""
        path = self.take(token)
        if path is not None:
            path.unlink(missing_ok=True)

    def close(self) -> None:
        """Oturum kapanırken oynatılmamış dosyaları bırakma."""
        with self._lock:
            for path in self._files.values():
                path.unlink(missing_ok=True)
            self._files.clear()
