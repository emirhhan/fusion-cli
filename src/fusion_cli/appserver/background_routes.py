"""Masaüstü uçları: arka plan görevleri (`arkaplan.*`) ve açık oturumlar (`esler.*`) — P-048/P-060.

İşler REPL ile AYNI modüllerden geçer (`tools.agent_tasks`, `cli.repl.agent_link`); masaüstü
yalnız yüzeydir. Panel `arkaplan.durum`'u birkaç saniyede bir çağırır: bu çağrı oturumu
deftere kaydeder/nabız yazar, bitiş ve girdi bildirimlerini, bekleyen gelen mesajları ve
sıradaki tura teslim edilecek sonuçları toplar.

Masaüstünde gelen mesaj HER ZAMAN bekletilir (accept ayarı da): tur, kullanıcı "Tura al"
deyince etiketli güvenilmez girdi metniyle başlar (`esler.al` metni döndürür, arayüz
olağan gönderim yolunu kullanır).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..cli.repl import agent_link
from ..cli.repl.background_commands import start_background
from ..cli.repl.state import ReplState
from ..core.background_store import BackgroundTaskStore
from ..core.background_tasks import BackgroundTask, BackgroundTaskError, TaskStatus
from ..core.peers import InboundPolicy, PeerRecord, inbound_turn_text
from ..tools import agent_tasks
from ..ui import background_messages as texts

BACKGROUND_ROUTES = frozenset(
    {
        "arkaplan.durum",
        "arkaplan.baslat",
        "arkaplan.goster",
        "arkaplan.durdur",
        "arkaplan.mesaj",
        "arkaplan.cevapla",
        "arkaplan.sil",
        "esler.gonder",
        "esler.al",
        "esler.reddet",
    }
)


def _link(state: ReplState) -> agent_link.AgentLink:
    link = state.agent_link
    if link is None:
        link = agent_link.open_link(state, kind="masaustu")
        link.policy = InboundPolicy.HOLD
    link.owner = state.conversation_id
    return link


def task_payload(task: BackgroundTask, question: dict[str, object] | None = None) -> dict[str, Any]:
    """Panel satırı; girdi bekleyen görevde bekleyen istek (`soru`: tur, ozet, arguman,
    tehlike, secenekler) de gelir. Ölçüldü (31 Ekim): panel soru türünü bilmediği için
    serbest metinli `ask_user` sorusunu cevaplayamıyordu."""
    payload: dict[str, Any] = {
        **task.to_dict(),
        "durum_etiketi": texts.BG_STATUS_LABELS.get(task.status.value, task.status.value),
        "etkin": task.is_active,
    }
    if question is not None:
        payload["soru"] = question
    return payload


def _row(store: BackgroundTaskStore, task: BackgroundTask) -> dict[str, Any]:
    waiting = task.status is TaskStatus.NEEDS_INPUT
    return task_payload(task, store.pending_question(task.id) if waiting else None)


def _peer_payload(peer: PeerRecord) -> dict[str, Any]:
    return {"id": peer.id, "ad": peer.name, "tur": peer.kind, "kok": peer.root, "durum": peer.state}


def _status(state: ReplState, turn_owner: str) -> dict[str, Any]:
    link = _link(state)
    result = link.poll(state, busy=False)
    # Uyandırma turları masaüstünde `cron.vadesi_gelenler` ile boştayken gönderilir.
    link.queued_turns.extend(result.turns)
    if turn_owner and turn_owner != link.owner:
        # Masaüstü turu sekme kimliğiyle (`app`/sohbet) koşar; araçla başlayan görev oraya aittir.
        extra = agent_tasks.collect_deliveries(link.store, turn_owner)
        if extra:
            from ..cli.repl import prefixes

            prefixes.push_pending_context(state, agent_tasks.delivery_block(link.store, extra))
    peers = [peer for peer in link.registry.peers() if peer.id != link.peer_id]
    return {
        "ok": True,
        "acik": bool(getattr(state.config.runtime, "background_agents", True)),
        "gorevler": [_row(link.store, task) for task in link.store.tasks(root=state.root)],
        "oturumlar": [_peer_payload(peer) for peer in peers],
        "bekleyen": [
            {"no": index, "kimden": message.sender_name, "metin": message.text}
            for index, message in enumerate(link.held, start=1)
        ],
        "bildirimler": list(result.notices),
        "ben": link.peer_id,
    }


def _task(state: ReplState, data: dict[str, Any]) -> BackgroundTask:
    raw = data.get("id")
    if not isinstance(raw, str) or not raw.strip():
        raise BackgroundTaskError("Görev kimliği gerekli.")
    return agent_tasks.task_store(state.config.memory_dir).resolve(raw)


def _text(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise BackgroundTaskError(texts.BG_SEND_USAGE)
    return value.strip()


def _number(data: dict[str, Any]) -> int:
    value = data.get("no")
    if not isinstance(value, int) or isinstance(value, bool):
        raise BackgroundTaskError(texts.PEER_HELD_MISSING.format(no=value))
    return value


def _start(state: ReplState, data: dict[str, Any]) -> dict[str, Any]:
    name = data.get("ad")
    task = start_background(state, _text(data, "gorev"), name=name if isinstance(name, str) else "")
    return {"ok": True, "gorev": task_payload(task)}


def _show(state: ReplState, data: dict[str, Any]) -> dict[str, Any]:
    task = _task(state, data)
    store = agent_tasks.task_store(state.config.memory_dir)
    return {
        "ok": True,
        "gorev": task_payload(task),
        "sonuc": store.read_result(task.id),
        "olaylar": agent_tasks.log_tail(store, task.id),
        "soru": store.pending_question(task.id),
    }


def _stop(state: ReplState, data: dict[str, Any]) -> dict[str, Any]:
    store = agent_tasks.task_store(state.config.memory_dir)
    task = agent_tasks.stop_task(store, _task(state, data), force=data.get("zorla") is True)
    return {"ok": True, "gorev": task_payload(task)}


def _send(state: ReplState, data: dict[str, Any]) -> dict[str, Any]:
    store = agent_tasks.task_store(state.config.memory_dir)
    task = agent_tasks.send_to_task(
        store, _task(state, data), _text(data, "metin"), sender=state.conversation_id
    )
    return {"ok": True, "gorev": task_payload(task)}


def _answer(state: ReplState, data: dict[str, Any]) -> dict[str, Any]:
    store = agent_tasks.task_store(state.config.memory_dir)
    task = agent_tasks.answer_task(store, _task(state, data), _text(data, "cevap"))
    return {"ok": True, "gorev": task_payload(task)}


def _remove(state: ReplState, data: dict[str, Any]) -> dict[str, Any]:
    task = _task(state, data)
    agent_tasks.task_store(state.config.memory_dir).remove(task.id)
    return {"ok": True, "id": task.id}


def _peer_send(state: ReplState, data: dict[str, Any]) -> dict[str, Any]:
    link = _link(state)
    if link.peer is None:
        raise BackgroundTaskError(texts.PEER_DISABLED)
    peer = link.registry.send(link.peer, _text(data, "hedef"), _text(data, "metin"))
    return {"ok": True, "metin": texts.PEER_SENT.format(name=peer.name)}


def _peer_take(state: ReplState, data: dict[str, Any]) -> dict[str, Any]:
    message = _link(state).take_held(_number(data))
    return {"ok": True, "tur_metni": inbound_turn_text(message), "kimden": message.sender_name}


def _peer_drop(state: ReplState, data: dict[str, Any]) -> dict[str, Any]:
    message = _link(state).take_held(_number(data))
    return {"ok": True, "kimden": message.sender_name}


_HANDLERS: dict[str, Callable[[ReplState, dict[str, Any]], dict[str, Any]]] = {
    "arkaplan.baslat": _start,
    "arkaplan.goster": _show,
    "arkaplan.durdur": _stop,
    "arkaplan.mesaj": _send,
    "arkaplan.cevapla": _answer,
    "arkaplan.sil": _remove,
    "esler.gonder": _peer_send,
    "esler.al": _peer_take,
    "esler.reddet": _peer_drop,
}


def dispatch_background(
    state: ReplState, name: str, data: dict[str, Any], *, turn_owner: str = ""
) -> dict[str, Any]:
    """`session.py` yalnız bunu çağırır; beklenen hatalar `ok: false` + Türkçe metin olur."""
    try:
        if name == "arkaplan.durum":
            return _status(state, turn_owner)
        return _HANDLERS[name](state, data)
    except (BackgroundTaskError, OSError) as error:
        return {"ok": False, "metin": str(error)}
