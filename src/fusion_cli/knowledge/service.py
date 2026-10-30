"""İstemci senkronizasyon servisi — doğrula, planla, uygula, durumu yaz.

İstemci tarafı akış: uzak manifesti doğrula (imza/bütünlük/sır) → yerel duruma göre
yalnızca değişeni planla → değişen dersleri belleğe uygula → yerel sync durumunu
güncelle. İstemci global depoya YAZMAZ; yalnızca doğrulanmış paketi okuyup uygular.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from ..core.memory import Lesson, LessonKind, LessonMemory, LessonSource
from .manifest import KnowledgeEntry, KnowledgeManifest
from .sync import SyncPlan, plan_sync
from .validation import validate_manifest

#: Durum dosyasındaki alan adları (yeni biçim: `{"version": n, "entries": {...}}`).
_STATE_VERSION_KEY = "version"
_STATE_ENTRIES_KEY = "entries"
_ROLLBACK_PROBLEM = "geri sürüm reddedildi: paket v{offered}, uygulanmış v{applied}"


@dataclass(frozen=True, slots=True)
class SyncReport:
    """Bir senkronizasyonun sonucu."""

    ok: bool
    added: int = 0
    updated: int = 0
    #: Doğrulama başarısızsa Türkçe sorunlar (ok=False iken dolu).
    problems: tuple[str, ...] = field(default_factory=tuple)


def _read_state_file(path: Path) -> dict[str, object]:
    """Durum dosyasını oku; yok/bozuk/okunamıyorsa boş. Eski düz biçim (`{id: hash}`) da okunur.

    Bozuk JSON eskiden `load_state`i (ve `fusion knowledge sync`i) çıplak traceback ile
    düşürüyordu (E1-39). Boş durumun sonucu yalnızca "her şeyi yeniden planla"dır;
    `LessonMemory.add` aynı metni tekilleştirir, veri kaybı yoktur.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    if isinstance(raw.get(_STATE_ENTRIES_KEY), dict):
        return raw
    return {_STATE_ENTRIES_KEY: raw}  # eski düz biçim: sürüm bilinmez


def load_state(path: Path) -> dict[str, str]:
    """Yerel sync durumu: `entry_id -> content_hash`. Yoksa ya da bozuksa boş."""
    entries = _read_state_file(path).get(_STATE_ENTRIES_KEY, {})
    if not isinstance(entries, dict):
        return {}
    return {str(key): str(value) for key, value in entries.items()}


def load_version(path: Path) -> int:
    """En son uygulanmış paket sürümü; hiç uygulanmadıysa (ya da eski biçimde) 0."""
    version = _read_state_file(path).get(_STATE_VERSION_KEY, 0)
    return version if isinstance(version, int) and not isinstance(version, bool) else 0


def save_state(state: dict[str, str], path: Path, *, version: int = 0) -> None:
    """Durumu ATOMİK yaz: yarım yazılmış dosya sonraki sync'i düşürmesin."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        {_STATE_VERSION_KEY: version, _STATE_ENTRIES_KEY: state}, ensure_ascii=False, indent=2
    )
    handle, name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    gecici = Path(name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as dosya:
            dosya.write(payload)
        gecici.replace(path)
    except BaseException:
        gecici.unlink(missing_ok=True)
        raise


def status(manifest: KnowledgeManifest, state_path: Path) -> SyncPlan:
    """Uygulanmadan, yerel duruma göre neyin değişeceğini göster."""
    return plan_sync(load_state(state_path), manifest)


def sync(
    manifest: KnowledgeManifest,
    memory: LessonMemory,
    *,
    state_path: Path,
    public_key: str,
) -> SyncReport:
    """Manifesti doğrula (AÇIK anahtarla) ve yalnızca değişen dersleri belleğe uygula."""

    validation = validate_manifest(manifest, public_key=public_key)
    if not validation.ok:
        return SyncReport(ok=False, problems=validation.problems)
    # Geri alma koruması: önceden geçerli imzalı ESKİ bir manifest tekrar sunulursa
    # (kaldırılmış/zararlı bulunmuş dersler dahil) kabul edilmez (E1-39).
    uygulanmis = load_version(state_path)
    if manifest.version < uygulanmis:
        return SyncReport(
            ok=False,
            problems=(_ROLLBACK_PROBLEM.format(offered=manifest.version, applied=uygulanmis),),
        )

    plan = plan_sync(load_state(state_path), manifest)
    for entry in (*plan.added, *plan.updated):
        memory.add(_to_lesson(entry))

    # Durum, uzağın TAMAMIYLA eşitlenir: sonraki sync yalnızca yeni değişeni taşır.
    new_state = {entry.entry_id: entry.content_hash for entry in manifest.entries}
    save_state(new_state, state_path, version=manifest.version)

    return SyncReport(ok=True, added=len(plan.added), updated=len(plan.updated))


def _to_lesson(entry: KnowledgeEntry) -> Lesson:
    kind = LessonKind.MISTAKE if entry.kind == "mistake" else LessonKind.SUCCESS
    return Lesson(text=entry.text, kind=kind, scope=entry.scope, source=LessonSource.SEED)
