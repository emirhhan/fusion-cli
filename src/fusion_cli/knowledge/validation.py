"""Paket doğrulama — imza, bütünlük ve sır taraması.

Bir manifest istemciye uygulanmadan ÖNCE buradan geçer. Üç kapı:

1. **İmza** — manifest imzası, verilen anahtarla doğrulanmalı (oynama tespiti).
2. **Bütünlük** — her girişin `content_hash`'i alanlarından yeniden hesaplananla
   eşleşmeli (giriş sessizce değiştirilmemiş olmalı).
3. **Sır/PII yok** — hiçbir giriş sır ya da kişisel veri içermemeli (Faz 1 taraması).

Herhangi biri düşerse manifest reddedilir ve hiçbir ders uygulanmaz.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core.redaction import contains_sensitive
from .manifest import KnowledgeManifest, entry_hash, signable_bytes
from .signing import verify


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Doğrulama sonucu: geçti mi ve (geçmediyse) Türkçe sorun listesi."""

    ok: bool
    problems: tuple[str, ...] = ()


def validate_manifest(manifest: KnowledgeManifest, *, public_key: str) -> ValidationResult:
    """Manifesti imza (AÇIK anahtarla), bütünlük ve sır kapılarından geçir."""

    problems: list[str] = []

    payload = signable_bytes(manifest.version, manifest.entries)
    if not manifest.signature or not verify(payload, manifest.signature, public_key):
        problems.append("imza geçersiz")

    for entry in manifest.entries:
        expected = entry_hash(entry.entry_id, entry.text, entry.kind, entry.scope)
        if entry.content_hash != expected:
            problems.append(f"bütünlük hatası: {entry.entry_id}")
        if contains_sensitive(entry.text):
            problems.append(f"sır/kişisel veri: {entry.entry_id}")

    return ValidationResult(ok=not problems, problems=tuple(problems))
