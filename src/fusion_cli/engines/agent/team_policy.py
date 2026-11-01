"""Alt görevin etki gereksinimi parent güven sınırlarını genişletemez."""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING, cast

from ...tools.capabilities import expand_tool_patterns
from .edit_hooks import EDIT_TOOLS
from .execution_policy import ExecutionPolicy, policy_for
from .team_scope import derive_sub_context
from .team_settings import MEMORY_TOOL_NAMES
from .team_tools_member import TEAM_MEMBER_TOOLS

_LOG = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ...tools.registry import ToolRegistry
    from .loop import AgentDeps
    from .team import Persona, SubRun, SubTask


def child_execution(deps: AgentDeps, subtask: SubTask) -> ExecutionPolicy | None:
    parent = deps.execution
    if parent is None:
        return None
    child = policy_for(deps.config, deps.config.agent, subtask.task)
    return dataclasses.replace(
        parent,
        requires_tool_evidence=child.requires_tool_evidence,
        required_effect=child.required_effect,
        complex_task=child.complex_task,
        allow_mutation=parent.allow_mutation and child.allow_mutation and not subtask.read_only,
    )


def allowed_tools(
    deps: AgentDeps,
    persona: Persona,
    subtask: SubTask,
    *,
    available: tuple[str, ...] = (),
) -> set[str] | None:
    """Üyenin araç kümesi: `tools` ∖ `disallowedTools`, MCP sunucu süzgeci, yazma alanı.

    `available` çalışma-anı defterinin adlarıdır: `disallowedTools` ya da `mcpServers`
    kümeyi DARALTIR, bu yüzden tam yetkili (`None`) üye bile o anda adlandırılabilir bir
    kümeye iner. Her adım yalnız çıkarır; alt ajan üstünden fazla araç göremez.
    """
    # AgentDeps.__post_init__ None değerini yapılandırılmış defterle tamamlar.
    registry = cast("ToolRegistry", deps.base_registry)
    allowed: set[str] | None = set(persona.tools) if persona.tools is not None else None
    if allowed is not None and available:
        allowed = expand_tool_patterns(allowed, available)
    if persona.disallowed_tools or persona.mcp_servers:
        if allowed is None:
            allowed = set(available) if available else None
        if allowed is not None:
            # Ölçüldü (31 Ekim): `mcp__srv` → `srv__*` deseni açılmadan çıkarılıyordu ve
            # yasaklı MCP araçları kalıyordu; yasak da izin gibi defter adlarına açılır.
            allowed = allowed - expand_tool_patterns(set(persona.disallowed_tools), available)
            if persona.mcp_servers:
                _warn_unknown_servers(deps, persona, available)
                allowed = {
                    name
                    for name in allowed
                    if not registry.is_remote(name) or name.split("__", 1)[0] in persona.mcp_servers
                }
    # Ajan belleği olan üyenin bellek araçları (P-055): yasak listesindekiler açılmaz ve
    # salt-okur görevde yalnız okuma kalır (ölçüldü, 31 Ekim: `remember` 'dosya değiştirme'
    # denen görevde .fusion/ altına yazıyordu; `disallowedTools: remember` de deliniyordu).
    memory_tools = _memory_tools(persona, subtask)
    if allowed is not None and memory_tools:
        allowed = allowed | memory_tools
    # Ekip üyesinin pano araçları (P-061) rol kısıtından (`tools:`) bağımsız açıktır: üye
    # görev alamazsa ekip kilitlenir. Yalnız üyenin defterinde bulunurlar.
    team_tools = TEAM_MEMBER_TOOLS & set(available)
    if allowed is not None and team_tools:
        allowed = allowed | team_tools
    # Gerçek çağıran alt ajanın kendi bağımlılığını verir: bağlamı bu görevden ZATEN
    # türetildi. Yeniden türetmek salt-okur alt bağlamın boş alanına karşı `yazma_alani`nı
    # doğrulayıp başlatmayı reddediyordu (ölçüldü, 1 Kasım: test_evidence_handoff).
    scope = deps.tool_context.write_scope
    if scope is None:
        scope = derive_sub_context(deps.tool_context, subtask).write_scope
    if not subtask.read_only and scope is None:
        return allowed
    safe = {
        tool.name
        for tool in registry
        if not tool.mutating or (not subtask.read_only and tool.name in EDIT_TOOLS)
    }
    narrowed = safe if allowed is None else allowed & safe
    # `safe` temel defterden türer; bellek araçları çalışma-anı defterindedir.
    return narrowed | memory_tools if memory_tools else narrowed


def _memory_tools(persona: Persona, subtask: SubTask) -> set[str]:
    if not persona.memory_scope:
        return set()
    tools = set(MEMORY_TOOL_NAMES) - set(persona.disallowed_tools)
    return tools - {"remember"} if subtask.read_only else tools


def _warn_unknown_servers(deps: AgentDeps, persona: Persona, available: tuple[str, ...]) -> None:
    """`mcpServers` Fusion'da yalnız SÜZGEÇTİR (Claude Code'daki gibi sunucu tanımlamaz):
    yapılandırmada olmayan ad sessizce 'araç yok' sonucu verirdi, günlüğe uyarı düşer."""
    # AgentDeps.__post_init__ None değerini yapılandırılmış defterle tamamlar.
    registry = cast("ToolRegistry", deps.base_registry)
    known = {name.split("__", 1)[0] for name in available if registry.is_remote(name)}
    missing = sorted(set(persona.mcp_servers) - known)
    if missing:
        _LOG.warning(
            "ajan tanımındaki MCP sunucusu yapılandırmada yok; mcpServers yalnız süzgeçtir",
            extra={"ajan": persona.name, "sunucular": missing},
        )


def member_brief(
    persona: Persona, subtask: SubTask, *, skills: str = "", fork_note: str = ""
) -> str:
    """Üyenin talimatı + ön yüklenen beceriler + bu görevin sınırları (modelin göreceği not)."""
    parts = [persona.prompt.strip()] if persona.prompt.strip() else []
    if skills:
        parts.append(skills)
    if subtask.brief.strip():
        parts.append(subtask.brief.strip())
    if fork_note:
        parts.append(fork_note)
    if subtask.read_only:
        parts.append("Bu görevde SALT OKUYORSUN: dosya değiştirme, yalnız bulgularını raporla.")
    elif subtask.write_scope:
        alan = ", ".join(subtask.write_scope)
        parts.append(
            f"Yalnız şu yollara yazabilirsin: {alan}. Başka ajanlar aynı anda başka "
            "dosyalarda çalışıyor; alanın dışına çıkma."
        )
    return "\n\n".join(parts)


#: Bir üyenin ana bağlama dönen raporunun üst sınırı: `max_parallel_agents` uzun rapor
#: birleşince bağlam şişiyordu (A4-40).
MEMBER_REPORT_CHARS = 6_000


def cap_report(text: str, limit: int = MEMBER_REPORT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n[… rapor kırpıldı; ayrıntı için değişen dosyalara bak.]"


def team_report(runs: Sequence[SubRun]) -> str:
    """Ana ajana dönen birleşik rapor: her üyenin sonucu kendi başlığıyla."""
    return "\n\n".join(
        f"## {run.persona.title} ({run.sub_id}) — {'tamam' if run.ok else 'yarım'}\n"
        f"{cap_report(run.text)}"
        for run in runs
    )


def summary(text: str, limit: int) -> str:
    first = " ".join(text.strip().split())
    return first if len(first) <= limit else first[: limit - 1] + "…"
