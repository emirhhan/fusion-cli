"""Kancalara verilen konuşma dökümü (`transcript_path`, P-009).

Claude betikleri (Stop/SessionEnd özetleri, oturum kaydı) `transcript_path`'teki JSONL'i
okur: her satır `{"type": "user"|"assistant", "message": {"role", "content": [{"type":
"text", "text"}]}}`. Fusion'ın kendi sohbet kaydı (`transcripts/<proje>/events.jsonl`)
proje başına ortak ve farklı biçimdedir; bu yüzden kanca oturumu kendi dökümünü tutar.

Döküm yalnız tanımlı kanca varken yazılır, metinler maskelenir (sırlar), dosya 0600'dür ve
`SessionEnd` kancalarından SONRA silinir. Araç çağrıları dökümde yoktur (yalnız istem ve
cevap). Ölçüldü (31 Ekim): yükte `transcript_path` hiç yoktu; onu okuyan betik KeyError ile
çıkıp her turda "Kanca hatası" basıyordu.
"""

from __future__ import annotations

import contextlib
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

from ...core.redaction import redact

#: Dökümlerin `memory_dir` altındaki klasörü.
HOOK_TRANSCRIPT_DIR = "hook-transcripts"
_UNSAFE = re.compile(r"[^A-Za-z0-9_.-]")


@dataclass(frozen=True, slots=True)
class HookTranscript:
    path: Path

    def ensure(self) -> Path:
        """Dosyayı (boşsa) oluştur ve yolunu döndür; yazılamıyorsa yol yine verilir."""
        with contextlib.suppress(OSError):
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.parent.chmod(0o700)
            self.path.touch(exist_ok=True)
            self.path.chmod(0o600)
        return self.path

    def append(self, role: str, text: str, session_id: str) -> None:
        line = {
            "type": role,
            "session_id": session_id,
            "timestamp": time.time(),
            "message": {"role": role, "content": [{"type": "text", "text": redact(text)}]},
        }
        with contextlib.suppress(OSError):
            self.ensure()
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(line, ensure_ascii=False) + "\n")

    def remove(self) -> None:
        with contextlib.suppress(OSError):
            self.path.unlink(missing_ok=True)


def transcript_for(directory: Path, session_id: str) -> HookTranscript:
    return HookTranscript(directory / f"{_UNSAFE.sub('_', session_id) or 'oturum'}.jsonl")
