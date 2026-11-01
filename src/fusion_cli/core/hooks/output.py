"""Kanca çıktısının olay başına kuralları (Claude Code hooks başvurusu ile aynı tablolar).

Bu modül saf veridir: `decision.py` hangi alanın hangi olayda atılacağını, hangi terminal
dizisine izin verildiğini ve nesne biçimli araç çıktısının metne nasıl çevrileceğini buradan
okur.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping

from .events import HookEvent

#: `systemMessage` ve `continue` alanlarını atan olaylar (Notification, PreCompact,
#: PostCompact, SessionEnd — Claude belgesinde her olayın bölümünde yazılı).
DISCARDS_SYSTEM_MESSAGE = frozenset(
    {
        HookEvent.NOTIFICATION,
        HookEvent.PRE_COMPACT,
        HookEvent.POST_COMPACT,
        HookEvent.SESSION_END,
        # StopFailure: yalnız `terminalSequence` uygulanır.
        HookEvent.STOP_FAILURE,
        # ConfigChange: yalnız engel kararı; engel mesajı kimseye gösterilmez.
        HookEvent.CONFIG_CHANGE,
    }
)
#: Yalnız `continue`'yu atan olaylar: CwdChanged, TaskCreated (`continue: false` yok sayılır).
DISCARDS_CONTINUE = DISCARDS_SYSTEM_MESSAGE | frozenset(
    {HookEvent.CWD_CHANGED, HookEvent.TASK_CREATED, HookEvent.FILE_CHANGED}
)
#: JSON alanlarının TAMAMI atılan olaylar (SessionEnd karar denetimi yoktur).
DISCARDS_ALL_JSON = frozenset(
    {HookEvent.SESSION_END, HookEvent.INSTRUCTIONS_LOADED, HookEvent.WORKTREE_REMOVE}
)
#: Çıkış kodu ve stderr'i yok sayılan olaylar (Notification hataları kullanıcıya basılmaz).
#: WorktreeRemove: karar denetimi yok, hatası yalnız hata ayıklama günlüğünde (Claude).
#: PermissionDenied: ret zaten verildi; kanca yalnız `retry` ile not düşebilir.
IGNORES_EXIT_CODE = frozenset(
    {
        HookEvent.NOTIFICATION,
        HookEvent.STOP_FAILURE,
        HookEvent.WORKTREE_REMOVE,
        HookEvent.PERMISSION_DENIED,
    }
)

#: İzinli terminal dizileri: OSC 0/1/2/9/99/777 (BEL ya da ST ile biten) ve yalın BEL.
_OSC = r"\x1b\][0-9]+;[^\x07\x1b]*(?:\x07|\x1b\\)"
_ALLOWED_OSC = frozenset({"0", "1", "2", "9", "99", "777"})
_SEQUENCE = re.compile(rf"(?:{_OSC}|\x07)")


def terminal_sequence(value: object) -> str | None:
    """`terminalSequence` izin listesine uyuyorsa dizinin kendisi; değilse `None` (alan atılır)."""
    if not isinstance(value, str) or not value:
        return None
    position = 0
    for match in _SEQUENCE.finditer(value):
        if match.start() != position:
            return None
        text = match.group(0)
        if text != "\x07" and text[2:].split(";", 1)[0] not in _ALLOWED_OSC:
            return None
        position = match.end()
    return value if position == len(value) else None


def tool_output_text(value: object) -> str | None:
    """`updatedToolOutput` / `updatedMCPToolOutput` değerini modele gidecek metne çevir.

    Fusion araçlarının çıktısı metindir: metin olduğu gibi, Claude'un Bash şekli
    (`stdout`/`stderr`) birleştirilerek, MCP `content` blokları metinleriyle, öteki nesneler
    JSON olarak gider. Şekle uymayan değer (sayı, boş) yok sayılır.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        if "stdout" in value or "stderr" in value:
            parts = (value.get("stdout"), value.get("stderr"))
            return "\n".join(part for part in parts if isinstance(part, str) and part)
        content = value.get("content")
        if isinstance(content, list):
            texts = [
                str(block.get("text"))
                for block in content
                if isinstance(block, Mapping) and isinstance(block.get("text"), str)
            ]
            if texts:
                return "\n".join(texts)
        return json.dumps(dict(value), ensure_ascii=False, default=str)
    if isinstance(value, list):
        return json.dumps(value, ensure_ascii=False, default=str)
    return None


def string_list(value: object) -> tuple[str, ...]:
    """Metin listesi alanı (`watchPaths`); bozuk girdiler atlanır."""
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str) and item)
