"""Kaynak dosyaları indekslenebilir parçalara bölme.

Tamamen SAF: dosya sistemi dışında bağımlılığı yoktur, ChromaDB'yi tanımaz ve
doğrudan test edilir. Kod indeksinin pahalı kısmı (gömme) bu katmanın üstündedir.

Parça kimliği İÇERİĞİ de kapsar. Bunun sonucu artımlı indekslemedir: içerik
değişmediyse kimlik aynı kalır, yeniden gömme yapılmaz. Değişmemiş bir repoda
yeniden indeksleme neredeyse anlıktır.
"""

from __future__ import annotations

import ast
import hashlib
import os
import sys
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
    generation: str = ""

    @property
    def id(self) -> str:
        """Yol + satır aralığı + İÇERİK üzerinden kararlı kimlik.

        İçeriğin kimliğe dâhil olması artımlı indekslemeyi mümkün kılar: dosya
        değişmediyse kimlikler de değişmez ve yeniden gömme gerekmez.
        """
        raw = f"{self.path}:{self.start_line}:{self.end_line}:{self.text}"
        if self.generation:
            raw = f"{self.generation}:{raw}"
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


def chunk_generation(strategy: str) -> str:
    """Strateji ve AST sürümü eski gömmelerle karışmasın; satır kimlikleri korunur."""
    if strategy == "lines":
        return ""
    if strategy == "symbols":
        return f"symbols:ast-v1:py{sys.version_info.major}.{sys.version_info.minor}"
    raise ValueError(f"Bilinmeyen parçalama stratejisi: {strategy}")


def chunk_file(path: Path, root: Path, *, strategy: str = "lines") -> list[Chunk]:
    """Dosyayı satır bloklarına veya Python AST sembol sınırlarına böl."""
    chunk_generation(strategy)
    try:
        source = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    return chunk_text(source, _relative(path, root), strategy=strategy)


def chunk_text(source: str, relative: str, *, strategy: str = "lines") -> list[Chunk]:
    """Daha önce okunmuş metni yeniden dosya açmadan aynı chunk kimliklerine böl."""
    generation = chunk_generation(strategy)
    lines = source.splitlines()
    if not lines:
        return []
    ranges = [(1, len(lines))]
    if strategy == "symbols" and Path(relative).suffix == ".py":
        try:
            tree = ast.parse(source)
        except (SyntaxError, ValueError, RecursionError):
            # Tamamlanmamış/çok derin Python kodu da satır geri dönüşüyle aranabilir.
            pass
        else:
            ranges = _symbol_ranges(tree.body, 1, len(lines))
    return [
        chunk
        for start, end in ranges
        for chunk in _line_chunks(lines, relative, start, end, generation)
    ]


def _symbol_ranges(nodes: list[ast.stmt], start: int, end: int) -> list[tuple[int, int]]:
    """Küçük sınıfı bütün tut; büyük sınıfta metot ve decorator sınırlarını kullan."""
    ranges: list[tuple[int, int]] = []
    cursor = start
    for node in nodes:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        first = min([node.lineno, *(item.lineno for item in node.decorator_list)])
        last = node.end_lineno or node.lineno
        if first > cursor:
            ranges.append((cursor, first - 1))
        if isinstance(node, ast.ClassDef) and last - first + 1 > CHUNK_LINES:
            ranges.extend(_symbol_ranges(node.body, first, last))
        else:
            ranges.append((first, last))
        cursor = last + 1
    if cursor <= end:
        ranges.append((cursor, end))
    return ranges


def _line_chunks(
    lines: list[str], relative: str, first: int, last: int, generation: str
) -> list[Chunk]:
    """Tek aralığı tavanı aşmadan ve komşu sembole taşmadan örtüştür."""
    chunks: list[Chunk] = []
    step = max(1, CHUNK_LINES - CHUNK_OVERLAP)
    for start in range(first - 1, last, step):
        end = min(start + CHUNK_LINES, last)
        text = "\n".join(lines[start:end]).strip()
        if text:
            chunks.append(Chunk(relative, start + 1, end, text, generation))
        if end == last:
            break
    return chunks


def build_chunks(root: Path, limit: int = MAX_CHUNKS, *, strategy: str = "lines") -> list[Chunk]:
    """Kökün altındaki kaynak dosyalardan sınırlandırılmış parça listesi üret."""
    chunk_generation(strategy)
    if limit <= 0:
        return []
    chunks: list[Chunk] = []
    for path in iter_source_files(root):
        for chunk in chunk_file(path, root, strategy=strategy):
            chunks.append(chunk)
            if len(chunks) >= limit:
                return chunks
    return chunks


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)
