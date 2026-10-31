"""`team_run(arka_plan=true)`: ekibi arka plan görevi olarak koştur (P-061 + P-048).

Ölçüldü (1 Kasım): ekip `team_run` çağrısının içinde koşuyordu; lider (ana ajan) ve
kullanıcı üyeler bitene kadar sohbete devam edemiyordu (Claude Code'da lider ekip
çalışırken konuşmayı sürdürür).

Arka plan kipinde ekip `fusion arka-plan-calistir` işçisinde koşar: işçinin ilk turu
aynı `team_run` çağrısını (arka_plan olmadan) yapar; maliyet onayı başlatmadan önce
burada sorulduğu için işçide kapalıdır. Lider hemen döner; sonuç bitince sahibin
sıradaki turuna teslim edilir (arka plan görevlerinin olağan yolu), pano diskte olduğu
için `/team goster`, masaüstü Ajanlar sekmesi ve `ekip.pano` canlı görür.

Koşan ekibe mesaj: `team_run(ad=X, mesajlar=[…])` ekibi ikinci kez başlatmaz; mesajları
panonun gelen kutusuna yazar, boştaki üye birkaç saniye içinde uyanır
(`TeamSession.wait_for_work` kutuyu yoklar). Aynı ekip için ikinci bir koşucu açılmaz.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING

from ...core.background_tasks import (
    WORKER_CONVERSATION_PREFIX,
    BackgroundTask,
    BackgroundTaskError,
    TaskOptions,
    normalize_name,
)
from ...core.tools import ToolArgs, ToolResult
from ...tools import agent_tasks
from .agent_task_tools import background_mode
from .team_board import BROADCAST, LEAD, MESSAGE_CHARS, TeamMessage, TeamStore
from .team_runtime import TeamRequest

if TYPE_CHECKING:
    from .loop import AgentDeps

#: Arka plan isteğini taşıyan argüman.
BACKGROUND_KEY = "arka_plan"
#: Maliyet onayı başlatmadan önce alındı; işçi yeniden sormasın.
_WORKER_OVERRIDES = ("runtime.agent_team_confirm=false",)
WORKER_PROMPT = (
    "Ekip işini arka planda yürütüyorsun. team_run aracını AŞAĞIDAKİ argümanlarla bir kez "
    "çağır (değiştirme, arka_plan ekleme), sonra ekibin raporunu kısa ve eksiksiz özetle.\n"
    "team_run argümanları (JSON):\n{args}"
)
STARTED = (
    "Ekip '{name}' arka planda başladı (görev {id}). Üyeler çalışırken sohbete devam "
    "edebilirsin; sonuç bitince sıradaki tura gelir. Pano: /team goster {name}. Üyelere "
    "mesaj: team_run(ad='{name}', mesajlar=[…]); durdurmak: stop_agent(id='{id}')."
)
ALREADY_RUNNING = (
    "Ekip '{name}' arka planda zaten çalışıyor (görev {id}); ikinci koşu açılmadı. Üyelere "
    "mesaj için team_run(ad='{name}', mesajlar=[…]), durdurmak için stop_agent(id='{id}')."
)
DELIVERED = "Mesajlar arka planda çalışan '{name}' ekibine iletildi (görev {id}): {targets}."
ONLY_MESSAGES = (
    "Ekip '{name}' arka planda çalışıyor (görev {id}); yeni görev ya da üye o koşu bitince "
    "eklenebilir. Şimdilik yalnız mesajlar iletilebilir."
)
BOARD_NOT_READY = "Ekip '{name}' panosu henüz hazır değil (görev {id}); birazdan yeniden dene."


def is_worker(deps: AgentDeps) -> bool:
    """Bu tur arka plan işçisinin turu mu? (İşçi ekibi kendisi koşturur.)"""
    return str(getattr(deps, "conversation_id", "")).startswith(WORKER_CONVERSATION_PREFIX)


def wants_background(args: ToolArgs, deps: AgentDeps) -> bool:
    """`arka_plan` istendi mi? İşçinin kendisi her zaman ön planda koşturur."""
    value = args.get(BACKGROUND_KEY)
    requested = value is True or str(value).strip().casefold() in {"true", "evet", "1"}
    return requested and not is_worker(deps)


def task_name(team: str) -> str:
    return normalize_name(f"ekip-{team}")


def running_team(deps: AgentDeps, root: Path, team: str) -> BackgroundTask | None:
    """Bu projede bu ekibi koşturan etkin arka plan görevi (yoksa None)."""
    try:
        tasks = agent_tasks.task_store(deps.config.memory_dir).tasks(root=root)
    except (OSError, BackgroundTaskError):
        return None
    name = task_name(team)
    return next((task for task in tasks if task.is_active and task.name == name), None)


async def launch(deps: AgentDeps, args: ToolArgs, request: TeamRequest, root: Path) -> ToolResult:
    """İşçiyi başlat; ekip argümanları (arka_plan hariç) işçinin ilk istemidir."""
    forwarded = {key: value for key, value in args.items() if key != BACKGROUND_KEY}
    launch_request = agent_tasks.LaunchRequest(
        prompt=WORKER_PROMPT.format(args=json.dumps(forwarded, ensure_ascii=False, indent=2)),
        root=root,
        name=task_name(request.name),
        owner=deps.conversation_id,
        origin="arac",
        mode=background_mode(deps),
        options=TaskOptions(config_overrides=_WORKER_OVERRIDES),
    )
    runtime = getattr(deps.config, "runtime", None)
    try:
        task = agent_tasks.start_with_settings(runtime, deps.config.memory_dir, launch_request)
    except BackgroundTaskError as error:
        return ToolResult.failure(str(error))
    return ToolResult(STARTED.format(name=request.name, id=task.id))


async def deliver(request: TeamRequest, task: BackgroundTask, root: Path, now: float) -> ToolResult:
    """Koşan arka plan ekibine liderin mesajlarını yaz (kutu dosyası; ekip yoklar)."""
    labels = {"name": request.name, "id": task.id}
    if request.tasks or request.members:
        return ToolResult.failure(ONLY_MESSAGES.format(**labels))
    if not request.messages:
        return ToolResult.failure(ALREADY_RUNNING.format(**labels))
    store = TeamStore(root)
    board = await asyncio.to_thread(store.load, request.name)
    if board is None:
        return ToolResult.failure(BOARD_NOT_READY.format(**labels))
    names = [member.name for member in board.members]
    unknown = [r for r, _ in request.messages if r != BROADCAST and r not in names]
    if unknown:
        return ToolResult.failure(f"'{unknown[0]}' ekipte yok (üyeler: {', '.join(names)}).")
    delivered: list[str] = []
    for recipient, text in request.messages:
        for target in names if recipient == BROADCAST else [recipient]:
            message = TeamMessage(LEAD, target, text[:MESSAGE_CHARS], now)
            await asyncio.to_thread(store.append, request.name, message)
            delivered.append(target)
    return ToolResult(DELIVERED.format(name=request.name, id=task.id, targets=", ".join(delivered)))
