"""Modelin arka plan görevleri ve öteki oturumlarla konuştuğu araçlar (P-048, P-060).

Claude Code `ListAgents` / `SendMessage` / `TaskStop` karşılığı:

- `list_agents`  — bu projenin arka plan görevleri + açık Fusion oturumları; `id` ile tek
  görevin durumu/sonucu, `bekle_s` ile bitene (ya da girdi isteyene) kadar bekleme.
- `send_message` — arka plan görevine devam mesajı (bitmişse yeniden başlar) ya da başka bir
  oturuma mesaj (alıcıda etiketli, güvenilmez girdi olur).
- `stop_agent`   — arka plan görevini durdur.

`spawn_agent(arka_plan=true)` başlatmayı `spawn_background` ile buraya devreder. Araçlar
yalnız arka plan/oturum işi konuşulan turda sunulur (`SCOPED_TOOLS`, istem bütçesi).
"""

from __future__ import annotations

import asyncio
import os
import re
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from ...core.background_store import BackgroundTaskStore
from ...core.background_tasks import (
    WORKER_CONVERSATION_PREFIX,
    BackgroundTask,
    BackgroundTaskError,
    TaskOptions,
    TaskStatus,
)
from ...core.errors import PathAccessError, WorktreeError
from ...core.peers import PeerRecord, PeerRegistry
from ...core.tools import Tool, ToolArgs, ToolContext, ToolResult
from ...tools import agent_tasks
from ...ui import background_messages as texts
from . import team_fork
from .approval import ApprovalMode

if TYPE_CHECKING:
    from .loop import AgentDeps
    from .team import SubTask

_STRING = {"type": "string"}
#: Alt ajanın arka plan görevi açması (iç içe süreç ağacı) engellenir.
BACKGROUND_DEPTH_MESSAGE = texts.BG_DEPTH_LIMIT
#: Bu araçları turda açan istek desenleri (arka plan görevi / öteki oturumlar).
_AGENT_TASK_REQUEST = re.compile(
    r"arka ?plan|background|\bbg\b|list_agents|send_message|stop_agent|"
    r"(?:diğer|öteki|başka|açık) (?:fusion )?oturum|oturuma mesaj|oturumlar arası|"
    r"<oturumlar_arasi_mesaj",
    re.IGNORECASE,
)


def is_agent_task_request(task: str, deps: AgentDeps) -> bool:
    """Tur arka plan görevleri/oturumlarla mı ilgili? Bu konuşmanın görevi varsa da evet."""
    if _AGENT_TASK_REQUEST.search(task):
        return True
    owner = getattr(deps, "conversation_id", "")
    memory_dir = getattr(getattr(deps, "config", None), "memory_dir", None)
    if not owner or memory_dir is None:
        return False
    try:
        store = agent_tasks.task_store(memory_dir)
        return any(item.owner == owner for item in store.tasks())
    except (OSError, BackgroundTaskError):
        return False


#: Aracın kabul ettiği en uzun bekleme (saniye); `job_status` ile aynı ölçek.
_MAX_WAIT_S = 300
#: Listede gösterilen en çok görev.
_LIST_LIMIT = 20


def _store(deps: AgentDeps) -> BackgroundTaskStore:
    return agent_tasks.task_store(deps.config.memory_dir)


def _peers(deps: AgentDeps) -> PeerRegistry:
    return agent_tasks.peer_registry(deps.config.memory_dir)


def _self_peer(registry: PeerRegistry, deps: AgentDeps) -> PeerRecord | None:
    """Bu sürecin bu konuşmaya ait oturum kaydı (REPL/masaüstü açtıysa)."""
    for peer in registry.peers():
        if peer.pid == os.getpid() and peer.conversation_id == deps.conversation_id:
            return peer
    return None


def _runtime(deps: AgentDeps) -> object:
    """`deps.config.runtime` ya da yoksa None (eski sahte `deps`'ler; ayarlar varsayılana düşer).

    Ölçüldü (31 Ekim): `build_agent_registry` çağıran mevcut testlerin `config`'i runtime
    taşımıyordu; doğrudan erişim tabanda geçen `test_forge_wiring` testlerini kırıyordu.
    """
    return getattr(getattr(deps, "config", None), "runtime", None)


def background_mode(deps: AgentDeps) -> str:
    """Arka plan görevinin kipi: üst kipten GEVŞEK olamaz; bypass miras alınmaz."""
    reader = getattr(deps, "approval_mode", None)
    current = reader() if reader is not None else ApprovalMode.AUTO
    return ApprovalMode.AUTO.value if current is ApprovalMode.BYPASS else current.value


