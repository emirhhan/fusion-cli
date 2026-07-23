"""Anlamsal kod indeksi.

"Auth nerede yönetiliyor?" gibi KAVRAMSAL soruları grep yerine anlamca cevaplar.
Kesin metin araması için `search_code` vardır; bu onun yerine geçmez, tamamlar.

Parçalama mantığı `chunking` modülündedir ve saf tutulur; burada yalnızca gömme ve
sorgulama vardır.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ..core.memory import CodeMatch, IndexStats
from .chunking import MAX_CHUNKS, Chunk, build_chunks
from .store import get_collection

#: Tek seferde gömülecek parça sayısı. Çok büyük yığınlar bellek ve istek sınırını zorlar.
EMBED_BATCH = 200


class ChromaCodeIndex:
    """ChromaDB destekli, artımlı çalışan kod indeksi."""

    def __init__(
        self,
        directory: Path,
        root: Path,
        *,
        embedding_function: Any = None,
        suffix: str = "",
    ) -> None:
        self._root = root.expanduser().resolve()
        self._collection = get_collection(
            directory / "code_index",
            _collection_name(self._root, suffix),
            embedding_function=embedding_function,
        )

    def search(self, query: str, limit: int = 6) -> tuple[CodeMatch, ...]:
        if not query.strip() or self._collection.count() == 0:
            return ()
        result = self._collection.query(query_texts=[query], n_results=limit)
        metadatas = (result.get("metadatas") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        return tuple(
            CodeMatch(
                path=str(metadata.get("path", "?")),
                start_line=int(metadata.get("start", 0)),
                end_line=int(metadata.get("end", 0)),
                snippet=document,
            )
            for metadata, document in zip(metadatas, documents, strict=False)
        )

    def reindex(self, limit: int = MAX_CHUNKS) -> IndexStats:
        """Yalnızca YENİ/DEĞİŞEN parçaları göm, silinenleri temizle."""
        chunks = build_chunks(self._root, limit=limit)
        current = {chunk.id for chunk in chunks}
        existing = set(self._collection.get(include=[]).get("ids", []))

        stale = list(existing - current)
        fresh = [chunk for chunk in chunks if chunk.id not in existing]

        if stale:
            self._collection.delete(ids=stale)
        for start in range(0, len(fresh), EMBED_BATCH):
            self._add(fresh[start : start + EMBED_BATCH])

        return IndexStats(total=len(chunks), added=len(fresh), removed=len(stale))

    def _add(self, batch: list[Chunk]) -> None:
        if not batch:
            return
        self._collection.add(
            ids=[chunk.id for chunk in batch],
            documents=[chunk.text for chunk in batch],
            metadatas=[
                {"path": chunk.path, "start": chunk.start_line, "end": chunk.end_line}
                for chunk in batch
            ],
        )


def _collection_name(root: Path, suffix: str) -> str:
    """Her proje kökü kendi koleksiyonunu kullanır; farklı repolar karışmaz."""
    digest = hashlib.sha1(str(root).encode("utf-8"), usedforsecurity=False).hexdigest()[:10]
    return f"code_{digest}_{suffix}" if suffix else f"code_{digest}"


def format_matches(matches: tuple[CodeMatch, ...], *, snippet_chars: int = 600) -> str:
    """Eşleşmeleri modele verilecek metne çevir."""
    if not matches:
        return "(anlamsal eşleşme yok)"
    return "\n\n".join(
        f"{match.path}:{match.start_line}-{match.end_line}\n{match.snippet[:snippet_chars]}"
        for match in matches
    )
