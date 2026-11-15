"""Slash ile çağrılan beceri/komut dosyaları: keşif, şablonlama, dinamik bağlam (P-019, P-020).

Claude Code'da `.claude/commands/x.md` ve `.claude/skills/x/SKILL.md` aynı `/x` komutunu
üretir; gövdede `$ARGUMENTS`, `$0..$N` (0 tabanlı), `$ad` (`arguments:`), `${CLAUDE_SKILL_DIR}`,
`${CLAUDE_PROJECT_DIR}`, `${CLAUDE_SESSION_ID}`, `${CLAUDE_EFFORT}` değişkenleri ve
`!`cmd`` / ` ```! ` ile komut çıktısı yerleştirilir. Fusion'ın eski adları
(`${FUSION_SKILL_DIR}`, `${FUSION_PROJECT_DIR}`, `${FUSION_SESSION_ID}`, `{SKILL_DIR}`) bir sürüm
boyunca okunur ve kullanımdan kalktığı bildirilir.

`!`cmd`` kuralları `skill_shell` modülündedir (Claude Code #168): başarısız ya da izinsiz komut
çağrının tamamını iptal eder.
"""

from __future__ import annotations

import json
import logging
import re
import shlex
from dataclasses import dataclass
from pathlib import Path

from ..core.proposal_invocation import (
    INVOCATION_PREFIX,
    ProposalInvocation,
    ProposalPolicy,
    ProposalValidator,
    body_revision,
    proposal_metadata,
    visible_proposal,
)
from .auto_policy import auto_risk, is_read_only_command
from .frontmatter import NO_TOOLS, body_after_frontmatter, parse_frontmatter
from .plugin_capabilities import with_plugin_root
from .safety import danger_reason
from .skill_shell import (
    MAX_SHELL_OUTPUT_CHARS,
    SHELL_CONTEXT_TIMEOUT_S,
    ShellPolicy,
    SkillShellError,
    bash_patterns,
    expand,
)

#: Komut dosyası kökleri: (ev/kök altı yol, kaynak etiketi, ev dizininde mi). Claude Code
#: yalnız `.claude/commands` okur; `.fusion/commands` kullanımdan kalktı (bir sürüm okunur,
#: `DEPRECATED_COMMAND_ROOTS` ile uyarılır).
COMMAND_ROOTS: tuple[tuple[str, str, bool], ...] = (
    (".claude/commands", "claude", True),
    (".fusion/commands", "fusion", True),
    (".claude/commands", "proje", False),
    (".fusion/commands", "proje", False),
)

#: Kullanımdan kalkan komut kökleri (Claude'da yok); dosya bulunursa bir kez uyarılır.
DEPRECATED_COMMAND_ROOTS = frozenset({".fusion/commands"})

_WARNED_ROOTS: set[Path] = set()
_LOG = logging.getLogger(__name__)

__all__ = ["MAX_SHELL_OUTPUT_CHARS", "SHELL_CONTEXT_TIMEOUT_S", "SkillShellError"]

#: Kullanıcı argüman vermediğinde becerinin görev metni (masaüstü `DEFAULT_SKILL_TASK` ile aynı).
DEFAULT_SKILL_TASK = "{name} becerisini bu görev için uygula."

#: Açıklaması olmayan komut dosyasında gövdenin ilk satırından alınacak en fazla karakter.
_SUMMARY_CHARS = 120

_POSITIONAL = re.compile(r"\$ARGUMENTS\[(\d+)\]|\$(\d+)\b")
_ESCAPED_DOLLAR = "\x00dolar\x00"


@dataclass(frozen=True, slots=True)
class TemplateEnv:
    """Şablon değişkenlerinin kaynağı."""

    skill_dir: Path
    project_dir: Path
    session_id: str = ""
    #: `${CLAUDE_EFFORT}`: low | medium | high | xhigh | max (boşsa boş metin).
    effort: str = ""


@dataclass(frozen=True, slots=True)
class SkillInvocation:
    """`/beceri argüman` çağrısının tura çevrilmiş hâli."""

    #: Kullanıcı mesajı olarak gidecek görev.
    task: str
    ok: bool = True
    #: Sistem bağlamına eklenecek beceri gövdesi (komut dosyasında boş: gövde görevdir).
    context: str = ""
    #: `allowed-tools` → Fusion araç adları; `None` = kısıt yok.
    allowed_tools: set[str] | None = None
    model: str = ""
    effort: str = ""
    fork: bool = False
    notes: tuple[str, ...] = ()
    #: `disallowed-tools` → Fusion araç adları (desen `sunucu__*` olabilir); boş = yasak yok.
    denied_tools: frozenset[str] = frozenset()
    #: `agent`: fork turunu koşacak alt ajan tanımı; boş = genel yardımcı.
    agent: str = ""


