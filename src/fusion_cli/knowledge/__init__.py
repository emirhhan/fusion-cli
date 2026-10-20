"""Ortak bilgi paketi — git tabanlı, imzalı, sunucusuz bilgi paylaşımı.

Doğrulanmış dersler sürümlü ve imzalı bir paket olarak paylaşılır. İstemci paketi
yalnızca OKUR ve doğruladıktan sonra yerel belleğe uygular; global depoya asla
yazmaz (katkı = gözden geçirilen PR). Otomatik push yoktur — zehirlenme riski böyle
kapanır.
"""

from __future__ import annotations

from .manifest import KnowledgeEntry, KnowledgeManifest
from .package import build_manifest, read_manifest, write_manifest
from .service import SyncReport, status, sync
from .sync import SyncPlan, plan_sync
from .validation import ValidationResult, validate_manifest

__all__ = [
    "KnowledgeEntry",
    "KnowledgeManifest",
    "SyncPlan",
    "SyncReport",
    "ValidationResult",
    "build_manifest",
    "plan_sync",
    "read_manifest",
    "status",
    "sync",
    "validate_manifest",
    "write_manifest",
]
