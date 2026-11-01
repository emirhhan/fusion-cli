"""Pazardan kaldırıldığı için otomatik kaldırılan ("Flagged") eklentiler (Claude Code, #397).

Claude Code 2.1.287: `forceRemoveDeletedPlugins: true` pazarda girdilerden düşen kurulum her
kapsamdan kaldırılır ve `flagged-plugins.json`'a `{"plugins": {"ad@pazar": {"flaggedAt"}}}`
olarak yazılır; `/plugin` Installed sekmesi bunları **Flagged** grubunda gösterir (ayrıntı:
"Status: Removed", "Removed from marketplace · reason: …", "Flagged on <tarih>"). Kullanıcı
gördüğünde `seenAt` yazılır; görüldükten 48 saat sonra kayıt oturum başında silinir. Zaten
işaretli eklenti yeniden işaretlenmez.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ..config.plugin_store import plugins_dir
from ..core.atomic_file import atomic_replace_text

_LOG = logging.getLogger(__name__)

FLAGGED_FILE = "flagged-plugins.json"
SEEN_TTL_S = 48 * 3600
REASON_DELISTED = "delisted"
TEXT_DELISTED = (
    "Bu eklenti pazardan kaldırıldı; pazar forceRemoveDeletedPlugins istediği için kurulumu da "
    "kaldırıldı."
)


@dataclass(frozen=True, slots=True)
class FlaggedPlugin:
    ident: str
    flagged_at: str
    seen_at: str = ""

    @property
    def name(self) -> str:
        return self.ident.partition("@")[0]

    @property
    def marketplace(self) -> str:
        return self.ident.partition("@")[2]

    @property
    def date(self) -> str:
        return self.flagged_at[:10]


def _file(base: Path | None) -> Path:
    return (base or plugins_dir()) / FLAGGED_FILE


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def load_flagged(base: Path | None = None) -> tuple[FlaggedPlugin, ...]:
    try:
        raw = json.loads(_file(base).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ()
    plugins = raw.get("plugins") if isinstance(raw, Mapping) else None
    if not isinstance(plugins, Mapping):
        return ()
    found: list[FlaggedPlugin] = []
    for ident, item in plugins.items():
        if isinstance(item, Mapping) and isinstance(item.get("flaggedAt"), str):
            seen = item.get("seenAt")
            found.append(
                FlaggedPlugin(str(ident), item["flaggedAt"], seen if isinstance(seen, str) else "")
            )
    return tuple(sorted(found, key=lambda f: f.ident))


def _save(items: Iterable[FlaggedPlugin], base: Path | None) -> None:
    payload = {
        "plugins": {
            item.ident: {
                "flaggedAt": item.flagged_at,
                **({"seenAt": item.seen_at} if item.seen_at else {}),
            }
            for item in items
        }
    }
    path = _file(base)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_replace_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def flag_plugin(ident: str, base: Path | None = None) -> None:
    current = load_flagged(base)
    if any(item.ident == ident for item in current):
        return
    _save((*current, FlaggedPlugin(ident, _now())), base)
    _LOG.info("Flagged plugin: %s", ident)


def is_flagged(ident: str, base: Path | None = None) -> bool:
    return any(item.ident == ident for item in load_flagged(base))


def mark_seen(idents: Iterable[str], base: Path | None = None) -> None:
    wanted = set(idents)
    current = load_flagged(base)
    changed = tuple(
        FlaggedPlugin(i.ident, i.flagged_at, _now()) if i.ident in wanted and not i.seen_at else i
        for i in current
    )
    if changed != current:
        _save(changed, base)


def expire_seen(base: Path | None = None, *, now: datetime | None = None) -> None:
    """Görüldükten 48 saat sonra kaydı sil (oturum başında)."""
    moment = now or datetime.now(UTC)
    current = load_flagged(base)
    kept = tuple(i for i in current if not i.seen_at or not _older(i.seen_at, moment))
    if kept != current:
        _save(kept, base)


def _older(stamp: str, moment: datetime) -> bool:
    try:
        seen = datetime.fromisoformat(stamp)
    except ValueError:
        return True
    if seen.tzinfo is None:
        seen = seen.replace(tzinfo=UTC)
    return (moment - seen).total_seconds() >= SEEN_TTL_S


def format_flagged_detail(item: FlaggedPlugin) -> str:
    return "\n".join(
        [
            f"{item.name} @ {item.marketplace}",
            "Status: Removed",
            f"Removed from marketplace · reason: {REASON_DELISTED}",
            TEXT_DELISTED,
            f"Flagged on {item.date}",
        ]
    )
