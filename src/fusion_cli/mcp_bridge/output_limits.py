"""MCP araç çıktı sınırları — Claude Code "MCP output limits and warnings" (#240).

- 10.000 token üstü uyarı; varsayılan sınır 25.000 token (`MAX_MCP_OUTPUT_TOKENS`).
- Sınırı aşan ya da 50.000 karakterden uzun BAŞARILI metin sonucu dosyaya kaydedilir;
  modele dosya yolu ve kısa önizleme verilir, içerik kaybolmaz.
- Araç `_meta["anthropic/maxResultSizeChars"]` ile metin sınırını en çok 500.000 karaktere
  çıkarabilir (bu durumda token sınırı yerine o karakter sınırı uygulanır).
- `isError` metni ~11.000 karakteri aşarsa ilk 5.000 ve son 5.000 karakter tutulur.

Token sayısı yaklaşık hesaplanır (4 karakter ≈ 1 token).
"""

from __future__ import annotations

import logging
import os
import uuid
from collections.abc import Mapping
from pathlib import Path

_LOG = logging.getLogger(__name__)

WARN_TOKENS = 10_000
DEFAULT_MAX_TOKENS = 25_000
SAVE_OVER_CHARS = 50_000
MAX_DECLARED_CHARS = 500_000
ERROR_KEEP_OVER_CHARS = 11_000
ERROR_HEAD_TAIL = 5_000
PREVIEW_CHARS = 2_000
CHARS_PER_TOKEN = 4
MAX_TOKENS_ENV = "MAX_MCP_OUTPUT_TOKENS"
RESULT_SIZE_META = "anthropic/maxResultSizeChars"


def max_tokens(environ: Mapping[str, str] | None = None) -> int:
    raw = (os.environ if environ is None else environ).get(MAX_TOKENS_ENV, "").strip()
    return int(raw) if raw.isdigit() and int(raw) > 0 else DEFAULT_MAX_TOKENS


def declared_limit(meta: object) -> int | None:
    """Araç tanımındaki `_meta` sınırı (en çok 500.000); yoksa None."""
    if not isinstance(meta, Mapping):
        return None
    value = meta.get(RESULT_SIZE_META)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return min(value, MAX_DECLARED_CHARS)


def results_dir() -> Path:
    from ..config.paths import base_data_dir

    return base_data_dir() / "tool-results"


def limit_output(
    text: str,
    *,
    ok: bool,
    declared_chars: int | None = None,
    environ: Mapping[str, str] | None = None,
    directory: Path | None = None,
) -> str:
    """Çıktıyı Claude Code sınırlarıyla modele uygun hâle getir."""
    if not ok:
        if len(text) <= ERROR_KEEP_OVER_CHARS:
            return text
        dropped = len(text) - 2 * ERROR_HEAD_TAIL
        return (
            f"{text[:ERROR_HEAD_TAIL]}\n[… {dropped} karakter gösterilmedi …]\n"
            f"{text[-ERROR_HEAD_TAIL:]}"
        )
    tokens = len(text) // CHARS_PER_TOKEN
    if tokens > WARN_TOKENS:
        _LOG.warning("MCP araç çıktısı büyük: ~%d token", tokens)
    if declared_chars is not None:
        too_big = len(text) > declared_chars
    else:
        too_big = tokens > max_tokens(environ) or len(text) > SAVE_OVER_CHARS
    if not too_big:
        return text
    path = _save(text, directory or results_dir())
    return (
        f"[MCP araç çıktısı çok büyük ({len(text)} karakter, ~{tokens} token); tamamı dosyaya "
        f"kaydedildi: {path}. Gerekli kısımları dosya okuma araçlarıyla oku.]\n\n"
        f"Önizleme:\n{text[:PREVIEW_CHARS]}"
    )


def _save(text: str, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"mcp-{uuid.uuid4().hex}.txt"
    path.write_text(text, encoding="utf-8")
    os.chmod(path, 0o600)
    return path
