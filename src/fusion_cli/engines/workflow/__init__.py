"""Deterministik workflow motoru — opt-in, bütçe kapılı aşamalı akış.

Serbest ReAct döngüsünün (loop.py) yanına EK bir moddur; yalnızca açıkça seçilince
(config.runtime.workflow_mode) devreye girer. Mevcut döngü değişmez.
"""

from __future__ import annotations

from .engine import StageExecutor, run_workflow
from .model import (
    PIPELINE,
    Budget,
    Stage,
    StageOutcome,
    WorkflowResult,
)

__all__ = [
    "PIPELINE",
    "Budget",
    "Stage",
    "StageExecutor",
    "StageOutcome",
    "WorkflowResult",
    "run_workflow",
]
