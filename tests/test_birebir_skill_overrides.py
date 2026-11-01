"""`settings.json` `skillOverrides` (Claude Code #176; code.claude.com/docs/en/skills)."""

from __future__ import annotations

import json
from pathlib import Path

from fusion_cli.tools.capability_overrides import registry_from_config

from .fakes import make_config


def _skill(base: Path, name: str) -> None:
    folder = base / ".claude" / "skills" / name
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {name} açıklaması\n---\ngövde", encoding="utf-8"
    )


def test_settings_skill_overrides_gorunurlugu_belirler(tmp_path: Path) -> None:
    home, root = tmp_path / "ev", tmp_path / "proje"
    for name in ("eski", "gizli", "kullanici", "olagan"):
        _skill(home, name)
    (root / ".claude").mkdir(parents=True)
    (root / ".claude" / "settings.json").write_text(
        json.dumps(
            {
                "skillOverrides": {
                    "eski": "name-only",
                    "gizli": "off",
                    "kullanici": "user-invocable-only",
                    "olagan": "gecersiz",
                }
            }
        ),
        encoding="utf-8",
    )

    registry = registry_from_config(make_config(), home, root)
    skills = {item.name: item for item in registry.skills()}

    assert "gizli" not in skills
    assert skills["eski"].describe_in_index is False
    assert skills["kullanici"].model_invocable is False and skills["kullanici"].user_invocable
    assert skills["olagan"].describe_in_index and skills["olagan"].model_invocable
