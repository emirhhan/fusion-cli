"""Oturum hedefinin kalıcı kaydı (P-058): `memory_dir/oturum-hedef/<sohbet>.json`.

Hedef sohbet kimliğine bağlıdır: `fusion --resume` ya da masaüstü sekmesi aynı kimlikle
açılınca etkin/duraklatılmış hedef geri gelir. Kapanan hedefin (Tamam/İmkânsız/`/goal
clear`) dosyası silinir. Yazma hatası oturumu düşürmez.
"""

from __future__ import annotations

import json
from pathlib import Path

from ...core.session_goal import SessionGoal
from .cron_store import conversation_file

_FOLDER = "oturum-hedef"


def load(memory_dir: Path, conversation_id: str) -> SessionGoal | None:
    """Kayıtlı hedefi oku; dosya yok ya da bozuksa None."""
    try:
        raw = conversation_file(memory_dir, _FOLDER, conversation_id).read_text(encoding="utf-8")
        return SessionGoal.from_dict(json.loads(raw))
    except (OSError, ValueError):
        return None


def save(memory_dir: Path, conversation_id: str, goal: SessionGoal | None) -> None:
    """Hedefi yaz; hedef yoksa dosyayı sil."""
    path = conversation_file(memory_dir, _FOLDER, conversation_id)
    try:
        if goal is None:
            path.unlink(missing_ok=True)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(goal.to_dict(), ensure_ascii=False), encoding="utf-8")
    except OSError:
        return
