"""İstemci senkronizasyon servisi — doğrula, planla, uygula, durumu yaz.

İstemci tarafı akış: uzak manifesti doğrula (imza/bütünlük/sır) → yerel duruma göre
yalnızca değişeni planla → değişen dersleri belleğe uygula → yerel sync durumunu
güncelle. İstemci global depoya YAZMAZ; yalnızca doğrulanmış paketi okuyup uygular.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ..core.memory import Lesson, LessonKind, LessonMemory, LessonSource
from .manifest import KnowledgeEntry, KnowledgeManifest
from .sync import SyncPlan, plan_sync
from .validation import validate_manifest


@dataclass(frozen=True, slots=True)
class SyncReport:
    """Bir senkronizasyonun sonucu."""

    ok: bool
    added: int = 0
    updated: int = 0
    #: Doğrulama başarısızsa Türkçe sorunlar (ok=False iken dolu).
    problems: tuple[str, ...] = field(default_factory=tuple)


def load_state(path: Path) -> dict[str, str]:
    """Yerel sync durumu: `entry_id -> content_hash`. Yoksa boş."""
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {str(key): str(value) for key, value in raw.items()} if isinstance(raw, dict) else {}


def save_state(state: dict[str, str], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def status(manifest: KnowledgeManifest, state_path: Path) -> SyncPlan:
    """Uygulanmadan, yerel duruma göre neyin değişeceğini göster."""
    return plan_sync(load_state(state_path), manifest)


def sync(
    manifest: KnowledgeManifest,
    memory: LessonMemory,
    *,
    state_path: Path,
    key: str,
) -> SyncReport:
    """Manifesti doğrula ve yalnızca değişen dersleri belleğe uygula."""

    validation = validate_manifest(manifest, key=key)
    if not validation.ok:
        return SyncReport(ok=False, problems=validation.problems)

    plan = plan_sync(load_state(state_path), manifest)
    for entry in (*plan.added, *plan.updated):
        memory.add(_to_lesson(entry))

    # Durum, uzağın TAMAMIYLA eşitlenir: sonraki sync yalnızca yeni değişeni taşır.
    new_state = {entry.entry_id: entry.content_hash for entry in manifest.entries}
    save_state(new_state, state_path)

    return SyncReport(ok=True, added=len(plan.added), updated=len(plan.updated))


def _to_lesson(entry: KnowledgeEntry) -> Lesson:
    kind = LessonKind.MISTAKE if entry.kind == "mistake" else LessonKind.SUCCESS
    return Lesson(text=entry.text, kind=kind, scope=entry.scope, source=LessonSource.SEED)
