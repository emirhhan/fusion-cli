"""Oturum boyu eklenen kancalar (beceri frontmatter'ı) ve `once` (Claude Code).

Beceri çağrılınca frontmatter'ındaki `hooks` bloğu oturumun geri kalanında etkin olur;
`once: true` taşıyan kanca ilk başarılı çalışmadan sonra kaldırılır (yalnız beceri
frontmatter'ında anlamlıdır; ayar dosyasında yok sayılır).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import replace

from ...config.hook_policy import policy_filter
from ...core.hooks.decision import is_failure
from ...core.hooks.events import HookCommand, HookRun, HookSet, HookVerdict


def identity(command: HookCommand) -> tuple[str, str, str, str]:
    """Süre değişse de aynı kalan kimlik (olay, eşleştirici, komut, dosya)."""
    return (command.event.value, command.matcher, command.command, command.path)


def merged(base: HookSet, extra: Sequence[HookCommand]) -> HookSet:
    """Dosya katmanları + oturum boyu kancalar (kapatma kuralı ve ayar politikası ortaktır)."""
    if not extra:
        return base
    kept, skipped = policy_filter(base, extra)
    return replace(base, commands=(*base.commands, *kept), skipped=(*base.skipped, *skipped))


def added(current: Sequence[HookCommand], new: Iterable[HookCommand]) -> tuple[HookCommand, ...]:
    """Aynı tanım ikinci çağrıda yinelenmez."""
    seen = {identity(command) for command in current}
    fresh = [command for command in new if identity(command) not in seen]
    return (*current, *fresh)


def after_once(
    current: Sequence[HookCommand], runs: Sequence[HookRun], verdicts: Sequence[HookVerdict]
) -> tuple[HookCommand, ...]:
    """`once` kancası başarılı çalıştıysa oturum listesinden çıkar."""
    done = {
        identity(run.command)
        for run, verdict in zip(runs, verdicts, strict=True)
        if run.command.once
        and not is_failure(verdict)
        and run.exit_code in (0, None)
        and run.error is None
        and not run.timed_out
    }
    if not done:
        return tuple(current)
    return tuple(command for command in current if identity(command) not in done)
