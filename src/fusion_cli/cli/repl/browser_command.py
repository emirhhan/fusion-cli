"""`/tarayici [ac | devral | birak | kapat]`: CLI'de ajanla paylaşılan görünür tarayıcı (P-045).

Masaüstü Tarayıcı panelinin terminal karşılığı. Terminal görüntü gösteremez; bu yüzden
paylaşılan oturum GÖRÜNÜR pencerede (`headless=False`) açılır ve turlar arasında açık kalır:
kullanıcı ajanın tıkladığını pencerede izler, girişi/CAPTCHA'yı kendisi yapar.

- `/tarayici ac`: paylaşımı aç (pencere ajanın ilk tarayıcı eyleminde açılır);
- `/tarayici devral`: ajanın tarayıcı eylemleri `/tarayici birak`a kadar bekler;
- `/tarayici kapat`: pencereyi kapat, tur başına tarayıcıya dön.

Komut işleyicileri senkrondur; kapanış `SharedBrowser.close_later` ile sahiplenilmiş görevde,
REPL çıkışında `shutdown` ile beklenir.
"""

from __future__ import annotations

from ...config.browser_profiles import browser_session_from
from ...core.browser_session import BrowserSession
from ...tools.browser_shared import SharedBrowser
from ...ui import messages
from .state import ReplState


def browser_command(state: ReplState, argument: str) -> str:
    action = argument.strip().lower()
    if action in ("", "durum"):
        return _status(state)
    if action in ("ac", "aç", "izle"):
        if state.shared_browser is None:
            state.shared_browser = SharedBrowser(lambda: _visible_session(state))
        state.shared_browser.session()
        return messages.TARAYICI_PANEL_ON
    shared = state.shared_browser
    if action in ("kapat", "close"):
        if shared is None:
            return messages.TARAYICI_PANEL_OFF
        shared.close_later()
        state.closing_browsers.append(shared)
        state.shared_browser = None
        return messages.TARAYICI_PANEL_CLOSED
    if action not in ("devral", "birak", "bırak"):
        return messages.TARAYICI_PANEL_USAGE
    if shared is None:
        return messages.TARAYICI_PANEL_NEEDS_ON
    if action == "devral":
        shared.session().take_control()
        return messages.TARAYICI_PANEL_TAKEN
    shared.session().release_control()
    return messages.TARAYICI_PANEL_RELEASED


def turn_browser(state: ReplState) -> BrowserSession:
    """Turun tarayıcısı: paylaşım açıksa ortak oturum, değilse tur başına yeni oturum."""
    if state.shared_browser is not None:
        return state.shared_browser.session()
    return browser_session_from(state.config)


def turn_origins(state: ReplState) -> set[str]:
    """Turun yerel adres izin kümesi; paylaşılan oturumda turlar AYNI kümeyi görür."""
    if state.shared_browser is not None:
        origins = state.shared_browser.session().origins
        if origins is not None:
            return origins
    return set()


async def shutdown(state: ReplState) -> None:
    """REPL kapanırken paylaşılan ve kapanmakta olan tarayıcıları kapat."""
    holders = [*state.closing_browsers, *([state.shared_browser] if state.shared_browser else [])]
    state.closing_browsers.clear()
    state.shared_browser = None
    for holder in holders:
        await holder.shutdown()


def _visible_session(state: ReplState) -> BrowserSession:
    session = browser_session_from(state.config)
    session.headless = False
    return session


def _status(state: ReplState) -> str:
    shared = state.shared_browser
    if shared is None:
        return messages.TARAYICI_PANEL_OFF
    session = shared.session()
    control = (
        messages.TARAYICI_PANEL_CONTROL_USER
        if session.user_control
        else messages.TARAYICI_PANEL_CONTROL_AGENT
    )
    profile = f" · profil: {session.active_profile}" if session.active_profile else ""
    lines = [
        messages.TARAYICI_PANEL_STATUS.format(
            state=messages.REPL_ON if session.is_open else messages.TARAYICI_PANEL_NOT_STARTED,
            control=control,
            profile=profile,
        )
    ]
    if session.is_open and session.context is not None:
        pages = [page for page in session.context.pages if not page.is_closed()]
        lines.extend(
            messages.TARAYICI_PANEL_TAB.format(
                marker="*" if page is session.page else " ", index=index, url=page.url
            )
            for index, page in enumerate(pages, start=1)
        )
    return "\n".join(lines)
