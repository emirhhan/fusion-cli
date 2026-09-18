"""Tur tarayıcısının pencere kipi."""

from __future__ import annotations

from enum import IntEnum


class WindowMode(IntEnum):
    """Fusion'ın tur Chrome'unun kullanıcının ekranında nasıl durduğu.

    Üç kip vardır:

    - `VISIBLE`: normal Chrome penceresi, ekranda görünür.
    - `HEADLESS`: pencere hiç açılmaz (`--headless=new`).
    - `HIDDEN`: normal (headed) Chrome açılır, ardından işletim sistemi düzeyinde
      gizlenir. Pencere ekranda görünmez ama tarayıcı gerçek headed Chrome'dur.

    `IntEnum` bilinçli: bu kip kullanıcının yapılandırmasında `headless: true/false`
    boolean'ı olarak yazılıydı. `True == 1` ve `False == 0` olduğu için eski dosyalar
    dönüşüm koduna gerek kalmadan `HEADLESS` ve `VISIBLE`'a oturur.
    """

    VISIBLE = 0
    HEADLESS = 1
    HIDDEN = 2

    @classmethod
    def _missing_(cls, value: object) -> WindowMode | None:
        """Kipin metin karşılığını tanı (`headless: hidden`)."""
        if isinstance(value, str):
            wanted = value.strip().lower()
            for member in cls:
                if member.slug == wanted:
                    return member
        return None

    @property
    def slug(self) -> str:
        """Yapılandırmada ve panel API'sinde kullanılan metin karşılığı."""
        return self.name.lower()

    @property
    def is_offscreen(self) -> bool:
        """Pencere kullanıcının ekranında durmuyor mu?"""
        return self is not WindowMode.VISIBLE

    @property
    def as_config_value(self) -> bool | str:
        """`headless` anahtarına yazılacak değer.

        Eski iki kip boolean olarak yazılmaya devam eder: kullanıcının dosyasının
        biçimi değişmez ve daha eski bir Fusion sürümü de aynı dosyayı okuyabilir.
        Yalnız yeni kip metin (`hidden`) olarak yazılır.
        """
        if self is WindowMode.HIDDEN:
            return self.slug
        return self is WindowMode.HEADLESS


def resolve_window_mode(requested: WindowMode, *, can_hide: bool) -> WindowMode:
    """İstenen kipi bu makinede GERÇEKTEN uygulanabilecek kipe çevir.

    Gizli kip pencereyi işletim sistemi düzeyinde gizlemeye dayanır; bu yalnız
    macOS'ta var. Gizlenemeyen bir makinede gizli kip, görünmez (headless) kipe
    düşer: kullanıcının önüne sessizce pencere açmak kabul edilemez, görünmez kip
    ise Fusion'ın zaten varsayılanıdır ve pencere hiç açılmaz.
    """
    if requested is WindowMode.HIDDEN and not can_hide:
        return WindowMode.HEADLESS
    return requested