def discover_commands(home: Path | None, root: Path) -> tuple[object, ...]:
    """`.claude/commands/**/*.md` dosyalarını `komut` türünde `Capability` olarak döndür.

    `frontend/component.md` → `frontend:component`. Açıklama frontmatter `description`,
    yoksa gövdenin ilk dolu satırı.
    """
    # Döngüsel içe aktarma: `capabilities` bu modülü kullanır; tip burada tembel alınır.
    from .capabilities import Capability

    found: list[Capability] = []
    for rel, source, in_home in COMMAND_ROOTS:
        if in_home and home is None:
            continue
        base = (home if in_home and home is not None else root) / rel
        if not base.is_dir():
            continue
        bound = base.resolve()
        _warn_deprecated_root(rel, base)
        for path in sorted(base.rglob("*.md")):
            try:
                resolved = path.resolve()
            except OSError:
                continue
            # Proje kökündeki sembolik bağ kök dışına çıkıyorsa okunmaz (depo içeriği).
            if source == "proje" and not resolved.is_relative_to(bound):
                continue
            name = ":".join(path.relative_to(base).with_suffix("").parts)
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            fields = parse_frontmatter(text)
            found.append(
                Capability(
                    # Claude Code: komut dosyasında `name` ve `paths` desteklenmez; ad yoldan.
                    name=name,
                    description=str(fields.get("description") or _first_line(text)),
                    path=path,
                    source=source,
                    kind="komut",
                    allowed_tools=_tuple(fields.get("allowed_tools")),
                    model=str(fields.get("model") or ""),
                    effort=str(fields.get("effort") or ""),
                    context=str(fields.get("context") or ""),
                    agent=str(fields.get("agent") or ""),
                    disallowed_tools=_tuple(fields.get("disallowed_tools")),
                    model_invocable=bool(fields.get("model_invocable", True)),
                    user_invocable=bool(fields.get("user_invocable", True)),
                    argument_hint=str(fields.get("argument_hint") or ""),
                )
            )
    return tuple(found)


def _warn_deprecated_root(rel: str, base: Path) -> None:
    if rel not in DEPRECATED_COMMAND_ROOTS or base in _WARNED_ROOTS:
        return
    _WARNED_ROOTS.add(base)
    _LOG.warning(
        "%s kullanımdan kalktı (Claude Code yalnız .claude/commands okur); dosyaları "
        ".claude/commands altına taşı",
        base,
    )


def _tuple(value: object) -> tuple[str, ...]:
    return tuple(value) if isinstance(value, tuple) else ()


def _first_line(text: str) -> str:
    for line in body_after_frontmatter(text).splitlines():
        cleaned = line.strip().lstrip("#").strip()
        if cleaned:
            return cleaned[:_SUMMARY_CHARS]
    return ""


# --- Şablon ---------------------------------------------------------------------- #

#: Kullanımdan kalkan Fusion şablon adları → Claude karşılığı (bir sürüm okunur, uyarılır).
DEPRECATED_TEMPLATE_NAMES: dict[str, str] = {
    "${FUSION_SKILL_DIR}": "${CLAUDE_SKILL_DIR}",
    "${FUSION_PROJECT_DIR}": "${CLAUDE_PROJECT_DIR}",
    "${FUSION_SESSION_ID}": "${CLAUDE_SESSION_ID}",
    "{SKILL_DIR}": "${CLAUDE_SKILL_DIR}",
}


def deprecated_template_notes(text: str) -> tuple[str, ...]:
    """Gövdedeki kullanımdan kalkmış Fusion değişkenleri için kullanıcı notu."""
    return tuple(
        f"{old} kullanımdan kalktı; {new} yaz"
        for old, new in DEPRECATED_TEMPLATE_NAMES.items()
        if old in text
    )


def _split_arguments(argument: str) -> list[str]:
    try:
        return shlex.split(argument) if argument else []
    except ValueError:  # kapanmamış tırnak: boşlukla böl
        return argument.split()


