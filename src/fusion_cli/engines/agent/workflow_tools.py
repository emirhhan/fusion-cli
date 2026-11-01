"""`workflow_run` aracı: modelin yazdığı ya da kayıtlı iş akışını koştur (P-062)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from ...config.paths import user_config_dir
from ...core.tools import Tool, ToolArgs, ToolContext, ToolResult
from .arg_coerce import coerce_bool
from .orchestration_runs import turn_budget_refusal
from .team import RunAgent
from .workflow_plan import bind_inputs, expand
from .workflow_runtime import check_plan, run_workflow, workflow_limits
from .workflow_spec import WorkflowError, WorkflowSpec, parse_workflow
from .workflow_store import WorkflowStore

if TYPE_CHECKING:
    from .loop import AgentDeps

#: Kullanıcı yapılandırma dizini altındaki kayıtlı iş akışları klasörü.
USER_WORKFLOWS_DIRNAME = "workflows"
#: Bu kadar ya da daha çok ajan başlatacak koşu kullanıcıya sorulur (yedek değer).
DEFAULT_CONFIRM_AGENTS = 10

START_CHOICE = "Başlat"
CANCEL_CHOICE = "Vazgeç"
CONFIRM_QUESTION = (
    "'{name}' iş akışı {count} alt ajan başlatacak (en çok {parallel} eşzamanlı). Token "
    "kullanımı tek ajana göre kat kat artabilir. Başlatılsın mı?"
)
DISABLED_MESSAGE = (
    "Dinamik iş akışları kapalı (runtime.dynamic_workflows: false); işi ayrı Agent çağrılarına böl."
)
NOT_SAVED_NOTE = (
    "\n\nTanım kaydedilmedi: koşu '{status}' bitti. Düzeltip kaydet: true ile yeniden çalıştır."
)
DECLINED_MESSAGE = "Kullanıcı iş akışını başlatmadı; ajan başlatılmadı."


def workflow_store(root: Path) -> WorkflowStore:
    """Projenin ve kullanıcının iş akışı deposu (CLI, REPL, RPC ve araç aynı yolu kullanır)."""
    return WorkflowStore(root, user_config_dir() / USER_WORKFLOWS_DIRNAME)


def workflow_run_tool(deps: AgentDeps, *, depth: int, run_agent: RunAgent) -> Tool:
    async def _run(args: ToolArgs, context: ToolContext) -> ToolResult:
        if not getattr(deps.config.runtime, "dynamic_workflows", True):
            return ToolResult.failure(DISABLED_MESSAGE)
        store = workflow_store(context.root)
        try:
            spec = _spec(args, store)
            inputs = bind_inputs(spec, _given_inputs(args.get("girdiler")))
            plan = expand(spec, inputs)
            limits = workflow_limits(deps, spec)
            count = check_plan(plan, limits)
            if (refusal := turn_budget_refusal(deps, count)) is not None:
                return ToolResult.failure(refusal)
            if not await _confirmed(deps, spec, count, limits.concurrency):
                return ToolResult.failure(DECLINED_MESSAGE)
            save = coerce_bool(args.get("kaydet", False)) is True and args.get("tanim") is not None
            if save:
                # Çakışma koşudan ÖNCE söylenir; kayıt yalnız koşu tam bitince yazılır.
                store.ensure_savable(spec, replace=False)
            result = await run_workflow(
                deps, spec, plan, inputs, depth=depth, run_agent=run_agent, store=store
            )
            saved = ""
            if save and result.status == "tamam":
                path = store.save(spec, replace=False)
                saved = f"\n\nKaydedildi: {path} (/workflows {spec.name} ile çalışır)"
            elif save:
                saved = NOT_SAVED_NOTE.format(status=result.status)
        except WorkflowError as error:
            return ToolResult.failure(str(error))
        except OSError as error:
            return ToolResult.failure(f"İş akışı kaydedilemedi: {error}")
        text = result.report + saved
        return ToolResult.failure(text) if result.status in {"iptal", "hata"} else ToolResult(text)

    return Tool(
        name="workflow_run",
        description="Çok sayıda alt ajanı bir JSON iş akışıyla yönet: 'tanim' adımları ajan "
        "(istem), paralel, sira (boru hattı, {onceki}), evre (ad + adimlar), her (liste + "
        "ajan/asamalar, {oge}); yer tutucular {girdi.X} {sonuc.ID}. Ya da kayıtlı akışı "
        "'ad' ile çalıştır. Yazmayan adıma salt_okunur:true, yazana yazma_alani ver (yoksa "
        "sırayla koşar). kaydet:true, koşu tam bitince tanımı .fusion/workflows/ altına yazar.",
        parameters={
            "type": "object",
            "properties": {
                "tanim": {"type": "object"},
                "ad": {"type": "string"},
                "girdiler": {"type": "object"},
                "kaydet": {"type": "boolean"},
            },
        },
        run=_run,
    )


def _given_inputs(raw: object) -> dict[str, object] | None:
    """`girdiler` nesne ya da (zayıf modelde) JSON metni olarak gelebilir."""
    if isinstance(raw, str) and raw.strip():
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as error:
            raise WorkflowError(f"'girdiler' geçerli JSON değil: {error.msg}.") from error
    if raw is None or raw == "":
        return None
    if not isinstance(raw, dict):
        raise WorkflowError("'girdiler' ad → değer nesnesi olmalı.")
    return {str(key): value for key, value in raw.items()}


def _spec(args: ToolArgs, store: WorkflowStore) -> WorkflowSpec:
    raw = args.get("tanim")
    if raw is not None:
        return parse_workflow(raw)
    name = args.get("ad")
    if isinstance(name, str) and name.strip():
        return store.load(name.strip())
    raise WorkflowError("'tanim' (iş akışı JSON'u) ya da kayıtlı iş akışının 'ad'ı gerekli.")


async def _confirmed(deps: AgentDeps, spec: WorkflowSpec, count: int, parallel: int) -> bool:
    """Büyük koşuda maliyet uyarısı (Claude Code 'Large workflow' uyarısının karşılığı)."""
    from .engine_tools import QuestionOption

    threshold = int(
        getattr(deps.config.runtime, "dynamic_workflow_confirm_agents", DEFAULT_CONFIRM_AGENTS)
    )
    if threshold <= 0 or count < threshold or deps.asker is None:
        return True
    answer = await deps.asker.ask(
        CONFIRM_QUESTION.format(name=spec.name, count=count, parallel=parallel),
        (QuestionOption(START_CHOICE), QuestionOption(CANCEL_CHOICE)),
        START_CHOICE,
    )
    return answer.strip() == START_CHOICE
