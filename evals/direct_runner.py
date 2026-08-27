"""Single-completion baseline for the arena benchmark."""

from __future__ import annotations

import re
from pathlib import Path

from evals.agent_runner import _CountingPublisher, _NullPublisher
from evals.executor import AgentRunObservation
from evals.transcript import TranscriptRecorder
from fusion_cli.cli.session import build_request
from fusion_cli.config.models import Config
from fusion_cli.core.events import EventPublisher
from fusion_cli.core.protocols import LlmProvider
from fusion_cli.core.types import is_rate_limit_error
from fusion_cli.providers.factory import build_provider
from fusion_cli.providers.web_registry import web_registry_for

_FENCE = re.compile(r"\A```html\s*\n(?P<html>.*)\n```\s*\Z", re.DOTALL | re.IGNORECASE)


def extract_html(text: str) -> str | None:
    stripped = text.strip()
    match = _FENCE.fullmatch(stripped)
    candidate = match.group("html") if match else text
    lowered = candidate.lstrip().lower()
    if not (lowered.startswith("<!doctype html") or lowered.startswith("<html")):
        return None
    if not lowered.rstrip().endswith("</html>") or ("```" in candidate):
        return None
    return candidate


class DirectRunner:
    def __init__(self, config: Config) -> None:
        self._config = config

    async def run(
        self,
        request: str,
        *,
        root: Path,
        strict_approval: bool = False,
        transcript: Path | None = None,
    ) -> AgentRunObservation:
        del strict_approval
        recorder = TranscriptRecorder(transcript) if transcript is not None else None
        publisher = _CountingPublisher(recorder or _NullPublisher())
        provider = build_direct_provider(self._config, publisher)
        prompt = (
            f"{request}\n\nReturn exactly one complete index.html document, either as raw HTML "
            "or in one ```html fenced block. Include no commentary or additional files."
        )
        try:
            result = await provider.complete(build_request(prompt, self._config))
            if result.ok:
                html = extract_html(result.text)
                if html is not None:
                    (root / "index.html").write_text(html, encoding="utf-8")
                    output = result.text
                else:
                    output = "Direct output did not satisfy the single-document contract."
            else:
                output = result.error or result.text
        finally:
            if recorder is not None:
                recorder.close()
        limited = not result.ok and is_rate_limit_error(output)
        return AgentRunObservation(
            output_text=output,
            model_calls=publisher.model_calls,
            rate_limited=limited,
            rate_limit_detail=output if limited else "",
        )


def build_direct_provider(config: Config, publisher: EventPublisher) -> LlmProvider:
    return build_provider(
        config.agent,
        publisher=publisher,
        retry_delays_s=config.runtime.retry_delays_s,
        web_sessions=web_registry_for(config),
    )
