"""Oturum zamanlayıcısının kalıcı kaydı (P-038): `memory_dir/oturum-cron/<sohbet>.json`.

Görevler sohbet kimliğine bağlıdır: masaüstü sekmesi kapanıp aynı kimlikle açılınca
süresi dolmamış görevler geri gelir. Terminal REPL'i her açılışta yeni kimlik
ürettiği için orada yalnız oturum boyunca yaşar (P-014 `--resume` gelince aynı
dosya devralınır). Yazma hatası oturumu düşürmez.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from ...core.session_cron import SessionCron

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def store_path(memory_dir: Path, conversation_id: str) -> Path:
    stem = _UNSAFE.sub("_", conversation_id).strip("._") or "oturum"
    return memory_dir / "oturum-cron" / f"{stem}.json"


def load(memory_dir: Path, conversation_id: str) -> SessionCron:
    """Kayıtlı görevleri oku; dosya yok ya da bozuksa boş liste."""
    try:
        raw = store_path(memory_dir, conversation_id).read_text(encoding="utf-8")
    except OSError:
        return SessionCron()
    try:
        return SessionCron.from_dict(json.loads(raw))
    except ValueError:
        return SessionCron()


def save(memory_dir: Path, conversation_id: str, cron: SessionCron) -> None:
    """Görev listesini yaz; boş listede dosya silinir ki çöp birikmesin."""
    path = store_path(memory_dir, conversation_id)
    try:
        if len(cron) == 0:
            path.unlink(missing_ok=True)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cron.to_dict(), ensure_ascii=False), encoding="utf-8")
    except OSError:
        return
