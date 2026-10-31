"""Oturum zamanlayıcısının kalıcı kaydı (P-038): `memory_dir/oturum-cron/<sohbet>.json`.

Görevler sohbet kimliğine bağlıdır: masaüstü sekmesi kapanıp aynı kimlikle açılınca
süresi dolmamış görevler geri gelir. Terminal REPL'i her açılışta yeni kimlik
ürettiği için orada yalnız oturum boyunca yaşar (P-014 `--resume` gelince aynı
dosya devralınır). Yazma hatası oturumu düşürmez.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from ...core.session_cron import MAX_AGE_S, SessionCron

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def store_path(memory_dir: Path, conversation_id: str) -> Path:
    stem = _UNSAFE.sub("_", conversation_id).strip("._") or "oturum"
    return memory_dir / "oturum-cron" / f"{stem}.json"


def load(memory_dir: Path, conversation_id: str) -> SessionCron:
    """Kayıtlı görevleri oku; dosya yok ya da bozuksa boş liste.

    Her yüklemede bayat kayıtlar süpürülür (`sweep_stale`); REPL ve masaüstü aynı
    yoldan geçtiği için ayrı çağrı gerekmez.
    """
    sweep_stale(memory_dir, now=time.time())
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


def sweep_stale(memory_dir: Path, *, now: float) -> int:
    """`MAX_AGE_S`'den uzun süredir yazılmamış kayıtları sil; silinen sayısını döndür.

    Görevler en çok 7 gün yaşar ve her tetiklemede kayıt yeniden yazılır; bu süreyi
    aşan dosyadaki görevlerin hepsi düşmüştür. Ölçüldü (31 Ekim): terminal REPL'i
    her açılışta yeni kimlik ürettiğinden görevli çıkılan oturumların dosyaları
    hiç yüklenmeden birikiyordu.
    """
    folder = memory_dir / "oturum-cron"
    removed = 0
    try:
        candidates = list(folder.glob("*.json"))
    except OSError:
        return 0
    for path in candidates:
        try:
            if now - path.stat().st_mtime > MAX_AGE_S:
                path.unlink()
                removed += 1
        except OSError:
            continue
    return removed
