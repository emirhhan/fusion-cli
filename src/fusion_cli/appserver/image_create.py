"""`gorsel.olustur`: arayüzün "Görsel oluştur" sayfasının çekirdek tarafı.

Bağlı web oturumu (Gemini web ya da ChatGPT web) görseli üretir; dosyalar
kullanıcının Resimler klasöründe `Fusion` altına yazılır ki Finder'dan da
bulunabilsin. Sağlayıcı seçilmezse önce Gemini denenir: 26 Eylül'de canlı
ölçülen tek yol oydu (ChatGPT web oturumu doğrulama bekliyordu).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config.models import Config
from ..providers.web_browser import WebBrowserError
from ..providers.web_image import IMAGE_SELECTORS, generate_images
from ..providers.web_registry import web_registry_for

#: Sağlayıcı sırası: canlı doğrulanan önce.
_PREFERENCE = ("gemini_web", "chatgpt_web")


def image_output_dir(home: Path | None = None) -> Path:
    return (home or Path.home()) / "Pictures" / "Fusion"


def image_providers(config: Config) -> list[dict[str, str]]:
    """Görsel üretebilen bağlı web oturumları (arayüzdeki seçici için)."""
    oturumlar = [s for s in config.web_sessions if s.provider in IMAGE_SELECTORS]
    oturumlar.sort(key=lambda s: _PREFERENCE.index(s.provider))
    return [
        {"deger": f"{s.provider}/{s.account}", "etiket": _label(s.provider, s.account)}
        for s in oturumlar
    ]


def _label(provider: str, account: str) -> str:
    ad = {"gemini_web": "Gemini", "chatgpt_web": "ChatGPT"}.get(provider, provider)
    return ad if account == "main" else f"{ad} ({account})"


async def create_image(config: Config, data: dict[str, Any]) -> dict[str, Any]:
    istem = str(data.get("istem") or "").strip()
    if not istem:
        return {"ok": False, "metin": "Ne çizileceğini yaz."}
    registry = web_registry_for(config)
    secenekler = image_providers(config)
    if registry is None or not secenekler:
        return {
            "ok": False,
            "metin": "Görsel için bağlı bir Gemini ya da ChatGPT web oturumu yok. "
            "Ayarlar → Sağlayıcılar'dan bağlan.",
        }
    secim = str(data.get("saglayici") or secenekler[0]["deger"])
    oturum = next((s for s in config.web_sessions if f"{s.provider}/{s.account}" == secim), None)
    if oturum is None:
        return {"ok": False, "metin": f"Bilinmeyen sağlayıcı: {secim}"}
    try:
        gorseller = await generate_images(
            oturum, registry.credential_for(oturum), istem, image_output_dir()
        )
    except WebBrowserError as error:
        return {"ok": False, "metin": str(error).removeprefix("authentication: ")}
    return {
        "ok": True,
        "saglayici": _label(oturum.provider, oturum.account),
        "dosyalar": [
            {"yol": str(g.path), "genislik": g.width, "yukseklik": g.height} for g in gorseller
        ],
    }
