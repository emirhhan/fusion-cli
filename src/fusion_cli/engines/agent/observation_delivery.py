"""Trusted desktop observations are activity, not implicit user deliverables."""

from __future__ import annotations

import re
from pathlib import Path

from ...core.desktop_frame import BackgroundCapture
from ...core.desktop_ref_handles import context_scope
from ...core.tools import ToolContext

_VISUAL_OUTPUT = re.compile(
    r"screenshot|screen[\s-]*(?:shot|capture)|ekran\s*g[öo]r[üu]nt|ekran\s*resm|"
    r"capture|snapshot|g[öo]rsel|resim|image|picture|photo|foto[ğg]raf|\bpng\b",
    re.IGNORECASE,
)


def internal_observation_paths(
    context: ToolContext, *, task: str | None = None, turn_id: str | None = None
) -> tuple[Path, ...]:
    """One delivery projection; never remove raw changes, undo or grounding evidence."""
    from .output_verify import requested_outputs_in

    if task is None:
        contract = context.delivery_contract.for_owner(context.root, context.job_scope)
        if contract is None:
            return ()  # No accepted user intent: conservatively keep normal artifact checks.
        task = contract.task
    paths = context.desktop.observation_artifact_paths(
        context.desktop.observation_turn_id if turn_id is None else turn_id,
        background_root=context.root,
        background_scope=context_scope(context),
    )
    if requested_outputs_in(task) or _VISUAL_OUTPUT.search(task):
        receipt = context.desktop.background_capture
        return tuple(
            path
            for path in paths
            if isinstance(receipt, BackgroundCapture) and receipt.path == path
        )
    return paths


def delivery_change_paths(context: ToolContext) -> tuple[Path, ...]:
    internal = frozenset(internal_observation_paths(context))
    return tuple(path for path in context.changes.paths if path not in internal)
