"""Tur boyunca yaşayan tarayıcı oturumunun taşıyıcısı.

Neden `core`'da ve neden bir taşıyıcı: tarayıcı durumu çağrılar arasında yaşamak
zorundadır (şifre alanına yaz → gönder → açılan sayfayı oku üç ayrı araç çağrısıdır),
ama modül-global tutulamaz — RULES.md "Paylaşılan araç durumu modül-global tutulmaz;
çağrı bağlamına bağlanır". `TodoList` ve `PendingWrite` ile aynı desendir.

Playwright burada import EDİLMEZ: `core` üçüncü parti bağımlılık tanımaz ve
playwright zorunlu bağımlılık değildir (`fusion-cli[web]`). Sayfa nesnesi dışarıdan
verilir, buradaki tip gevşek kalır.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable
from typing import Any

#: Tur sonunda tarayıcının güncel `storage_state` sözlüğünü kalıcılaştıran geri çağırım.
StateSaver = Callable[[dict[str, Any]], None]


class BrowserSession:
    """Açık tarayıcıyı ve etkin sayfayı tutan taşıyıcı.

    Kapatma SORUMLULUĞU sahibinindir: turu süren motor tur bitiminde `close`
    çağırır. Kapatılmayan bir oturum arkada bir tarayıcı süreci bırakır — RULES.md
    "Oluşturulan her task'ın sahibi vardır" aynı gerekçeyle burada da geçerlidir.

    `profile_name` / `headless` yapılandırmadan gelen varsayılanlardır (P-023): tarayıcı
    aracı oturumu açarken bu profilin çerezlerini yükler. `state_saver` doluysa
    kapanışta tarayıcının güncel oturumu geri yazılır — yenilenen belirteçler kaybolmaz.
    """

    def __init__(
        self,
        *,
        profile_name: str = "",
        headless: bool = True,
        profiles_enabled: bool = True,
        state_saver: StateSaver | None = None,
    ) -> None:
        #: Playwright bağlamı ve etkin sayfa. Tip `Any`: `core` playwright'ı tanımaz
        #: ve tanısaydı zorunlu bağımlılık olurdu.
        self.playwright: Any = None
        self.browser: Any = None
        self.context: Any = None
        self.page: Any = None
        self.profile_name = profile_name
        self.headless = headless
        self.profiles_enabled = profiles_enabled
        self.state_saver = state_saver
        #: Bu oturumda GERÇEKTEN yüklenen profil (araç argümanı varsayılanı ezebilir).
        self.active_profile = ""
        #: Paylaşılan oturum (P-045: masaüstü Tarayıcı paneli, CLI `/tarayici`): tur bitince
        #: KAPATILMAZ; sahibi paneli/REPL'i tutan taraftır. Tur başına oturumda False.
        self.persistent = False
        #: Paylaşılan oturumun yerel adres izin kümesi; panel ve turlar AYNI kümeyi görür.
        self.origins: set[str] | None = None
        #: Kullanıcı denetimi devraldı mı? Ajanın tarayıcı araçları bırakılana kadar bekler.
        self._user_control = False
        self._released = asyncio.Event()
        self._released.set()

    @property
    def is_open(self) -> bool:
        return self.page is not None

    @property
    def user_control(self) -> bool:
        return self._user_control

    def take_control(self) -> None:
        """Kullanıcı tarayıcıyı devraldı (P-045): ajan eylemleri `wait_for_control`'da bekler."""
        self._user_control = True
        self._released.clear()

    def release_control(self) -> None:
        """Denetimi ajana geri ver; bekleyen tarayıcı aracı kaldığı yerden sürer."""
        self._user_control = False
        self._released.set()

    async def wait_for_control(self, timeout_s: float) -> bool:
        """Kullanıcı denetimi bırakana kadar bekle; süre dolarsa False (iptal yayılır)."""
        if not self._user_control:
            return True
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._released.wait(), timeout_s)
        return not self._user_control

    def derive(self) -> BrowserSession:
        """Aynı AYARLARLA (profil, pencere kipi, profil kapısı) yeni, kapalı bir oturum.

        Plan adımları ve alt ajanlar tarayıcıyı ayrı tutar ama yapılandırmayı DEVRALIR.
        Ölçüldü (31 Ekim): `BrowserSession()` varsayılanı `profiles_enabled=True` olduğu
        için alt ajan `browser.profiles_enabled: false` kapısını deliyordu. Açık sayfa,
        etkin profil ve geri yazıcı kopyalanmaz: bunlar bu oturuma aittir.
        """
        return BrowserSession(
            profile_name=self.profile_name,
            headless=self.headless,
            profiles_enabled=self.profiles_enabled,
        )

    async def close(self) -> None:
        """Sayfayı, tarayıcıyı ve playwright'ı sırayla kapat; hepsini dene.

        Bir adımın hatası diğerlerini engellemez: yarım temizlik, hiç temizlik
        yapmamaktan iyidir ve amaç arkada süreç bırakmamaktır.
        """
        await self._persist_state()
        for nesne, yontem in (
            (self.page, "close"),
            (self.context, "close"),
            (self.browser, "close"),
            (self.playwright, "stop"),
        ):
            if nesne is None:
                continue
            try:
                await getattr(nesne, yontem)()
            except Exception as hata:
                # Kapanış sınır katmanıdır: hangi hata gelirse gelsin diğer
                # kaynakların kapatılması denenmelidir. Sızan tarayıcı süreci
                # teşhis edilebilsin diye hata günlüğe yazılır.
                logging.getLogger(__name__).warning(
                    "Tarayıcı oturumu kapatılırken %s başarısız: %s", yontem, type(hata).__name__
                )
                continue
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.active_profile = ""
        self.release_control()
        # Geri yazıcı oturuma bağlıdır: sıfırlanmazsa sonraki PROFİLSİZ açılışın boş
        # oturumu önceki profilin üstüne yazılır (ölçüldü 31 Ekim: `is` profili silindi).
        self.state_saver = None

    async def _persist_state(self) -> None:
        """Profil kullanıldıysa güncel çerezleri geri yaz; hata kapanışı engellemez."""
        if self.state_saver is None or self.context is None:
            return
        try:
            state = await self.context.storage_state()
            if isinstance(state, dict):
                self.state_saver(state)
        except Exception as hata:
            logging.getLogger(__name__).warning(
                "Tarayıcı profili geri yazılamadı: %s", type(hata).__name__
            )

    async def pages(self) -> tuple[Any, ...]:
        """Aynı tarayıcı bağlamındaki açık sayfaları sırayla döndür."""
        if self.context is None:
            return ()
        return tuple(page for page in self.context.pages if not page.is_closed())
