"""Turlar arasında yaşayan paylaşılan tarayıcı (P-045) ve kullanıcı devralma kapısı.

Ölçüldü (31 Ekim): ajanın `browser_*` araçları her turda yeni bir başsız Chromium açıp tur
sonunda kapatıyordu; kullanıcı ajanın ne yaptığını göremiyor, girişi/CAPTCHA'yı kendisi
geçip ajana devredemiyordu. Masaüstü Tarayıcı paneli ve CLI `/tarayici` aynı nesneyi kullanır:

- `SharedBrowser` tek bir `BrowserSession`'ı `persistent=True` ile tutar; motor tur sonunda
  onu kapatmaz (`loop.run_agent`), sahibi (panel/REPL) `close` ile kapatır.
- `control_gate`: kullanıcı denetimi devraldıysa ajanın tarayıcı aracı bırakılana kadar
  BEKLER (giriş yap → "Ajana bırak" → ajan aynı çağrıda sürer); süre dolarsa açık bir
  hata döner, ajan kullanıcıyla tarayıcı için kavga etmez.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from ..core.browser_session import BrowserSession

#: Kullanıcı devraldığında ajan aracının bekleyeceği en uzun süre (sn). Giriş, iki adımlı
#: doğrulama ya da CAPTCHA birkaç dakika sürebilir; daha uzunu turu askıda bırakırdı.
USER_CONTROL_WAIT_S = 300.0

USER_CONTROL_TIMEOUT = (
    "Kullanıcı tarayıcıyı devraldı ve {seconds:.0f} sn içinde bırakmadı; tarayıcıda eylem "
    "yapma. Kullanıcıya ne beklediğini söyle ve işi bitince 'Ajana bırak' demesini iste."
)


async def control_gate(session: BrowserSession, timeout_s: float = USER_CONTROL_WAIT_S) -> str:
    """Kullanıcı denetimdeyse bırakılmasını bekle; süre dolarsa hata metni, yoksa boş."""
    if await session.wait_for_control(timeout_s):
        return ""
    return USER_CONTROL_TIMEOUT.format(seconds=timeout_s)


class SharedBrowser:
    """Paylaşılan tarayıcı oturumunun sahibi: yaratır, ayırır, kapatır.

    `factory` yapılandırmadan (`browser:` ayarları) yeni oturum kurar; paylaşılan oturum
    `persistent` işaretlenir ve kendi yerel izin kümesini (`origins`) taşır — panelde yazılan
    yerel adres ile ajanın turunda yazılan aynı kümeye girer.
    """

    def __init__(self, factory: Callable[[], BrowserSession]) -> None:
        self._factory = factory
        self._session: BrowserSession | None = None
        #: Senkron komuttan (`/tarayici kapat`) başlatılan kapanışlar; `shutdown` bekler.
        self._closing: set[asyncio.Task[None]] = set()

    @property
    def current(self) -> BrowserSession | None:
        return self._session

    def session(self) -> BrowserSession:
        """Paylaşılan oturum; yoksa kurulur (tarayıcı süreci ilk kullanımda başlar)."""
        if self._session is None:
            session = self._factory()
            session.persistent = True
            session.origins = set()
            self._session = session
        return self._session

    def detach(self) -> BrowserSession | None:
        """Paylaşımı bitir; oturumu çağırana ver (kapatma sorumluluğu onundur)."""
        session, self._session = self._session, None
        return session

    async def close(self) -> None:
        """Oturumu kapat ve paylaşımı bitir; açık değilse bir şey yapmaz."""
        session = self.detach()
        if session is not None:
            await session.close()

    def close_later(self) -> bool:
        """Senkron çağırandan kapat: görev sahiplenilir, `shutdown` onu bekler.

        Dönüş: paylaşım açık mıydı. Tarayıcı hiç açılmadıysa kapatılacak süreç yoktur.
        """
        session = self.detach()
        if session is None:
            return False
        if not session.is_open:
            return True
        task = asyncio.get_running_loop().create_task(session.close())
        self._closing.add(task)
        task.add_done_callback(self._closed)
        return True

    def _closed(self, task: asyncio.Task[None]) -> None:
        self._closing.discard(task)
        if not task.cancelled() and task.exception() is not None:
            logging.getLogger(__name__).warning(
                "Paylaşılan tarayıcı kapatılamadı: %s", type(task.exception()).__name__
            )

    async def shutdown(self) -> None:
        """Bekleyen kapanışları bitir ve açık oturumu kapat (REPL/uygulama çıkışı)."""
        if self._closing:
            await asyncio.gather(*tuple(self._closing), return_exceptions=True)
        await self.close()
