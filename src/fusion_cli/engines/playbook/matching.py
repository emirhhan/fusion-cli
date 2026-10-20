"""Playbook ön-koşul eşleşmesi — saf.

Bir isteğin hangi playbook'u tetiklediğini belirler. Kaba ama öngörülebilir:
istekte playbook tetikleyicilerinden herhangi biri geçiyorsa eşleşir. İlk eşleşen
playbook seçilir (kütüphane sırası önceliktir).
"""

from __future__ import annotations

import re

from .model import Playbook


def matches(playbook: Playbook, task: str) -> bool:
    """İstek metni bu playbook'un tetikleyicilerinden herhangi birini içeriyor mu."""

    tokens = set(re.split(r"[^0-9a-zçğıöşü]+", task.lower()))
    lowered = task.lower()
    return any(_trigger_hit(trigger, tokens, lowered) for trigger in playbook.triggers)


def find_match(playbooks: tuple[Playbook, ...], task: str) -> Playbook | None:
    """İsteğe uyan ilk playbook; hiçbiri uymuyorsa None."""

    return next((playbook for playbook in playbooks if matches(playbook, task)), None)


def _trigger_hit(trigger: str, tokens: set[str], lowered: str) -> bool:
    normalized = trigger.lower()
    if " " in normalized:
        return normalized in lowered
    return normalized in tokens
