"""Oturumun PR künyesi sohbete bağlıdır ve kalıcıdır (P-057).

Kayıt: `memory_dir/oturum-pr/<sohbet>.json` (`{"repo", "number", "url"}`). Terminal REPL'i,
tam ekran ve masaüstü tur sonunda `bind_from_turn` çağırır; sohbet değişince (`/resume`,
masaüstü sekme değişimi) `restore`, sohbet temizlenince (`/reset`, masaüstü `/clear`) ya da
silinince `forget` çağrılır.

Ölçüldü (31 Ekim, bağımsız inceleme): `linked_pr` yalnız bellekteydi; masaüstünde sohbet A'da
açılan PR rozeti aynı oturumda sohbet B'ye geçince B'de görünüyor, `/reset` sonrası durum
satırı eski PR'ı gösteriyor, `--resume` ile açılan sohbette bağ kayboluyordu. Ayrıca künye
çıkarımı tur bittikten sonra korumasız koşuyordu: beklenmeyen bir araç kaydı turu düşürüyordu.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from ...core.pull_request import PullRequestLink
from ...engines.effects.pull_request import session_pull_request

if TYPE_CHECKING:
    from .state import ReplState

_LOG = logging.getLogger(__name__)
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")
STORE_DIR = "oturum-pr"


def store_path(memory_dir: Path, conversation_id: str) -> Path:
    stem = _UNSAFE.sub("_", conversation_id).strip("._") or "oturum"
    return memory_dir / STORE_DIR / f"{stem}.json"


def load(memory_dir: Path, conversation_id: str) -> PullRequestLink | None:
    """Sohbetin kayıtlı PR künyesi; yoksa ya da bozuksa None."""
    try:
        raw = json.loads(store_path(memory_dir, conversation_id).read_text(encoding="utf-8"))
        link = PullRequestLink(str(raw["repo"]), int(raw["number"]), str(raw["url"]))
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return link if link.url.startswith("https://") else None


def save(memory_dir: Path, conversation_id: str, link: PullRequestLink | None) -> None:
    """Künyeyi yaz; `None` kaydı siler. Yazma hatası oturumu düşürmez."""
    path = store_path(memory_dir, conversation_id)
    try:
        if link is None:
            path.unlink(missing_ok=True)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"repo": link.repo, "number": link.number, "url": link.url}
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except OSError:
        _LOG.info("PR künyesi yazılamadı", extra={"sohbet": conversation_id})


def bind_from_turn(state: ReplState, tool_uses: Sequence[object]) -> None:
    """Turda açılan/okunan PR'ı oturuma bağla; künye yalnız süstür, hata turu düşürmez."""
    try:
        link = session_pull_request(tool_uses)
    except Exception:  # künye çıkarımı tur kaydını bozamaz; log'lanır
        _LOG.exception("Tur sonu PR künyesi çıkarılamadı")
        return
    if link is None or link == state.linked_pr:
        return
    state.linked_pr = link
    save(state.config.memory_dir, state.conversation_id, link)


def restore(state: ReplState) -> None:
    """Etkin sohbetin künyesini yükle (sohbet değişti)."""
    state.linked_pr = load(state.config.memory_dir, state.conversation_id)


def forget(state: ReplState) -> None:
    """Etkin sohbetin künyesini sil (sohbet temizlendi)."""
    state.linked_pr = None
    save(state.config.memory_dir, state.conversation_id, None)
