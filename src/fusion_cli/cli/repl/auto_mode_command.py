"""`/auto-mode` — Otomatik kip denetçisinin durumu, ayarı ve Manuel'den dönüş (P-011).

    /auto-mode [durum]          ayar, model, engel sayaçları, son kararlar
    /auto-mode devam            Manuel'e düşen oturumu Otomatik'e döndür, sayaçları sıfırla
    /auto-mode off|ask_only|on  `runtime.auto_classifier` ayarını kalıcı yaz

Masaüstü RPC'si (`oto.*`) ve `fusion auto-mode` aynı yardımcıları kullanır.
"""

from __future__ import annotations

from dataclasses import replace

from ...config.models import Config
from ...config.settings_access import write_setting
from ...core.auto_review import AutoClassifierMode
from ...core.errors import ConfigError
from ...engines.agent.approval import ApprovalMode
from ...engines.agent.risk_classifier import classifier_label
from ...ui import messages
from ...ui.auto_review_view import setting_label, status_text
from .state import ReplState

SETTING_PATH = "runtime.auto_classifier"
#: Türkçe/kısa yazımlar → ayar değeri.
SETTING_ALIASES = {
    "kapat": "off",
    "kapali": "off",
    "kapalı": "off",
    "ac": "ask_only",
    "aç": "ask_only",
    "acik": "ask_only",
    "açık": "ask_only",
    "tum": "on",
    "tüm": "on",
    "tumu": "on",
    "tümü": "on",
}
_STATUS_WORDS = frozenset({"", "durum", "status"})
_RESUME_WORDS = frozenset({"devam", "resume", "sifirla", "sıfırla"})


def parse_setting(raw: str) -> AutoClassifierMode:
    """Kullanıcının yazdığı değeri çöz; geçersizse `ValueError`."""
    text = raw.strip().lower()
    return AutoClassifierMode(SETTING_ALIASES.get(text, text))


def save_setting(config: Config, mode: AutoClassifierMode) -> tuple[Config, str]:
    """Ayarı kalıcı yaz; yazılamazsa yalnız oturuma uygula. (Güncel config, kullanıcı metni)."""
    label = setting_label(mode)
    try:
        updated, target = write_setting(config, SETTING_PATH, mode.value)
    except ConfigError as error:
        runtime = replace(config.runtime, auto_classifier=mode)
        return replace(config, runtime=runtime), messages.AUTO_REVIEW_SET_UNSAVED.format(
            setting=label, error=error
        )
    return updated, messages.AUTO_REVIEW_SET.format(setting=label, path=target)


def resume_auto(state: ReplState) -> str:
    """Manuel'e düşen oturumu Otomatik'e döndür; sayaçlar sıfırlanır."""
    state.approval_memory.auto_review.resume()
    state.approval = ApprovalMode.AUTO
    return messages.AUTO_REVIEW_RESUMED


def status(state: ReplState) -> str:
    guard = state.approval_memory.auto_review
    snapshot = guard.snapshot()
    if state.approval is ApprovalMode.AUTO and snapshot.fell_back:
        # Kullanıcı kipi kendisi Otomatik'e döndürdü; düşüş uyarısı artık geçersiz.
        guard.acknowledge_auto()
        snapshot = guard.snapshot()
    return status_text(
        snapshot, state.config.runtime.auto_classifier, classifier_label(state.config)
    )


def auto_mode_command(state: ReplState, argument: str) -> str:
    word = argument.strip().lower()
    if word in _STATUS_WORDS:
        return status(state)
    if word in _RESUME_WORDS:
        return resume_auto(state)
    try:
        mode = parse_setting(word)
    except ValueError:
        return messages.AUTO_REVIEW_USAGE
    state.config, text = save_setting(state.config, mode)
    return text
