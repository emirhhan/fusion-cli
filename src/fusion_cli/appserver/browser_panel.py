"""Masaüstü Tarayıcı paneli (P-045): `tarayici_panel.*` RPC'leri ve paylaşılan tarayıcı.

Ölçüldü (31 Ekim): uygulama içinde tarayıcı yoktu; ajanın `browser_*` eylemleri görünmez bir
Chromium'da tur sonunda kayboluyor, kullanıcı ne olduğunu göremiyor ve girişi kendisi yapıp
devredemiyordu. Panel ajanla AYNI tarayıcıyı gösterir (`browser.panel_agent`):

- görüntü CDP ekran yayınıdır, panel `tarayici_panel.kare` ile çeker (bkz. `browser_live`);
- sekmeler, adres, geri/ileri/yenile, tıklama/kaydırma/yazma kullanıcıdan gelir;
- tur sürerken kullanıcının tıklaması/yazması/gezinmesi denetimi kendiliğinden devralır;
  ajanın tarayıcı aracı "Ajana bırak" denene kadar bekler (`browser_shared.control_gate`).
  İzlemek için kaydırmak devralmaz; kendiliğinden devralınan denetim tur bitince ajana döner
  (açık "Devral" kullanıcıda kalır). Ölçüldü (31 Ekim, inceleme): tekerlek bile denetimi
  alıyor, denetim tur sonrasına taşınıp sonraki turu 300 sn bekletiyordu;
- profil seçimi: temiz oturum (varsayılan), "Panel oturumu" (çerezler çıkışta saklanır —
  Claude Code "Keep cookies") ya da `fusion browser` profilleri. Kullanıcının yüklediği
  girişli oturumu ajan yalnız "Ajan bu oturumu kullanabilir" açıkken görür; yoksa tur kendi
  temiz tarayıcısını açar.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from ..config.browser_profiles import BrowserProfileStore, default_browser_profile_store
from ..config.models import Config
from ..core.browser_session import BrowserSession
from ..tools import browser_picker
from ..tools.browser import start_lock, start_session
from ..tools.browser_live import LiveInputError, LiveView
from ..tools.browser_shared import SharedBrowser
from .browser_panel_payloads import (
    PANEL_PROFILE,
    element_payload,
    ensure_panel_profile,
    snapshot_payload,
)
from .preview_rpc import log_payload

_logger = logging.getLogger(__name__)

RPC_PREFIX = "tarayici_panel."
#: Panel ayarları (`tarayici_panel.ayar`).
SETTING_AGENT = "ajan_paylasir"
SETTING_CONSENT = "profil_onayi"

_PROFILE_BUSY = "Ajan turu bu tarayıcıyı kullanırken profil değiştirilemez; tur bitince dene."
_UNKNOWN = "Bilinmeyen tarayıcı paneli isteği: {name}"

Handler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


def _ok(**fields: object) -> dict[str, Any]:
    return {"ok": True, **fields}


def _error(message: str) -> dict[str, Any]:
    return {"ok": False, "metin": message}


class BrowserPanel:
    """Bir masaüstü oturumunun tarayıcı paneli; paylaşılan oturumun sahibi."""

    def __init__(
        self,
        *,
        config: Callable[[], Config],
        root: Callable[[], Path],
        turn_running: Callable[[], bool],
        store: Callable[[], BrowserProfileStore] = default_browser_profile_store,
        save_agent_share: Callable[[bool], Awaitable[str]] | None = None,
    ) -> None:
        self._config = config
        self._root = root
        self._turn_running = turn_running
        self._store = store
        #: "Ajan bu tarayıcıyı kullanır" seçimini `browser.panel_agent`'a yazar (hata metni ya
        #: da ""). Ölçüldü (31 Ekim, inceleme): seçim yalnız oturumda tutuluyor, uygulama yeniden
        #: açılınca sıfırlanıyordu. Verilmezse (testler, CLI) seçim oturum içinde kalır.
        self._save_agent_share = save_agent_share
        self._shared = SharedBrowser(self._new_session)
        self._live: LiveView | None = None
        #: Panelden verilen oturum içi seçim; None ise `browser.panel_agent` geçerlidir.
        self._agent_choice: bool | None = None
        #: Kullanıcının panelde yüklediği girişli oturum ve ajanın onu kullanma izni.
        self._user_profile = ""
        self.profile_consent = False
        #: Denetim tur sürerken girdiyle KENDİLİĞİNDEN mi alındı? (tur bitince geri verilir)
        self._auto_control = False
        self._handlers: dict[str, Handler] = {
            "durum": self._status,
            "ac": self._open,
            "kapat": self._close_browser,
            "kare": self._frame,
            "git": self._input(lambda live, data: live.navigate(data.get("url"))),
            "geri": self._input(lambda live, _data: live.history("geri")),
            "ileri": self._input(lambda live, _data: live.history("ileri")),
            "yenile": self._input(lambda live, _data: live.history("yenile")),
            "sekme_ac": self._input(lambda live, data: live.new_tab(data.get("url"))),
            "sekme_sec": self._input(lambda live, data: live.select_tab(data.get("no"))),
            "sekme_kapat": self._input(lambda live, data: live.close_tab(data.get("no"))),
            "tikla": self._input(self._click),
            "kaydir": self._view(
                lambda live, data: live.scroll(
                    data.get("x"), data.get("y"), data.get("dx", 0), data.get("dy", 0)
                )
            ),
            "yaz": self._input(lambda live, data: live.type_text(data.get("metin"))),
            "tus": self._input(lambda live, data: live.press(data.get("tus"))),
            "boyut": self._view(
                lambda live, data: live.resize(
                    data.get("genislik"), data.get("yukseklik"), data.get("tema")
                )
            ),
            "devral": self._take,
            "birak": self._release,
            "oge": self._hover,
            "oge_sec": self._pick,
            "ekran": self._screenshot,
            "konsol": self._console,
            "ayar": self._setting,
            "profil": self._profile,
        }

    # ------------------------------------------------------------------ oturum
    def _new_session(self) -> BrowserSession:
        browser = self._config().browser
        # Panel görüntüyü kendisi gösterir: pencere hep başsızdır (headless ayarı tur
        # başına tarayıcı içindir). Varsayılan profil ajanın onayıyla yüklenir (REMOTE_SESSION).
        return BrowserSession(
            profile_name=browser.default_profile,
            headless=True,
            profiles_enabled=browser.profiles_enabled,
        )

    @property
    def agent_shares(self) -> bool:
        if self._agent_choice is not None:
            return self._agent_choice
        return self._config().browser.panel_agent

    @property
    def agent_sees(self) -> bool:
        """Ajan paneli paylaşıyor mu? Kullanıcının girişli oturumu yalnız onayla paylaşılır."""
        return self.agent_shares and not (self._user_profile and not self.profile_consent)

    def turn_browser(self) -> BrowserSession | None:
        """Ajan turunun tarayıcısı: paylaşılan oturum ya da None (tur kendi tarayıcısını açar)."""
        return self._shared.session() if self.agent_sees else None

    def _agent_busy(self) -> bool:
        """Ajan turu şu an paneldeki tarayıcıyı kullanıyor mu?"""
        return self._turn_running() and self.agent_sees

    async def close(self) -> None:
        """Masaüstü oturumu kapanırken: yayını bırak, tarayıcıyı kapat (çerezler yazılır)."""
        if self._live is not None:
            await self._live.detach()
        self._live = None
        await self._shared.close()
        self._user_profile = ""

    async def handle(self, name: str, data: dict[str, Any]) -> dict[str, Any]:
        handler = self._handlers.get(name.removeprefix(RPC_PREFIX))
        if handler is None:
            return _error(_UNKNOWN.format(name=name))
        try:
            return await handler(data)
        except LiveInputError as error:
            return _error(str(error))
        except Exception as error:
            # RPC sınırı: Playwright'ın gezinme/zaman aşımı/kapanmış sayfa hataları tek tip
            # değildir (`playwright` burada zorunlu bağımlılık değil); panel çökmez, sebep söylenir.
            _logger.warning("Tarayıcı paneli isteği başarısız: %s (%s)", name, type(error).__name__)
            first = str(error).splitlines()[0] if str(error) else type(error).__name__
            return _error(f"Tarayıcı eylemi yapılamadı: {first[:300]}")

    def _view_of(self, session: BrowserSession) -> LiveView:
        if self._live is None or self._live.session is not session:
            self._live = LiveView(session)
        return self._live

    def _state(self) -> dict[str, Any]:
        session = self._shared.current
        is_open = session is not None and session.is_open
        return {
            "acik": is_open,
            "profil": session.active_profile if is_open and session is not None else "",
            "kullanici_profili": self._user_profile,
            "denetim": "kullanici" if session is not None and session.user_control else "ajan",
            "ajan_bekliyor": session is not None and session.agent_waiting,
            SETTING_AGENT: self.agent_shares,
            SETTING_CONSENT: self.profile_consent,
            "ajan_goruyor": self.agent_sees,
            "tur_suruyor": self._turn_running(),
        }

    async def _status(self, _data: dict[str, Any]) -> dict[str, Any]:
        store = self._store()
        names: list[str] = []
        if store.available:
            names = [summary.name for summary in await asyncio.to_thread(store.list)]
        return _ok(**self._state(), profiller=names, panel_profili=PANEL_PROFILE)

    async def _ensure_open(self, profile: str = "") -> tuple[BrowserSession | None, str]:
        session = self._shared.session()
        async with start_lock(session):
            if session.is_open:
                return session, ""
            page, error = await start_session(
                session,
                session.origins if session.origins is not None else set(),
                profile=profile,
                store=self._store(),
            )
        if page is None:
            return None, error
        # Konsol/ağ toplayıcısı ilk gezinmeden ÖNCE bağlanır: yükleme anındaki hatalar kaçmaz.
        self._view_of(session).watch_context(session.context)
        return session, ""

    async def _open(self, data: dict[str, Any]) -> dict[str, Any]:
        if not self._shared.session().is_open:
            # Kullanıcının açtığı panel temizdir: varsayılan profil (girişli oturum) yalnız
            # ajan isteyince ve onayla yüklenir; yoksa ajan onaysız girişli sayfa görürdü.
            self._shared.session().profile_name = ""
        session, error = await self._ensure_open()
        if session is None:
            return _error(error)
        url = data.get("url")
        if isinstance(url, str) and url.strip():
            await self._view_of(session).navigate(url)
        return _ok(**self._state())

    async def _close_browser(self, _data: dict[str, Any]) -> dict[str, Any]:
        if self._agent_busy():
            return _error("Ajan turu bu tarayıcıyı kullanıyor; tur bitince kapat.")
        session = self._shared.current
        if self._live is not None:
            await self._live.detach()
        if session is not None and session.is_open:
            await session.close()
        if session is not None:
            # Turlar boyu biriken yerel adres izinleri kapanışla sıfırlanır (tur başına
            # tarayıcının boş başlangıcı); sonraki açılış yeni kümeyle kurulur.
            session.origins = set()
        self._forget_user_profile()
        return _ok(**self._state())

    def _forget_user_profile(self) -> None:
        """Kullanıcının panelde seçtiği profili bırak; oturum yeni açılmış gibi kalır.

        Ölçüldü (31 Ekim, inceleme): kapatınca yalnız `_user_profile` sıfırlanıyordu; oturumun
        `profile_name`'i girişli profilde kaldığı için sonraki ajan turu onu onaysız yüklüyordu.
        Yapılandırmadaki varsayılan profil ajan isteyince onayla (REMOTE_SESSION) yüklenir.
        """
        current = self._shared.current
        if self._user_profile and current is not None:
            current.profile_name = self._new_session().profile_name
        self._user_profile = ""
        self.profile_consent = False

    # ------------------------------------------------------------------ görüntü
    async def _frame(self, data: dict[str, Any]) -> dict[str, Any]:
        session = self._shared.current
        if session is None or not session.is_open:
            return _ok(**self._state(), seq=0)
        since = data.get("son")
        snapshot = await self._view_of(session).snapshot(since if isinstance(since, int) else 0)
        return _ok(**self._state(), **snapshot_payload(snapshot))

    # ------------------------------------------------------------------ girdi
    def _input(self, action: Callable[[LiveView, dict[str, Any]], Awaitable[None]]) -> Handler:
        """Kullanıcı girdisi: tur sürüyorsa denetim kendiliğinden kullanıcıya geçer."""

        async def run(data: dict[str, Any]) -> dict[str, Any]:
            session = self._shared.current
            if session is None or not session.is_open:
                return _error("Tarayıcı açık değil; panelde bir adres aç.")
            if self._agent_busy() and not session.user_control:
                session.take_control()
                self._auto_control = True
            await action(self._view_of(session), data)
            return _ok(**self._state())

        return run

    def _view(self, action: Callable[[LiveView, dict[str, Any]], Awaitable[None]]) -> Handler:
        """Görünüm değişikliği (boyut/tema, kaydırma): denetimi devralmaz."""

        async def run(data: dict[str, Any]) -> dict[str, Any]:
            session = self._shared.current
            if session is None or not session.is_open:
                return _error("Tarayıcı açık değil; panelde bir adres aç.")
            await action(self._view_of(session), data)
            return _ok(**self._state())

        return run

    @staticmethod
    async def _click(live: LiveView, data: dict[str, Any]) -> None:
        clicks = data.get("tik", 1)
        await live.click(
            data.get("x"),
            data.get("y"),
            clicks=clicks if isinstance(clicks, int) and not isinstance(clicks, bool) else 1,
            button=str(data.get("dugme") or "left"),
        )

    async def _take(self, _data: dict[str, Any]) -> dict[str, Any]:
        self._shared.session().take_control()
        self._auto_control = False
        return _ok(**self._state())

    async def _release(self, _data: dict[str, Any]) -> dict[str, Any]:
        session = self._shared.current
        if session is not None:
            session.release_control()
        self._auto_control = False
        return _ok(**self._state())

    def turn_finished(self) -> None:
        """Ajan turu bitti: girdiyle kendiliğinden devralınan denetim ajana döner."""
        session = self._shared.current
        if self._auto_control and session is not None:
            session.release_control()
        self._auto_control = False

    # ------------------------------------------------------------------ öğe seçici
    async def _element(self, data: dict[str, Any]) -> tuple[Any, browser_picker.PickedElement]:
        session = self._shared.current
        if session is None or not session.is_open:
            raise LiveInputError("Tarayıcı açık değil; panelde bir adres aç.")
        live = self._view_of(session)
        page = await live.active_page()
        x, y = await live.to_css(data.get("x"), data.get("y"))
        element = await browser_picker.element_at(page, x, y)
        if element is None:
            raise LiveInputError("Bu noktada seçilebilir öğe yok.")
        return page, element

    async def _hover(self, data: dict[str, Any]) -> dict[str, Any]:
        _page, element = await self._element(data)
        return _ok(**element_payload(element))

    async def _pick(self, data: dict[str, Any]) -> dict[str, Any]:
        page, element = await self._element(data)
        image = await browser_picker.capture(page, element)
        path = await asyncio.to_thread(browser_picker.save_pick, self._root(), image)
        return _ok(
            **element_payload(element),
            url=page.url,
            yol=path,
            metin=browser_picker.mention_text(element, page.url),
            base64=base64.b64encode(image).decode("ascii"),
        )

    async def _screenshot(self, _data: dict[str, Any]) -> dict[str, Any]:
        session = self._shared.current
        if session is None or not session.is_open:
            return _error("Tarayıcı açık değil; panelde bir adres aç.")
        page = await self._view_of(session).active_page()
        image = await browser_picker.capture(page)
        path = await asyncio.to_thread(
            browser_picker.save_pick, self._root(), image, prefix="sayfa"
        )
        if not path:
            return _error("Görüntü proje içine yazılamadı (.fusion/secimler).")
        return _ok(yol=path, url=page.url, metin=f"Tarayıcı panelinin görüntüsü ({page.url}).")

    async def _console(self, data: dict[str, Any]) -> dict[str, Any]:
        session = self._shared.current
        if session is None or not session.is_open:
            return _error("Tarayıcı açık değil; panelde bir adres aç.")
        live = self._view_of(session)
        await live.active_page()
        return log_payload(live.page_log(clear=data.get("temizle") is True))

    # ------------------------------------------------------------------ ayarlar
    async def _setting(self, data: dict[str, Any]) -> dict[str, Any]:
        key, value = data.get("anahtar"), data.get("deger")
        if not isinstance(value, bool):
            return _error("Ayar değeri true ya da false olmalı.")
        if key == SETTING_AGENT:
            if self._save_agent_share is None:
                self._agent_choice = value
            else:
                error = await self._save_agent_share(value)
                if error:
                    return _error(error)
                self._agent_choice = None
        elif key == SETTING_CONSENT:
            self.profile_consent = value
        else:
            return _error(f"Bilinmeyen panel ayarı: {key}")
        return _ok(**self._state())

    async def _profile(self, data: dict[str, Any]) -> dict[str, Any]:
        """Panelin oturumunu başka profille yeniden aç ("" = temiz, panel profili = kalıcı)."""
        name = data.get("ad")
        if not isinstance(name, str):
            return _error("Profil adı (`ad`) gerekir; temiz oturum için boş metin.")
        if self._agent_busy():
            return _error(_PROFILE_BUSY)
        name = name.strip()
        if name == PANEL_PROFILE:
            error = await asyncio.to_thread(ensure_panel_profile, self._store())
            if error:
                return _error(error)
        await self._close_browser({})
        # Kullanıcının seçimi varsayılan profili ezer ("" = temiz); profil kapısı yine geçerlidir.
        self._shared.session().profile_name = name
        self._user_profile = name
        self.profile_consent = False
        opened, error = await self._ensure_open(name)
        if opened is None:
            self._forget_user_profile()
            return _error(error)
        return _ok(**self._state())
