"""Bir agent turunun sonucunu takip önerilerinin kanıtına çevirir.

Ayrı bir modül çünkü `core/followups.py` saf kalmalı: `core` katmanı
`engines`'e bakamaz (RULES.md "Katman Sınırları"). Dönüştürme burada, kural
orada durur; böylece kural CLI, masaüstü ve testlerde aynı girdiyle çalışır.
"""

from __future__ import annotations

from ...core.followups import TurnEvidence
from ...core.tools import ToolContext

__all__ = ["evidence_from_turn"]


def evidence_from_turn(
    outcome: object,
    tool_context: ToolContext,
    *,
    verification_command: str = "",
    verification_failed: bool = False,
) -> TurnEvidence:
    """Tur sonucundan öneri kanıtı üret.

    `outcome` bilinçli olarak gevşek yazılmıştır: `AgentOutcome` bu modülü
    import eden `loop.py`'de tanımlı ve ters import döngüsü doğar. Okunan
    alanlar sayaçlardır, hepsi `getattr` ile güvenli alınır.
    """
    # Yollar rozete yazılacak; dosya adı son parçadan okunuyor, metin yeter.
    degisenler = tuple(sorted(str(yol) for yol in tool_context.changes.paths))
    basarisiz = tuple(
        dict.fromkeys(
            kullanim.name
            for kullanim in getattr(outcome, "tool_uses", ())
            if not getattr(kullanim, "ok", True)
        )
    )
    return TurnEvidence(
        changed_files=degisenler,
        failed_tools=basarisiz,
        hit_limit=bool(getattr(outcome, "hit_step_limit", False))
        or bool(getattr(outcome, "budget_stopped", False)),
        wrong_workspace=bool(getattr(outcome, "wrong_workspace", False)),
        made_no_changes=bool(getattr(outcome, "made_no_changes", False)),
        ok=bool(getattr(outcome, "ok", True)),
        verification_failed=verification_failed,
        verification_command=verification_command,
        used_tools=tuple(
            dict.fromkeys(kullanim.name for kullanim in getattr(outcome, "tool_uses", ()))
        ),
    )
