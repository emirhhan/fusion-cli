"""Çalışma dizini tohumlarını tek executor yoluna sınırlı metin olarak hazırla."""

from __future__ import annotations

from fusion_cli.core.errors import EvalError

MAX_SETUP_FILE_BYTES = 1 << 20


def setup_content(value: object) -> str:
    """Metin veya literal/tekrar parçalarından oluşan deterministik tarif."""
    if not isinstance(value, dict):
        return str(value)
    if set(value) != {"segments"} or not isinstance(value["segments"], list):
        raise EvalError("Setup tarifi yalnız segments listesi içermeli.")
    parts: list[str] = []
    total_bytes = 0
    for segment in value["segments"]:
        text, count = _segment(segment)
        total_bytes += len(text.encode("utf-8")) * count
        if total_bytes > MAX_SETUP_FILE_BYTES:
            raise EvalError("Setup tarifi dosya boyutu sınırını aşıyor.")
        parts.append(text * count)
    return "".join(parts)


def _segment(value: object) -> tuple[str, int]:
    if isinstance(value, str):
        return value, 1
    if not isinstance(value, dict) or set(value) != {"repeat", "count"}:
        raise EvalError("Setup parçası metin veya repeat/count tarifi olmalı.")
    text, count = value["repeat"], value["count"]
    if not isinstance(text, str) or type(count) is not int or count < 0:
        raise EvalError("Setup tekrar metni ve negatif olmayan tam sayı gerekli.")
    return text, count
