"""Kabuk sınırında host kit bütünlüğü; komut yazımlarını önlediği iddiası yok."""

from __future__ import annotations

from dataclasses import replace

from ..core.tools import ToolContext, ToolResult
from .remotion_contract_check import check_packaged, project_root


def remotion_integrity_error(context: ToolContext) -> str | None:
    contract = context.remotion_contract.registered
    if contract is None:
        return None
    try:
        root = project_root(context.root, contract.project_dir)
        check_packaged(root, contract)
    except (OSError, ValueError) as error:
        return f"Host Remotion kaynak bütünlüğü doğrulanamadı: {error}"
    return None


def check_shell_result(context: ToolContext, result: ToolResult) -> ToolResult:
    error = remotion_integrity_error(context)
    if error is None:
        return result
    # Gerçek exit çıktısı ve completion makbuzu değişmez; bütünlük başarı değildir.
    return replace(result, ok=False, output=f"{result.output}\n{error}")
