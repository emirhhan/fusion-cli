"""Bilgisayar kullanımı (computer use) ayarları ve hedef uygulama tipi (P-006, P-007).

Claude Desktop "Settings › This computer" karşılığı: computer use anahtarı, uygulamaların
en çok hangi kademede yönetilebileceği, reddedilen uygulamalar ve tur davranışı (arka plan,
gizlenen uygulamaları geri gösterme, Esc ile durdurma). Tek kaynak `defaults.yaml`'ın
`desktop:` bölümüdür; buradaki varsayılanlar eski yapılandırma dosyası (bölümsüz) içindir ve
`tests/test_desktop_settings.py` ikisinin aynı kaldığını denetler.

`core` katmanındadır: `ToolContext` (core) turun ayarını taşır, onay isteği (`engines`)
hedef uygulamayı (`DesktopTarget`) taşır; ikisi de stdlib dışı bir şey bilmez.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class DesktopLevel(StrEnum):
    """Bir uygulamada izin verilen en yüksek eylem kademesi (Claude: View/Click/Full)."""

    #: Yalnız bak: ekran görüntüsü ve okuma; tıklama, yazma yok (tarayıcılar).
    OBSERVE = "observe"
    #: Tıkla: tıklama ve kaydırma; yazma, kısayol ve sürükleme yok (terminaller, IDE'ler).
    CLICK = "click"
    #: Tam kontrol: tıkla, yaz, sürükle, kısayol.
    FULL = "full"

    @property
    def rank(self) -> int:
        return _RANKS[self]

    @property
    def label(self) -> str:
        """Kullanıcıya görünen Türkçe ad (kart, ayarlar, hata metni)."""
        return _LABELS[self]


_RANKS = {DesktopLevel.OBSERVE: 0, DesktopLevel.CLICK: 1, DesktopLevel.FULL: 2}
_LABELS = {
    DesktopLevel.OBSERVE: "yalnız bak",
    DesktopLevel.CLICK: "tıkla",
    DesktopLevel.FULL: "tam kontrol",
}


@dataclass(frozen=True, slots=True)
class DesktopSettings:
    """`desktop:` bölümü: computer use anahtarı, kademe tavanı, uygulama listeleri."""

    #: Kapalıysa `desktop_*` araçları modele hiç sunulmaz (kayıt defterinden çıkar). Claude
    #: Code gibi varsayılan KAPALI (#420); CLI'de proje başına `/mcp enable computer-use`.
    enabled: bool = False
    #: KULLANIMDAN KALKTI (#424): kademeler kategoriye göre sabittir; okunur, uygulanmaz.
    control_level: DesktopLevel = DesktopLevel.FULL
    #: KULLANIMDAN KALKTI (#424): kategori tablosu her zaman uygulanır.
    category_defaults: bool = True
    #: Hiç dokunulmayan uygulamalar (ad ya da paket kimliği, büyük/küçük harf duyarsız).
    denied_apps: tuple[str, ...] = ()
    #: KULLANIMDAN KALKTI (#424): uygulama başına kademe değiştirilemez.
    app_levels: tuple[str, ...] = ()
    #: KULLANIMDAN KALKTI (#426): uygulama onayı her zaman sorulur ("Bu oturum için izin ver /
    #: Reddet"); istemi kapatan ayar yok.
    app_consent: bool = True
    #: Arka planda çalış: diğer uygulamalar gizlenmez, kullanıcı çalışmaya devam eder.
    #: Kapalıysa ilk ön plan eyleminde hedef uygulama ve Fusion dışındakiler gizlenir.
    background: bool = True
    #: Tur bitince Fusion'ın gizlediği uygulamaları yeniden göster.
    unhide_on_finish: bool = True
    #: Ön plan eylemi süren turda fiziksel Esc tuşu turu durdurur (tuş uygulamaya gitmez).
    escape_stops: bool = True


#: Okunup uygulanmayan eski `desktop:` anahtarları (kullanıcı dosyası bozulmaz, bir kez uyarılır).
DEPRECATED_KEYS: tuple[str, ...] = (
    "control_level",
    "category_defaults",
    "app_levels",
    "app_consent",
)


@dataclass(frozen=True, slots=True)
class DesktopTarget:
    """Masaüstü eyleminin çözülmüş hedef uygulaması; onay kartı ve oturum izni bunu kullanır."""

    app: str
    bundle: str = ""
    pid: int = 0
    #: Bu uygulamada izin verilen kademe (kategori + uygulama ayarı + tavan).
    level: DesktopLevel = DesktopLevel.FULL
    #: Kategori uyarısı ("Kabuk erişimine eşdeğer"); yoksa boş.
    warning: str = ""
    #: Tıklanan/odaktaki öğenin adı (rol + başlık); yoksa boş.
    element: str = ""

    @property
    def key(self) -> str:
        """Oturum izninin anahtarı: paket kimliği yoksa küçük harfli ad."""
        return (self.bundle or self.app).casefold()

    def payload(self) -> dict[str, object]:
        """Onay olaylarındaki `masaustu` alanı: kart, stream-json ve uzak onay aynı biçimi okur."""
        return {
            "uygulama": self.app,
            "paket": self.bundle,
            "kademe": self.level.value,
            "kademe_etiket": self.level.label,
            "uyari": self.warning,
            "oge": self.element,
        }


def parse_app_level(entry: str) -> tuple[str, DesktopLevel]:
    """`"Terminal=full"` → ("terminal", FULL); biçim bozuksa `ValueError` (Türkçe metin)."""
    name, equals, raw = entry.partition("=")
    name, raw = name.strip(), raw.strip().lower()
    if not equals or not name:
        raise ValueError(f"'{entry}': 'uygulama=kademe' biçiminde olmalı (ör. Terminal=full).")
    try:
        return name.casefold(), DesktopLevel(raw)
    except ValueError:
        allowed = ", ".join(level.value for level in DesktopLevel)
        raise ValueError(f"'{entry}': kademe {allowed} olmalı.") from None
