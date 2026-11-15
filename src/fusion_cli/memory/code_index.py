"""Anlamsal kod indeksi.

"Auth nerede yönetiliyor?" gibi KAVRAMSAL soruları grep yerine anlamca cevaplar.
Kesin metin araması için `search_code` vardır; bu onun yerine geçmez, tamamlar.

Parçalama mantığı `chunking` modülündedir ve saf tutulur; burada yalnızca gömme ve
sorgulama vardır.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any

from ..core.constants import SKIP_DIRECTORIES
from ..core.memory import CodeMatch, IndexStats
from ..core.redaction import redact
from ..core.source_read import read_scoped_source
from .chunking import (
    MAX_CHUNKS,
    MAX_FILE_BYTES,
    SOURCE_SUFFIXES,
    Chunk,
    build_chunks,
    chunk_generation,
    chunk_text,
)
from .hybrid import CANDIDATE_MULTIPLIER, bm25_scores, fuse_ranked_ids, reciprocal_rank_fusion
from .store import get_collection

#: Tek seferde gömülecek parça sayısı. Çok büyük yığınlar bellek ve istek sınırını zorlar.
EMBED_BATCH = 200


@dataclass(frozen=True, slots=True)
class _Candidate:
    """SDK verisi dışarı çıkmadan tiplenmiş arama adayı."""

    identifier: str
    match: CodeMatch
    distance: float | None = None


class ChromaCodeIndex:
    """ChromaDB destekli, artımlı çalışan kod indeksi."""

    def __init__(
        self,
        directory: Path,
        root: Path,
        *,
        embedding_function: Any = None,
        suffix: str = "",
        lexical_candidates: int = 0,
        chunk_strategy: str = "lines",
    ) -> None:
        if lexical_candidates < 0:
            raise ValueError("Lexical aday sınırı negatif olamaz.")
        self._generation = chunk_generation(chunk_strategy)
        self._chunk_strategy = chunk_strategy
        self._lexical_candidates = lexical_candidates
        self._lock = RLock()
        self._root = root.expanduser().resolve()
        self._collection = get_collection(
            directory / "code_index",
            _collection_name(self._root, suffix),
            embedding_function=embedding_function,
        )

    def search(self, query: str, limit: int = 6) -> tuple[CodeMatch, ...]:
        """Aynı redacted indeksten bağımsız adayları gerçek vektör sırasıyla birleştir."""
        if not query.strip() or limit <= 0:
            return ()
        with self._lock:
            total = self._collection.count()
            if total == 0:
                return ()
            pool = min(limit * CANDIDATE_MULTIPLIER, total)
            result = self._collection.query(query_texts=[query], n_results=pool)
            source_ids: dict[str, set[str]] = {}
            vectors = self._fresh_candidates(
                self._read_candidates(result, is_query=True), source_ids
            )
            if self._lexical_candidates == 0:
                return self._rerank_vectors(query, vectors, limit)
            # İkinci DB veya kalıcı tam-kod kopyası yok. Her arama mevcut redacted
            # koleksiyonu okur; yeniden açılan süreç de silinmiş aday önbelleği tutmaz.
            indexed = self._fresh_candidates(
                self._read_candidates(
                    self._collection.get(include=["documents", "metadatas"]), is_query=False
                ),
                source_ids,
            )
            current = {candidate.identifier for candidate in indexed}
            vectors = [candidate for candidate in vectors if candidate.identifier in current]
            lexical = self._lexical_candidates_for(query, indexed)
            scores = fuse_ranked_ids(
                tuple(candidate.identifier for candidate in vectors),
                tuple(candidate.identifier for candidate in lexical),
            )
            # Eşit RRF'de lexical aday önce gelir; mevcut gerçek vektör sırası bozulmaz.
            union = {candidate.identifier: candidate for candidate in (*lexical, *vectors)}
            order = sorted(union, key=lambda identifier: -scores[identifier])
            return tuple(union[identifier].match for identifier in order[:limit])

    def _read_candidates(self, result: Any, *, is_query: bool) -> list[_Candidate]:
        """Chroma SDK sözlüklerini normalize et; başka stratejinin neslini ele."""
        identifiers = result.get("ids") or ([[]] if is_query else [])
        documents = result.get("documents") or ([[]] if is_query else [])
        metadatas = result.get("metadatas") or ([[]] if is_query else [])
        distances = (result.get("distances") or [[]])[0] if is_query else []
        if is_query:
            identifiers, documents, metadatas = identifiers[0], documents[0], metadatas[0]
        candidates: list[_Candidate] = []
        for index, (identifier, document, metadata) in enumerate(
            zip(identifiers, documents, metadatas, strict=False)
        ):
            metadata = metadata or {}
            if metadata.get("generation", "") != self._generation:
                continue
            if not isinstance(document, str):
                continue
            match = CodeMatch(
                path=str(metadata.get("path", "?")),
                start_line=int(metadata.get("start", 0)),
                end_line=int(metadata.get("end", 0)),
                snippet=document,
            )
            distance = float(distances[index]) if index < len(distances) else None
            candidates.append(_Candidate(str(identifier), match, distance))
        return candidates

    def _fresh_candidates(
        self, candidates: list[_Candidate], source_ids: dict[str, set[str]]
    ) -> list[_Candidate]:
        """Başarısız DB silmesi başka nesnede de eski içeriği geri getiremesin."""
        fresh: list[_Candidate] = []
        for candidate in candidates:
            relative = candidate.match.path
            if relative not in source_ids:
                source_ids[relative] = self._source_ids(relative)
            if candidate.identifier in source_ids[relative]:
                fresh.append(candidate)
        return fresh

    def _source_ids(self, path: str) -> set[str]:
        """İndeks yolunu güven sınırında doğrula; yalnız güncel chunk kimliklerini tut."""
        try:
            source = self._root / path
            relative = source.relative_to(self._root)
            if ".." in relative.parts:
                return set()
            resolved = source.resolve(strict=True)
            actual_relative = resolved.relative_to(self._root)
            for candidate_path in (relative, actual_relative):
                if (
                    candidate_path.name.startswith(".env")
                    or candidate_path.suffix.lower() not in SOURCE_SUFFIXES
                    or any(part in SKIP_DIRECTORIES for part in candidate_path.parts[:-1])
                ):
                    return set()
            if not resolved.is_file() or resolved.stat().st_size > MAX_FILE_BYTES:
                return set()
        except (OSError, RuntimeError, ValueError):
            return set()
        payload = read_scoped_source(self._root, actual_relative, max_bytes=MAX_FILE_BYTES)
        if payload is None:
            return set()
        content = payload.decode("utf-8", errors="ignore")
        # Lexical skor ve snippet mevcut redacted DB'dendir; kaynak yalnız ID doğrular.
        return {
            chunk.id for chunk in chunk_text(content, str(relative), strategy=self._chunk_strategy)
        }

    def _lexical_candidates_for(self, query: str, indexed: list[_Candidate]) -> list[_Candidate]:
        """Pozitif BM25 sinyalini bağımsız, sınırlandırılmış bir aday sırasına çevir."""
        scores = bm25_scores(query, [candidate.match.snippet for candidate in indexed])
        order = sorted(
            range(len(indexed)), key=lambda index: (-scores[index], indexed[index].identifier)
        )
        return [indexed[index] for index in order if scores[index] > 0][: self._lexical_candidates]

    @staticmethod
    def _rerank_vectors(query: str, vectors: list[_Candidate], limit: int) -> tuple[CodeMatch, ...]:
        """Bağımsız havuz kapalıyken mevcut vektör-içi hibrit davranışı koru."""
        distances = [candidate.distance for candidate in vectors if candidate.distance is not None]
        if len(distances) != len(vectors):
            return tuple(candidate.match for candidate in vectors[:limit])
        lexical = bm25_scores(query, [candidate.match.snippet for candidate in vectors])
        fused = reciprocal_rank_fusion(distances, lexical)
        order = sorted(range(len(vectors)), key=lambda index: -fused[index])
        return tuple(vectors[index].match for index in order[:limit])

    def reindex(self, limit: int = MAX_CHUNKS) -> IndexStats:
        """Yalnızca YENİ/DEĞİŞEN parçaları göm, silinenleri temizle."""
        with self._lock:
            return self._reindex(limit)

    def _reindex(self, limit: int) -> IndexStats:
        if limit < 0:
            raise ValueError("İndeks parça sınırı negatif olamaz.")
        # Tavanın bir fazlası istenir: tavana tam denk gelen depo "kısmi" sayılmasın.
        chunks = build_chunks(self._root, limit=limit + 1, strategy=self._chunk_strategy)
        truncated = len(chunks) > limit
        chunks = chunks[:limit]
        current = {chunk.id for chunk in chunks}
        existing = set(self._collection.get(include=[]).get("ids", []))

        stale = list(existing - current)
        fresh = [chunk for chunk in chunks if chunk.id not in existing]

        # Yalnız GERÇEKTEN yazılan partiler/silmeler sayılır; yazılamayan parti
        # `failed`e girer ve sonuç özeti bunu söyler (M1-31).
        removed = len(stale) if stale and self._collection.delete(ids=stale) else 0
        added = 0
        failed = 0
        for start in range(0, len(fresh), EMBED_BATCH):
            batch = fresh[start : start + EMBED_BATCH]
            if self._add(batch):
                added += len(batch)
            else:
                failed += len(batch)

        return IndexStats(
            total=len(chunks),
            added=added,
            removed=removed,
            truncated=truncated,
            failed=failed + (len(stale) - removed),
        )

    def _add(self, batch: list[Chunk]) -> bool:
        if not batch:
            return True
        return bool(
            self._collection.add(
                ids=[chunk.id for chunk in batch],
                # Sır içeren yapılandırmalar (compose, workflow, toml) gömme sağlayıcısına
                # (NIM = üçüncü taraf) ve diskteki düz metne SIR olarak gitmesin.
                documents=[redact(chunk.text) for chunk in batch],
                metadatas=[
                    {
                        "path": chunk.path,
                        "start": chunk.start_line,
                        "end": chunk.end_line,
                        "generation": chunk.generation,
                    }
                    for chunk in batch
                ],
            )
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
