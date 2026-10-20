"""Prompt varyantı veri modeli."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PromptVariant:
    """Sürümlenmiş bir prompt metni.

    `name` optimize edilen promptu tanımlar (ör. "planner"); `version` yayım sırasını
    (1'den artan) taşır; `text` promptun kendisidir.
    """

    name: str
    text: str
    version: int = 0
