"""Görsel üretiminin TEK çekirdeği — masaüstü "Görsel oluştur" sayfası ve ajan aracı.

İki üretici vardır:

- **NVIDIA NIM (FLUX)** — API anahtarıyla, tarayıcısız; çalıştığı ölçülen modeller
  `nim_image.py`'de listelenir. Referans görsel almaz.
- **Bağlı web oturumu** (Gemini web, ChatGPT web) — görseli kullanıcının kendi
  hesabı üretir. Referans görsel yalnız Gemini web'e yüklenebilir.

Eskiden bu mantık masaüstü katmanındaydı (`appserver/image_create.py`); ajan
görsel üretemiyordu çünkü motor o katmanı göremez. Çekirdek buraya indi, iki
kullanıcı da aynı yoldan geçer.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ..config.keys import NIM_ENV, environ_snapshot
from ..config.models import Config
from .nim_image import (
    NIM_IMAGE_MODELS,
    NIM_PREFIX,
    NimImageError,
    NimImageModel,
    generate_nim_image,
    nim_model_from_choice,
)
from .web_browser import WebBrowserError
from .web_image import IMAGE_SELECTORS, REFERENCE_PROVIDERS, GeneratedImage, generate_images
from .web_registry import web_registry_for

#: Web sağlayıcı sırası: canlı doğrulanan önce.
_WEB_PREFERENCE = ("gemini_web", "chatgpt_web")


class ImageGenerationError(RuntimeError):
    """Görsel üretilemedi; mesaj kullanıcıya/modele olduğu gibi gösterilir."""


@dataclass(frozen=True, slots=True)
class ImageChoice:
    """Seçilebilir bir görsel üreticisi."""

    value: str
    label: str
    #: Referans görsel (düzenleme/varyasyon) alabiliyor mu?
    reference: bool
    #: İstenen piksel ölçüsünü parametre olarak kabul ediyor mu?
    exact_size: bool


@dataclass(frozen=True, slots=True)
class GenerationResult:
    label: str
    images: tuple[GeneratedImage, ...]


def image_choices(
    config: Config, *, environ: Mapping[str, str] | None = None
) -> tuple[ImageChoice, ...]:
    """Bu yapılandırmada görsel üretebilen sağlayıcılar (web önce, sonra NIM)."""
    # Kısmi/sahte yapılandırmada (alt sistem testleri) oturum listesi olmayabilir:
    # görsel üretimi o zaman yalnız anahtara bakar, araç kurulumu düşmez.
    web_sessions = getattr(config, "web_sessions", ())
    sessions = sorted(
        (s for s in web_sessions if s.provider in IMAGE_SELECTORS),
        key=lambda s: _WEB_PREFERENCE.index(s.provider),
    )
    choices = [
        ImageChoice(
            value=f"{s.provider}/{s.account}",
            label=web_label(s.provider, s.account),
            reference=s.provider in REFERENCE_PROVIDERS,
            exact_size=False,
        )
        for s in sessions
    ]
    ortam = environ if environ is not None else environ_snapshot()
    if ortam.get(NIM_ENV, "").strip():
        choices += [
            ImageChoice(
                value=NIM_PREFIX + item.model,
                label=item.label,
                reference=False,
                exact_size=item.aspect_sizes,
            )
            for item in NIM_IMAGE_MODELS
        ]
    return tuple(choices)


def web_label(provider: str, account: str) -> str:
    ad = {"gemini_web": "Gemini", "chatgpt_web": "ChatGPT"}.get(provider, provider)
    return ad if account == "main" else f"{ad} ({account})"


async def render_images(
    config: Config,
    choice: str,
    prompt: str,
    out_dir: Path,
    *,
    size: tuple[int, int] | None = None,
    reference: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> GenerationResult:
    """Seçilen üreticiyle görsel(ler) üret; başarısızlıkta `ImageGenerationError`.

    `size` yalnız ölçü kabul eden NIM modeline parametre olarak gider; diğerlerinde
    çağıranın istemde oranı söylemesi beklenir.
    """
    nim = nim_model_from_choice(choice)
    if nim is not None:
        return await _render_nim(nim, prompt, out_dir, size, reference, environ)
    return await _render_web(config, choice, prompt, out_dir, reference)


async def _render_nim(
    nim: NimImageModel,
    prompt: str,
    out_dir: Path,
    size: tuple[int, int] | None,
    reference: Path | None,
    environ: Mapping[str, str] | None,
) -> GenerationResult:
    if reference is not None:
        raise ImageGenerationError(f"{nim.label} referans görsel almaz; Gemini web seç.")
    anahtar = (environ if environ is not None else environ_snapshot()).get(NIM_ENV, "").strip()
    if not anahtar:
        raise ImageGenerationError("NVIDIA NIM anahtarı bulunamadı.")
    try:
        if size is None:
            images = await generate_nim_image(nim, prompt, out_dir, api_key=anahtar)
        else:
            images = await generate_nim_image(nim, prompt, out_dir, api_key=anahtar, size=size)
    except NimImageError as error:
        raise ImageGenerationError(str(error)) from error
    return GenerationResult(nim.label, tuple(images))


async def _render_web(
    config: Config, choice: str, prompt: str, out_dir: Path, reference: Path | None
) -> GenerationResult:
    session = next((s for s in config.web_sessions if f"{s.provider}/{s.account}" == choice), None)
    if session is None or session.provider not in IMAGE_SELECTORS:
        raise ImageGenerationError(f"Bilinmeyen sağlayıcı: {choice}")
    registry = web_registry_for(config)
    if registry is None:
        raise ImageGenerationError("Web oturumu kayıt defteri kurulamadı.")
    label = web_label(session.provider, session.account)
    if reference is not None and session.provider not in REFERENCE_PROVIDERS:
        raise ImageGenerationError(f"{label} referans görsel almaz.")
    try:
        images = await generate_images(
            session, registry.credential_for(session), prompt, out_dir, reference=reference
        )
    except WebBrowserError as error:
        raise ImageGenerationError(str(error).removeprefix("authentication: ")) from error
    return GenerationResult(label, tuple(images))
