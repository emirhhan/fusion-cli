"""Kaynak dosyaları indekslenebilir parçalara bölme.

Tamamen SAF: dosya sistemi dışında bağımlılığı yoktur, ChromaDB'yi tanımaz ve
doğrudan test edilir. Kod indeksinin pahalı kısmı (gömme) bu katmanın üstündedir.

Parça kimliği İÇERİĞİ de kapsar. Bunun sonucu artımlı indekslemedir: içerik
değişmediyse kimlik aynı kalır, yeniden gömme yapılmaz. Değişmemiş bir repoda
yeniden indeksleme neredeyse anlıktır.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from ..core.constants import SKIP_DIRECTORIES

#: Bir parçadaki satır sayısı.
CHUNK_LINES = 60
#: Parçalar arası örtüşme — bir fonksiyon iki parçaya bölünürse bağlam kopmasın.
CHUNK_OVERLAP = 10
#: Bundan büyük dosyalar indekslenmez.
MAX_FILE_BYTES = 400_000
#: Tek bir indeksin üst sınırı (çok büyük repo koruması).
MAX_CHUNKS = 4_000

#: İndekslenen kaynak dosya uzantıları.
SOURCE_SUFFIXES = frozenset(
    {
        ".py",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".go",
        ".rs",
        ".java",
        ".rb",
        ".php",
        ".c",
        ".h",
        ".cpp",
        ".hpp",
        ".cs",
        ".swift",
        ".kt",
        ".scala",
        ".css",
        ".scss",
        ".html",
        ".vue",
        ".svelte",
        ".sql",
        ".sh",
        ".yaml",
        ".yml",
        ".toml",
        ".md",
    }
)


@dataclass(frozen=True, slots=True)
class Chunk:
    """İndekslenecek tek bir kod parçası."""

    path: str
    start_line: int
    end_line: int
    text: str

    @property
    def id(self) -> str:
        """Yol + satır aralığı + İÇERİK üzerinden kararlı kimlik.

        İçeriğin kimliğe dâhil olması artımlı indekslemeyi mümkün kılar: dosya
        değişmediyse kimlikler de değişmez ve yeniden gömme gerekmez.
        """
        raw = f"{self.path}:{self.start_line}:{self.end_line}:{self.text}"
        return hashlib.sha1(raw.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]


def iter_source_files(root: Path) -> Iterator[Path]:
    """İndekslenecek kaynak dosyaları üret; gürültü dizinleri atlanır."""
    # `os.walk` gürültü dizinine HİÇ girmez (eskiden `rglob` önce hepsini geziyor,
    # atlamayı sonra yapıyordu: büyük repoda her `reindex` yavaştı). Süzme yalnız
    # kökün ALTINDAKİ dizin adlarına bakar: proje `~/work/build/app` gibi gürültü
    # adlı bir ata dizindeyse eskiden bütün dosyalar atlanıyor, indeks boş kalıyordu.
    for current, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(name for name in dirnames if name not in SKIP_DIRECTORIES)
        for filename in sorted(filenames):
            path = Path(current) / filename
            if path.suffix.lower() not in SOURCE_SUFFIXES or not path.is_file():
                continue
            if filename.startswith(".env"):
                # `.env.yaml` gibi uzantılı sır dosyaları `.env` korumasını aşmasın.
                continue
            try:
                if path.stat().st_size > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            yield path


def chunk_file(path: Path, root: Path) -> list[Chunk]:
    """Bir dosyayı örtüşen satır bloklarına böl."""
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return []
    if not lines:
        return []

    relative = _relative(path, root)
    step = max(1, CHUNK_LINES - CHUNK_OVERLAP)
    chunks: list[Chunk] = []
    for start in range(0, len(lines), step):
        block = lines[start : start + CHUNK_LINES]
        text = "\n".join(block).strip()
        if text:
            chunks.append(Chunk(relative, start + 1, start + len(block), text))
        if start + CHUNK_LINES >= len(lines):
            break
    return chunks


def build_chunks(root: Path, limit: int = MAX_CHUNKS) -> list[Chunk]:
    """Kökün altındaki tüm kaynak dosyalardan parça listesi üret."""
    chunks: list[Chunk] = []
    for path in iter_source_files(root):
        for chunk in chunk_file(path, root):
            chunks.append(chunk)
            if len(chunks) >= limit:
                return chunks
    return chunks


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)
