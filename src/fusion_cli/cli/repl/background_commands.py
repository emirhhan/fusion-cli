"""`/background` (`/bg`), `/tasks`, `/list-agents` ve `@oturum mesaj` (P-048, P-060).

Gövdeler burada; `commands.py` yalnız `SlashCommand` kayıtlarını tutar. İşleyiciler senkron
ve saftır (masaüstü `komut.calistir` de aynı işleyicileri çağırır): disk deposunu okur,
`tools.agent_tasks` üzerinden görev başlatır/durdurur, tek metin döndürür.
"""

from __future__ import annotations

from pathlib import Path

from ...core.background_tasks import BackgroundTask, BackgroundTaskError
from ...core.peers import inbound_turn_text
from ...engines.agent.approval import ApprovalMode
from ...tools import agent_tasks
from ...ui import background_messages as texts
from ...ui.background_view import peer_lines, task_detail, task_lines
from .state import ReplState


def _mode(state: ReplState) -> str:
    """Arka plan görevi bypass'ı miras almaz (alt ajan kuralıyla aynı)."""
    return (
        ApprovalMode.AUTO.value if state.approval is ApprovalMode.BYPASS else state.approval.value
    )


def start_background(state: ReplState, prompt: str, *, name: str = "") -> BackgroundTask:
    """Konuşma bağlamını devralan arka plan görevi başlat (`/bg`, Ctrl+B)."""
    request = agent_tasks.LaunchRequest(
        prompt=prompt,
        root=state.root,
        name=name,
        owner=state.conversation_id,
        origin="repl",
        mode=_mode(state),
        agent=state.persona.name if state.persona is not None else "",
        history=agent_tasks.fork_history(state.history),
    )
    return agent_tasks.start_with_settings(state.config.runtime, state.config.memory_dir, request)


def background_command(state: ReplState, argument: str) -> str:
    """`/bg [görev]` — görevi arka planda başlat; boşsa son görevi kaldığı yerden sürdür."""
    prompt = argument.strip()
    if not prompt:
        last = agent_tasks.last_user_text(state.history)
        if not last:
            return texts.BG_USAGE
        prompt = texts.BG_CONTINUE_PROMPT.format(task=last)
    try:
        task = start_background(state, prompt)
    except BackgroundTaskError as error:
        return str(error)
    return texts.BG_STARTED.format(id=task.id, name=task.name)


def interrupted_to_background(state: ReplState, line: str) -> str:
    """Ctrl+B: kesilen turun görevini aynı bağlamla arka planda sürdür."""
    try:
        task = start_background(state, texts.BG_CONTINUE_PROMPT.format(task=line))
    except BackgroundTaskError as error:
        return str(error)
    return texts.BG_MOVED.format(id=task.id, name=task.name)


def tasks_command(state: ReplState, argument: str) -> str:
    """`/tasks [list|show|stop|send|answer|rm|clean] …`."""
    store = agent_tasks.task_store(state.config.memory_dir)
    word, _, rest = argument.strip().partition(" ")
    action = word.casefold()
    try:
        if action in {"", "list", "liste"}:
            return task_lines(store.tasks(root=_root(state, rest)))
        if action in {"clean", "temizle"}:
            removed, failed = agent_tasks.clean_finished(store, _root(state, rest))
            text = texts.BG_CLEANED.format(count=removed)
            if failed:
                text += "\n" + texts.BG_CLEAN_FAILED.format(names=", ".join(failed))
            return text
        query, _, value = rest.strip().partition(" ")
        task = store.resolve(query)
        return _task_action(state, action, task, value.strip())
    except BackgroundTaskError as error:
        return str(error)


def _root(state: ReplState, rest: str) -> Path | None:
    """`/tasks list all` tüm projeleri gösterir; varsayılan bu proje."""
    return None if rest.strip().casefold() in {"all", "tum", "tüm"} else state.root


def _task_action(state: ReplState, action: str, task: BackgroundTask, value: str) -> str:
    store = agent_tasks.task_store(state.config.memory_dir)
    if action in {"show", "goster", "göster", "attach"}:
        return task_detail(
            task,
            store.read_result(task.id),
            agent_tasks.log_tail(store, task.id),
            question=store.pending_question(task.id),
        )
    if action in {"stop", "durdur"}:
        updated = agent_tasks.stop_task(store, task, force=value.casefold() in {"zorla", "force"})
        return texts.BG_STOP_REQUESTED.format(name=updated.name)
    if action in {"send", "gonder", "gönder"}:
        if not value:
            return texts.BG_TASKS_USAGE
        updated = agent_tasks.send_to_task(store, task, value, sender=state.conversation_id)
        return texts.BG_SENT.format(name=updated.name, status=updated.status.value)
    if action in {"answer", "cevapla"}:
        agent_tasks.answer_task(store, task, value)
        return texts.BG_ANSWERED.format(name=task.name)
    if action in {"rm", "sil"}:
        store.remove(task.id)
        return texts.BG_REMOVED.format(name=task.name)
    return texts.BG_TASKS_USAGE


def list_agents_command(state: ReplState, argument: str) -> str:
    """`/list-agents [al <no>|reddet <no>|gonder <ad> <mesaj>]` (Claude Code `/peers`)."""
    link = state.agent_link
    if link is None or link.peer is None:
        return texts.PEER_DISABLED
    word, _, rest = argument.strip().partition(" ")
    action = word.casefold()
    try:
        if action in {"al", "kabul", "accept"}:
            message = link.take_held(_number(rest))
            # Bekleyen görev KOMUT olarak çözülmez, doğrudan tur olur (makro yolu).
            state.pending_task = inbound_turn_text(message)
            return texts.PEER_HELD_TAKEN.format(sender=message.sender_name)
        if action in {"reddet", "sil", "drop"}:
            message = link.take_held(_number(rest))
            return texts.PEER_HELD_DROPPED.format(sender=message.sender_name)
        if action in {"gonder", "gönder", "send"}:
            target, _, text = rest.strip().partition(" ")
            peer = link.registry.send(link.peer, target, text)
            return texts.PEER_SENT.format(name=peer.name)
    except BackgroundTaskError as error:
        return str(error)
    return peer_lines(link.registry.peers(), link.held, link.peer_id)


def _number(raw: str) -> int:
    try:
        return int(raw.strip())
    except ValueError:
        raise BackgroundTaskError(texts.PEER_HELD_MISSING.format(no=raw.strip() or "?")) from None


def route_at_message(state: ReplState, line: str) -> str | None:
    """`@ad mesaj`: ad açık bir oturum ya da arka plan görevi ise mesajı gönder.

    Ad bir dosya/dizin olarak VARSA dokunulmaz (`@dosya` anması; P-022). Eşleşme yoksa None:
    satır olağan tura gider.
    """
    if not line.startswith("@"):
        return None
    head, _, text = line[1:].partition(" ")
    name = head.strip()
    if not name or not text.strip() or (state.root / name).exists():
        return None
    store = agent_tasks.task_store(state.config.memory_dir)
    try:
        task = store.resolve(name)
    except BackgroundTaskError:
        task = None
    try:
        if task is not None:
            updated = agent_tasks.send_to_task(store, task, text, sender=state.conversation_id)
            return texts.BG_SENT.format(name=updated.name, status=updated.status.value)
        link = state.agent_link
        if link is None or link.peer is None:
            return None
        if not any(peer.name == name or peer.id == name for peer in link.registry.peers()):
            return None
        peer = link.registry.send(link.peer, name, text)
    except BackgroundTaskError as error:
        return str(error)
    return texts.PEER_SENT.format(name=peer.name)
