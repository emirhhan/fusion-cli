"""`gorsel.olustur`: arayüzün "Görsel oluştur" (düğümlü akış) sayfasının çekirdek tarafı.

İki üretici vardır:

- **NVIDIA NIM (FLUX)** — API anahtarıyla, tarayıcısız; canlı ölçümde çalışan
  modeller `providers/nim_image.py`'de listelenir. Referans görsel almaz.
- **Bağlı web oturumu** (Gemini web, ChatGPT web) — görseli kullanıcının kendi
  hesabı üretir. Referans görsel yalnız Gemini web'e yüklenebilir.

Üretilen dosyalar uygulama içi galeriye (`image_flows.gallery_dir`) yazılır;
Finder'da görünen bir klasöre kendiliğinden inmez. Kullanıcı "İndir" ile
seçtiği yere kopyalar (`gorsel.kaydet`).
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ..config.keys import NIM_ENV, environ_snapshot
from ..config.models import Config
from ..providers.nim_image import (
    ASPECT_SIZES,
    NIM_IMAGE_MODELS,
    NIM_PREFIX,
    NimImageError,
    NimImageModel,
    generate_nim_image,
    nim_model_from_choice,
)
from ..providers.web_browser import WebBrowserError
from ..providers.web_image import (
    IMAGE_SELECTORS,
    REFERENCE_PROVIDERS,
    GeneratedImage,
    generate_images,
)
from ..providers.web_registry import web_registry_for
from .image_flows import gallery_dir, write_sidecar

#: Sağlayıcı sırası: canlı doğrulanan önce.
_PREFERENCE = ("gemini_web", "chatgpt_web")

#: İşlem → modele giden istem kalıbı. Web modelleri gerçek bir "büyütme"
#: aracı sunmaz; büyütme, referans görselin aynı içerikle yüksek çözünürlükte
#: yeniden üretilmesi olarak istenir ve arayüz bunu böyle adlandırır.
_ISLEM_KALIBI = {
    "uret": "{istem}",
    "varyasyon": "Ekteki görselin aynı konu ve üslupta farklı bir varyasyonunu oluştur. {istem}",
    "buyut": "Ekteki görseli aynı içerik ve kompozisyonla daha yüksek çözünürlükte, "
    "daha keskin ve ayrıntılı olarak yeniden oluştur.",
    "duzenle": "Ekteki görseli şu şekilde düzenle, geri kalanını koru: {istem}",
}
_REFERANS_GEREKEN = frozenset({"varyasyon", "buyut", "duzenle"})


def image_output_dir() -> Path:
    """Üretilen görsellerin yazıldığı uygulama içi galeri."""
    return gallery_dir()


def image_providers(
    config: Config, *, environ: Mapping[str, str] | None = None
) -> list[dict[str, Any]]:
    """Görsel üretebilen sağlayıcılar (arayüzdeki seçici için), referans yetenekleriyle."""
    oturumlar = [s for s in config.web_sessions if s.provider in IMAGE_SELECTORS]
    oturumlar.sort(key=lambda s: _PREFERENCE.index(s.provider))
    secenekler: list[dict[str, Any]] = [
        {
            "deger": f"{s.provider}/{s.account}",
            "etiket": _label(s.provider, s.account),
            "referans": s.provider in REFERENCE_PROVIDERS,
        }
        for s in oturumlar
    ]
    ortam = environ if environ is not None else environ_snapshot()
    if ortam.get(NIM_ENV, "").strip():
        secenekler += [
            {"deger": NIM_PREFIX + item.model, "etiket": item.label, "referans": False}
            for item in NIM_IMAGE_MODELS
        ]
    return secenekler


def _label(provider: str, account: str) -> str:
    ad = {"gemini_web": "Gemini", "chatgpt_web": "ChatGPT"}.get(provider, provider)
    return ad if account == "main" else f"{ad} ({account})"


def _compose(islem: str, istem: str) -> str:
    return _ISLEM_KALIBI[islem].format(istem=istem).strip()


def _reference(data: dict[str, Any]) -> Path | None:
    """Referans yalnız galerideki bir görsel olabilir; başka dosya gönderilmez."""
    raw = data.get("referans")
    if not isinstance(raw, str) or not raw:
        return None
    path = Path(raw).resolve()
    if not path.is_relative_to(image_output_dir().resolve()) or not path.is_file():
        raise ValueError("Referans görsel galeride bulunamadı.")
    return path


async def create_image(
    config: Config, data: dict[str, Any], *, environ: Mapping[str, str] | None = None
) -> dict[str, Any]:
    islem = str(data.get("islem") or "uret")
    if islem not in _ISLEM_KALIBI:
        return {"ok": False, "metin": f"Bilinmeyen işlem: {islem}"}
    istem = str(data.get("istem") or "").strip()
    if not istem and islem in ("uret", "duzenle"):
        return {"ok": False, "metin": "Ne çizileceğini yaz."}
    try:
        referans = _reference(data)
    except ValueError as error:
        return {"ok": False, "metin": str(error)}
    if islem in _REFERANS_GEREKEN and referans is None:
        return {"ok": False, "metin": "Bu işlem için bir görsel girdisi bağla."}
    secenekler = image_providers(config, environ=environ)
    if not secenekler:
        return {
            "ok": False,
            "metin": "Görsel üretebilen bağlı sağlayıcı yok. Ayarlar → Sağlayıcılar'dan "
            "NVIDIA NIM anahtarı ekle ya da Gemini web'e bağlan.",
        }
    secim = str(data.get("saglayici") or secenekler[0]["deger"])
    oran = str(data.get("oran") or "1:1")
    if oran not in ASPECT_SIZES:
        return {"ok": False, "metin": f"Desteklenmeyen en-boy oranı: {oran}"}
    istem_son = _compose(islem, istem)
    nim = nim_model_from_choice(secim)
    if nim is not None and nim.aspect_sizes:
        return await _create_with_nim(nim, istem_son, referans, environ, istem, ASPECT_SIZES[oran])
    # Boyut parametresi olmayan sağlayıcıya oran istemde söylenir.
    if oran != "1:1":
        istem_son = f"{istem_son}\n\nGörselin en-boy oranı {oran} olsun."
    if nim is not None:
        return await _create_with_nim(nim, istem_son, referans, environ, istem)
    return await _create_with_web(config, secim, istem_son, referans, istem)


async def _create_with_nim(
    nim: NimImageModel,
    prompt: str,
    referans: Path | None,
    environ: Mapping[str, str] | None,
    istem: str,
    size: tuple[int, int] = ASPECT_SIZES["1:1"],
) -> dict[str, Any]:
    if referans is not None:
        return {"ok": False, "metin": f"{nim.label} referans görsel almaz; Gemini web seç."}
    anahtar = (environ if environ is not None else environ_snapshot()).get(NIM_ENV, "").strip()
    if not anahtar:
        return {"ok": False, "metin": "NVIDIA NIM anahtarı bulunamadı."}
    try:
        gorseller = await generate_nim_image(
            nim, prompt, image_output_dir(), api_key=anahtar, size=size
        )
    except NimImageError as error:
        return {"ok": False, "metin": str(error)}
    return _result(nim.label, gorseller, istem)


async def _create_with_web(
    config: Config, secim: str, prompt: str, referans: Path | None, istem: str
) -> dict[str, Any]:
    registry = web_registry_for(config)
    oturum = next((s for s in config.web_sessions if f"{s.provider}/{s.account}" == secim), None)
    if oturum is None or oturum.provider not in IMAGE_SELECTORS:
        return {"ok": False, "metin": f"Bilinmeyen sağlayıcı: {secim}"}
    if registry is None:
        return {"ok": False, "metin": "Web oturumu kayıt defteri kurulamadı."}
    if referans is not None and oturum.provider not in REFERENCE_PROVIDERS:
        return {
            "ok": False,
            "metin": f"{_label(oturum.provider, oturum.account)} referans görsel almaz.",
        }
    try:
        gorseller = await generate_images(
            oturum,
            registry.credential_for(oturum),
            prompt,
            image_output_dir(),
            reference=referans,
        )
    except WebBrowserError as error:
        return {"ok": False, "metin": str(error).removeprefix("authentication: ")}
    return _result(_label(oturum.provider, oturum.account), gorseller, istem)


def _result(label: str, gorseller: list[GeneratedImage], istem: str) -> dict[str, Any]:
    for gorsel in gorseller:
        write_sidecar(gorsel.path, prompt=istem, provider=label)
    return {
        "ok": True,
        "saglayici": label,
        "dosyalar": [
            {"yol": str(g.path), "genislik": g.width, "yukseklik": g.height} for g in gorseller
        ],
    }
