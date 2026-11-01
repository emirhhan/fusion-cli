"""Çalışma dizinleri dışından okumanın onay alanları (#56; `tools.outside_reads`)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from ...tools.outside_reads import OUTSIDE_READ_REASON, outside_read_target

if TYPE_CHECKING:
    from .approval import ApprovalRequest


def mark_outside_read(
    request: ApprovalRequest, root: Path | None, roots: tuple[Path, ...], *, blocked: bool = False
) -> ApprovalRequest:
    """Dışarıyı okuyan çağrı: auto sormaz (`risk` boş), acceptEdits ve Manuel sorar.

    Oturum izni hedefin dizinine bağlanır (`outside_dir`): `~/a` okuma izni `~/.ssh`'ı
    kapsamaz.
    """
    target = outside_read_target(request.tool.name, request.args, root, roots)
    if target is None or request.pre_denied is not None:
        return request
    reason = OUTSIDE_READ_REASON.format(yol=target)
    if blocked:
        # `blockReadsOutsideWorkingDirectories` (#76): sormak anlamsız, araç da reddeder.
        return replace(request, pre_denied=f"{reason}; kök dışı okuma kapalı")
    return replace(
        request,
        read_only=False,
        unattended_safe=False,
        note=request.note or reason,
        outside_dir=str(Path(target).parent),
    )
