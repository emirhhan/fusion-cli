"""Oturum ajanı sohbete bağlıdır ve sürdürmede geri yüklenir (#16).

Claude Code: `--agent` ya da `agent` ayarıyla seçilen ajan, oturum sürdürülünce araç kısıtları
ve modeliyle geri gelir; ajan artık yoksa uyarı verilip varsayılan araçlarla devam edilir.
Kayıt: `memory_dir/oturum-ajan/<sohbet>.json` (`{"agent": "<ad>"}`).
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

from ...core.errors import ConfigError
from ...ui import messages

if TYPE_CHECKING:
    from .state import ReplState

_LOG = logging.getLogger(__name__)
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")
STORE_DIR = "oturum-ajan"


def store_path(memory_dir: Path, conversation_id: str) -> Path:
    stem = _UNSAFE.sub("_", conversation_id).strip("._") or "oturum"
    return memory_dir / STORE_DIR / f"{stem}.json"


def load(memory_dir: Path, conversation_id: str) -> str:
    """Sohbetin kayıtlı ajan adı; yoksa ya da bozuksa boş metin."""
    try:
        raw = json.loads(store_path(memory_dir, conversation_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    name = raw.get("agent") if isinstance(raw, dict) else None
    return name.strip() if isinstance(name, str) else ""


def save(memory_dir: Path, conversation_id: str, name: str) -> None:
    """Ajan adını yaz; boş ad kaydı siler. Yazma hatası oturumu düşürmez."""
    if not conversation_id:
        return
    path = store_path(memory_dir, conversation_id)
    try:
        if not name:
            path.unlink(missing_ok=True)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"agent": name}, ensure_ascii=False), encoding="utf-8")
    except OSError:
        _LOG.info("oturum ajanı yazılamadı", extra={"sohbet": conversation_id})


def restore(state: ReplState) -> str:
    """Etkin sohbetin ajanını yükle; ajan artık yoksa uyarı metni döndür."""
    from .persona_commands import resolve_session_persona

    name = load(state.config.memory_dir, state.conversation_id)
    if not name:
        return ""
    found = resolve_session_persona(state.capabilities, name)
    if found is None:
        return messages.SESSION_AGENT_MISSING.format(name=name)
    try:
        state.select_persona(found)
    except ConfigError as error:
        return str(error)
    return ""
