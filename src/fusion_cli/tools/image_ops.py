"""Görsel dosyası işlemleri — tam ölçüye getirme ve duyarlı (srcset) varyantlar.

Saf ve senkrondur; ağ görmez. Pillow ağır bir bağımlılıktır ve yalnız görsel işi
olan turda gerekir, bu yüzden fonksiyon içinde tembel yüklenir.

Neden "kapla ve kırp" (cover): üreticiler sabit oran kovalarıyla çalışır
(FLUX ~1 MP). 1920×1080 bir hero alanına 1344×768 üretilen görsel ölçeklenip
taşan kenarı ortadan kırpılır; görsel bozulmaz (germe yok), boşluk kalmaz.
Kırpma ve büyütme yapıldıysa sonuç bunu AÇIKÇA söyler.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from ..core.tools import ToolArgs, ToolContext, ToolResult

if TYPE_CHECKING:
    from PIL.Image import Image as PilImage

#: Kayıpsız olmayan biçimlerin kalitesi. 82: WebP/JPEG'de gözle fark edilmeyen
#: kaybın üst sınırı olarak yaygın kabul gören değer (web.dev görsel rehberi
#: 75-85 aralığını önerir); AVIF aynı ölçekte daha küçük dosya verir.
DEFAULT_QUALITY = 82
#: Desteklenen çıkış biçimleri: uzantı → Pillow biçim adı.
FORMATS: dict[str, str] = {
    ".webp": "WEBP",
    ".avif": "AVIF",
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".png": "PNG",
}
#: srcset için varsayılan genişlikler: telefon, tablet, dizüstü, geniş ekran.
DEFAULT_SRCSET_WIDTHS: tuple[int, ...] = (640, 1024, 1600)


class ImageOpsError(RuntimeError):
    """Görsel işlenemedi; mesaj modele gösterilir."""


@dataclass(frozen=True, slots=True)
class ImageFile:
    path: Path
    width: int
    height: int
    bytes: int
    #: Kaynak hedef ölçüden küçüktü ve büyütüldü mü?
    upscaled: bool = False
    #: Oran uymadığı için kenar kırpıldı mı?
    cropped: bool = False


def _require_pillow() -> None:
    """Pillow yoksa anlaşılır hata (paket bağımlılıktır; eksikse kurulum bozuktur)."""
    try:
        import PIL  # noqa: F401 - yalnız varlık denetimi
    except ImportError as error:  # pragma: no cover - paket kurulumuna bağlı
        raise ImageOpsError("Görsel işleme için Pillow gerekli: `pip install pillow`.") from error


def output_format(path: Path) -> str:
    """Uzantıdan Pillow biçimi; desteklenmiyorsa açık hata."""
    fmt = FORMATS.get(path.suffix.lower())
    if fmt is None:
        izinli = ", ".join(sorted(FORMATS))
        raise ImageOpsError(f"Desteklenmeyen görsel uzantısı: {path.suffix}. İzinli: {izinli}")
    return fmt


def fit_cover(
    source: Path, target: Path, width: int, height: int, *, quality: int = DEFAULT_QUALITY
) -> ImageFile:
    """Kaynağı tam `width×height` ölçüye getir (kapla + ortadan kırp) ve kaydet."""
    if width <= 0 or height <= 0:
        raise ImageOpsError("Genişlik ve yükseklik pozitif olmalı.")
    _require_pillow()
    from PIL import Image, ImageOps

    fmt = output_format(target)
    with Image.open(source) as opened:
        image = ImageOps.exif_transpose(opened)
        upscaled = image.width < width or image.height < height
        cropped = image.width * height != image.height * width
        fitted = ImageOps.fit(image, (width, height), method=Image.Resampling.LANCZOS)
    return _save(fitted, target, fmt, quality, upscaled=upscaled, cropped=cropped)


def srcset_variants(
    source: Path,
    widths: tuple[int, ...] = DEFAULT_SRCSET_WIDTHS,
    *,
    suffix: str = ".webp",
    quality: int = DEFAULT_QUALITY,
) -> tuple[ImageFile, ...]:
    """Kaynaktan daha dar genişliklerde kopyalar üret (büyütme YAPILMAZ)."""
    _require_pillow()
    from PIL import Image

    fmt = output_format(Path(f"x{suffix}"))
    variants: list[ImageFile] = []
    with Image.open(source) as opened:
        image = opened.convert("RGBA") if fmt == "PNG" else opened.convert("RGB")
        for width in sorted(set(widths)):
            if width >= image.width:
                continue
            height = round(image.height * width / image.width)
            resized = image.resize((width, height), Image.Resampling.LANCZOS)
            target = source.with_name(f"{source.stem}-{width}w{suffix}")
            variants.append(_save(resized, target, fmt, quality))
    return tuple(variants)


def describe(path: Path) -> ImageFile:
    """Var olan bir görselin ölçüsü ve boyutu."""
    _require_pillow()
    from PIL import Image

    with Image.open(path) as image:
        return ImageFile(path, image.width, image.height, path.stat().st_size)


def img_tag(
    main: ImageFile, *, alt: str, root: Path, eager: bool, variants: tuple[ImageFile, ...] = ()
) -> str:
    """Sayfaya konacak `<img>` önerisi: ölçü, alt metin, yüklenme önceliği, srcset."""
    src = _relative(main.path, root)
    parts = [
        f'src="{src}"',
        f'width="{main.width}"',
        f'height="{main.height}"',
        f'alt="{_attr(alt)}"',
    ]
    if variants:
        adaylar = [f"{_relative(v.path, root)} {v.width}w" for v in variants]
        adaylar.append(f"{src} {main.width}w")
        parts.append(f'srcset="{", ".join(adaylar)}"')
        parts.append('sizes="(max-width: 768px) 100vw, 50vw"')
    parts.append(
        'loading="eager" fetchpriority="high"' if eager else 'loading="lazy" decoding="async"'
    )
    return "<img " + " ".join(parts) + ">"


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _attr(text: str) -> str:
    return text.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")


def _save(
    image: PilImage,
    target: Path,
    fmt: str,
    quality: int,
    *,
    upscaled: bool = False,
    cropped: bool = False,
) -> ImageFile:
    target.parent.mkdir(parents=True, exist_ok=True)
    kayit = image if fmt == "PNG" or image.mode in ("RGB", "L") else image.convert("RGB")
    options: dict[str, object] = {} if fmt == "PNG" else {"quality": quality}
    if fmt == "PNG":
        options["optimize"] = True
    kayit.save(target, fmt, **options)
    return ImageFile(
        target, kayit.width, kayit.height, target.stat().st_size, upscaled=upscaled, cropped=cropped
    )


def optimize_image(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Var olan görseli web için hazırla: isteğe bağlı tam ölçü + srcset kopyaları."""
    from .args import optional_str, require_str
    from .files import resolve_path, writable_path

    source = resolve_path(context, require_str(args, "path"))
    if not source.is_file():
        return ToolResult.failure(f"Görsel bulunamadı: {source}")
    target = writable_path(
        context, optional_str(args, "out", "") or str(source.with_suffix(".webp"))
    )
    width, height = args.get("width"), args.get("height")
    try:
        if isinstance(width, int) and isinstance(height, int):
            main = fit_cover(source, target, width, height)
        else:
            main = _convert(source, target)
        variants = srcset_variants(target, suffix=target.suffix)
    except (ImageOpsError, OSError) as error:
        return ToolResult.failure(f"Görsel işlenemedi: {error}")
    context.touched.update({main.path, *(variant.path for variant in variants)})
    eager = args.get("ilk_ekran") is True
    alt = optional_str(args, "alt", "")
    return ToolResult(
        f"Hazır: {main.path} — {main.width}×{main.height}, {main.bytes // 1024} KB "
        f"(kaynak {source.stat().st_size // 1024} KB).\n"
        + img_tag(main, alt=alt, root=context.root, eager=eager, variants=variants)
    )


def _convert(source: Path, target: Path) -> ImageFile:
    """Ölçüyü değiştirmeden biçim dönüştür (ör. PNG → WebP)."""
    _require_pillow()
    from PIL import Image, ImageOps

    fmt = output_format(target)
    with Image.open(source) as opened:
        image = ImageOps.exif_transpose(opened)
        image.load()
    return _save(image, target, fmt, DEFAULT_QUALITY)
