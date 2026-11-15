"""`sandbox.excludedCommands` eşleşmesi Claude'un Bash kural söz dizimiyle (#367).

Claude Code (sandboxing, excludedCommands): desenler `Bash(...)` kural söz dizimindedir;
sondaki ` *` argümanlı ve argümansız biçimi birlikte eşler (`docker *` → `docker`,
`docker ps`). Zincirlenmiş çağrıda (`&&`, `|`, `;`) HER komut bir desene uyarsa çağrı
sandbox dışında çalışır; biri uymazsa çağrı sandbox'ta kalır. `unshare` ile başlayan
komut hangi desen yazılırsa yazılsın sandbox'ta kalır (her programı başlatabilir).

Kullanımdan kalkan Fusion yazımı: yıldızsız düz önek (`docker`, `git push`) bir sürüm
boyunca `docker *` gibi okunur ve bir kez uyarılır.
"""

from __future__ import annotations

import logging
from pathlib import Path

from ..config.permission_rules import PermissionDecision, PermissionRule, PermissionRuleSet
from .permission_match import evaluate, shell_segments

__all__ = ["is_excluded"]

_LOG = logging.getLogger(__name__)
_WARNED: set[str] = set()


def _pattern(raw: str) -> str:
    text = raw.strip()
    if text.startswith("Bash(") and text.endswith(")"):
        return text[len("Bash(") : -1].strip()
    if "*" not in text and ":" not in text:
        if text not in _WARNED:
            _WARNED.add(text)
            _LOG.warning(
                "sandbox.excludedCommands: %r yıldızsız önek kullanımdan kalkıyor; "
                "Claude Code yazımı %r",
                text,
                f"{text} *",
            )
        return f"{text} *"
    return text


def is_excluded(command: str, patterns: tuple[str, ...], root: Path | None = None) -> bool:
    """Zincirin her komutu bir `excludedCommands` desenine uyuyor mu?"""
    if not patterns or not command.strip():
        return False
    if any(segment.split()[:1] == ["unshare"] for segment in shell_segments(command)):
        return False
    rules = PermissionRuleSet(
        tuple(
            PermissionRule("Bash", _pattern(raw), PermissionDecision.ALLOW)
            for raw in patterns
            if raw.strip()
        )
    )
    match = evaluate(rules, "run_shell", {"command": command}, root)
    return match is not None and match.decision is PermissionDecision.ALLOW
