"""Tek mesajda beceri yığma: `/a /b 123` (Claude Code #174).

Belge (code.claude.com/docs/en/skills, "Stack several skills in one message"): terminal
isteminde mesaj başına birden çok beceri yığılabilir; ilk beceri ve ardından en çok beş
beceri daha açılır. Açılım satır içi (fork olmayan), kullanıcının çağırabileceği beceri
olmayan ilk belirteçte durur; o belirteç ve sonrası açılan HER beceriye `$ARGUMENTS` olur.
Fork becerisi yığına girmez (açılım orada biter). `-p`/SDK yolunda yalnız ilk beceri açılır.
"""

from __future__ import annotations

from ...tools.capabilities import Capability, CapabilityRegistry

#: İlk beceriden sonra açılabilecek en çok beceri.
MAX_STACKED = 5


def _inline(skill: Capability) -> bool:
    return skill.user_invocable and skill.context.strip().lower() != "fork"


def split_stack(
    registry: CapabilityRegistry, first: Capability, argument: str
) -> tuple[tuple[Capability, ...], str]:
    """Yığılmış becerileri ve hepsine verilecek ortak argüman metnini ayır."""
    if not _inline(first):
        return (first,), argument
    stacked: list[Capability] = [first]
    rest = argument
    while len(stacked) <= MAX_STACKED:
        stripped = rest.lstrip()
        token, _, tail = stripped.partition(" ")
        if not token.startswith("/") or len(token) < 2:
            break
        candidate = registry.get_skill(token[1:])
        if candidate is None or not _inline(candidate):
            break
        stacked.append(candidate)
        rest = tail
    return tuple(stacked), rest.strip() if len(stacked) > 1 else argument
