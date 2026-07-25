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
