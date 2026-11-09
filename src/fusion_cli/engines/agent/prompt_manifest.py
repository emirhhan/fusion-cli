"""İlk yüklenen talimatı ve gerçek gönderim sonucunu içeriksiz ölç."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from ...core.events import EventPublisher, PromptManifestRecorded
from ...core.prompt_manifest import ComponentLocation, InstructionMeasurement, PromptManifest
from ...core.redaction import redact
from ...core.types import CompletionRequest, ModelResult
from .instruction_layers import InstructionLoad


@dataclass(frozen=True, slots=True)
class PromptComponents:
    """İlk yüklemeden gelen altkırılımlar; ölçmek için dosya yeniden açılmaz."""

    instructions: InstructionLoad = field(default_factory=lambda: InstructionLoad(""))
    repo_map: str = ""
    skill: str = ""


def _location(request: CompletionRequest, text: str) -> ComponentLocation:
    """Count only complete components present in an actual message, never joined fragments."""
    layers = {
        "system" if message.role == "system" else "history"
        for message in request.messages
        if text and text in message.content
    }
    if len(layers) == 2:
        return "mixed"
    if "system" in layers:
        return "system"
    return "history" if layers else "absent"


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
    instructions = components.instructions
    instruction_location = _location(request, instructions.text)
    map_location = _location(request, components.repo_map)
    skill_location = _location(request, components.skill)
    present_locations = {
        location
        for location in (instruction_location, map_location, skill_location)
        if location != "absent"
    }
    manifest = PromptManifest(
        system,
        history,
        tools,
        system + history + tools,
        len(components.repo_map) if map_location != "absent" else 0,
        len(components.skill) if skill_location != "absent" else 0,
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
        subcomponents_in_system=present_locations == {"system"},
        measurement_version=2,
        instructions_location=instruction_location,
        repo_map_location=map_location,
        skill_location=skill_location,
    )
    publisher.publish(PromptManifestRecorded(manifest))
