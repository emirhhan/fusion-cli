"""Deterministik workflow'ların mevcut onay ve araç altyapısını kullanması."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ...core.events import ToolExecuted, ToolOutcome
from ...core.tools import ToolResult
from ...tools import ToolRegistry

if TYPE_CHECKING:  # pragma: no cover
    from ..agent.loop import AgentDeps


@dataclass(frozen=True, slots=True)
class ExecutedTool:
    name: str
    args: dict[str, object]
    result: ToolResult
    outcome: ToolOutcome


class EffectToolRunner:
    """Araçları registry + approval + event zincirinden geçirir."""

    def __init__(self, deps: "AgentDeps", registry: ToolRegistry) -> None:
        self.deps = deps
        self.registry = registry
        self.tool_calls_made = 0
        self.mutating_tool_calls_made = 0
        self.failed_tool_calls = 0

    async def execute(self, name: str, args: dict[str, object]) -> ExecutedTool:
        # Agent paketinin __init__ modülü loop.py'yi içe aktarıyor; approval'ı
        # modül yüklenirken almak effects.runner -> tool_runner -> agent -> loop
        # çevrimini oluşturur. Çalışma anındaki yerel import bu çevrimi keser.
        from ..agent.approval import Decision, build_request

        tool = self.registry.get(name)
        if tool is None:
            result = ToolResult.failure(f"'{name}' adlı araç kayıtlı değil.")
            outcome = ToolOutcome.FAILED
            self.failed_tool_calls += 1
            self._publish(name, args, result, outcome)
            return ExecutedTool(name, args, result, outcome)

        if tool.mutating:
            decision = await self.deps.policy.decide(
                build_request(tool, args, self.deps.allowed_commands)
            )
            if decision is not Decision.ALLOW:
                message = (
                    "Kullanıcı bu işlemi onaylamadı."
                    if decision is Decision.DENIED
                    else "PLAN MODU: değişiklik yapılamaz."
                )
                outcome = (
                    ToolOutcome.DENIED if decision is Decision.DENIED else ToolOutcome.BLOCKED
                )
                result = ToolResult(message, ok=False)
                self._publish(name, args, result, outcome)
                return ExecutedTool(name, args, result, outcome)

        result = await self.registry.execute(name, args, self.deps.tool_context)
        outcome = ToolOutcome.OK if result.ok else ToolOutcome.FAILED
        if outcome is ToolOutcome.OK:
            self.tool_calls_made += 1
            if tool.mutating:
                self.mutating_tool_calls_made += 1
        else:
            self.failed_tool_calls += 1
        self._publish(name, args, result, outcome)
        return ExecutedTool(name, args, result, outcome)

    def _publish(
        self,
        name: str,
        args: dict[str, object],
        result: ToolResult,
        outcome: ToolOutcome,
    ) -> None:
        self.deps.publisher.publish(
            ToolExecuted(name=name, args=args, outcome=outcome, output=result.output, diff=None)
        )
