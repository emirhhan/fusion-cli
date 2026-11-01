"""`/memory` komutu: düz metin otomatik bellek (P-036).

`#` not kısayolu Claude Code'da olmadığı için kaldırıldı (#220); `add_memory_note` kalır.

Claude Code'un `/memory` komutuyla aynı iş: durum, aç/kapa (kalıcı), düzenleyicide aç,
konu listesi, Claude belleğinden içe aktarma. İşleyiciler ince kalır; bellek mantığı
`memory/plain_memory.py`'dedir.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import replace

from ...config.paths import editor_command
from ...config.writer import write_runtime_flag
from ...engines.agent.team import resolve_persona
from ...history.claude_source import slug_for
from ...memory.plain_memory import PlainMemoryError, build_plain_memory, open_agent_memory
from ...ui import messages
from . import memory_picker
from .state import ReplState

#: `/memory import <kaynak>` ile alınabilecek dış bellekler: kaynak adı → ev dizinine göre yol.
IMPORT_SOURCES = ("claude",)


def memory(state: ReplState, argument: str) -> str:
    """`/memory [<n>|durum|on|off|edit|list|import <kaynak>|ajan <ad> [sil]|<konu>]`."""
    word, _, rest = argument.strip().partition(" ")
    word = word.lower()
    if word in ("on", "off", "ac", "aç", "kapat"):
        return _toggle(state, word in ("on", "ac", "aç"))
    if word in ("ajan", "agent"):
        # Ajan belleği projenin otomatik belleğinden bağımsızdır (P-055); kapalıyken de görülür.
        return _agent(state, rest.strip())
    if not word:
        # Claude Code `/memory` (#154): bellek dosyası seçicisi; `/memory <n>` açar.
        return memory_picker.render_picker(state)
    if word.isdigit():
        return memory_picker.open_choice(state, word)
    if word in ("durum", "status"):
        return _status(state) if state.plain_memory is not None else messages.MEMORY_OFF_HINT
    if state.plain_memory is None:
        return messages.MEMORY_OFF_HINT
    if word == "edit":
        return _edit(state)
    if word == "list":
        topics = ", ".join(state.plain_memory.topics()) or "-"
        return f"Konular: {topics}"
    if word == "import":
        return _import(state, rest.strip().lower())
    if word:
        text = state.plain_memory.read(word)
        if not text.strip():
            topics = ", ".join(state.plain_memory.topics()) or "-"
            return messages.MEMORY_TOPIC_NONE.format(topics=topics)
        return text
    return _status(state)


def _status(state: ReplState) -> str:
    assert state.plain_memory is not None
    status = state.plain_memory.status()
    return messages.MEMORY_STATUS.format(
        state=messages.REPL_ON,
        path=state.plain_memory.index_path,
        lines=status.index_lines,
        kb=status.index_bytes / 1024,
        truncated=messages.MEMORY_STATUS_TRUNCATED if status.truncated else "",
        topics=", ".join(status.topics) or "-",
    )


def _toggle(state: ReplState, enabled: bool) -> str:
    state.config = replace(state.config, runtime=replace(state.config.runtime, auto_memory=enabled))
    write_runtime_flag(state.config, "auto_memory", enabled)
    state.plain_memory = build_plain_memory(state.config, state.root)
    return messages.MEMORY_TOGGLED.format(state=messages.REPL_ON if enabled else messages.REPL_OFF)


def _edit(state: ReplState) -> str:
    assert state.plain_memory is not None
    path = state.plain_memory.index_path
    if not path.is_file():
        state.plain_memory.note("(ilk not; bu satırı silebilirsin)")
    if not sys.stdin.isatty():
        return messages.MEMORY_EDIT_NO_TTY.format(path=path)
    try:
        subprocess.run([*editor_command(), str(path)], check=False)
    except OSError as error:
        return f"Düzenleyici açılamadı: {error}. Dosya: {path}"
    return messages.MEMORY_EDIT_OPENED


def _agent(state: ReplState, argument: str) -> str:
    """`/memory ajan <ad>` durum + indeks, `/memory ajan <ad> sil` belleği siler (P-055)."""
    name, _, action = argument.partition(" ")
    if not name:
        return messages.MEMORY_AGENT_USAGE
    persona = resolve_persona(state.capabilities, name)
    if persona.name != name and persona.name.lower() != name.lower():
        return messages.MEMORY_AGENT_UNKNOWN.format(agent=name)
    memory = open_agent_memory(
        state.config, state.root, persona.name, persona.memory_scope, home=state.home
    )
    if memory is None:
        return messages.MEMORY_AGENT_NO_SCOPE.format(agent=persona.name)
    if action.strip().lower() in ("sil", "clear", "temizle"):
        try:
            cleared = memory.clear()
        except PlainMemoryError as error:
            return str(error)
        template = messages.MEMORY_AGENT_CLEARED if cleared else messages.MEMORY_AGENT_CLEAR_NONE
        return template.format(agent=persona.name)
    if not memory.exists():
        return messages.MEMORY_AGENT_EMPTY.format(
            agent=persona.name, scope=persona.memory_scope, path=memory.index_path
        )
    status = memory.status()
    head = messages.MEMORY_AGENT_STATUS.format(
        agent=persona.name,
        scope=persona.memory_scope,
        path=memory.index_path,
        lines=status.index_lines,
        kb=status.index_bytes / 1024,
        topics=", ".join(status.topics) or "-",
    )
    return f"{head}\n\n{memory.read()}"


def _import(state: ReplState, source: str) -> str:
    assert state.plain_memory is not None
    if source not in IMPORT_SOURCES:
        return messages.MEMORY_IMPORT_USAGE
    source_dir = state.home / ".claude" / "projects" / slug_for(state.root) / "memory"
    count = state.plain_memory.import_markdown(source_dir, source=source)
    if count == 0:
        return messages.MEMORY_IMPORT_NONE.format(source=source, path=source_dir)
    return messages.MEMORY_IMPORTED.format(
        count=count, source=source, path=state.plain_memory.index_path
    )