def render_template(
    text: str, argument: str, env: TemplateEnv, *, names: tuple[str, ...] = ()
) -> str:
    """`$ARGUMENTS`, `$ARGUMENTS[N]`, `$N` (ikisi de 0 tabanlı), `$ad` ve `${CLAUDE_*}`.

    Claude Code: `$0` ilk, `$1` ikinci argümandır; `arguments:` alanındaki adlar sırayla
    konumlara eşlenir (`$issue`). Hiçbir yer tutucu argüman almıyorsa argümanlar
    `ARGUMENTS: <değer>` satırıyla sona eklenir. `\\$` kaçışı dolar işaretini korur.
    """
    argument = argument.strip()
    parts = _split_arguments(argument)
    text = text.replace("\\$", _ESCAPED_DOLLAR)
    named = _named_pattern(names)
    has_placeholder = (
        "$ARGUMENTS" in text
        or _POSITIONAL.search(text) is not None
        or (named is not None and named.search(text) is not None)
    )

    def positional(match: re.Match[str]) -> str:
        index = int(match.group(1) if match.group(1) is not None else match.group(2))
        return parts[index] if 0 <= index < len(parts) else ""

    # Önce `$ARGUMENTS[N]`/`$N`, sonra düz `$ARGUMENTS` (alt dizesi olduğu için sıra önemli).
    text = _POSITIONAL.sub(positional, text)
    if named is not None:
        text = named.sub(lambda m: _at(parts, names.index(m.group(1))), text)
    text = text.replace("$ARGUMENTS", argument)
    for names_, value in (
        (("CLAUDE_SKILL_DIR", "FUSION_SKILL_DIR"), str(env.skill_dir)),
        (("CLAUDE_PROJECT_DIR", "FUSION_PROJECT_DIR"), str(env.project_dir)),
        (("CLAUDE_SESSION_ID", "FUSION_SESSION_ID"), env.session_id),
        (("CLAUDE_EFFORT",), env.effort),
    ):
        for name in names_:
            text = text.replace("${" + name + "}", value)
    text = text.replace(_ESCAPED_DOLLAR, "$")
    if not has_placeholder and argument:
        text = f"{text.rstrip()}\n\nARGUMENTS: {argument}"
    return text


def _at(parts: list[str], index: int) -> str:
    return parts[index] if 0 <= index < len(parts) else ""


def _named_pattern(names: tuple[str, ...]) -> re.Pattern[str] | None:
    cleaned = [name for name in names if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name)]
    if not cleaned:
        return None
    alternatives = "|".join(re.escape(name) for name in sorted(cleaned, key=len, reverse=True))
    return re.compile(rf"\$({alternatives})\b")


# --- !`cmd` dinamik bağlam -------------------------------------------------------- #


def shell_context_block_reason(command: str, *, cwd: Path, read_only: bool) -> str | None:
    """Komut neden koşmamalı? `run_shell` ile aynı denetim; sorun yoksa `None`.

    Geri uyum: yeni denetim `skill_shell.check_command` içindedir.
    """
    reason = danger_reason("run_shell", {"command": command}) or auto_risk(command, cwd)
    if reason is not None:
        return f"riskli komut ({reason})"
    if read_only and not is_read_only_command(command):
        return "proje becerisinde yalnız salt-okur komut çalışır"
    return None


def expand_shell_context(
    text: str,
    *,
    cwd: Path,
    allowed: bool,
    read_only: bool = False,
    timeout_s: float = SHELL_CONTEXT_TIMEOUT_S,
    policy: ShellPolicy | None = None,
) -> tuple[str, tuple[str, ...]]:
    """`!`cmd`` ve ` ```! ` parçalarını komut çıktısıyla değiştir (Claude kuralları).

    Başarısız ya da izinsiz komut `SkillShellError` fırlatır: çağrının tamamı iptal edilir.
    """
    policy = policy or ShellPolicy(mode_allows=allowed, read_only=read_only, timeout_s=timeout_s)
    return expand(text, cwd=cwd, policy=policy)


# --- Çağrı ----------------------------------------------------------------------- #


