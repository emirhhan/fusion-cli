"""`team_run` aracı: liderin (ana ajan) ekip kurma/sürdürme yüzü (P-061)."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from ...core.clock import SystemClock
from ...core.tools import Tool, ToolArgs, ToolContext, ToolResult
from . import team_background
from .arg_coerce import coerce_list

# `_parse_read_only`: spawn_agents ile AYNI açık-güvenli `salt_okunur` okuması (tek kaynak).
from .orchestration_runs import turn_budget_refusal
from .team import RunAgent, _parse_read_only
from .team_board import TeamError, TeamMember, TeamStore, check_name
from .team_runtime import NewTask, TeamRequest, run_agent_team, team_limits

if TYPE_CHECKING:
    from .loop import AgentDeps

START_CHOICE = "Ekibi başlat"
CANCEL_CHOICE = "Vazgeç"
CONFIRM_QUESTION = (
    "'{name}' ekibi {members} üyeyle çalışacak (en fazla {runs} üye koşusu). Üyeler aynı "
    "anda çalışır; token kullanımı tek ajana göre kat kat artabilir. Başlatılsın mı?"
)
DISABLED_MESSAGE = (
    "Ajan ekipleri kapalı (runtime.agent_teams: false); işi ayrı Agent çağrılarına böl."
)
DECLINED_MESSAGE = "Kullanıcı ekibi başlatmadı; üye çalıştırılmadı."
_STRING = {"type": "string"}


def team_run_tool(deps: AgentDeps, *, depth: int, run_agent: RunAgent) -> Tool:
    async def _run(args: ToolArgs, context: ToolContext) -> ToolResult:
        if not getattr(deps.config.runtime, "agent_teams", True):
            return ToolResult.failure(DISABLED_MESSAGE)
        store = TeamStore(context.root)
        try:
            request = parse_request(args)
            # Ekip arka planda koşuyorsa ikinci koşucu açılmaz; mesajlar kutusuna yazılır.
            active = None
            if not team_background.is_worker(deps):
                active = await asyncio.to_thread(
                    team_background.running_team, deps, context.root, request.name
                )
            if active is not None:
                return await team_background.deliver(request, active, context.root, _now(deps))
            # Tur tavanı dolduysa kullanıcıya maliyet sorusu sorulmadan reddedilir.
            if (refusal := turn_budget_refusal(deps, 1)) is not None:
                return ToolResult.failure(refusal)
            is_new = await asyncio.to_thread(store.load, request.name) is None
            if is_new and not await _confirmed(deps, request):
                return ToolResult.failure(DECLINED_MESSAGE)
            if team_background.wants_background(args, deps):
                return await team_background.launch(deps, args, request, context.root)
            result = await run_agent_team(
                deps, request, depth=depth, run_agent=run_agent, store=store
            )
        except TeamError as error:
            return ToolResult.failure(str(error))
        return ToolResult.failure(result.report) if result.error else ToolResult(result.report)

    return Tool(
        name="team_run",
        description="Ajan EKİBİ kur ya da sürdür: üyeler aynı anda çalışır, paylaşımlı görev "
        "listesinden görev alır, birbirine ve sana mesaj atar. Yeni ekipte ad, hedef, uyeler "
        "(ad, uzman, salt_okunur, yazma_alani) ve gorevler (baslik, aciklama, bagimli: id ya "
        "da önceki görevin başlığı, atanan) ver; görevler sırayla g1, g2… olur. Aynı adla "
        "tekrar çağırınca kaldığı yerden sürer; mesajlar ile üyelere yaz. arka_plan=true: "
        "ekip arka planda koşar, sen sohbete devam edersin.",
        parameters={
            "type": "object",
            "properties": {
                "ad": _STRING,
                "hedef": _STRING,
                "uyeler": {"type": "array", "items": {"type": "object"}},
                "gorevler": {"type": "array", "items": {"type": "object"}},
                "mesajlar": {"type": "array", "items": {"type": "object"}},
                "arka_plan": {"type": "boolean"},
            },
            "required": ["ad"],
        },
        run=_run,
    )


def _now(deps: AgentDeps) -> float:
    clock = deps.budget.clock if deps.budget is not None else SystemClock()
    return clock.now()


def parse_request(args: ToolArgs) -> TeamRequest:
    name = check_name(str(args.get("ad") or ""))
    return TeamRequest(
        name=name,
        goal=str(args.get("hedef") or "").strip(),
        members=tuple(_member(item, index) for index, item in enumerate(_objects(args, "uyeler"))),
        tasks=tuple(_task(item, index) for index, item in enumerate(_objects(args, "gorevler"))),
        messages=tuple(
            _message(item, index) for index, item in enumerate(_objects(args, "mesajlar"))
        ),
    )


def _objects(args: ToolArgs, key: str) -> list[dict[str, object]]:
    raw = coerce_list(args.get(key, []))
    if raw is None or raw == "":
        return []
    if not isinstance(raw, list) or not all(isinstance(item, dict) for item in raw):
        raise TeamError(f"'{key}' nesne listesi olmalı.")
    return [{str(k): v for k, v in item.items()} for item in raw]


def _member(item: dict[str, object], index: int) -> TeamMember:
    name = check_name(str(item.get("ad") or ""), f"uyeler[{index}].ad")
    scope = item.get("yazma_alani", ())
    if not isinstance(scope, (list, tuple)) or not all(isinstance(path, str) for path in scope):
        raise TeamError(f"uyeler[{index}].yazma_alani metin listesi olmalı.")
    isolation = str(item.get("izolasyon") or "")
    if isolation not in {"", "worktree"}:
        raise TeamError(f"uyeler[{index}].izolasyon yalnız 'worktree' olabilir.")
    return TeamMember(
        name=name,
        persona=str(item.get("uzman") or "").strip(),
        read_only=_parse_read_only(item.get("salt_okunur")),
        write_scope=tuple(path.strip() for path in scope if path.strip()),
        isolation=isolation,
    )


def _task(item: dict[str, object], index: int) -> NewTask:
    title = str(item.get("baslik") or "").strip()
    if not title:
        raise TeamError(f"gorevler[{index}].baslik boş olamaz.")
    deps = coerce_list(item.get("bagimli", []))
    if not isinstance(deps, list):
        raise TeamError(f"gorevler[{index}].bagimli liste olmalı.")
    return NewTask(
        title=title,
        description=str(item.get("aciklama") or ""),
        depends_on=tuple(str(dep) for dep in deps),
        assignee=str(item.get("atanan") or "").strip().casefold(),
    )


def _message(item: dict[str, object], index: int) -> tuple[str, str]:
    recipient = str(item.get("kime") or "").strip().casefold()
    text = str(item.get("metin") or "").strip()
    if not recipient or not text:
        raise TeamError(f"mesajlar[{index}]: 'kime' ve 'metin' gerekli.")
    return recipient, text


async def _confirmed(deps: AgentDeps, request: TeamRequest) -> bool:
    """Yeni ekipte maliyet uyarısı (Claude Code: ekip ~7 kat token)."""
    from .engine_tools import QuestionOption

    if not getattr(deps.config.runtime, "agent_team_confirm", True):
        return True
    if not deps.config.runtime.interaction_prompts:
        return False
    if deps.asker is None:
        return True
    limits = team_limits(deps)
    answer = await deps.asker.ask(
        CONFIRM_QUESTION.format(
            name=request.name, members=len(request.members), runs=limits.max_runs
        ),
        (QuestionOption(START_CHOICE), QuestionOption(CANCEL_CHOICE)),
        START_CHOICE,
    )
    return answer.strip() == START_CHOICE