async def spawn_background(deps: AgentDeps, subtask: SubTask) -> ToolResult:
    """`spawn_agent(arka_plan=true)`: görevi ayrı süreçte başlat, kimliği hemen döndür.

    Üst turun kısıtları aynen taşınır (`run_subagent` yolundaki kesişim kuralı): araç tavanı
    ve yasakları, yazma alanı, ek kökler, adım tavanı, brif, `baglam_miras` ve `izolasyon`.
    Ölçüldü (31 Ekim): yalnız görev/kişilik/salt-okur/kip taşınıyordu; salt-okur kişilikli ya da
    `disallowedTools`lu oturumdan açılan arka plan görevi tam araç setiyle koşuyordu.
    """
    if getattr(deps, "conversation_id", "").startswith(WORKER_CONVERSATION_PREFIX):
        # İşçi de derinlik 0'dır; açacağı görevin sonucunu teslim alacak gözcü yoktur.
        return ToolResult.failure(texts.BG_NESTED_WORKER)
    try:
        root, options = await asyncio.to_thread(_inherited_limits, deps, subtask)
    except (PathAccessError, WorktreeError) as error:
        return ToolResult.failure(texts.BG_LIMITS_FAILED.format(error=error))
    history = (
        agent_tasks.fork_history(team_fork.parent_history(deps)) if subtask.inherit_context else ()
    )
    request = agent_tasks.LaunchRequest(
        prompt=subtask.task,
        root=root,
        name=subtask.persona,
        owner=deps.conversation_id,
        origin="arac",
        mode=background_mode(deps),
        agent=subtask.persona,
        read_only=subtask.read_only,
        max_turns=subtask.step_limit or 0,
        history=history,
        options=options,
    )
    try:
        task = agent_tasks.start_with_settings(_runtime(deps), deps.config.memory_dir, request)
    except BackgroundTaskError as error:
        return ToolResult.failure(str(error))
    template = (
        texts.BG_TOOL_STARTED_DETACHED
        if deps.conversation_id in _NO_DELIVERY_OWNERS
        else texts.BG_TOOL_STARTED
    )
    worktree_note = (
        texts.BG_TOOL_WORKTREE.format(path=root) if root != deps.tool_context.root else ""
    )
    return ToolResult(template.format(id=task.id, name=task.name) + worktree_note)


#: Sonucu sıradaki tura teslim alacak gözcüsü olmayan sahipler (tek atış `fusion agent`).
_NO_DELIVERY_OWNERS = frozenset({"", "cli"})


def _inherited_limits(deps: AgentDeps, subtask: SubTask) -> tuple[Path, TaskOptions]:
    """Üst turun araç tavanı/yasakları ve yazma alanı; izolasyon istendiyse çalışma ağacı."""
    from ...core.worktree import enter_worktree
    from .team_scope import derive_sub_context

    context = deps.tool_context
    scope = derive_sub_context(context, subtask).write_scope
    execution = getattr(deps, "execution", None)
    parent_cap = getattr(execution, "allowed_tool_names", None)
    caps = [set(cap) for cap in (parent_cap, subtask.tool_cap) if cap is not None]
    allowed = set.intersection(*caps) if caps else None
    denied = frozenset(getattr(deps, "denied_tools", ())) | subtask.tool_deny
    root = context.root
    if subtask.isolation == "worktree" and not subtask.read_only:
        name = "arka-" + uuid.uuid4().hex[:8]
        root = enter_worktree(context.root, name).path
        # Yazma alanı ana köke göre çözüldü; izole ağaçta aynı göreli yollara çevrilir.
        scope = tuple(_rebase(path, context.root, root) for path in scope) if scope else scope
    options = TaskOptions(
        allowed_tools=tuple(sorted(allowed)) if allowed is not None else None,
        denied_tools=tuple(sorted(denied)),
        write_scope=tuple(str(path) for path in scope or ()),
        extra_roots=tuple(str(path) for path in context.extra_roots),
        extra_system=subtask.brief,
    )
    return root, options


def _rebase(path: Path, old_root: Path, new_root: Path) -> Path:
    try:
        return new_root / path.relative_to(old_root.resolve())
    except ValueError:
        return path  # ek kökteki yol: ağaçtan bağımsız


def task_line(task: BackgroundTask) -> str:
    label = texts.BG_STATUS_LABELS.get(task.status.value, task.status.value)
    detail = task.question or task.summary or task.note
    return f"{task.id} {task.name} [{label}] {detail}".rstrip()


def _task_detail(store: BackgroundTaskStore, task: BackgroundTask) -> str:
    lines = [task_line(task), texts.BG_DETAIL_PROMPT.format(prompt=task.prompt[:400])]
    if task.status is TaskStatus.NEEDS_INPUT:
        lines.append(texts.BG_DETAIL_NEEDS_INPUT.format(question=task.question))
    result = store.read_result(task.id)
    if result:
        lines.append(
            texts.BG_DETAIL_RESULT.format(result=result[: agent_tasks.DELIVERY_EXCERPT_CHARS])
        )
    return "\n".join(lines)


