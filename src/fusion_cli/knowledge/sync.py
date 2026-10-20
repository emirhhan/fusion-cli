"""Senkronizasyon planı — yalnızca değişeni indir.

İstemcinin bildiği girişlerin özetleriyle uzak manifesti karşılaştırır: hangi giriş
yeni, hangisi değişmiş, hangisi aynı. Aynı olanlar yeniden uygulanmaz — sync
yalnızca gerçekten değişeni taşır. Saftır; ağ/dosya tanımaz, doğrudan test edilir.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .manifest import KnowledgeEntry, KnowledgeManifest


@dataclass(frozen=True, slots=True)
class SyncPlan:
    """Uygulanacak değişiklikler: yeni, güncellenen ve dokunulmayan girişler."""

    added: tuple[KnowledgeEntry, ...] = field(default_factory=tuple)
    updated: tuple[KnowledgeEntry, ...] = field(default_factory=tuple)
    unchanged: tuple[str, ...] = field(default_factory=tuple)

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.updated)


def plan_sync(local_hashes: dict[str, str], manifest: KnowledgeManifest) -> SyncPlan:
    """Yerel özetlerle uzak manifesti karşılaştırıp uygulanacak farkı çıkar.

    `local_hashes`: istemcinin bildiği `entry_id -> content_hash`. Uzakta olup yerelde
    olmayan giriş "yeni"; özeti değişen "güncellenen"; aynı olan "dokunulmayan".
    """

    added: list[KnowledgeEntry] = []
    updated: list[KnowledgeEntry] = []
    unchanged: list[str] = []

    for entry in manifest.entries:
        known = local_hashes.get(entry.entry_id)
        if known is None:
            added.append(entry)
        elif known != entry.content_hash:
            updated.append(entry)
        else:
            unchanged.append(entry.entry_id)

    return SyncPlan(added=tuple(added), updated=tuple(updated), unchanged=tuple(unchanged))
