"""Uzaktan onay sınıflandırması: hangi onay uzaktan verilebilir, hangisi step-up ister."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..core.tools import ToolFamily, tool_family
from .scopes import Scope

#: Uzaktan verilebilen karar kelimeleri; "session" (kalıcı genişletme) uzaktan YOK.
REMOTE_CHOICES = frozenset({"once", "deny"})


@dataclass(frozen=True, slots=True)
class ApprovalClass:
    """Bir onay isteğinin uzaktan işlenme kuralı."""

    required_scope: str
    step_up: bool
    reason: str


def classify_question(question: dict[str, Any]) -> ApprovalClass:
    """Onay sorusunun yetki gereksinimini belirle; belirsizse en sıkıya düş."""
    tool = str(question.get("arac", ""))
    if question.get("tehlike"):
        return ApprovalClass(
            Scope.PROJECT_WRITE.value, True, "Tehlikeli işlem masaüstünde onaylanır."
        )
    if "__" in tool:
        server = tool.split("__", 1)[0]
        return ApprovalClass(
            f"mcp.write.{server}", True, "Dış servis işlemi masaüstünde onaylanır."
        )
    family = tool_family(tool)
    if family is ToolFamily.DESKTOP:
        return ApprovalClass(
            Scope.DESKTOP_CONTROL.value, True, "Masaüstü kontrolü masaüstünde onaylanır."
        )
    if family in (ToolFamily.SHELL, ToolFamily.FILES, ToolFamily.VCS):
        return ApprovalClass(Scope.PROJECT_WRITE.value, False, "")
    if family in (ToolFamily.BROWSER, ToolFamily.WEB, ToolFamily.SEARCH):
        return ApprovalClass(Scope.AGENT_RUN.value, False, "")
    return ApprovalClass(
        Scope.PROJECT_WRITE.value, True, "Sınıflandırılamayan işlem masaüstünde onaylanır."
    )


def is_approval(question: dict[str, Any]) -> bool:
    return question.get("tur") == "onay"
