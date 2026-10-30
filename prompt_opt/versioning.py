"""Prompt sürüm deposu — yayımla, geçerli sürümü oku, geri al.

Her prompt adı için sürüm geçmişi tek bir JSON dosyasında tutulur. Yayım sürüm
numarasını 1'den artırır; geçerli sürüm daima en son yayımlanandır. Geri alma,
geçmişteki bir sürümü yeniden yayımlar (yeni bir sürüm numarasıyla) — geçmiş silinmez.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

from .variants import PromptVariant

#: Prompt adı dosya adına dönüşür; yol ayırıcı ve `..` ile depo dışına yazılamaz (Q1-25).
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")


class PromptStore:
    """Dosya tabanlı, sürümlü prompt deposu."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def publish(self, name: str, text: str) -> PromptVariant:
        """Yeni bir sürüm yayımla ve döndür (sürüm numarası otomatik artar)."""
        history = self._read(name)
        version = (history[-1].version + 1) if history else 1
        variant = PromptVariant(name=name, text=text, version=version)
        self._write(name, [*history, variant])
        return variant

    def current(self, name: str) -> PromptVariant | None:
        """En son yayımlanan sürüm; hiç yayım yoksa None."""
        history = self._read(name)
        return history[-1] if history else None

    def history(self, name: str) -> tuple[PromptVariant, ...]:
        """Yayım geçmişi (eskiden yeniye)."""
        return tuple(self._read(name))

    def rollback(self, name: str, version: int) -> PromptVariant:
        """Geçmişteki bir sürümü yeni bir sürüm olarak yeniden yayımla."""
        target = next((item for item in self._read(name) if item.version == version), None)
        if target is None:
            raise ValueError(f"{name}: {version} sürümü geçmişte yok")
        return self.publish(name, target.text)

    # ----------------------------------------------------------------------- #

    def _path(self, name: str) -> Path:
        if not _NAME.fullmatch(name) or ".." in name:
            raise ValueError(f"Geçersiz prompt adı: {name!r}")
        return self._directory / f"{name}.json"

    def _read(self, name: str) -> list[PromptVariant]:
        path = self._path(name)
        if not path.exists():
            return []
        raw = json.loads(path.read_text(encoding="utf-8"))
        return [
            PromptVariant(name=item["name"], text=item["text"], version=int(item["version"]))
            for item in raw
        ]

    def _write(self, name: str, variants: list[PromptVariant]) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)
        payload = [
            {"name": variant.name, "text": variant.text, "version": variant.version}
            for variant in variants
        ]
        target = self._path(name)
        # Atomik yazım: yarım JSON bırakıp sonraki `_read`'i JSONDecodeError'a düşürmez.
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=self._directory
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(json.dumps(payload, ensure_ascii=False, indent=2))
                stream.flush()
                os.fsync(stream.fileno())
            Path(temporary).replace(target)
        finally:
            Path(temporary).unlink(missing_ok=True)
