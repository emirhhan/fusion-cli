"""Beceri ve komut dosyalarını slash komutu olarak sunan dinamik defter (P-019).

`/<beceri> argüman` yazımı Claude Code'da `.claude/skills/x/SKILL.md` ya da
`.claude/commands/x.md` dosyasını çalıştırır. Beceri yalnız mesaj başındaki `/` ile çağrılır
(Codex `$beceri` yazımı Claude'da yok; #174): `build_registry(..., skills=…)` bu modülün
ürettiği komutları "Beceri" grubunda dinamik olarak defterin arkasına ekler; aynı adlı
yerleşik komutu gölgeler (takma adı değil).

İşleyici turu ÇALIŞTIRMAZ (makrolarla aynı sözleşme): görevi `pending_task`, beceri gövdesini
`pending_context`, `allowed-tools` kısıtını `pending_tools` olarak durumda bekletir; terminal,
TUI ve masaüstü döngüleri bunları sıradaki turda tüketir.
"""

from __future__ import annotations

from collections.abc import Callable

from ...engines.agent import skill_tool
from ...engines.agent.skill_turn import resolve_turn_model
from ...tools.capabilities import Capability, CapabilityRegistry
from ...tools.skill_shell import ShellPolicy
from ...ui import messages
from .macros import Mode
from .state import Engine, ReplState

#: Ortak kurallar `engines/agent/skill_tool`'da (modelin `Skill` aracı ile aynı, #139).
TRUSTED_SOURCES = skill_tool.TRUSTED_SOURCES
PROJECT_SOURCES = skill_tool.PROJECT_SOURCES
SHELL_CONTEXT_MODES = skill_tool.SHELL_CONTEXT_MODES

#: Yardım satırında açıklamanın en fazla uzunluğu.
_SUMMARY_CHARS = 72

#: Yardım/tamamlama grubu.
GROUP = "Beceri"


def shell_context_policy(state: ReplState, skill: Capability) -> tuple[bool, bool]:
    """`!`cmd`` bu beceri için koşabilir mi ve yalnız salt-okur mu: `(izinli, salt_okur)`."""
    return skill_tool.shell_mode_policy(skill, state.approval, state.root)


def skill_shell_policy(state: ReplState, skill: Capability) -> ShellPolicy:
    """Becerinin `!`cmd`` politikası: kip, izin kuralları ve `disableSkillShellExecution`."""
    from pathlib import Path

    return skill_tool.shell_policy(skill, state.approval, state.root, Path.home())


def model_override_allowed(state: ReplState, skill: Capability) -> bool:
    """Becerinin `model:` alanı uygulanabilir mi: depo kaynaklıysa proje güvenilmeli."""
    return skill_tool.skill_trusted(skill, state.root)


def shell_context_allowed(state: ReplState, skill: Capability) -> bool:
    """`!`cmd`` bu beceri için koşabilir mi (geri uyumlu kısa yol; bkz. `shell_context_policy`)."""
    return shell_context_policy(state, skill)[0]


def skill_handler(qualified_name: str) -> Callable[[ReplState, str], str]:
    """`/beceri argüman` işleyicisi: görevi ve bağlamı sıradaki tur için hazırla."""

    def _handler(state: ReplState, argument: str) -> str:
        registry = state.capabilities
        skill = registry.get_skill(qualified_name) if registry is not None else None
        if skill is None:
            return messages.REPL_SKILL_MISSING.format(name=qualified_name.split("@", 1)[0])
        from pathlib import Path

        invocation = skill_tool.invoke(
            skill,
            argument,
            mode=state.approval,
            root=state.root,
            home=Path.home(),
            session_id=state.conversation_id,
            effort=getattr(state.config.runtime, "reasoning_effort", "") or "",
            verified_proposals=state.config.runtime.verified_skill_proposals,
            memory_dir=state.config.memory_dir,
        )
        if not invocation.ok:
            return "\n".join(invocation.notes)
        state.pending_task = invocation.task
        # `context: fork`: tur fork alt ajanda koşar (`/subtask` yolu), ama geçmişsiz.
        state.pending_mode = Mode.SUBTASK if invocation.fork else Mode.NONE
        state.pending_context = invocation.context
        # `allowed-tools` araçları daraltmaz, bu turda ön onaylar; `disallowed-tools` deseni
        # (`Bash(rm *)`) izin kuralı olarak yalnız o komutu düşürür (Claude Code #142, #180).
        state.pending_tools = None
        state.pending_grants = skill_tool.grant_entries(skill, state.root)
        # `model`/`effort` (P-020): yalnız bu turun yapılandırması değişir; oturum seçimi kalır.
        resolution = resolve_turn_model(
            invocation.model,
            invocation.effort,
            allow_model=model_override_allowed(state, skill),
            aliases=dict(getattr(state.config.agent_launch, "model_aliases", {}) or {}),
        )
        state.pending_model_choice = resolution.choice
        state.pending_denied_tools = invocation.denied_tools
        state.pending_fork_agent = invocation.agent
        # `context: fork` (#141): alt ajan konuşma geçmişini görmez; gövde görev istemidir.
        state.pending_fresh_fork = invocation.fork
        # Beceri gövdesi sonraki turlarda da bağlamda kalır (#140); komut dosyası görevdir.
        carry = bool(invocation.context) and skill.proposal is None
        state.pending_skill_name = skill.name if carry else ""
        lines = [messages.REPL_SKILL_STARTED.format(name=skill.name)]
        if state.engine is not Engine.AGENT:
            # Beceri gövdesi ve araç kısıtı yalnız agent turunda tüketilir; Fusion motorunda
            # sessizce düşüp sonraki agent turuna sızıyordu (ölçüldü 31 Ekim). `/init` gibi
            # motor çevrilir ve kullanıcıya söylenir.
            state.engine = Engine.AGENT
            lines.append(messages.REPL_SKILL_ENGINE_NOTE)
        if invocation.fork:
            lines.append(messages.REPL_SKILL_FORK_NOTE)
        if invocation.agent:
            lines.append(messages.REPL_SKILL_FORK_AGENT_NOTE.format(agent=invocation.agent))
        lines.extend(resolution.notes)
        lines.extend(invocation.notes)
        return "\n".join(lines)

    return _handler


def skill_slash_commands(registry: CapabilityRegistry | None) -> tuple[object, ...]:
    """Kullanıcının çağırabileceği her beceri/komut için bir `SlashCommand`."""
    # Döngüsel içe aktarma: `commands` bu modülü dinamik sağlayıcı olarak kullanır.
    from .commands import SlashCommand

    if registry is None:
        return ()
    commands: list[SlashCommand] = []
    seen: set[str] = set()
    for skill in registry.skills():
        if not skill.user_invocable:
            continue
        key = skill.name.lower()
        if key in seen:  # aynı ad farklı kaynakta: ilk bulunan (öncelikli kök) kazanır
            continue
        seen.add(key)
        summary = skill.description.strip().splitlines()[0] if skill.description.strip() else ""
        if len(summary) > _SUMMARY_CHARS:
            summary = summary[: _SUMMARY_CHARS - 1] + "…"
        commands.append(
            SlashCommand(
                skill.name,
                summary or messages.CMD_SKILL_DEFAULT.format(kind=skill.kind),
                skill_handler(skill.qualified_name),
                group=GROUP,
                usage=skill.argument_hint or "[görev]",
            )
        )
    return tuple(commands)
