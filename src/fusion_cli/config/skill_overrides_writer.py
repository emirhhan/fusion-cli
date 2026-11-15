"""`/skills` panelinin kaydı: `skillOverrides` projenin yerel ayarına yazılır (#176).

Claude Code (code.claude.com/docs/en/skills, "Override skill visibility from settings";
commands `/skills`): panelde Space/Enter görünürlüğü döndürür, Esc kaydeder; değer
`skillOverrides` altına beceri adıyla yazılır. Hedef projenin `.claude/settings.local.json`'ı
(kişisel, depoya girmeyen katman). Dosyanın öteki anahtarları korunur.

Fusion bu dosyanın içeriğine güven karması tutar (izinler aynı dosyadadır): yazmadan önce
güvenilen dosya yazımdan sonra da güvenilir kalsın diye karma tazelenir; güvenilmeyen dosya
Fusion'ın yazımıyla güvenilir hâle GELMEZ.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from ..core.atomic_file import atomic_replace_text
from ..core.errors import ConfigError
from . import trust
from .models import SkillVisibility

#: Panelde Space/Enter ile döngü sırası.
CYCLE: tuple[SkillVisibility, ...] = (
    SkillVisibility.ON,
    SkillVisibility.NAME_ONLY,
    SkillVisibility.USER_INVOCABLE_ONLY,
    SkillVisibility.OFF,
)

SETTINGS_KEY = "skillOverrides"


def next_visibility(current: SkillVisibility) -> SkillVisibility:
    """Döngüde sıradaki görünürlük."""
    index = CYCLE.index(current) if current in CYCLE else 0
    return CYCLE[(index + 1) % len(CYCLE)]


def local_settings_file(root: Path) -> Path:
    return root / trust.PROJECT_PERMISSIONS_PATH


def _read(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ConfigError(f"{path} okunamadı; skillOverrides yazılmadı: {error}") from error
    if not isinstance(data, dict):
        raise ConfigError(f"{path} bir JSON nesnesi değil; skillOverrides yazılmadı.")
    return data


def write_skill_overrides(root: Path, changes: Mapping[str, SkillVisibility]) -> Path:
    """Değişiklikleri `skillOverrides`'a işle (ad → değer); yazılan dosyayı döndür."""
    path = local_settings_file(root)
    if not changes:
        return path
    was_trusted = trust.is_permissions_trusted(root)
    data = _read(path)
    current = data.get(SETTINGS_KEY)
    merged = dict(current) if isinstance(current, dict) else {}
    merged.update({name: value.value for name, value in changes.items()})
    updated = {**data, SETTINGS_KEY: merged}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_replace_text(path, json.dumps(updated, ensure_ascii=False, indent=2) + "\n")
    except OSError as error:
        raise ConfigError(f"{path} yazılamadı: {error}") from error
    if was_trusted:
        trust.record_permissions_digest(root)
    return path
