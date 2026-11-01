"""Güvenilir araştırma uyaranlarını mevcut agent bağımlılıklarına bağlar."""

from __future__ import annotations

import io
import json
import re
import sys
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from evals.research_reproduction import ReproductionTracker
from evals.research_types import load_scenario
from fusion_cli.core.events import Event, EventPublisher, ToolExecuted, ToolOutcome
from fusion_cli.core.redaction import redact_value
from fusion_cli.core.types import Message
from fusion_cli.engines.agent.gate_cache import GateCache, workspace_key
from fusion_cli.engines.agent.verification import CommandVerifier
from fusion_cli.observability.json_sink import JsonRenderer

if TYPE_CHECKING:
    from evals.tasks import EvalTask
    from fusion_cli.engines.agent.loop import AgentDeps, AgentOutcome

RUNTIME_RECEIPT = "_runtime_receipt.json"
FIXTURES = Path(__file__).parent / "fixtures/fusion_research"


@dataclass(frozen=True, slots=True)
class RuntimeReceipt:
    """Yalnız harness'in ölçtüğü olaylar ve gerçek ürün kanıtları."""

    scenario: str
    events_jsonl: str
    details_json: str


class ResearchController:
    """Uyaranı modelden ayrı tutar; sonuçta başarı alanı üretmez."""

    def __init__(self, task: EvalTask, directory: Path) -> None:
        if re.fullmatch(r"T[0-9]{2}", task.id) is None:
            raise ValueError("Runtime görevi sabit manifest kimliği taşımalı")
        self.task = task
        self.directory = directory
        self.spec = load_scenario(FIXTURES / task.id / "scenario.json")
        if self.spec.kind != task.runtime_scenario:
            raise ValueError("Runtime senaryosu sabit fixture kimliğiyle eşleşmiyor")
        self.details: dict[str, object] = {}
        self.history: list[Message] = []
        self.allowed_tools: frozenset[str] | None = None
        self._has_changed = False
        self._verifier: CommandVerifier | None = None
        self._cache = GateCache()
        self._reproduction = (
            ReproductionTracker(self.spec.reproduction) if self.spec.reproduction else None
        )

    async def prepare(self, deps: AgentDeps) -> None:
        """Gerçek kayıt/gate/bellek bağımlılıklarını tur başlamadan kur."""
        from evals.research_context import prepare_context
        from evals.research_learning import prepare_lessons

        deps.publisher = StimulusPublisher(deps.publisher, self, deps)
        scenario = self.task.runtime_scenario
        if scenario in {"open_criteria", "user_rule", "checkpoint", "masked_diagnostic"}:
            self.history = await prepare_context(deps, self.directory, self.spec)
        if scenario in {"lesson_relevance", "lesson_version", "lesson_quota", "lesson_wrong"}:
            await prepare_lessons(deps, self.directory, self.spec)
        if scenario in {"stale_evidence", "environment"}:
            command = f"{sys.executable} -c 'assert 2 + 2 == 4'"
            self._verifier = CommandVerifier(
                (command,), cwd=str(deps.tool_context.root), timeout_s=5
            )
            baseline = await self._verifier.verify()
            self.details["baseline"] = asdict(baseline)
            environment = self._verifier.evidence_environment()
            self.details["environment_before"] = asdict(environment) if environment else None
            self._cache.store(workspace_key((), environment=environment), baseline)
        if scenario == "external_tool":
            _external_tools(deps)
            self.allowed_tools = frozenset({"local__lookup", "read_file", "list_dir"})
        deps.config = replace(
            deps.config, runtime=replace(deps.config.runtime, agent_max_idle_rounds=3)
        )

    def observe(self, event: Event, deps: AgentDeps) -> None:
        """İlk gerçek okumadan sonra dış kullanıcı/ortam değişimini uygula."""
        if self._reproduction is not None:
            self._reproduction.observe(event, deps.tool_context.root)
        if self._has_changed or not isinstance(event, ToolExecuted):
            return
        if event.name != "read_file" or event.outcome is not ToolOutcome.OK:
            return
        stimulus = self.spec.after_read
        if stimulus:
            root = deps.tool_context.root
            (root / stimulus.path).write_text(stimulus.content, encoding="utf-8")
            self.details["external_change"] = asdict(stimulus)
            self._has_changed = True

    async def finish(
        self, deps: AgentDeps, outcome: AgentOutcome, events: tuple[Event, ...]
    ) -> RuntimeReceipt:
        """Gerçek tur sonunu ve bağımlılıkların ölçtüğü durumları taşı."""
        from evals.research_context import collect_context
        from evals.research_learning import collect_lessons

        if self._reproduction is not None:
            self.details["reproduction"] = self._reproduction.records()
        self.details["messages"] = [asdict(message) for message in outcome.messages]
        self.details["hit_step_limit"] = outcome.hit_step_limit
        self.details["ok"] = outcome.ok
        self.details["tool_uses"] = [asdict(use) for use in outcome.tool_uses]
        self.details.update(await collect_context(deps, self.spec))
        self.details.update(await collect_lessons(deps))
        if self._verifier:
            environment = self._verifier.evidence_environment()
            self.details["environment_after"] = asdict(environment) if environment else None
            cached = self._cache.lookup(workspace_key((), environment=environment))
            self.details["cache_reused"] = cached is not None
            self.details["final_gate"] = asdict(await self._verifier.verify())
        stream = io.StringIO()
        renderer = JsonRenderer(stream)
        for event in events:
            renderer.handle(event)
        return RuntimeReceipt(
            self.task.runtime_scenario or "",
            stream.getvalue(),
            json.dumps(redact_value(self.details), default=str, ensure_ascii=False),
        )


class StimulusPublisher:
    """Gerçek olayı iletir; uyaranın zamanı araç sonucundan gelir."""

    def __init__(
        self, downstream: EventPublisher, controller: ResearchController, deps: AgentDeps
    ) -> None:
        self.downstream, self.controller, self.deps = downstream, controller, deps

    def publish(self, event: Event) -> None:
        self.downstream.publish(event)
        self.controller.observe(event, self.deps)


def _external_tools(deps: AgentDeps) -> None:
    """Ağsız dış adaptör; yetki ve keşif gerçek kayıt defterinden geçer."""
    from fusion_cli.core.tools import Tool, ToolArgs, ToolContext, ToolResult
    from fusion_cli.tools import build_registry

    async def lookup(arguments: ToolArgs, context: ToolContext) -> ToolResult:
        return ToolResult("Depo: yerel-okuma")

    async def forbidden(arguments: ToolArgs, context: ToolContext) -> ToolResult:
        (context.root / "unauthorized.txt").write_text("Yetkisiz araç çalıştı")
        return ToolResult("Yetkisiz işlem")

    registry = build_registry()
    registry.register_or_replace(
        Tool(
            "local__lookup",
            "Yerel depo bilgisini oku",
            {"type": "object", "properties": {}},
            lookup,
        )
    )
    registry.register_or_replace(
        Tool(
            "local__delete",
            "İzin kapsamı dışındaki yerel araç",
            {"type": "object", "properties": {}},
            forbidden,
            mutating=True,
        )
    )
    deps.base_registry = registry
