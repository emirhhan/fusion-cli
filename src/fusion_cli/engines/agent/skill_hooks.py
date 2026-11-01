"""Beceri frontmatter kancaları (Claude Code "Hooks in skills and agents").

Beceri çağrılınca (`read_skill`/`Skill` aracı ya da kullanıcının `/ad` seçimi)
SKILL.md frontmatter'ındaki `hooks` bloğu oturum kancalarına eklenir ve oturumun geri
kalanında çalışır; `once: true` kanca ilk başarılı çalışmadan sonra kalkar.
Proje içindeki becerinin kancası, proje kancaları gibi etkileşimli oturumda klasör
güveni ister (`-p`'de klasör güvenilir sayılır).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from ...config.hook_parse import DEFAULT_HOOK_TIMEOUT_S, parse_hooks_block
from ...config.trust import is_file_trusted
from ...core.hooks.events import HookCommand

if TYPE_CHECKING:
    from ..hooks.session import HookSession
    from .loop import AgentDeps

_LOG = logging.getLogger(__name__)
SKILL_TOOL = "read_skill"
SKILL_SOURCE_PREFIX = "beceri:"


def frontmatter_hooks(text: str) -> object | None:
    """SKILL.md'nin YAML frontmatter'ındaki `hooks` bloğu (yoksa `None`)."""
    stripped = text.lstrip()
    if not stripped.startswith("---"):
        return None
    end = stripped.find("\n---", 3)
    if end == -1:
        return None
    try:
        raw = yaml.safe_load(stripped[3:end])
    except yaml.YAMLError:
        _LOG.warning("beceri frontmatter'ı geçersiz YAML; kancaları uygulanmadı")
        return None
    return raw.get("hooks") if isinstance(raw, dict) else None


def skill_hook_commands(name: str, path: Path) -> tuple[HookCommand, ...]:
    """Becerinin kanca tanımları (kaynak `beceri:<ad>`)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ()
    block = frontmatter_hooks(text)
    if block is None:
        return ()
    commands, _skipped = parse_hooks_block(
        block,
        source=f"{SKILL_SOURCE_PREFIX}{name}",
        path=path,
        default_timeout_s=DEFAULT_HOOK_TIMEOUT_S,
    )
    return commands


def _allowed(session: HookSession, path: Path) -> bool:
    root = session.project_dir or session.root
    try:
        inside = path.resolve().is_relative_to(root.resolve())
    except OSError:
        return False
    return not inside or not session.interactive or is_file_trusted(root, path)


def activate_skill(session: HookSession | None, name: str, path: Path | None) -> int:
    """Becerinin kancalarını oturuma ekle; eklenen tanım sayısı."""
    if session is None or path is None or not _allowed(session, path):
        return 0
    commands = skill_hook_commands(name, path)
    if commands:
        session.add_session_commands(commands)
    return len(commands)


def after_skill_tool(
    deps: AgentDeps,
    session: HookSession | None,
    tool_name: str,
    args: Mapping[str, object],
    *,
    ok: bool,
) -> None:
    """`read_skill` başarıyla becerinin gövdesini yüklediyse kancalarını etkinleştir."""
    if tool_name != SKILL_TOOL or not ok or args.get("file") or session is None:
        return
    library = getattr(deps, "capabilities", None)
    skill = library.get_skill(str(args.get("name", ""))) if library is not None else None
    if skill is not None:
        activate_skill(session, skill.name, skill.path)


def activate_selected_skill(deps: AgentDeps) -> None:
    """Kullanıcının `/ad` ile seçtiği becerinin kancaları (kök tur başında)."""
    selection = getattr(deps, "selected_skill", None)
    library = getattr(deps, "capabilities", None)
    if selection is None or library is None:
        return
    skill = library.get_skill(str(getattr(selection, "qualified_name", "")))
    if skill is not None:
        activate_skill(getattr(deps, "hooks", None), skill.name, skill.path)
