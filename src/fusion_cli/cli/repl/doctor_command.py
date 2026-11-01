"""`/doctor [prompt-audit [path]]` işleyicisi (#212).

Claude Code'da `/doctor` kurulum denetimidir, `prompt-audit [path]` alt komutu talimatları
denetler, takma adı `/checkup`. Argümansız hâli `help_view` basar (bkz. `RENDERED_WHEN_BARE`);
argümanla bu işleyiciye düşer. Fusion'ın eski `prompt` / `talimat` adı bir sürüm boyunca
kullanımdan kalkmış takma ad olarak okunur ve oturumda bir kez uyarır.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ...ui import messages
from .state import ReplState

if TYPE_CHECKING:
    from ..doctor import DoctorReport

#: Claude Code alt komutu.
PROMPT_AUDIT = "prompt-audit"
#: Fusion'ın eski adları (kullanımdan kalktı).
LEGACY_PROMPT_NAMES = frozenset({"prompt", "talimat"})
_WARNED_ATTR = "doctor_prompt_warned"


def doctor_command(state: ReplState, argument: str) -> str:
    """Alt komutu ayır; talimat denetimini (verilen yolda) çalıştır."""
    sub, _, rest = argument.strip().partition(" ")
    sub = sub.lower()
    if sub == PROMPT_AUDIT:
        return _audit(state, rest.strip())
    if sub in LEGACY_PROMPT_NAMES:
        report = _audit(state, rest.strip())
        if getattr(state, _WARNED_ATTR, False):
            return report
        setattr(state, _WARNED_ATTR, True)
        return f"{messages.REPL_DOCTOR_PROMPT_DEPRECATED}\n{report}"
    return f"{_audit(state, '')}\n{messages.REPL_DOCTOR_SETUP_HINT}"


def _audit(state: ReplState, raw_path: str) -> str:
    from ...engines.agent.instruction_audit import audit_instructions, render_audit

    root = state.root
    if raw_path:
        target = Path(raw_path).expanduser()
        if not target.is_absolute():
            target = state.root / target
        if not target.exists():
            return messages.REPL_DOCTOR_PATH_MISSING.format(path=target)
        root = target if target.is_dir() else target.parent
    runtime = state.config.runtime
    return render_audit(
        audit_instructions(
            root,
            state.home,
            merge=getattr(runtime, "instruction_merge", True),
            max_chars=getattr(runtime, "instruction_max_chars", 32_000),
        )
    )


def fix_task(report: DoctorReport) -> str:
    """Kalan denetimlerden düzeltme turu görevi; sorun yoksa boş (#212).

    Claude Code'un `/doctor`'u paketli bir skill'dir: sorunları teşhis eder ve kullanıcı
    onaylarsa düzeltir. Görev modele önce öneri listesi sundurur, onay olmadan değişiklik
    yaptırmaz; değerler sır taşımaz (`Check.value` sözleşmesi).
    """
    failed = [check for check in report.checks if check.ok is False]
    if not failed:
        return ""
    lines = "\n".join(
        messages.REPL_DOCTOR_FIX_LINE.format(
            name=check.name, value=check.value, remedy=check.remedy or "-"
        )
        for check in failed
    )
    return messages.REPL_DOCTOR_FIX_TASK.format(issues=lines)
