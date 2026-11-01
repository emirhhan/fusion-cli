"""Oturum kişiliği: `--agent <ad>` ve `/persona` (P-053).

Claude Code'un `claude --agent <name>` davranışının karşılığı: oturumun TAMAMI bir ajan
tanımıyla çalışır — tanımın gövdesi sistem istemine girer, `tools`/`disallowedTools`
kümesi araçları daraltır. Yerleşik `explore` (salt-okur keşif) ve `plan` (planlayıcı)
dahil `.claude/agents`, `.codex/agents` ve proje tanımları kullanılabilir. Kişilik tur
bazında uygulanır; `/persona off` ile kapanır. Alt ajan ayarlarının geri kalanı
(model/izin kipi) oturumda uygulanmaz: oturumun modeli `/model`, kipi `/auto` gibi
komutlarla kullanıcı seçer.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...engines.agent.team import GENERIC_PERSONA, Persona, resolve_persona
from ...tools.capabilities import CapabilityRegistry
from ...ui import messages
from .state import ReplState

#: `/persona off` eş anlamlıları.
_OFF_WORDS = frozenset({"off", "kapat", "none", "yok"})


@dataclass(frozen=True, slots=True)
class PersonaTurn:
    """Kişiliğin bir tura kattığı sistem çekirdeği, ek not ve araç kısıtı (`None` = tam set)."""

    extra_system: str = ""
    system_prompt: str | None = None
    allowed_tools: set[str] | None = None
    #: `tools` verilmeyip yalnız `disallowedTools` yazılmışsa (Claude Code'un yaygın salt-okur
    #: kalıbı) yasak kümesi: defter kurulduktan sonra `run_agent(denied_tools=...)` düşürür.
    #: Ölçüldü (31 Ekim): bu durumda `allowed_tools` None kalıyor, yasak hiç uygulanmıyordu.
    denied_tools: frozenset[str] = frozenset()


def resolve_session_persona(library: CapabilityRegistry | None, name: str) -> Persona | None:
    """Adı verilen ajanı bul; kütüphanede yoksa None (genel yardımcıya DÜŞMEZ)."""
    cleaned = name.strip()
    if not cleaned:
        return None
    persona = resolve_persona(library, cleaned)
    if persona is GENERIC_PERSONA:
        return None
    return persona


def persona_turn(persona: Persona | None) -> PersonaTurn:
    """Oturum kişiliğinin tura etkisi; kişilik yoksa boş."""
    if persona is None:
        return PersonaTurn()
    parts = [f"# Oturum kişiliği: {persona.title} ({persona.name})"]
    allowed: set[str] | None = None
    denied: frozenset[str] = frozenset()
    if persona.tools is not None:
        allowed = set(persona.tools) - persona.disallowed_tools
    else:
        denied = persona.disallowed_tools
    return PersonaTurn(
        extra_system="\n".join(parts),
        system_prompt=persona.prompt.strip() or None,
        allowed_tools=allowed,
        denied_tools=denied,
    )


def persona(state: ReplState, argument: str) -> str:
    """`/persona [ad|off]`: kişiliği göster, seç ya da kapat."""
    word = argument.strip()
    if not word:
        if state.persona is None:
            return messages.PERSONA_NONE
        return messages.PERSONA_CURRENT.format(title=state.persona.title, name=state.persona.name)
    if word.lower() in _OFF_WORDS:
        state.persona = None
        return messages.PERSONA_CLEARED
    found = resolve_session_persona(state.capabilities, word)
    if found is None:
        return messages.PERSONA_UNKNOWN.format(name=word)
    state.persona = found
    tools = (
        messages.PERSONA_TOOLS_ALL
        if found.tools is None
        else ", ".join(sorted(found.tools - found.disallowed_tools)) or "-"
    )
    return messages.PERSONA_SET.format(title=found.title, name=found.name, tools=tools)
