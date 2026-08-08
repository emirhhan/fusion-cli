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

from typing import Any


class BrowserSession:
    """Açık tarayıcıyı ve etkin sayfayı tutan taşıyıcı.

    Kapatma SORUMLULUĞU sahibinindir: turu süren motor tur bitiminde `close`
    çağırır. Kapatılmayan bir oturum arkada bir tarayıcı süreci bırakır — RULES.md
    "Oluşturulan her task'ın sahibi vardır" aynı gerekçeyle burada da geçerlidir.
    """

    def __init__(self) -> None:
        #: Playwright bağlamı ve etkin sayfa. Tip `Any`: `core` playwright'ı tanımaz
        #: ve tanısaydı zorunlu bağımlılık olurdu.
        self.playwright: Any = None
        self.browser: Any = None
        self.page: Any = None

    @property
    def is_open(self) -> bool:
        return self.page is not None

    async def close(self) -> None:
        """Sayfayı, tarayıcıyı ve playwright'ı sırayla kapat; hepsini dene.

        Bir adımın hatası diğerlerini engellemez: yarım temizlik, hiç temizlik
        yapmamaktan iyidir ve amaç arkada süreç bırakmamaktır.
        """
        for nesne, yontem in (
            (self.page, "close"),
            (self.browser, "close"),
            (self.playwright, "stop"),
        ):
            if nesne is None:
                continue
            try:
                await getattr(nesne, yontem)()
            except Exception:
                # Kapanış sınır katmanıdır: hangi hata gelirse gelsin diğer
                # kaynakların kapatılması denenmelidir.
                continue
        self.playwright = None
        self.browser = None
        self.page = None
