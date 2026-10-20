"""Bot doğrulaması ara sayfası, "arayüz değişmiş" sanılmamalı.

Ölçüldü (11 Eylül, chatgpt_web/main, headless): ChatGPT Cloudflare ara sayfası
döndürdü. Sayfanın BAŞLIĞI "Bir dakika lütfen..." ve GÖVDESİ BOŞ; giriş işareti
de yok. Fusion bu durumda "mesaj alanı bulunamadı; web arayüzü değişmiş olabilir"
diyordu ve kullanıcıyı seçicileri aramaya yönlendiriyordu — oysa sayfa hiç
yüklenmemişti ve yapılacak şey doğrulamayı görünür tarayıcıda tamamlamaktı.

İki boşluk vardı: Türkçe Cloudflare metni işaret listesinde yoktu ve sınıflandırma
yalnız GÖVDEYE bakıyordu, oysa bu ara sayfada sinyal başlıktadır.
"""

from __future__ import annotations

from fusion_cli.providers.web_browser import (
    _CHALLENGE_MARKERS,
    _matched_marker,
    provider_definition,
)


def test_cloudflare_ara_sayfasinin_turkce_metni_taninir():
    # `_matched_marker` küçük harf bekler: gövde `_page_chrome_text` içinde
    # `.lower()` ile veriliyor, başlık da `_challenge_signal` içinde.
    assert _matched_marker("bir dakika lütfen…", _CHALLENGE_MARKERS) is not None


def test_cloudflare_ara_sayfasinin_ingilizce_metni_taninir():
    assert _matched_marker("just a moment...", _CHALLENGE_MARKERS) is not None


def test_normal_sohbet_metni_dogrulama_sanilmaz():
    """Yanlış pozitif, teşhis yokluğundan zararlıdır (bkz. kota işaretleri dersi)."""
    assert _matched_marker("merhaba, bir dakika içinde hallederim.", _CHALLENGE_MARKERS) is None
    assert _matched_marker("kodu yazdım ve testleri çalıştırdım.", _CHALLENGE_MARKERS) is None


async def test_bos_govdeli_ara_sayfa_basliktan_yakalanir():
    """Ara sayfanın gövdesi boş gelir; başlık okunmazsa hiçbir işaret eşleşmez."""
    from fusion_cli.providers.web_browser import _challenge_signal

    class _Page:
        url = "https://chatgpt.com/"

        async def title(self) -> str:
            return "Bir dakika lütfen..."

    işaret = await _challenge_signal(_Page(), provider_definition("chatgpt_web"), body="")

    assert işaret is not None
    assert "dakika" in işaret
