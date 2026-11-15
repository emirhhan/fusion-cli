"""Eklentinin kalıcı veri klasörü — `${CLAUDE_PLUGIN_DATA}` (#387).

Claude Code (plugins-reference "Environment variables"): `~/.claude/plugins/data/<id>/`;
ilk başvuruda oluşturulur, güncellemelerde korunur. `<id>` eklenti kimliğidir; harf, rakam,
`_` ve `-` dışındaki her karakter `-` olur. Fusion'da kök `<veri>/eklentiler/.veri/<id>/`
(nokta öneki: hiçbir eklentinin kurulum klasörüyle çakışmaz).
"""

from __future__ import annotations

import re
from pathlib import Path

from .paths import user_data_dir

DATA_DIRNAME = ".veri"
_UNSAFE = re.compile(r"[^A-Za-z0-9_-]")


def plugin_data_dir(plugin_id: str, *, create: bool = False) -> Path:
    path = user_data_dir() / "eklentiler" / DATA_DIRNAME / _UNSAFE.sub("-", plugin_id)
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path
