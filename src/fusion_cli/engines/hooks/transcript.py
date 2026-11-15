"""Kancalara verilen konuşma dökümü (`transcript_path`, P-009).

Claude betikleri (Stop/SessionEnd özetleri, oturum kaydı) `transcript_path`'teki JSONL'i
okur: her satır `{"type": "user"|"assistant", "message": {"role", "content": [{"type":
"text", "text"}]}}`. Fusion'ın kendi sohbet kaydı (`transcripts/<proje>/events.jsonl`)
proje başına ortak ve farklı biçimdedir; bu yüzden kanca oturumu kendi dökümünü tutar.

Döküm oturum boyunca (kanca tanımı olmasa da) yazılır ve kalıcıdır (#129): `SessionEnd`'den
sonra silinmez, 30 günden eskisi yerel durum temizliğinde (`retention`) silinir. Metinler
maskelenir (sırlar), dosya 0600'dür. Ana ajanın araç çağrıları da yazılır: assistant
satırında `tool_use` (`id`, `name` — Claude adı, `input`), user satırında `tool_result`
(`tool_use_id`, `content`, `is_error`); girdi ve çıktı maskeli ve kırpılmıştır.

Ölçüldü (31 Ekim): yükte `transcript_path` hiç yoktu; onu okuyan betik KeyError ile çıkıp
her turda "Kanca hatası" basıyordu. Ölçüldü (1 Kasım): dökümde araç çağrıları yoktu.
"""

from __future__ import annotations

import contextlib
import json
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ...core.redaction import redact

#: Dökümlerin `memory_dir` altındaki klasörü.
HOOK_TRANSCRIPT_DIR = "hook-transcripts"
#: Dökümde araç girdisi/çıktısı başına en fazla karakter.
TOOL_TEXT_CHARS = 8_000
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
        self._write(role, [{"type": "text", "text": redact(text)}], session_id)

    def append_tool_use(
        self, name: str, tool_input: Mapping[str, object], tool_use_id: str, session_id: str
    ) -> None:
        """Modelin araç çağrısı (Claude: assistant mesajında `tool_use` bloğu)."""
        block = {"type": "tool_use", "id": tool_use_id, "name": name, "input": _masked(tool_input)}
        self._write("assistant", [block], session_id)

    def append_tool_result(
        self, tool_use_id: str, output: str, session_id: str, *, is_error: bool
    ) -> None:
        """Aracın sonucu (Claude: user mesajında `tool_result` bloğu)."""
        block = {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": redact(output[:TOOL_TEXT_CHARS]),
            "is_error": is_error,
        }
        self._write("user", [block], session_id)

    def append_compact_boundary(self, session_id: str, trigger: str) -> None:
        """Özetleme sınırı (Claude: `system`/`compact_boundary` satırı)."""
        line = {
            "type": "system",
            "subtype": "compact_boundary",
            "session_id": session_id,
            "timestamp": time.time(),
            "compactMetadata": {"trigger": trigger},
        }
        self._append(line)

    def _write(self, role: str, content: list[dict[str, object]], session_id: str) -> None:
        line = {
            "type": role,
            "session_id": session_id,
            "timestamp": time.time(),
            "message": {"role": role, "content": content},
        }
        self._append(line)

    def _append(self, line: Mapping[str, object]) -> None:
        with contextlib.suppress(OSError):
            self.ensure()
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(line, ensure_ascii=False) + "\n")

    def remove(self) -> None:
        with contextlib.suppress(OSError):
            self.path.unlink(missing_ok=True)


def _masked(value: object) -> object:
    """Araç girdisini yapısı korunarak maskele ve kırp (sırlar dökümde düz görünmez)."""
    if isinstance(value, str):
        return redact(value)[:TOOL_TEXT_CHARS]
    if isinstance(value, Mapping):
        return {str(key): _masked(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_masked(item) for item in value]
    if value is None or isinstance(value, bool | int | float):
        return value
    return redact(str(value))[:TOOL_TEXT_CHARS]


def transcript_for(directory: Path, session_id: str) -> HookTranscript:
    return HookTranscript(directory / f"{_UNSAFE.sub('_', session_id) or 'oturum'}.jsonl")
