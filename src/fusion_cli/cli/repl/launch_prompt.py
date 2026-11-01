"""`fusion "query"` ilk istemle açılış ve `--session-id <uuid>` (#204).

Claude Code: `claude "query"` etkileşimli oturumu ilk istemle açar, `claude -r "<oturum>"
"query"` sürdürüp istemi gönderir; `--session-id` sohbete belirli bir UUID verir. typer ana
callback'i alt komutları olan bir gruptur ve konum argümanı alt komut adı sanılır; bu yüzden
giriş noktası ilk konum argümanı bir alt komut DEĞİLSE önüne gizli `--prompt-arg` bayrağını
koyar (`--resume` seçici işaretiyle aynı yöntem, bkz. `resume_launch`).
"""

from __future__ import annotations

import uuid
from collections.abc import Collection, Sequence
from pathlib import Path

from ...core.errors import SessionNotFoundError
from ...ui import messages

#: Ana callback'in gizli ilk-istem seçeneği.
PROMPT_FLAG = "--prompt-arg"
#: Ana callback'te değer alan seçenekler: ardından gelen sözcük konum argümanı değildir.
#: `tests/test_launch_prompt.py` ana komutun değerli her seçeneğinin burada olduğunu sınar.
VALUE_OPTIONS = frozenset(
    {
        "--add-dir",
        "--agent",
        "--agents",
        "--set",
        "--profile",
        "--resume",
        "-r",
        "--name",
        "-n",
        "--worktree",
        "-w",
        "--session-id",
        "--from-pr",
        PROMPT_FLAG,
    }
)


def normalize_prompt_argv(argv: Sequence[str], subcommands: Collection[str]) -> list[str]:
    """İlk konum argümanı alt komut değilse önüne `--prompt-arg` ekle."""
    index = 0
    while index < len(argv):
        token = argv[index]
        if token == "--":
            return list(argv)
        if token.startswith("-"):
            takes_value = token in VALUE_OPTIONS and "=" not in token
            index += 2 if takes_value else 1
            continue
        if token in subcommands:
            return list(argv)
        return [*argv[:index], PROMPT_FLAG, *argv[index:]]
    return list(argv)


def session_id_value(raw: str) -> str:
    """`--session-id` değerini doğrula; Fusion sohbet kimliğine (`session-<hex>`) çevir."""
    try:
        parsed = uuid.UUID(raw.strip())
    except ValueError:
        raise SessionNotFoundError(messages.SESSION_ID_INVALID.format(value=raw)) from None
    return f"session-{parsed.hex}"


def ensure_unused(memory_dir: Path, root: Path, conversation_id: str) -> None:
    """Claude Code: kullanılan bir kimlik `--session-id` ile yeniden açılmaz."""
    from .transcript_store import list_conversations

    if any(ref.conversation_id == conversation_id for ref in list_conversations(memory_dir, root)):
        raise SessionNotFoundError(messages.SESSION_ID_IN_USE.format(value=conversation_id))
