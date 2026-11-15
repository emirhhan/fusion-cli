"""Masaüstü plan onay kartı: REPL/TUI ile aynı seçenekler ve kabul (#325).

`plan.kart`: bekleyen plan (`exit_plan_mode` ile sunulmuş) varsa kartın seçenekleri —
`cli/repl/plan_card.choices` ile aynı kaynak: otomatik kip kullanılamıyorsa "düzenlemeleri
otomatik kabul et", bypass kullanılabilir başladıysa "İZİNLERİ ATLA", Claude
`showClearContextOnPlanAccept` açıksa başta "bağlamı temizle ve …".
`plan.kabul {deger}`: seçimi uygular; kip, uygulama görevi ve bağlam temizlendiyse
`temizle: true` döner (arayüz ekranı `/clear` gibi temizler).
"""

from __future__ import annotations

from typing import Any

from ..cli.repl import plan_card
from ..cli.repl.state import ReplState

__all__ = ["plan_accept", "plan_card_payload"]


def plan_card_payload(state: ReplState) -> dict[str, Any]:
    if state.pending_plan is None:
        return {"ok": True, "bekliyor": False, "secenekler": []}
    choices = plan_card.choices(state)
    return {
        "ok": True,
        "bekliyor": True,
        "yol": str(state.pending_plan),
        "secenekler": [
            {"deger": item.value, "etiket": item.label, "aciklama": item.description}
            for item in choices
        ],
        "onerilen": choices[0].label,
    }


def plan_accept(state: ReplState, data: dict[str, Any]) -> dict[str, Any]:
    choice = data.get("deger")
    value = choice if isinstance(choice, str) else ""
    allowed = {item.value for item in plan_card.choices(state)}
    if state.pending_plan is None or value not in allowed:
        return {"ok": False, "metin": "Bekleyen plan ya da geçerli seçim yok."}
    mode = plan_card.mode_for(value)
    if mode is None:
        return {"ok": True, "kip": None, "metin": plan_card.decline(state)}
    clear = plan_card.clears_context(value)
    task = plan_card.accept(state, mode, clear=clear)
    return {"ok": True, "kip": mode.value, "gorev": task, "temizle": clear}
