"""Paket kurma, imzalama ve JSON olarak okuma/yazma.

Kurma (maintainer/CI tarafı): doğrulanmış girişlerden özetleri hesaplar ve tüm
içeriği imzalar. Okuma (istemci tarafı): JSON manifesti tiplenmiş nesneye çevirir.
İstemci ASLA global depoya yazmaz; katkı gözden geçirilen bir PR ile yapılır.
"""

from __future__ import annotations

import json
from pathlib import Path

from .manifest import KnowledgeEntry, KnowledgeManifest, signable_bytes, with_hashes
from .signing import sign


def build_manifest(
    entries: tuple[KnowledgeEntry, ...], *, version: int, private_key: str
) -> KnowledgeManifest:
    """Girişlerin özetlerini doldur, içeriği ÖZEL anahtarla imzala ve manifesti üret."""

    hashed = with_hashes(entries)
    signature = sign(signable_bytes(version, hashed), private_key)
    return KnowledgeManifest(version=version, entries=hashed, signature=signature)


def manifest_to_dict(manifest: KnowledgeManifest) -> dict[str, object]:
    return {
        "version": manifest.version,
        "signature": manifest.signature,
        "entries": [
            {
                "entry_id": entry.entry_id,
                "text": entry.text,
                "kind": entry.kind,
                "scope": entry.scope,
                "content_hash": entry.content_hash,
            }
            for entry in manifest.entries
        ],
    }


def manifest_from_dict(payload: dict[str, object]) -> KnowledgeManifest:
    raw_entries = payload.get("entries", [])
    if not isinstance(raw_entries, list):
        raise ValueError("manifest 'entries' bir liste olmalı")
    entries = tuple(_entry_from_dict(item) for item in raw_entries)
    raw_version = payload.get("version", 0)
    version = int(raw_version) if isinstance(raw_version, int | str) else 0
    return KnowledgeManifest(
        version=version,
        entries=entries,
        signature=str(payload.get("signature", "")),
    )


def _entry_from_dict(item: object) -> KnowledgeEntry:
    if not isinstance(item, dict):
        raise ValueError("manifest girişi bir sözlük olmalı")
    return KnowledgeEntry(
        entry_id=str(item["entry_id"]),
        text=str(item["text"]),
        kind=str(item["kind"]),
        scope=str(item.get("scope", "")),
        content_hash=str(item.get("content_hash", "")),
    )


def write_manifest(manifest: KnowledgeManifest, path: Path) -> None:
    path.write_text(
        json.dumps(manifest_to_dict(manifest), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def read_manifest(path: Path) -> KnowledgeManifest:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("manifest kök öğesi bir sözlük olmalı")
    return manifest_from_dict(payload)
