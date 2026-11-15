"""Model argümanlarını güvenle okuma.

Model JSON üretir; alan eksik, yanlış tipte ya da hiç yok olabilir. Bu yardımcılar
`ArgumentError` fırlatır, kayıt defteri de bunu modele düzeltme şansı veren bir
`ToolResult.failure` mesajına çevirir. Böylece her executor aynı doğrulama kodunu
tekrar yazmaz.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..core.errors import FusionError
from ..core.tools import ToolArgs


class ArgumentError(FusionError):
    """Model aracı yanlış argümanlarla çağırdı."""


def require_str(args: ToolArgs, key: str) -> str:
    value = args.get(key)
    if key not in args:
        # Eksik ile boş AYRI hatalardır. Büyük içerikli çağrılarda (write_file) model
        # küçük alanı sona yazıp bazen hiç üretmiyor; "boş olmalı" demek onu yanlış
        # yönlendirip aynı devasa içeriği körlemesine tekrar ürettiriyordu.
        raise ArgumentError(
            f"'{key}' alanı eksik: çağrıda hiç gönderilmemiş. Aynı çağrıyı '{key}' "
            f"alanını EKLEYEREK tekrarla; büyük alanları yazmadan ÖNCE '{key}' yaz."
        )
    if not isinstance(value, str) or not value.strip():
        raise ArgumentError(f"'{key}' alanı boş olmayan bir metin olmalı.")
    return value


def optional_str(args: ToolArgs, key: str, default: str) -> str:
    value = args.get(key)
    if value is None:
        return default
    if not isinstance(value, str):
        raise ArgumentError(f"'{key}' alanı metin olmalı.")
    return value or default


def require_text(args: ToolArgs, key: str) -> str:
    """Boş olabilen metin (ör. bir dosyayı boşaltmak geçerli bir istektir)."""
    value = args.get(key)
    if not isinstance(value, str):
        raise ArgumentError(f"'{key}' alanı metin olmalı.")
    return value


def require_list(args: ToolArgs, key: str) -> Sequence[object]:
    value = args.get(key)
    if not isinstance(value, list) or not value:
        raise ArgumentError(f"'{key}' alanı boş olmayan bir liste olmalı.")
    return value


def require_positive_int(args: ToolArgs, name: str, *, default: int) -> int:
    """Pozitif tam sayı argümanı oku; yoksa varsayılana düş.

    Taklit araç sözleşmesinde sayılar bazen string gelir ("50"); modelin JSON
    tipini tutturmasını şart koşmak turu boşa harcatır. Geçersiz değer sessizce
    varsayılana düşer — okuma penceresi güvenlik sınırı değil kolaylıktır.
    """
    raw = args.get(name)
    # `True` bir `int`'tir ama "1" demek değildir; sonsuz/NaN float `int()`'te
    # ValueError/OverflowError verir. Üçü de varsayılana düşer (ölçüldü, 30 Ekim).
    if isinstance(raw, bool) or not isinstance(raw, int | float | str):
        return default
    try:
        value = int(raw)
    except (ValueError, OverflowError):
        return default
    return value if value > 0 else default


_TRUE_TEXTS = frozenset({"true", "1", "yes", "evet"})


def is_truthy(value: object) -> bool:
    """Bool bekleyen alan için zayıf model toleransı: `true`, `"true"`, `1`, `"evet"`.

    Ölçüldü (30 Ekim): `replace_all: "true"` sessizce False sayılıyor, çok eşleşme
    hatası "replace_all: true ekleyin" diyor ve model aynı metni yollayıp döngüye giriyordu.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value == 1
    return isinstance(value, str) and value.strip().lower() in _TRUE_TEXTS


def coerce_int(value: object) -> int | None:
    """`5`, `"5"`, `5.0` -> 5; bool, kesirli sayı, ayrıştırılamayan değer -> None.

    Zayıf modeller kimlik/boyut alanlarını metin ya da `.0`'lı sayı olarak yollar;
    sıkı `type(x) is int` her seferinde bir tur kaybettirir (ölçüldü, 30 Ekim).
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None
