"""Ajanın görsel üretme aracı — site/içerik için doğru ölçüde görsel üret ve yerleştir.

Eskiden görsel yalnız masaüstündeki "Görsel oluştur" sayfasından üretilebiliyordu;
ajan bir site yaparken görsel gerekince ya yer tutucu bırakıyor ya da internetten
rastgele adres yazıyordu. Bu araç aynı çekirdeği (`providers/image_generation`)
kullanır ve üç işi tek çağrıda yapar:

1. Üretici seç: ölçüyü parametre olarak alan NIM FLUX önce (hızlı, tarayıcısız,
   doğrulama sayfasına düşmez), yoksa bağlı web oturumu (Gemini).
2. Üreticinin kovasında üret, sonra İSTENEN ölçüye kapla+kırp ve istenen biçimde
   (WebP/AVIF/JPEG/PNG) proje dosyasına yaz. Büyütme ya da kırpma olduysa söylenir.
3. Sayfaya konacak `<img>` önerisini (ölçü, alt metin, yüklenme önceliği, srcset)
   döndür; model onu kopyalayıp yerleştirir.
"""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from ...core.tools import Tool, ToolArgs, ToolContext, ToolResult
from ...providers.image_generation import (
    ImageChoice,
    ImageGenerationError,
    image_choices,
    render_images,
)
from ...providers.nim_image import flux_size_for
from ...tools.files import writable_path
from ...tools.image_ops import ImageFile, ImageOpsError, fit_cover, img_tag, srcset_variants

if TYPE_CHECKING:
    from .loop import AgentDeps

#: Bir kenar için kabul edilen en büyük ölçü. 4096: 4K ekranın uzun kenarı; daha
#: büyüğü web görseli değildir ve kırp/büyüt sonucu bulanıklaşır.
MAX_EDGE = 4096
#: srcset varyantı üretmek için hedefin en az bu genişlikte olması gerekir;
#: daha dar görseller zaten küçüktür.
SRCSET_MIN_WIDTH = 1024

_INT = {"type": "integer", "minimum": 16, "maximum": MAX_EDGE}


def pick_generator(choices: tuple[ImageChoice, ...]) -> ImageChoice | None:
    """Ajan için üretici: tam ölçü kabul eden önce, sonra diğer NIM, sonra web."""
    if not choices:
        return None
    return sorted(choices, key=lambda choice: (not choice.exact_size, choice.reference))[0]


def generate_image_tool(deps: AgentDeps) -> Tool | None:
    """Görsel üretebilen bir sağlayıcı varsa aracı kur; yoksa hiç sunma."""
    generator = pick_generator(image_choices(deps.config))
    if generator is None:
        return None

    async def _run(args: ToolArgs, context: ToolContext) -> ToolResult:
        request = _parse(args)
        if isinstance(request, str):
            return ToolResult.failure(request)
        prompt, width, height, raw_path, alt, eager = request
        target = writable_path(context, raw_path)
        return await _generate(
            deps, generator, prompt, (width, height), target, alt, eager, context
        )

    return Tool(
        name="generate_image",
        description=(
            "Siteye/içeriğe konacak görseli ÜRET ve tam istenen ölçüde proje dosyasına yaz "
            f"(üretici: {generator.label}). Ölçüyü istemde değil width/height ile ver; "
            "uzantı biçimi belirler (.webp önerilir). Sonuçtaki <img> önerisini sayfaya koy. "
            "Bütün görsellerde aynı üslup için markanın renklerini/tonunu istemde tekrarla."
        ),
        parameters={
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "görselin ayrıntılı tarifi"},
                "width": _INT,
                "height": _INT,
                "path": {"type": "string", "description": "yazılacak dosya (ör. assets/hero.webp)"},
                "alt": {"type": "string", "description": "erişilebilir alternatif metin"},
                "ilk_ekran": {
                    "type": "boolean",
                    "description": "sayfanın ilk ekranındaki ana görsel mi (öncelikli yüklenir)",
                },
            },
            "required": ["prompt", "width", "height", "path"],
        },
        run=_run,
        mutating=True,
    )


