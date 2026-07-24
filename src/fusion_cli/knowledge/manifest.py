"""Ortak bilgi paketi veri modeli ve kanonik serileştirme.

Paket, gözden geçirilmiş derslerin sürümlü ve imzalı bir manifestidir. Her giriş
kendi içerik özetini (hash) taşır; manifest bir sürüm ve tüm içeriğin üstünde bir
imza taşır. İmza ve özetler, paketin git üzerinden dağıtılırken bozulmadığını ve
gözden geçirme sürecinden geçtiğini doğrular (sunucu YOK).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class KnowledgeEntry:
    """Pakete giren tek bir doğrulanmış ders."""

    entry_id: str
    text: str
    #: "mistake" | "success" (LessonKind değeriyle uyumlu).
    kind: str
    scope: str = ""
    #: İçerik özeti; giriş değiştiğinde değişir (sync farkı ve bütünlük için).
    content_hash: str = ""


@dataclass(frozen=True, slots=True)
class KnowledgeManifest:
    """Sürümlü, imzalı bilgi paketi."""

    version: int
    entries: tuple[KnowledgeEntry, ...]
    #: İçeriğin üstündeki HMAC imzası (imzasız manifest için boş).
    signature: str = ""


def entry_hash(entry_id: str, text: str, kind: str, scope: str) -> str:
    """Bir girişin içerik özeti: alanlar değişince değişir."""

    digest = hashlib.sha256()
    digest.update("\x1f".join((entry_id, text, kind, scope)).encode("utf-8"))
    return digest.hexdigest()


def with_hashes(entries: tuple[KnowledgeEntry, ...]) -> tuple[KnowledgeEntry, ...]:
    """Her girişin `content_hash`'ini alanlarından yeniden hesaplayıp doldurur."""

    from dataclasses import replace

    return tuple(
        replace(entry, content_hash=entry_hash(entry.entry_id, entry.text, entry.kind, entry.scope))
        for entry in entries
    )


def signable_bytes(version: int, entries: tuple[KnowledgeEntry, ...]) -> bytes:
    """İmzalanacak/İmzası doğrulanacak kanonik bayt dizisi (imza alanı hariç).

    Sıralı ve deterministik: aynı içerik daima aynı baytları üretir; imza kararlıdır.
    """

    payload = {
        "version": version,
        "entries": [
            {
                "entry_id": entry.entry_id,
                "text": entry.text,
                "kind": entry.kind,
                "scope": entry.scope,
                "content_hash": entry.content_hash,
            }
            for entry in entries
        ],
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