def build_invocation(
    capability: object,
    argument: str,
    env: TemplateEnv,
    *,
    shell_allowed: bool,
    shell_read_only: bool = False,
    proposal_policy: ProposalPolicy | None = None,
    proposal_validator: ProposalValidator | None = None,
    shell_policy: ShellPolicy | None = None,
) -> SkillInvocation:
    """`Capability` + argümanı tura çevir (komut: görev; beceri: bağlam + görev).

    `!`cmd`` başarısız ya da izinsizse çağrı iptal edilir (`ok=False`, Claude Code #168).
    """
    from .capabilities import Capability

    assert isinstance(capability, Capability)
    proposal_policy = proposal_policy or ProposalPolicy()
    try:
        raw = capability.path.read_text(encoding="utf-8")
    except OSError as error:
        return SkillInvocation(task=argument, notes=(f"beceri okunamadı: {error}",))
    try:
        proposal = proposal_metadata(raw)
        if capability.proposal is not None or proposal is not None:
            return _proposal_invocation(
                capability, raw, proposal, argument, env, proposal_policy, proposal_validator
            )
    except (ValueError, OSError) as error:
        return SkillInvocation(task="", ok=False, notes=(str(error),))
    body = body_after_frontmatter(raw)
    deprecated = deprecated_template_notes(body)
    body = body.replace("{SKILL_DIR}", str(capability.path.parent))
    body = with_plugin_root(body, capability.path, env.project_dir)
    rendered = render_template(body, argument, env, names=capability.arguments)
    policy = shell_policy or ShellPolicy(mode_allows=shell_allowed, read_only=shell_read_only)
    policy = ShellPolicy(
        mode_allows=policy.mode_allows,
        read_only=policy.read_only,
        disabled=policy.disabled,
        rule_decision=policy.rule_decision,
        preapproved=(*policy.preapproved, *bash_patterns(capability.allowed_tools)),
        shell=capability.shell or policy.shell,
        timeout_s=policy.timeout_s,
    )
    try:
        rendered, shell_notes = expand(rendered, cwd=env.project_dir, policy=policy)
    except SkillShellError as error:
        return SkillInvocation(task="", ok=False, notes=(str(error),))
    allowed_tools, tool_notes = _allowed_tools(capability.allowed_tools)
    notes = (*deprecated, *shell_notes, *tool_notes)
    fork = capability.context.strip().lower() == "fork"
    if capability.agent and not fork:
        notes = (*notes, "agent alanı yalnız context: fork ile anlamlı; yok sayıldı")
    if capability.kind == "komut":
        task, context = rendered, ""
    else:
        context = (
            f'<beceri ad="{capability.name}" kaynak="{capability.source}">\n'
            "Kullanıcının açıkça seçtiği beceri; bu turda yönergeleri uygula.\n"
            f"{rendered}\n</beceri>"
        )
        task = argument.strip() or DEFAULT_SKILL_TASK.format(name=capability.name)
    return SkillInvocation(
        task=task,
        context=context,
        allowed_tools=allowed_tools,
        model=capability.model,
        effort=capability.effort,
        fork=fork,
        notes=notes,
        denied_tools=map_denied_tools(capability.disallowed_tools),
        agent=capability.agent if fork else "",
    )


def _proposal_invocation(
    capability: object,
    raw: str,
    proposal: ProposalInvocation | None,
    argument: str,
    env: TemplateEnv,
    policy: ProposalPolicy,
    validator: ProposalValidator | None,
) -> SkillInvocation:
    """Doğrulanmış beceri önerisi: yalnız kimlik/sürüm bağlamı; geçersizse `ValueError`."""
    from .capabilities import Capability

    assert isinstance(capability, Capability)
    if (
        proposal != capability.proposal
        or proposal is None
        or proposal.revision != body_revision(raw)
        or not visible_proposal(proposal, policy)
        or validator is None
        or "!`" in argument
    ):
        raise ValueError("Öneri kaynağı, sürümü veya çağrı politikası geçersiz.")
    validator(proposal, argument, env.project_dir)
    context = INVOCATION_PREFIX + json.dumps(
        {
            "path": str(capability.path.resolve()),
            "arguments": argument,
            "revision": proposal.revision,
        },
        ensure_ascii=False,
    )
    return SkillInvocation(task=argument, context=context)


def _allowed_tools(entries: tuple[str, ...]) -> tuple[set[str] | None, tuple[str, ...]]:
    """`allowed-tools` → Fusion araç adları ve kullanıcı notları; `None` = kısıt yok."""
    from .capabilities import map_tools

    if not entries or entries == NO_TOOLS:
        return None, ()
    notes: list[str] = []
    names = tuple(name.split("(", 1)[0].strip() for name in entries)
    allowed = map_tools(names)
    unmapped = [name for name in names if map_tools((name,)) == set()]
    if allowed == set():
        # Hiçbir ad Fusion aracına eşlenmedi (`ExitPlanMode`…): tur araçsız kalmasın.
        notes.append(
            "allowed-tools: hiçbir ad Fusion aracına eşlenmedi ("
            + ", ".join(unmapped)
            + "); kısıt uygulanmadı"
        )
        return None, tuple(notes)
    if unmapped:
        notes.append("allowed-tools: eşlenmeyen adlar yok sayıldı: " + ", ".join(unmapped))
    return allowed, tuple(notes)


def map_denied_tools(names: tuple[str, ...]) -> frozenset[str]:
    """`disallowed-tools` Claude adları → Fusion adları; `Bash(rm *)` deseninde araç adı."""
    from .capabilities import map_tools

    cleaned = tuple(name.split("(", 1)[0].strip() for name in names if name.strip())
    mapped = map_tools(cleaned) if cleaned else set()
    return frozenset(mapped or ())