def _parse(args: ToolArgs) -> tuple[str, int, int, str, str, bool] | str:
    prompt = args.get("prompt")
    path = args.get("path")
    width, height = args.get("width"), args.get("height")
    if not isinstance(prompt, str) or not prompt.strip():
        return "'prompt' boş olmayan bir metin olmalı."
    if not isinstance(path, str) or not path.strip():
        return "'path' boş olmayan bir dosya yolu olmalı (ör. assets/hero.webp)."
    if not isinstance(width, int) or not isinstance(height, int):
        return "'width' ve 'height' tam sayı olmalı."
    if not (0 < width <= MAX_EDGE and 0 < height <= MAX_EDGE):
        return f"Ölçü 1–{MAX_EDGE} piksel aralığında olmalı."
    alt = args.get("alt", "")
    return (
        prompt.strip(),
        width,
        height,
        path.strip(),
        alt if isinstance(alt, str) else "",
        args.get("ilk_ekran") is True,
    )


async def _generate(
    deps: AgentDeps,
    generator: ImageChoice,
    prompt: str,
    size: tuple[int, int],
    target: Path,
    alt: str,
    eager: bool,
    context: ToolContext,
) -> ToolResult:
    width, height = size
    istem = (
        prompt if generator.exact_size else f"{prompt}\n\nGörselin en-boy oranı {width}:{height}."
    )
    workdir = Path(tempfile.mkdtemp(prefix="fusion-gorsel-"))
    try:
        result = await render_images(
            deps.config,
            generator.value,
            istem,
            workdir,
            size=flux_size_for(width, height) if generator.exact_size else None,
        )
        if not result.images:
            return ToolResult.failure(f"{generator.label} görsel döndürmedi.")
        main = await asyncio.to_thread(fit_cover, result.images[0].path, target, width, height)
        variants = (
            await asyncio.to_thread(srcset_variants, target, suffix=target.suffix)
            if width >= SRCSET_MIN_WIDTH
            else ()
        )
    except (ImageGenerationError, ImageOpsError) as error:
        return ToolResult.failure(f"Görsel üretilemedi: {error}")
    finally:
        await asyncio.to_thread(shutil.rmtree, workdir, True)
    context.touched.update({main.path, *(variant.path for variant in variants)})
    return ToolResult(_report(generator, main, variants, alt, eager, context.root))


def _report(
    generator: ImageChoice,
    main: ImageFile,
    variants: tuple[ImageFile, ...],
    alt: str,
    eager: bool,
    root: Path,
) -> str:
    """Modele dönen özet: ne üretildi, nereye yazıldı, sayfaya nasıl konur."""
    notlar: list[str] = []
    if main.upscaled:
        notlar.append(
            "üretici daha küçük üretti, hedefe büyütüldü (yakın bakışta yumuşak olabilir)"
        )
    if main.cropped:
        notlar.append("oran tutmadığı için kenarlar ortadan kırpıldı")
    satirlar = [
        f"Görsel üretildi ({generator.label}): {main.path} — {main.width}×{main.height}, "
        f"{main.bytes // 1024} KB.",
    ]
    if variants:
        satirlar.append(
            "Duyarlı kopyalar: " + ", ".join(f"{v.path.name} ({v.width}w)" for v in variants)
        )
    if notlar:
        satirlar.append("Not: " + "; ".join(notlar) + ".")
    if not alt.strip():
        satirlar.append("Uyarı: alt metin verilmedi; içerik görseliyse anlamlı bir alt yaz.")
    satirlar.append("Sayfaya şöyle yerleştir:")
    satirlar.append(img_tag(main, alt=alt, root=root, eager=eager, variants=variants))
    return "\n".join(satirlar)
