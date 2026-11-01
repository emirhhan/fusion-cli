"""İlk yüklenen talimatı ve gerçek gönderim sonucunu içeriksiz ölç."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from ...core.events import EventPublisher, PromptManifestRecorded
from ...core.prompt_manifest import InstructionMeasurement, PromptManifest
from ...core.redaction import redact
from ...core.types import CompletionRequest, ModelResult
from .instruction_layers import InstructionLoad


@dataclass(frozen=True, slots=True)
class PromptComponents:
    """İlk yüklemeden gelen altkırılımlar; ölçmek için dosya yeniden açılmaz."""

    instructions: InstructionLoad = field(default_factory=lambda: InstructionLoad(""))
    repo_map: str = ""
    skill: str = ""


def publish_manifest(
    request: CompletionRequest,
    result: ModelResult,
    components: PromptComponents,
    publisher: EventPublisher,
    *,
    profile: str | None = None,
) -> None:
    """Modelin görmediği olayda, gerçekten gönderilmiş isteği ölç."""
    system = sum(len(message.content) for message in request.messages if message.role == "system")
    history = sum(
        len(message.content) + sum(len(call.arguments) for call in message.tool_calls)
        for message in request.messages
        if message.role != "system"
    )
    tools = len(json.dumps(request.tools, ensure_ascii=False)) if request.tools else 0
    system_text = "\n".join(
        message.content for message in request.messages if message.role == "system"
    )
    instructions = components.instructions
    manifest = PromptManifest(
        system,
        history,
        tools,
        system + history + tools,
        len(components.repo_map) if components.repo_map in system_text else 0,
        len(components.skill) if components.skill in system_text else 0,
        tuple(
            InstructionMeasurement(redact(item.label), item.layer, item.chars, item.trimmed)
            for item in instructions.files
        ),
        instructions.trimmed_chars,
        tuple(redact(note) for note in instructions.notes),
        result.prompt_measurement,
        redact(result.model),
        redact(profile) if profile else None,
        not result.usage.prompt_measured,
        result.usage.prompt_tokens,
    )
    publisher.publish(PromptManifestRecorded(manifest))
