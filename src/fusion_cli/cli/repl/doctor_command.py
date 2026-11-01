"""`/doctor [prompt-audit [path]]` işleyicisi (#212).

Claude Code'da `/doctor` kurulum denetimidir, `prompt-audit [path]` alt komutu talimatları
denetler, takma adı `/checkup`. Argümansız hâli `help_view` basar (bkz. `RENDERED_WHEN_BARE`);
argümanla bu işleyiciye düşer. Fusion'ın eski `prompt` / `talimat` adı bir sürüm boyunca
kullanımdan kalkmış takma ad olarak okunur ve oturumda bir kez uyarır.
"""

from __future__ import annotations

from pathlib import Path

from ...ui import messages
from .state import ReplState

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
