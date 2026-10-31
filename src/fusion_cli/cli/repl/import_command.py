"""REPL `/import <kaynak> [--dry-run|--yes]` ve `/release-notes [sürüm|liste]` (P-071).

Claude Code'daki gibi argümansız `/import` önizleme gösterir; yazma yalnız `--yes` ile olur
(REPL komutları senkron metin döndürür, ayrıca soru sorulmaz).
"""

from __future__ import annotations

from ... import __version__
from ...config.importers import apply_plan, build_plan, default_secrets, source_names
from ...config.release_notes import release_notes_text
from ...core.errors import ConfigError
from ..import_view import format_plan, format_report
from .state import ReplState

USAGE = "Kullanım: /import <{sources}> [--dry-run|--yes]"
INSTALLED_VERSION = "Kurulu sürüm: {version}"
_YES = frozenset({"--yes", "-y", "evet"})
_DRY = frozenset({"--dry-run", "onizle", "önizle"})


def import_command(state: ReplState, argument: str) -> str:
    words = argument.split()
    sources = [word for word in words if not word.startswith("-") and word not in _YES | _DRY]
    if len(sources) != 1:
        return USAGE.format(sources="|".join(source_names()))
    flags = set(words) - set(sources)
    try:
        plan = build_plan(sources[0], home=state.home, root=state.root, config=state.config)
    except ConfigError as error:
        return str(error)
    if not (flags & _YES) or (flags & _DRY) or not plan.pending:
        return format_plan(plan, command=f"/import {plan.source}")
    preview = format_plan(plan)
    state.config, report = apply_plan(
        plan, config=state.config, root=state.root, secrets=default_secrets()
    )
    if state.capabilities is not None:
        # Yeni komut/kural dosyaları katalogda hemen görünsün.
        state.capabilities.invalidate()
    return f"{preview}\n\n{format_report(report)}"


def release_notes_command(state: ReplState, argument: str) -> str:
    del state  # imza kayıt defteriyle aynı
    return f"{INSTALLED_VERSION.format(version=__version__)}\n{release_notes_text(argument)}"
