"""Ekip araçları: canonical `Agent`, eski `spawn_agent`/`spawn_agents` ve çağrı ayrıştırıcı.

`team.py`'den ayrıldı (dosya ≤800 satır). Çalışma zamanı adları `team` modülünden çağrı anında
okunur; testlerin `team.resolve_persona` gibi yamaları aynen etkili olur.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ...core.errors import PathAccessError
from ...core.tools import Tool, ToolArgs, ToolContext, ToolResult
from . import team as _team
from .team_policy import cap_report, team_report

if TYPE_CHECKING:
    from .loop import AgentDeps
    from .team import RunAgent, SubTask

_LOG = logging.getLogger("fusion_cli.engines.agent.team")
_STRING = {"type": "string"}


_SUBTASK_PROPERTIES: dict[str, object] = {
    "task": {**_STRING, "description": "alt ajana verilecek net, bağımsız görev"},
    "uzman": {
        **_STRING,
        "description": "ajan türü: keşif/arama için Explore (salt-okur), plan çıkarmak "
        "için Plan, genel işler için general-purpose; tanımlı diğer ajanlar find_agent ile "
        "aranabilir",
    },
    "salt_okunur": {"type": "boolean", "description": "görev dosya değiştirmeyecekse true"},
    "baglam_miras": {
        "type": "boolean",
        "description": "true ise alt ajan bu konuşmanın bağlamını devralır (fork): uzun "
        "ara görevi ana bağlamı şişirmeden yürütmek için; varsayılan temiz bağlam",
    },
    "yazma_alani": {
        "type": "array",
        "items": _STRING,
        "description": "görevin yazacağı dosya/dizinler (köke göreli); paralel koşu için gerekli",
    },
    "izolasyon": {
        **_STRING,
        "description": "'worktree' ise üye izole bir git çalışma ağacında yazar; ana proje "
        "değişmez, iş kaldıysa sonuç dal olarak kalır. Ağaç bu kökün son commit'inden "
        "açılır: commit edilmemiş değişiklikler üyeye GÖRÜNMEZ",
    },
}


def spawn_agent_tool(
    deps: AgentDeps,
    *,
    depth: int,
    run_agent: RunAgent,
    canonical: bool = False,
    legacy_name: str = "",
) -> Tool:
    """Tek bir alt görevi bir ekip üyesine devreden araç."""

    async def _run(args: ToolArgs, context: ToolContext) -> ToolResult:
        if legacy_name:
            _LOG.warning("Task eski araç adıdır; yeni çağrılarda Agent kullanın.")
        if not canonical:
            _LOG.warning("spawn_agent eski araç adıdır; yeni çağrılarda Agent kullanın.")
        subtask = _parse_subtask(args)
        if isinstance(subtask, str):
            return ToolResult.failure(subtask)
        if _team.depth_limit_reached(deps, depth):
            return ToolResult.failure(_team.DEPTH_LIMIT_MESSAGE)
        if canonical:
            from .agent_runtime_tools import launch_agent

            return await launch_agent(deps, subtask, args, depth=depth, run_agent=run_agent)
        from .agent_runtime_context import launch_denial

        denial = launch_denial(
            deps, _team.resolve_persona(deps.capabilities, subtask.persona), subtask.persona
        )
        if denial:
            return ToolResult.failure(denial)
        if _parse_true(args.get("run_in_background", args.get("arka_plan"))):
            from .agent_runtime_tools import legacy_background

            return await legacy_background(deps, subtask, depth=depth, run_agent=run_agent)
        run = await _team.run_subagent(deps, subtask, depth=depth, run_agent=run_agent)
        return ToolResult(cap_report(run.text), ok=run.ok)

    return Tool(
        name=legacy_name or ("Agent" if canonical else "spawn_agent"),
        description="Odaklı bir ALT-GÖREVİ temiz bağlamlı bir alt ajana devret; ajan işi "
        "kendi araçlarıyla yapıp sonucunu döner. Birden çok bağımsız iş varsa aynı yanıtta "
        "birden çok Agent çağrısı yap. Basit işlerde kullanma.",
        parameters=_AGENT_PARAMETERS if canonical else _LEGACY_SPAWN_PARAMETERS,
        run=_run,
    )


#: Claude Code `Agent` aracının parametreleri; eski Türkçe alanlar (`uzman`, `salt_okunur`,
#: `yazma_alani`, `baglam_miras`, `izolasyon`, `arka_plan`, `resume`) şemada yok ama gelen
#: çağrıda okunmaya devam eder.
_AGENT_PARAMETERS: dict[str, object] = {
    "type": "object",
    "properties": {
        "description": {**_STRING, "description": "Görevin kısa (3-5 sözcük) açıklaması."},
        "prompt": {**_STRING, "description": "Alt ajanın yapacağı görevin tam metni."},
        "subagent_type": {**_STRING, "description": "Kullanılacak ajan tanımının adı."},
        "model": {
            **_STRING,
            "description": "İsteğe bağlı model: sonnet, opus, haiku, inherit ya da tam kimlik.",
        },
        "name": {**_STRING, "description": "SendMessage ile ulaşmak için ajana verilen ad."},
        "isolation": {
            "type": "string",
            "enum": ["worktree"],
            "description": "worktree ise ajan geçici bir git çalışma ağacında koşar.",
        },
        "effort": {
            "type": "string",
            "enum": ["low", "medium", "high", "xhigh", "max"],
            "description": "Bu alt ajanın düşünme yoğunluğu; tanımdaki effort'u ezer.",
        },
        "run_in_background": {
            "type": "boolean",
            "description": "false ise sonuç beklenir; varsayılan arka plandır.",
        },
    },
    "required": ["prompt"],
}

_LEGACY_SPAWN_PARAMETERS: dict[str, object] = {
    "type": "object",
    "properties": {
        **_SUBTASK_PROPERTIES,
        "arka_plan": {"type": "boolean"},
        **_AGENT_PARAMETERS["properties"],  # type: ignore[dict-item]
        "resume": _STRING,
    },
    "required": ["task"],
}


def spawn_agents_tool(deps: AgentDeps, *, depth: int, run_agent: RunAgent) -> Tool:
    """Birden çok bağımsız alt görevi aynı anda koşturan araç."""

    async def _run(args: ToolArgs, context: ToolContext) -> ToolResult:
        raw = args.get("gorevler")
        if not isinstance(raw, list) or not raw:
            return ToolResult.failure("'gorevler' boş olmayan bir liste olmalı.")
        if _team.depth_limit_reached(deps, depth):
            return ToolResult.failure(_team.DEPTH_LIMIT_MESSAGE)
        subtasks: list[SubTask] = []
        for index, item in enumerate(raw):
            parsed = _parse_subtask(item if isinstance(item, dict) else {})
            if isinstance(parsed, str):
                return ToolResult.failure(f"gorevler[{index}]: {parsed}")
            subtasks.append(parsed)
        try:
            runs = await _team.run_team(deps, subtasks, depth=depth, run_agent=run_agent)
        except PathAccessError as error:
            # Geçersiz `yazma_alani` ham istisna olarak değil modelin düzeltebileceği sonuç (A4-39).
            return ToolResult.failure(f"Yazma alanı geçersiz: {error}")
        return ToolResult(team_report(runs))

    return Tool(
        name="spawn_agents",
        description="Birbirinden BAĞIMSIZ birden çok alt görevi ekip üyelerine dağıt ve AYNI "
        "ANDA koştur (ör. biri araştırırken öteki tasarlasın). Dosya yazan her görev için "
        "yazma_alani ver; alanlar ayrıksa paralel, belirsizse sırayla koşar. Sonuçlar "
        "görev sırasıyla döner.",
        parameters={
            "type": "object",
            "properties": {
                "gorevler": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": _SUBTASK_PROPERTIES,
                        "required": ["task"],
                    },
                }
            },
            "required": ["gorevler"],
        },
        run=_run,
    )


_FALSE_WORDS = frozenset({"false", "no", "hayır", "hayir", "0", "off", ""})


def _parse_read_only(value: object) -> bool:
    """`salt_okunur` değerini AÇIK-GÜVENLİ oku: belirsizse salt-okuma say.

    Ölçüldü (29 Ekim): `is True` katı karşılaştırması `"true"`, `1`, `"evet"` gibi zayıf
    model çıktılarını `False` sayıp görevi YAZMA YETKİLİ yapıyordu (A4-09). Alan hiç
    verilmediyse varsayılan (yazma yetkili) korunur; açıkça yanlış denmediyse kısıtlanır.
    """
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().casefold() not in _FALSE_WORDS
    return True


def _parse_subtask(args: ToolArgs) -> SubTask | str:
    task = args.get("prompt", args.get("task"))
    if not isinstance(task, str) or not task.strip():
        return "'task' alanı boş olmayan bir metin olmalı."
    persona = args.get("subagent_type", args.get("uzman", ""))
    scope = args.get("yazma_alani", ())
    if not isinstance(scope, (list, tuple)) or not all(isinstance(item, str) for item in scope):
        return "'yazma_alani' metin listesi olmalı."
    isolation = args.get("isolation", args.get("izolasyon", ""))
    if isolation and isolation != "worktree":
        return "'izolasyon' yalnız 'worktree' olabilir."
    return _team.SubTask(
        task=task.strip(),
        model=str(args.get("model") or ""),
        name=str(args.get("name") or ""),
        resume=str(args.get("resume") or ""),
        effort=str(args.get("effort") or "").strip().lower(),
        persona=persona if isinstance(persona, str) else "",
        read_only=_parse_read_only(args.get("salt_okunur")),
        write_scope=tuple(item.strip() for item in scope if item.strip()),
        inherit_context=persona == "fork" or _parse_true(args.get("baglam_miras")),
        isolation=str(isolation or ""),
    )


_TRUE_WORDS = frozenset({"true", "evet", "1", "yes", "on"})


def _parse_true(value: object) -> bool:
    """`baglam_miras` KAPALI-GÜVENLİ okunur: yalnız açık doğru değer fork açar."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value == 1
    return isinstance(value, str) and value.strip().casefold() in _TRUE_WORDS
