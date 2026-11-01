"""Sistem istemi bayrakları ve `--system-prompt-snapshot` (#295).

Claude Code'da beş bayrak hem etkileşimli (`claude`) hem başsız (`claude -p`) kipte çalışır:
`--system-prompt` / `--system-prompt-file` varsayılan istemin yerine geçer,
`--append-system-prompt` / `--append-system-prompt-file` sonuna eklenir (dosya içeriği önce).
İstem sohbetin ilk isteğinde kurulup oturuma kaydedilir; `--resume`/`--continue` ile dönülen
sohbet kayıtlı metni kullanır, farklı bayrak metni ancak yeni sohbette etkili olur.
`--system-prompt-snapshot off` her istekte yeniden kurar; `--bare` kipinde kayıt, açıkça `on`
verilmedikçe kapalıdır.

Fusion'da kaydedilen, bayraklardan gelen metindir (Fusion'ın çekirdek istemi her turda
kurulur); sıkıştırma sonrası yeniden kurma henüz yoktur.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..ui import print_messages as texts

if TYPE_CHECKING:
    from .repl.persona_commands import PersonaTurn

SNAPSHOT_DIR = "system-prompt-snapshots"
_SNAPSHOT_VALUES = frozenset({"on", "off"})


@dataclass(frozen=True, slots=True)
class LaunchPrompts:
    """Bayraklardan gelen istem metni: yerine geçen (ya da `None`) ve ek."""

    system_prompt: str | None = None
    extra_system: str = ""
    #: `--bare` (#298): turda sunulan araç kümesi (Bash + dosya okuma/düzenleme); None = kısıt yok.
    tools: frozenset[str] | None = None

    @property
    def empty(self) -> bool:
        return self.system_prompt is None and not self.extra_system and self.tools is None


def from_flags(
    *,
    system_prompt: str | None,
    system_prompt_file: str | None,
    append: str | None,
    append_file: str | None,
) -> LaunchPrompts:
    """Dört bayrağı birleştir; okunamayan dosya `ValueError`."""
    from .print_options import system_prompts

    replacement, extra = system_prompts(
        system_prompt=system_prompt,
        system_prompt_file=system_prompt_file,
        append=append,
        append_file=append_file,
    )
    return LaunchPrompts(replacement, extra)


def check_snapshot(raw: str | None) -> str | None:
    """`--system-prompt-snapshot on|off`; başka değer `ValueError`."""
    if raw is None:
        return None
    value = raw.strip().lower()
    if value not in _SNAPSHOT_VALUES:
        raise ValueError(texts.SYSTEM_PROMPT_SNAPSHOT_INVALID.format(given=raw))
    return value


def snapshot_enabled(raw: str | None, *, bare: bool) -> bool:
    value = check_snapshot(raw)
    if value is None:
        return not bare
    return value == "on"


def recorded(
    memory_dir: Path,
    conversation_id: str,
    current: LaunchPrompts,
    *,
    resuming: bool,
    enabled: bool,
    persist: bool = True,
) -> LaunchPrompts:
    """Sürdürülen sohbette kayıtlı metni, yeni sohbette güncel metni (kaydederek) döndür."""
    if not enabled or not conversation_id:
        return current
    path = memory_dir / SNAPSHOT_DIR / f"{conversation_id}.json"
    if resuming:
        stored = _load(path)
        if stored is not None:
            return stored
    if persist:
        _save(path, current)
    return current


def _load(path: Path) -> LaunchPrompts | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    replacement = data.get("system_prompt")
    extra = data.get("extra_system")
    return LaunchPrompts(
        replacement if isinstance(replacement, str) and replacement else None,
        extra if isinstance(extra, str) else "",
    )


def _save(path: Path, prompts: LaunchPrompts) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"system_prompt": prompts.system_prompt, "extra_system": prompts.extra_system}
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except OSError:
        return  # kayıt yazılamazsa istem yine bu oturumda uygulanır


def bind(state: object, prompts: object, *, resumed: object) -> LaunchPrompts | None:
    """REPL açılışı: sürdürülen sohbette kayıtlı istemi, yenisinde bayrak metnini bağla."""
    if not isinstance(prompts, LaunchSpec):
        return None
    bound = recorded(
        Path(getattr(getattr(state, "config", None), "memory_dir", ".")),
        str(getattr(state, "conversation_id", "") or ""),
        prompts.prompts,
        resuming=resumed is not None,
        enabled=prompts.snapshot,
    )
    if not prompts.bare:
        return bound
    _bind_bare_catalog(state)
    from .print_runtime import BARE_TOOLS

    return replace(bound, tools=BARE_TOOLS)


def _bind_bare_catalog(state: Any) -> None:
    """`--bare`: oturum kataloğu yalnız `--add-dir` becerileri ve `--agents` tanımlarıdır."""
    from .print_runtime import bare_catalog

    state.capabilities = bare_catalog(
        state.config,
        tuple(getattr(state, "extra_roots", ()) or ()),
        tuple(getattr(state, "session_agents", ()) or ()),
    )


@dataclass(frozen=True, slots=True)
class LaunchSpec:
    """Kök komuttan REPL'e geçen açılış istemi, kayıt tercihi ve `--bare`."""

    prompts: LaunchPrompts
    snapshot: bool = True
    bare: bool = False


def apply_to_turn(turn: PersonaTurn, state: object) -> PersonaTurn:
    """REPL turu: oturumun açılış istemini kişilik turuna kat (bayrak kişilikten önce gelir)."""
    prompts = getattr(state, "launch_prompts", None)
    if not isinstance(prompts, LaunchPrompts) or prompts.empty:
        return turn
    extra = "\n\n".join(part for part in (turn.extra_system, prompts.extra_system) if part)
    tools = turn.allowed_tools
    if prompts.tools is not None:
        tools = set(prompts.tools) if tools is None else set(tools) & prompts.tools
    return replace(
        turn,
        system_prompt=prompts.system_prompt or turn.system_prompt,
        extra_system=extra,
        allowed_tools=tools,
    )
