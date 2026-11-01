"""Modelin beceriyi kendi başına çağırdığı `Skill` aracı (Claude Code #139).

Claude Code (code.claude.com/docs/en/skills, "Skill content lifecycle"): model beceriyi
`Skill` aracıyla çağırır; işlenmiş SKILL.md (argümanlar yerleşmiş, !`cmd` çalışmış) tek mesaj
olarak konuşmaya girer ve sonraki turlarda da kalır. `allowed-tools`, `disallowed-tools` ve
`context: fork` model çağırınca da uygulanır.

Fusion'da gövde aracın sonucudur: araç sonucu konuşma geçmişinde kalır (yalnız o turun
sistem ekine girmez). Kullanıcının `/ad` çağrısıyla aynı `build_invocation` yolu kullanılır;
`!`cmd`` güven/kip kuralı (`shell_policy`) iki yolda ortaktır.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING

from ...config import trust
from ...core.proposal_invocation import ProposalPolicy
from ...core.tools import Tool, ToolArgs, ToolContext, ToolResult
from ...tools.capabilities import Capability, CapabilityRegistry
from ...tools.skill_commands import SkillInvocation, TemplateEnv, build_invocation
from ...tools.skill_shell import ShellPolicy
from . import skill_grants, skill_usage
from .approval import ApprovalMode
from .routine_invocation import RoutineInvocationValidator

if TYPE_CHECKING:
    from .loop import AgentDeps, AgentOutcome

#: Kullanıcının kendi dizinindeki beceri kaynakları: `!`cmd`` koşabilir, ön onayı geçerli.
TRUSTED_SOURCES = frozenset({"claude", "codex", "hermes", "fusion", "managed"})

#: Depo içeriği sayılan kaynaklar: güvenilen projede yalnız salt-okur `!`cmd``.
PROJECT_SOURCES = frozenset({"proje", "ek-kok"})

#: `!`cmd`` yalnız komut çalıştırmaya zaten izinli kiplerde koşar.
SHELL_CONTEXT_MODES = frozenset({ApprovalMode.AUTO, ApprovalMode.ACCEPT_EDITS, ApprovalMode.BYPASS})

#: `disableSkillShellExecution` bu kaynakları etkilemez (Claude: paketli ve kurumsal beceriler).
POLICY_EXEMPT_SOURCES = frozenset({"fusion", "managed"})

SKILL_TOOL_NAME = "Skill"

_USER_ONLY = (
    "'{name}' yalnız kullanıcı /{name} ile çağırır; model yükleyemez. Gerekiyorsa kullanıcıya "
    "/{name} yazmasını öner."
)


def _sources(skill: Capability) -> set[str]:
    return set(skill.source.split("+"))


def skill_trusted(skill: Capability, root: Path) -> bool:
    """Depo kaynaklı becerinin `model:`/`allowed-tools` alanı ancak güvenilen projede geçer."""
    sources = _sources(skill)
    if sources & TRUSTED_SOURCES or not sources & PROJECT_SOURCES:
        return True
    return trust.resolve_project_trust(root).trusted


def shell_mode_policy(skill: Capability, mode: ApprovalMode, root: Path) -> tuple[bool, bool]:
    """`!`cmd`` bu beceri için koşabilir mi ve yalnız salt-okur mu: `(izinli, salt_okur)`."""
    if mode not in SHELL_CONTEXT_MODES:
        return False, False
    sources = _sources(skill)
    if sources & TRUSTED_SOURCES:
        return True, False
    project = bool(sources & PROJECT_SOURCES) and trust.resolve_project_trust(root).trusted
    return project, True


def shell_policy(skill: Capability, mode: ApprovalMode, root: Path, home: Path) -> ShellPolicy:
    """Becerinin `!`cmd`` politikası: kip, izin kuralları ve `disableSkillShellExecution`."""
    from ...config import claude_settings
    from ...config.permission_rules import load_permission_rules
    from ...tools.permission_match import evaluate

    allowed, read_only = shell_mode_policy(skill, mode, root)
    rules = load_permission_rules(root)

    def decision(command: str) -> str | None:
        match = evaluate(rules, "run_shell", {"command": command}, root)
        return match.decision.value if match is not None else None

    disabled = (
        claude_settings.effective_bool(root, home, "disableSkillShellExecution")
        and not _sources(skill) & POLICY_EXEMPT_SOURCES
    )
    return ShellPolicy(
        mode_allows=allowed, read_only=read_only, disabled=disabled, rule_decision=decision
    )


def grant_entries(skill: Capability, root: Path) -> tuple[tuple[str, str], ...]:
    """Becerinin tur kuralları: ön onay yalnız güvenilen kaynakta, yasak her zaman.

    `disallowed-tools` belgede "Tools removed from Claude's available pool": desenli girdi
    (`Bash(rm *)`) de aracın TAMAMINI yasaklar (güvenli taraf; desen anlamı belgede yok).
    Model tur ortasında çağırınca araç listesi değişmez; yasak bu yüzden araç adı düzeyinde
    `deny` kuralıdır.
    """
    allowed = skill.allowed_tools if skill_trusted(skill, root) else ()
    denied = tuple(item.partition("(")[0].strip() for item in skill.disallowed_tools)
    return skill_grants.entries(allowed, denied)


def skill_denied(rules: object, name: str) -> bool:
    """`Skill`, `Skill(ad)` ya da `Skill(önek *)` deny kuralı bu çağrıyı yasaklıyor mu?"""
    from ...config.permission_rules import PermissionDecision

    for rule in getattr(rules, "rules", ()) or ():
        if rule.decision is not PermissionDecision.DENY or rule.tool != SKILL_TOOL_NAME:
            continue
        spec = (rule.specifier or "").strip()
        if not spec or spec == name or (spec.endswith(" *") and name.startswith(spec[:-2])):
            return True
    return False


def invoke(
    skill: Capability, argument: str, *, mode: ApprovalMode, root: Path, home: Path, **env: object
) -> SkillInvocation:
    """Beceriyi işle (kullanıcı ve model yolu ortak): şablon, `!`cmd``, frontmatter alanları."""
    proposals = ProposalPolicy(bool(env.get("verified_proposals", False)))
    memory_dir = env.get("memory_dir")
    policy = shell_policy(skill, mode, root, home)
    return build_invocation(
        skill,
        argument,
        TemplateEnv(
            skill_dir=skill.path.parent,
            project_dir=root,
            session_id=str(env.get("session_id", "") or ""),
            effort=str(env.get("effort", "") or ""),
        ),
        shell_allowed=policy.mode_allows,
        shell_read_only=policy.read_only,
        shell_policy=policy,
        proposal_policy=proposals,
        proposal_validator=(
            RoutineInvocationValidator(memory_dir, proposals)
            if isinstance(memory_dir, Path)
            else None
        ),
    )


def apply_turn_choice(
    skill: Capability, invocation: SkillInvocation, deps: AgentDeps, root: Path
) -> tuple[str, ...]:
    """Modelin çağırdığı becerinin `model`/`effort` alanı turun KALANINA uygulanır (#139).

    Belge (skills, Frontmatter reference): "The override applies for the rest of the current
    turn and isn't saved to settings. The session model resumes when you send your next
    prompt." Fusion karşılığı `deps.active_model_override` ve `deps.turn_effort_override`;
    ikisi de döngüde yeni kullanıcı turunun başında sıfırlanır.
    """
    from .skill_turn import resolve_turn_model

    config = deps.config
    resolution = resolve_turn_model(
        invocation.model,
        invocation.effort,
        allow_model=skill_trusted(skill, root),
        aliases=dict(getattr(getattr(config, "agent_launch", None), "model_aliases", {}) or {}),
    )
    choice = resolution.choice
    if choice.model:
        deps.active_model_override = choice.apply(config).agent
    if choice.effort is not None:
        deps.turn_effort_override = choice.effort
    return resolution.notes


def _lookup(library: CapabilityRegistry, name: str) -> Capability | str:
    skill = library.get_skill(name)
    if skill is not None:
        return skill if skill.model_invocable else _USER_ONLY.format(name=skill.name)
    candidates = library.candidates(name)
    if candidates:
        return f"'{name}' birden çok kaynakta var; nitelikli adıyla çağır: " + ", ".join(candidates)
    return f"'{name}' adlı beceri yok; kullanılabilir beceriler listesindeki adı yaz."


def build_skill_tool(
    library: CapabilityRegistry,
    deps: AgentDeps,
    *,
    depth: int,
    run_agent: Callable[..., Awaitable[AgentOutcome]],
) -> Tool:
    """`Skill(skill, args)`: beceriyi işleyip gövdesini konuşmaya kat; fork ise alt ajanda koş."""

    async def _run(args: ToolArgs, context: ToolContext) -> ToolResult:
        name = str(args.get("skill", "")).strip().lstrip("/")
        found = _lookup(library, name) if name else "'skill' alanı dolu olmalı."
        if isinstance(found, str):
            return ToolResult.failure(found)
        if skill_denied(getattr(deps, "permission_rules", None), found.name):
            return ToolResult.failure(f"'{found.name}' becerisi izin kuralıyla yasak (Skill).")
        mode_reader = getattr(deps, "approval_mode", None)
        runtime = deps.config.runtime
        invocation = invoke(
            found,
            str(args.get("args", "") or ""),
            mode=mode_reader() if callable(mode_reader) else ApprovalMode.AUTO,
            root=context.root,
            home=getattr(deps, "home", None) or Path.home(),
            effort=getattr(runtime, "reasoning_effort", "") or "",
            verified_proposals=getattr(runtime, "verified_skill_proposals", False),
            memory_dir=deps.config.memory_dir,
        )
        if not invocation.ok:
            return ToolResult.failure("\n".join(invocation.notes) or "beceri çağrısı iptal")
        skill_grants.grant(context, grant_entries(found, context.root))
        skill_usage.record_invocation(getattr(deps.config, "memory_dir", None), found.name)
        if invocation.fork:
            return await _run_forked(found, invocation, deps, (depth, context.root), run_agent)
        turn_notes = apply_turn_choice(found, invocation, deps, context.root)
        notes = "\n".join(f"[not: {note}]" for note in (*invocation.notes, *turn_notes))
        body = invocation.context or invocation.task
        return ToolResult("\n\n".join(part for part in (body, notes) if part))

    return Tool(
        name=SKILL_TOOL_NAME,
        description=(
            "Kullanılabilir beceriler listesindeki bir beceriyi çağır. Gövde işlenmiş olarak "
            "(argümanlar yerleşmiş, !`komut` çalışmış) sonuçta döner; yönergelerini uygula."
        ),
        parameters={
            "type": "object",
            "properties": {
                "skill": {"type": "string", "description": "beceri adı (ör. pdf, ekip:inceleme)"},
                "args": {"type": "string", "description": "isteğe bağlı argümanlar"},
            },
            "required": ["skill"],
        },
        run=_run,
    )


def runs_in_background(skill: Capability, deps: object, depth: int) -> bool:
    """`context: fork` becerisi arka planda mı koşar (Claude Code #141)?

    Belge (skills, "Run skills in a subagent"): fork varsayılan olarak arka planda koşar, sonuç
    tamamlanınca konuşmaya gelir; `background: false` turda bekletir. Etkileşimsiz kipte
    (`-p`, SDK) her zaman beklenir.
    """
    return skill.skill_background and bool(getattr(deps, "interactive", False)) and depth == 0


async def _run_forked(
    skill: Capability,
    invocation: SkillInvocation,
    deps: AgentDeps,
    where: tuple[int, Path],
    run_agent: Callable[..., Awaitable[AgentOutcome]],
) -> ToolResult:
    """`context: fork`: gövde geçmişsiz alt ajanın görev istemi olur (Claude Code #141)."""
    from .team import DEPTH_LIMIT_MESSAGE, SubTask, depth_limit_reached, run_subagent

    depth, root = where
    if depth_limit_reached(deps, depth):
        return ToolResult.failure(DEPTH_LIMIT_MESSAGE)
    task = "\n\n".join(part for part in (invocation.context, invocation.task) if part)
    # Claude Code: `context: fork` ile `model`/`effort` alt ajanın modelini/eforunu belirler.
    subtask = SubTask(
        task=task,
        persona=invocation.agent,
        model=invocation.model if skill_trusted(skill, root) else "",
        effort=invocation.effort.strip().lower(),
    )
    if runs_in_background(skill, deps, depth):
        from .agent_runtime_tools import launch_agent

        # Kapalı arka plan (`disable_background_tasks`, `background_agents`) ön planda bekler.
        return await launch_agent(
            deps, subtask, {"run_in_background": True}, depth=depth, run_agent=run_agent
        )
    run = await run_subagent(deps, subtask, depth=depth, run_agent=run_agent)
    return ToolResult(run.text or f"('{skill.name}' alt ajanı boş yanıt verdi)")
