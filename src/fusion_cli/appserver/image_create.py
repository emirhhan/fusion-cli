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

from ..config.models import Config
from ..providers.image_generation import (
    GenerationResult,
    ImageGenerationError,
    image_choices,
    render_images,
)
from ..providers.nim_image import ASPECT_SIZES, nim_model_from_choice
from .image_flows import gallery_dir, write_sidecar

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
    return [
        {"deger": choice.value, "etiket": choice.label, "referans": choice.reference}
        for choice in image_choices(config, environ=environ)
    ]


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
    olcu: tuple[int, int] | None = None
    if nim is not None and nim.aspect_sizes:
        olcu = ASPECT_SIZES[oran]
    elif oran != "1:1":
        # Boyut parametresi olmayan sağlayıcıya oran istemde söylenir.
        istem_son = f"{istem_son}\n\nGörselin en-boy oranı {oran} olsun."
    try:
        sonuc = await render_images(
            config,
            secim,
            istem_son,
            image_output_dir(),
            size=olcu,
            reference=referans,
            environ=environ,
        )
    except ImageGenerationError as error:
        return {"ok": False, "metin": str(error)}
    return _result(sonuc, istem)


def _result(sonuc: GenerationResult, istem: str) -> dict[str, Any]:
    for gorsel in sonuc.images:
        write_sidecar(gorsel.path, prompt=istem, provider=sonuc.label)
    return {
        "ok": True,
        "saglayici": sonuc.label,
        "dosyalar": [
            {"yol": str(g.path), "genislik": g.width, "yukseklik": g.height} for g in sonuc.images
        ],
    }
