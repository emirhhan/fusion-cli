"""Masaüstü `oto.*` istekleri — Otomatik kip denetçisi (P-011).

    oto.durum   ayar, model, engel sayaçları, düşüş bilgisi, son kararlar, oturum kipi
    oto.ayar    {deger: off|ask_only|on}  → `runtime.auto_classifier` kalıcı yazılır
    oto.devam   Manuel'e düşen oturumu Otomatik'e döndürür, sayaçları sıfırlar

İşlevler oturum durumunu (`ReplState`) alır; REPL `/auto-mode` ile aynı yardımcıları kullanır.
"""

from __future__ import annotations

from typing import Any

from ..cli.repl import auto_mode_command
from ..cli.repl.state import ReplState
from ..core.auto_review import (
    AUTO_REVIEW_CONSECUTIVE_LIMIT,
    AUTO_REVIEW_TOTAL_LIMIT,
)
from ..engines.agent.risk_classifier import classifier_label
from ..ui import messages
from ..ui.auto_review_view import setting_label, source_label, verdict_label
from .protocol import Request


def handle(state: ReplState, request: Request) -> dict[str, Any]:
    if request.name == "oto.durum":
        return status_payload(state)
    if request.name == "oto.ayar":
        try:
            mode = auto_mode_command.parse_setting(str(request.data.get("deger", "")))
        except ValueError:
            return {"ok": False, "metin": messages.AUTO_REVIEW_USAGE}
        state.config, text = auto_mode_command.save_setting(state.config, mode)
        return {**status_payload(state), "metin": text}
    if request.name == "oto.devam":
        text = auto_mode_command.resume_auto(state)
        return {**status_payload(state), "metin": text}
    return {"ok": False, "metin": f"Bilinmeyen istek: {request.name}"}


def status_payload(state: ReplState) -> dict[str, Any]:
    guard = state.approval_memory.auto_review
    # Kullanıcı Manuel dışında bir kip seçtiyse (Otomatik dahil) düşüş uyarısı kalkar.
    auto_mode_command.acknowledge_mode(state)
    snapshot = guard.snapshot()
    setting = state.config.runtime.auto_classifier
    return {
        "ok": True,
        "mod": state.approval.value,
        "ayar": setting.value,
        "ayar_etiketi": setting_label(setting),
        "model": classifier_label(state.config),
        "ardisik": snapshot.consecutive,
        "toplam": snapshot.total,
        "esik_ardisik": AUTO_REVIEW_CONSECUTIVE_LIMIT,
        "esik_toplam": AUTO_REVIEW_TOTAL_LIMIT,
        "dusus_sayisi": snapshot.trips,
        "dustu": snapshot.fell_back,
        "dusus_nedeni": snapshot.last_trip_reason,
        "model_erisilemiyor": guard.model_unavailable,
        "son_kararlar": [
            {
                "arac": outcome.tool,
                "karar": outcome.verdict.value,
                "karar_etiketi": verdict_label(outcome.verdict),
                "kaynak": source_label(outcome.source),
                "ozet": outcome.summary,
                "gerekce": outcome.reason,
            }
            for outcome in reversed(snapshot.recent)
        ],
    }
