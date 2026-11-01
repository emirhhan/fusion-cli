"""Beceri ve komut dosyalarını slash komutu olarak sunan dinamik defter (P-019).

`/<beceri> argüman` yazımı Claude Code'da `.claude/skills/x/SKILL.md` ya da
`.claude/commands/x.md` dosyasını çalıştırır. Beceri yalnız mesaj başındaki `/` ile çağrılır
(Codex `$beceri` yazımı Claude'da yok; #174): `build_registry(..., skills=…)` bu modülün ürettiği komutları "Beceri" grubunda
dinamik olarak defterin arkasına ekler; aynı adlı yerleşik komutu gölgeler (takma adı değil).

İşleyici turu ÇALIŞTIRMAZ (makrolarla aynı sözleşme): görevi `pending_task`, beceri gövdesini
`pending_context`, `allowed-tools` kısıtını `pending_tools` olarak durumda bekletir; terminal,
TUI ve masaüstü döngüleri bunları sıradaki turda tüketir.
"""

from __future__ import annotations

from collections.abc import Callable

from ...config import trust
from ...core.proposal_invocation import ProposalPolicy
from ...engines.agent.approval import ApprovalMode
from ...engines.agent.routine_invocation import RoutineInvocationValidator
from ...engines.agent.skill_turn import resolve_turn_model
from ...tools.capabilities import Capability, CapabilityRegistry
from ...tools.skill_commands import TemplateEnv, build_invocation
from ...tools.skill_shell import ShellPolicy
from ...ui import messages
from .macros import Mode
from .state import Engine, ReplState

#: Bu kaynaklardan gelen beceri dosyaları kullanıcının kendi dizinindedir: `!`cmd`` koşabilir.
TRUSTED_SOURCES = frozenset({"claude", "codex", "hermes", "fusion"})

#: Depo içeriği sayılan kaynaklar: güvenilen projede bile yalnız salt-okur `!`cmd``.
PROJECT_SOURCES = frozenset({"proje", "ek-kok"})

#: `!`cmd`` yalnız komut çalıştırmaya zaten izinli kiplerde koşar; plan/security sormadan koşmaz.
SHELL_CONTEXT_MODES = frozenset({ApprovalMode.AUTO, ApprovalMode.ACCEPT_EDITS, ApprovalMode.BYPASS})

#: Yardım satırında açıklamanın en fazla uzunluğu.
_SUMMARY_CHARS = 72

#: Yardım/tamamlama grubu.
GROUP = "Beceri"


def shell_context_policy(state: ReplState, skill: Capability) -> tuple[bool, bool]:
    """`!`cmd`` bu beceri için koşabilir mi ve yalnız salt-okur mu: `(izinli, salt_okur)`.

    Kullanıcının kendi kökleri (`~/.claude`, `~/.codex`, …) tam yetkili; proje (ya da ek kök)
    kaynaklı beceri `fusion trust` ile güvenilen projede YALNIZ salt-okur komut koşar: güven
    özeti `config.yaml`a bağlıdır, beceri dosyasının içeriğine değil (ölçüldü 31 Ekim).
    """
    if state.approval not in SHELL_CONTEXT_MODES:
        return False, False
    sources = set(skill.source.split("+"))
    if sources & TRUSTED_SOURCES:
        return True, False
    project = bool(sources & PROJECT_SOURCES) and trust.resolve_project_trust(state.root).trusted
    return project, True


#: `disableSkillShellExecution` bu kaynakları etkilemez (Claude: paketli ve kurumsal beceriler).
_POLICY_EXEMPT_SOURCES = frozenset({"fusion", "managed"})


def skill_shell_policy(state: ReplState, skill: Capability) -> ShellPolicy:
    """Becerinin `!`cmd`` politikası: kip, izin kuralları ve `disableSkillShellExecution`."""
    from pathlib import Path

    from ...config import claude_settings
    from ...config.permission_rules import load_permission_rules
    from ...tools.permission_match import evaluate

    allowed, read_only = shell_context_policy(state, skill)
    root = state.root
    rules = load_permission_rules(root)

    def decision(command: str) -> str | None:
        match = evaluate(rules, "run_shell", {"command": command}, root)
        return match.decision.value if match is not None else None

    disabled = claude_settings.effective_bool(
        root, Path.home(), "disableSkillShellExecution"
    ) and not set(skill.source.split("+")) & _POLICY_EXEMPT_SOURCES
    return ShellPolicy(
        mode_allows=allowed, read_only=read_only, disabled=disabled, rule_decision=decision
    )


def model_override_allowed(state: ReplState, skill: Capability) -> bool:
    """Becerinin `model:` alanı uygulanabilir mi: depo kaynaklıysa proje güvenilmeli."""
    sources = set(skill.source.split("+"))
    if sources & TRUSTED_SOURCES or not sources & PROJECT_SOURCES:
        return True
    return trust.resolve_project_trust(state.root).trusted


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
        policy = skill_shell_policy(state, skill)
        invocation = build_invocation(
            skill,
            argument,
            TemplateEnv(
                skill_dir=skill.path.parent,
                project_dir=state.root,
                session_id=state.conversation_id,
                effort=str(getattr(state.config.runtime, "reasoning_effort", "") or ""),
            ),
            shell_allowed=policy.mode_allows,
            shell_read_only=policy.read_only,
            shell_policy=policy,
            proposal_policy=ProposalPolicy(state.config.runtime.verified_skill_proposals),
            proposal_validator=RoutineInvocationValidator(
                state.config.memory_dir,
                ProposalPolicy(state.config.runtime.verified_skill_proposals),
            ),
        )
        if not invocation.ok:
            return "\n".join(invocation.notes)
        state.pending_task = invocation.task
        # `context: fork` (P-054): tur ana bağlamı devralan fork alt ajanda koşar (`/subtask`
        # ile aynı yol); beceri gövdesi ve araç kısıtı brif/tavan olarak alt ajana geçer.
        state.pending_mode = Mode.SUBTASK if invocation.fork else Mode.NONE
        state.pending_context = invocation.context
        state.pending_tools = (
            frozenset(invocation.allowed_tools) if invocation.allowed_tools is not None else None
        )
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
