"""`fusion -p "/beceri argüman"` — istemdeki beceri/özel komut genişletmesi (#313).

Claude Code'da `-p` isteminde kullanıcının çağırabildiği beceri ve özel komutlar koşudan
önce genişletilir. Burada REPL'in `/beceri` yolu (`tools/skill_commands.build_invocation`)
aynen kullanılır: gövde sistem bağlamına, argüman göreve gider; `allowed-tools`,
`disallowed-tools` turu daraltır. `!`komut`` bağlamı REPL'deki güven kuralıyla koşar.
Terminal arayüzüne özgü komutlar (`/clear`, `/config` menüsü…) için Claude'un metniyle
"kullanılamaz" denir. `--disable-slash-commands` genişletmeyi kapatır.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..config import trust
from ..config.models import Config
from ..core.proposal_invocation import ProposalPolicy
from ..engines.agent.approval import ApprovalMode
from ..engines.agent.routine_invocation import RoutineInvocationValidator
from ..tools.capabilities import Capability, CapabilityRegistry
from ..tools.skill_commands import TemplateEnv, build_invocation
from ..ui import print_messages as texts
from .repl.skill_commands import PROJECT_SOURCES, SHELL_CONTEXT_MODES, TRUSTED_SOURCES

#: `-p`'de anlamı olmayan, yalnız etkileşimli arayüzde çalışan yerleşik komutlar.
INTERACTIVE_ONLY = frozenset(
    {"clear", "exit", "quit", "resume", "rewind", "theme", "vim", "login", "logout", "help"}
)


@dataclass(frozen=True, slots=True)
class SlashExpansion:
    """Genişletilmiş istem; `error` doluysa koşu başlamadan bu metinle biter."""

    task: str
    extra_system: str = ""
    allowed_tools: frozenset[str] | None = None
    denied_tools: frozenset[str] = frozenset()
    error: str = ""
    #: `context: fork` (#289): tur fork alt ajanda koşar; akışta `forked-command-<ad>`.
    fork: bool = False
    #: Fork'u koşacak alt ajan tanımı (`agent:`); boş = genel yardımcı.
    fork_agent: str = ""
    skill_name: str = ""


def _shell_policy(mode: ApprovalMode, skill: Capability, root: Path) -> tuple[bool, bool]:
    if mode not in SHELL_CONTEXT_MODES:
        return False, False
    sources = set(skill.source.split("+"))
    if sources & TRUSTED_SOURCES:
        return True, False
    project = bool(sources & PROJECT_SOURCES) and trust.resolve_project_trust(root).trusted
    return project, True


def expand_slash(
    task: str,
    registry: CapabilityRegistry | None,
    *,
    config: Config,
    mode: ApprovalMode,
    root: Path,
    session_id: str,
) -> SlashExpansion:
    """İstem `/ad` ile başlıyorsa beceriyi genişlet; değilse olduğu gibi döndür."""
    text = task.strip()
    if not text.startswith("/") or text.startswith("//") or registry is None:
        return SlashExpansion(task)
    head, _, argument = text[1:].partition(" ")
    name = head.strip()
    if not name or "/" in name:
        return SlashExpansion(task)
    skill = registry.get_skill(name)
    if skill is None:
        if name in INTERACTIVE_ONLY:
            return SlashExpansion(task, error=texts.PRINT_SLASH_UNAVAILABLE.format(name=name))
        return SlashExpansion(task)
    shell_allowed, read_only = _shell_policy(mode, skill, root)
    policy = ProposalPolicy(config.runtime.verified_skill_proposals)
    invocation = build_invocation(
        skill,
        argument.strip(),
        TemplateEnv(skill_dir=skill.path.parent, project_dir=root, session_id=session_id),
        shell_allowed=shell_allowed,
        shell_read_only=read_only,
        proposal_policy=policy,
        proposal_validator=RoutineInvocationValidator(config.memory_dir, policy),
    )
    if not invocation.ok:
        return SlashExpansion(task, error="\n".join(invocation.notes))
    return SlashExpansion(
        task=invocation.task,
        extra_system=invocation.context,
        allowed_tools=(
            frozenset(invocation.allowed_tools) if invocation.allowed_tools is not None else None
        ),
        denied_tools=invocation.denied_tools,
        fork=invocation.fork,
        fork_agent=invocation.agent,
        skill_name=skill.name,
    )
