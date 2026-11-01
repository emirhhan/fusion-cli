"""REPL oturumunun arka plan görevleri ve öteki oturumlarla bağı (P-048, P-060).

Her iki REPL yüzeyi (satır-içi `loop.py`, tam ekran `tui_loop.py`) açılışta `open_link`
ile oturum defterine kaydolur ve `watch` gözcüsünü cron gözcüsünün yanında koşturur:

- Bu konuşmanın başlattığı arka plan görevi girdi isterse ya da biterse kısa bildirim
  basılır; biten görevin sonucu sıradaki turun bağlamına (`<arka_plan_sonuclari>`) girer.
- Başka oturumdan gelen mesaj `runtime.cross_session_inbound`'a göre ya etiketli TUR olur
  (accept; boştayken, slash komutu olarak asla), ya bekletilir (hold; `/list-agents al <no>`),
  ya da hiç gelmez (refuse; gönderen hata alır).

Gözcü hatası oturumu düşürmez: günlüğe yazılır, sonraki yoklamada yeniden denenir.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field

from ...core.background_store import BackgroundTaskStore
from ...core.background_tasks import BackgroundTask, BackgroundTaskError, TaskStatus
from ...core.peers import (
    PEER_HEARTBEAT_S,
    InboundPolicy,
    PeerMessage,
    PeerRecord,
    PeerRegistry,
    inbound_turn_text,
    parse_inbound_policy,
)
from ...tools import agent_tasks
from ...ui import background_messages as texts
from . import prefixes
from .state import ReplState

_LOG = logging.getLogger(__name__)

#: Bildirim üretilen durumlar (girdi isteyen ve bitenler).
_NOTIFY = {
    TaskStatus.NEEDS_INPUT: texts.BG_NOTICE_NEEDS_INPUT,
    TaskStatus.COMPLETED: texts.BG_NOTICE_COMPLETED,
    TaskStatus.FAILED: texts.BG_NOTICE_FAILED,
    TaskStatus.STOPPED: texts.BG_NOTICE_STOPPED,
    TaskStatus.LOST: texts.BG_NOTICE_LOST,
}


@dataclass(frozen=True, slots=True)
class LinkPoll:
    """Bir yoklamanın sonucu: basılacak bildirimler ve tur olacak gelen mesajlar."""

    notices: tuple[str, ...] = ()
    turns: tuple[str, ...] = ()


@dataclass(slots=True)
class AgentLink:
    store: BackgroundTaskStore
    registry: PeerRegistry
    owner: str
    policy: InboundPolicy
    peer: PeerRecord | None = None
    #: hold kipinde bekletilen gelen mesajlar (`/list-agents al <no>`).
    held: list[PeerMessage] = field(default_factory=list)
    #: accept kipinde gelen ama oturum meşgulken bekleyen turlar.
    queued_turns: list[str] = field(default_factory=list)
    #: Biten arka plan görevinin sonucu bağlama girdi; oturum boşa düşünce tur başlar.
    wake_for_delivery: bool = False
    _seen: dict[str, TaskStatus] = field(default_factory=dict)

    @property
    def peer_id(self) -> str:
        return self.peer.id if self.peer is not None else ""

    def poll(self, state: ReplState, *, busy: bool) -> LinkPoll:
        notices = [*self._task_notices(state), *self._peer_notices(busy=busy)]
        turns: tuple[str, ...] = ()
        if not busy and self.queued_turns:
            turns, self.queued_turns = tuple(self.queued_turns), []
        if not busy:
            turns = (*turns, *self._wake_turns(state))
        return LinkPoll(tuple(notices), turns)

    def _wake_turns(self, state: ReplState) -> tuple[str, ...]:
        """Claude gibi boştaki oturumu uyandır: arka plan raporu ve `asyncRewake` kancası.

        Tur kendi başına başlar (UserPromptSubmit tetiklenir); rapor/kanca metni turun
        bağlamına eklenir. Kullanıcı arada tur başlattıysa (bağlam tüketildiyse) uyanılmaz.
        """
        wake = ""
        if self.wake_for_delivery:
            self.wake_for_delivery = False
            if state.pending_blocks:
                wake = texts.BG_WAKE_TURN
        hooks = state.hook_session
        if hooks is not None and getattr(hooks, "wake_requested", False):
            hooks.wake_requested = False
            if hooks.rewake_notes and not wake:
                wake = texts.HOOK_WAKE_TURN
        return (wake,) if wake else ()

    def _task_notices(self, state: ReplState) -> list[str]:
        notices: list[str] = []
        for task in self.store.tasks():
            if task.owner != self.owner:
                continue
            previous = self._seen.get(task.id)
            self._seen[task.id] = task.status
            if previous is None and not task.is_active and task.delivered:
                continue
            if task.status != previous and task.status in _NOTIFY:
                notices.append(_notice(task))
        delivered = agent_tasks.collect_deliveries(self.store, self.owner)
        if delivered:
            prefixes.push_pending_context(state, agent_tasks.delivery_block(self.store, delivered))
            self.wake_for_delivery = True
        return notices

    def _peer_notices(self, *, busy: bool) -> list[str]:
        if self.peer is None:
            return []
        self.peer = self.registry.heartbeat(self.peer, state="calisiyor" if busy else "bosta")
        notices: list[str] = []
        for message in self.registry.take(self.peer.id):
            if self.policy is InboundPolicy.ACCEPT:
                self.queued_turns.append(inbound_turn_text(message))
                notices.append(texts.PEER_NOTICE_ACCEPTED.format(sender=message.sender_name))
            else:
                self.held.append(message)
                notices.append(
                    texts.PEER_NOTICE_HELD.format(
                        sender=message.sender_name, no=len(self.held), text=message.text[:80]
                    )
                )
        return notices

    def take_held(self, number: int) -> PeerMessage:
        if not 1 <= number <= len(self.held):
            raise BackgroundTaskError(texts.PEER_HELD_MISSING.format(no=number))
        return self.held.pop(number - 1)

    def close(self) -> None:
        if self.peer is not None:
            self.registry.unregister(self.peer.id)
            self.peer = None


def _notice(task: BackgroundTask) -> str:
    return _NOTIFY[task.status].format(
        id=task.id, name=task.name, question=task.question, summary=task.summary or task.note
    )


def open_link(state: ReplState, *, kind: str) -> AgentLink:
    """Oturumu deftere kaydet (mesajlaşma açıksa) ve bağı duruma bağla."""
    runtime = state.config.runtime
    memory_dir = state.config.memory_dir
    link = AgentLink(
        store=agent_tasks.task_store(memory_dir),
        registry=agent_tasks.peer_registry(memory_dir),
        owner=state.conversation_id,
        policy=parse_inbound_policy(str(getattr(runtime, "cross_session_inbound", "hold"))),
    )
    if getattr(runtime, "cross_session_messaging", True):
        try:
            # Çöken oturumların kayıtları ve gelen kutuları birikmesin (ölçüldü, 31 Ekim).
            link.registry.prune()
            link.peer = link.registry.register(
                name=state.conversation_name or state.root.name,
                kind=kind,
                pid=os.getpid(),
                root=state.root,
                conversation_id=state.conversation_id,
                inbound=link.policy,
            )
        except OSError:
            _LOG.warning("oturum defterine kayıt yapılamadı", exc_info=True)
    # Açılışta var olan görevler "yeni" sayılmasın: yalnız bundan sonraki değişiklik bildirilir.
    try:
        link.poll(state, busy=False)
    except (OSError, BackgroundTaskError):
        _LOG.warning("arka plan görevleri okunamadı", exc_info=True)
    state.agent_link = link
    return link


async def watch(
    state: ReplState,
    emit: Callable[[str], None],
    inject: Callable[[str], bool],
    is_busy: Callable[[], bool],
) -> None:
    """Gözcü: bildirimleri bas, kabul edilen gelen mesajları boşta tur olarak ver."""
    while state.running:
        await asyncio.sleep(PEER_HEARTBEAT_S)
        link = state.agent_link
        if link is None:
            continue
        try:
            result = link.poll(state, busy=is_busy())
        except (OSError, BackgroundTaskError):
            _LOG.warning("arka plan/oturum yoklaması başarısız", exc_info=True)
            continue
        for notice in result.notices:
            emit(notice)
        for turn in result.turns:
            # Gelen mesaj KOMUT değildir: slash ile başlasa da tur olarak işlenir.
            state.scheduled_turn_only = True
            if not inject(turn):
                state.scheduled_turn_only = False
                link.queued_turns.append(turn)


def close_link(state: ReplState) -> None:
    link, state.agent_link = state.agent_link, None
    if link is not None:
        try:
            link.close()
        except OSError:
            _LOG.warning("oturum kaydı silinemedi", exc_info=True)


def start_watch(
    state: ReplState,
    *,
    kind: str,
    emit: Callable[[str], None],
    inject: Callable[[str], bool],
    is_busy: Callable[[], bool],
) -> asyncio.Future[None]:
    """Bağı aç ve gözcüyü başlat; sahibi çağıran döngüdür (`stop_watch` ile kapatır)."""
    open_link(state, kind=kind)
    return asyncio.ensure_future(watch(state, emit, inject, is_busy))


async def stop_watch(state: ReplState, watcher: asyncio.Future[None]) -> None:
    watcher.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await watcher
    close_link(state)
