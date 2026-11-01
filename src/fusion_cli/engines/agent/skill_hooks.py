"""Beceri frontmatter `hooks` alanı: çağrıda kaydedilir, oturum boyunca etkin kalır (#161).

Claude Code (code.claude.com/docs/en/skills, Frontmatter reference; hooks "Hooks in skills
and agents"): becerinin `hooks:` bloğu beceri çağrıldığında oturumun kancalarına eklenir ve
oturum bitene kadar çalışır (belge: "registered when the skill is invoked and persist until the
session ends"; bileşen yaşam döngüsüyle sınırlı değildir).
Fusion'da kayıt, oturumun `HookSession.loader`'ını saran
`SkillHookLoader` ile yapılır: küresel tanımlar her tur yine dosyadan okunur, becerinin
kancaları üstüne eklenir. Aynı beceri ikinci kez çağrılınca kancası çiftlenmez.

Güvenlik: depo kaynaklı becerinin kancası ancak güvenilen projede kaydedilir (`model:` ve
`allowed-tools` ile aynı sınır); `disableAllHooks` beceri kancalarını da kapatır; eklenti
becerilerinin kancası katalogda zaten düşürülür. `/clear` kayıtları siler (yeni oturum).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from ...core.hooks.events import HookSet

if TYPE_CHECKING:
    from ...tools.capabilities import Capability
    from ..hooks.session import HookSession


@dataclass(frozen=True, slots=True)
class SkillHookLoader:
    """Küresel yükleyicinin üstüne oturumda çağrılmış becerilerin kancalarını ekle."""

    base: Callable[[], HookSet]
    skills: tuple[tuple[str, HookSet], ...] = ()

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(name for name, _ in self.skills)

    def __call__(self) -> HookSet:
        inherited = self.base()
        if inherited.disabled_reason is not None:
            return inherited
        commands = [*inherited.commands]
        skipped = [*inherited.skipped]
        for _, hooks in self.skills:
            commands.extend(hooks.commands)
            skipped.extend(hooks.skipped)
        return replace(inherited, commands=tuple(commands), skipped=tuple(skipped))


def registered_names(session: HookSession | None) -> tuple[str, ...]:
    """Bu oturumda kancası kaydedilmiş beceri adları."""
    loader = getattr(session, "loader", None)
    return loader.names if isinstance(loader, SkillHookLoader) else ()


def register(session: HookSession | None, skill: Capability, *, trusted: bool) -> bool:
    """Becerinin kancalarını oturuma ekle; eklenmediyse (yok, güvenilmez, kayıtlı) False."""
    hooks = getattr(skill, "hook_definitions", None)
    if session is None or not isinstance(hooks, HookSet) or not trusted:
        return False
    if not hooks.commands and not hooks.skipped:
        return False
    key = skill.qualified_name
    loader = session.loader
    if isinstance(loader, SkillHookLoader):
        if key in loader.names:
            return False
        session.loader = replace(loader, skills=(*loader.skills, (key, hooks)))
    else:
        session.loader = SkillHookLoader(loader, ((key, hooks),))
    session.refresh()
    return True


def forget(session: HookSession | None) -> None:
    """`/clear`: yeni oturumda beceri kancaları yeniden çağrılana kadar yok."""
    loader = getattr(session, "loader", None)
    if session is not None and isinstance(loader, SkillHookLoader):
        session.loader = loader.base
        session.refresh()
