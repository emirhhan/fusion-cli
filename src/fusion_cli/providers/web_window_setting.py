"""Kayıtlı bir web oturumunun pencere kipini değiştirmek.

Panel kipi seçer; burada yalnız yapılandırma güncellenir ve yazılır. Çalışan
Chrome'u yeniden başlatmak çağıranın işidir: kip ancak Chrome yeniden açılınca
uygulanır ve bu async bir tarayıcı işlemidir.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace as _replace

from ..config.models import Config
from ..config.writer import write_web_sessions
from ..core.errors import ConfigError
from ..core.window_mode import WindowMode
from .web_browser import normalize_account

#: Kullanıcıya görünen kip adları; paneldeki seçeneklerle aynı.
WINDOW_MODE_LABELS = {
    WindowMode.VISIBLE: "Görünür",
    WindowMode.HEADLESS: "Görünmez",
    WindowMode.HIDDEN: "Gizli",
}

INVALID_MODE_MESSAGE = "Geçersiz pencere kipi. Seçenekler: " + ", ".join(
    mode.slug for mode in WindowMode
)
NO_SESSION_MESSAGE = "Bu sağlayıcı için kayıtlı oturum yok. Önce oturum aç."


@dataclass(frozen=True, slots=True)
class WindowModeChange:
    """Kip değişikliğinin sonucu. `config` None ise hiçbir şey yazılmadı."""

    ok: bool
    message: str
    config: Config | None = None
    mode: WindowMode | None = None
    #: Kip gerçekten değişti mi? Değiştiyse çalışan Chrome yeniden başlatılmalı.
    is_changed: bool = False


def parse_window_mode(raw: object) -> WindowMode | None:
    """Panelden gelen kip metnini çöz; yalnız metin adları kabul edilir."""
    if not isinstance(raw, str):
        return None
    wanted = raw.strip().lower()
    return next((mode for mode in WindowMode if mode.slug == wanted), None)


def set_window_mode(config: Config, provider: str, account: str, raw: object) -> WindowModeChange:
    """Oturumun pencere kipini yapılandırmaya yaz."""
    mode = parse_window_mode(raw)
    if mode is None:
        return WindowModeChange(ok=False, message=INVALID_MODE_MESSAGE)
    hesap = normalize_account(account or "main")
    sessions = list(config.web_sessions)
    index = next(
        (
            position
            for position, item in enumerate(sessions)
            if item.provider == provider and normalize_account(str(item.account)) == hesap
        ),
        None,
    )
    if index is None:
        return WindowModeChange(ok=False, message=NO_SESSION_MESSAGE)
    label = WINDOW_MODE_LABELS[mode]
    if WindowMode(sessions[index].headless) is mode:
        return WindowModeChange(
            ok=True, message=f"Tarayıcı penceresi zaten: {label}.", config=config, mode=mode
        )
    sessions[index] = _replace(sessions[index], headless=mode)
    updated = _replace(config, web_sessions=tuple(sessions))
    try:
        write_web_sessions(updated)
    except (ConfigError, OSError) as error:
        return WindowModeChange(ok=False, message=f"Pencere kipi kaydedilemedi: {error}")
    return WindowModeChange(
        ok=True,
        message=f"Tarayıcı penceresi: {label}. Bir sonraki turda bu kiple açılacak.",
        config=updated,
        mode=mode,
        is_changed=True,
    )
