"""Etkileşimli oturumun (`fusion` kök komutu) izin bayrakları (#49, #73).

Claude Code'da `claude --permission-mode plan`, `claude --dangerously-skip-permissions` ve
`claude --allow-dangerously-skip-permissions` etkileşimli oturumu da başlatır. Kök komut
bayrakları burada süreç boyunca saklanır; REPL başlangıç kipi ve Shift+Tab döngüsü buradan
okur (`cli/repl/state.py`). Değer değiştirilmez, yerine yenisi konur.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..engines.agent.approval import ApprovalMode
from .permission_flags import resolve_start_mode


@dataclass(frozen=True, slots=True)
class LaunchPermissions:
    """Kök komutta verilen izin bayrakları."""

    #: `--permission-mode`/`--dangerously-skip-permissions` ile seçilen kip; yoksa `None`.
    mode: ApprovalMode | None = None
    #: `--allow-dangerously-skip-permissions`: bypass döngüye eklenir, oturum onunla başlamaz.
    allow_bypass: bool = False


_CURRENT = LaunchPermissions()


def set_launch_permissions(
    *, flag: str | None, skip_permissions: bool, allow_bypass: bool, root: Path
) -> LaunchPermissions:
    """Bayrakları çöz ve sakla; geçersiz kip adı `ValueError`."""
    global _CURRENT
    mode = None
    if flag or skip_permissions:
        mode = resolve_start_mode(
            flag=flag, legacy=None, skip_permissions=skip_permissions, root=root, headless=False
        )
    _CURRENT = LaunchPermissions(mode, allow_bypass or skip_permissions)
    return _CURRENT


def launch_permissions() -> LaunchPermissions:
    return _CURRENT


def reset_launch_permissions() -> None:
    """Testler ve yeniden başlatma için varsayılana dön."""
    global _CURRENT
    _CURRENT = LaunchPermissions()
