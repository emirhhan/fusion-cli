"""Plan kipinde izin istemi çıkaran tarayıcı eylemleri (#450).

Claude Code (`chrome` › Browser tools in plan mode): plan kipinde GIF kaydı, yeni sekme açma
ve kısayol çalıştırma öncesinde izin istemi çıkar (bunları içeren toplu çağrılar dahil);
onaylanırsa çalışır. Diğer kiplerde bu eylemlerin onay kuralı değişmez.
"""

from __future__ import annotations

from collections.abc import Mapping

#: `chrome_action` eylemleri: `record` (GIF), `open`/`window` (yeni sekme/pencere), `shortcut`.
PLAN_PROMPT_ACTIONS = frozenset({"record", "open", "new_tab", "window", "shortcut"})


def plan_prompt_call(tool_name: str, args: Mapping[str, object]) -> bool:
    """Bu çağrı plan kipinde sorulup onaylanırsa çalışmalı mı?"""
    return tool_name == "chrome_action" and args.get("action") in PLAN_PROMPT_ACTIONS