def list_agents_tool(deps: AgentDeps) -> Tool:
    async def _run(args: ToolArgs, context: ToolContext) -> ToolResult:
        store = _store(deps)
        query = str(args.get("id") or "").strip()
        try:
            if query:
                task = store.resolve(query)
                wait = args.get("bekle_s")
                if isinstance(wait, (int, float)) and wait > 0:
                    task = await agent_tasks.wait_task(
                        store, task.id, min(float(wait), _MAX_WAIT_S)
                    )
                return ToolResult(_task_detail(store, task))
        except BackgroundTaskError as error:
            return ToolResult.failure(str(error))
        tasks = store.tasks(root=context.root)[:_LIST_LIMIT]
        registry = _peers(deps)
        me = _self_peer(registry, deps)
        peers = [peer for peer in registry.peers() if me is None or peer.id != me.id]
        lines = [texts.BG_LIST_TASKS_HEADER, *(task_line(task) for task in tasks)]
        if not tasks:
            lines.append(texts.BG_LIST_NONE)
        lines.append(texts.PEER_LIST_HEADER)
        lines.extend(texts.PEER_LINE.format(**_peer_fields(peer)) for peer in peers)
        if not peers:
            lines.append(texts.PEER_LIST_NONE)
        return ToolResult("\n".join(lines))

    return Tool(
        name="list_agents",
        description="Arka plan ajan görevlerini ve açık öteki Fusion oturumlarını listele; "
        "id ile tek görevin durumunu/sonucunu gör, bekle_s ile bitmesini bekle.",
        parameters={
            "type": "object",
            "properties": {"id": _STRING, "bekle_s": {"type": "integer"}},
        },
        run=_run,
    )


def _peer_fields(peer: PeerRecord) -> dict[str, str]:
    return {"id": peer.id, "name": peer.name, "kind": peer.kind, "root": peer.root}


def send_message_tool(deps: AgentDeps) -> Tool:
    async def _run(args: ToolArgs, context: ToolContext) -> ToolResult:
        target = str(args.get("to") or "").strip()
        text = str(args.get("message") or "").strip()
        if not target or not text:
            return ToolResult.failure(texts.BG_SEND_USAGE)
        try:
            return ToolResult(deliver_message(deps, target, text))
        except BackgroundTaskError as error:
            return ToolResult.failure(str(error))

    return Tool(
        name="send_message",
        description="Arka plan görevine devam mesajı ya da başka bir Fusion oturumuna mesaj "
        "gönder (to: görev/oturum adı ya da kimliği).",
        parameters={
            "type": "object",
            "properties": {"to": _STRING, "message": _STRING},
            "required": ["to", "message"],
        },
        run=_run,
    )


def deliver_message(deps: AgentDeps, target: str, text: str) -> str:
    """Önce arka plan görevi, yoksa açık oturum; ikisi de yoksa açık hata."""
    if not getattr(_runtime(deps), "background_agents", True):
        task = None
    else:
        task = _find_task(_store(deps), target)
    if task is not None:
        trusted = not task.owner or task.owner == deps.conversation_id
        updated = agent_tasks.send_to_task(
            _store(deps), task, text, sender=deps.conversation_id or "ajan", trusted=trusted
        )
        return texts.BG_SENT.format(name=updated.name, status=updated.status.value)
    if not getattr(_runtime(deps), "cross_session_messaging", True):
        raise BackgroundTaskError(texts.PEER_DISABLED)
    registry = _peers(deps)
    peer = registry.send(_self_peer(registry, deps), target, text)
    return texts.PEER_SENT.format(name=peer.name)


def _find_task(store: BackgroundTaskStore, target: str) -> BackgroundTask | None:
    try:
        return store.resolve(target)
    except BackgroundTaskError:
        return None


def stop_agent_tool(deps: AgentDeps) -> Tool:
    async def _run(args: ToolArgs, context: ToolContext) -> ToolResult:
        store = _store(deps)
        try:
            task = agent_tasks.stop_task(store, store.resolve(str(args.get("id") or "")))
        except BackgroundTaskError as error:
            return ToolResult.failure(str(error))
        return ToolResult(texts.BG_STOP_REQUESTED.format(name=task.name))

    return Tool(
        name="stop_agent",
        description="Çalışan bir arka plan ajan görevini durdur.",
        parameters={"type": "object", "properties": {"id": _STRING}, "required": ["id"]},
        run=_run,
    )


def agent_task_tools(deps: AgentDeps) -> tuple[Tool, ...]:
    """Ayarlar açıksa araçlar; ikisi de kapalıysa hiçbiri."""
    runtime = _runtime(deps)
    background = getattr(runtime, "background_agents", True)
    peers = getattr(runtime, "cross_session_messaging", True)
    if not background and not peers:
        return ()
    tools = [list_agents_tool(deps), send_message_tool(deps)]
    if background:
        tools.append(stop_agent_tool(deps))
    return tuple(tools)
