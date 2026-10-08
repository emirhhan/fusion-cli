"""Yakalama kararını tema ilk yazımı ve sonraki değişikliklerden ayıran kanıt.

Bu kayıt görsel başarı ölçmez; etkin tema klasörü çağıran tarafından verilmelidir.
Ham HTML, URL sorgusu, kaynak CSS veya yapılandırma kaydedilmez.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .site_capture import SiteCapture
from .site_responsive import width_conditions
from .woo_theme import ThemeFiles

PROVENANCE_PATH = Path(".fusion/capture-provenance.json")
_TEMPLATE_FILES = frozenset(
    {
        "style.css",
        "kopya.css",
        "functions.php",
        "header.php",
        "footer.php",
        "front-page.php",
        "woocommerce.php",
        "page.php",
        "index.php",
        "responsive.js",
    }
)

_SOURCE_STATUSES = frozenset(
    {
        "no_viewport_contract",
        "verified_source_transition",
        "unverified_source_transition",
    }
)


@dataclass(frozen=True, slots=True)
class CaptureProvenanceCheck:
    """İlk kaydın kararı ve açıkça seçilen tema dosyalarının hash farkı."""

    source_status: str
    has_responsive_transfer: bool
    changed_files: tuple[str, ...]
    missing_files: tuple[str, ...]
    is_original_theme: bool


def _public_path(url: str) -> str:
    """Sorgu ve kişiye özel ödeme rotasını kayda taşıma."""
    path = unquote(urlsplit(url).path) or "/"
    if any(
        part.lower() in {"order-pay", "order-received", "my-account"} for part in path.split("/")
    ):
        return "/[redacted]"
    return path


def _safe_path(root: Path, relative: Path) -> Path:
    """Kayıt ve tema yollarında linkleri ve sır dosyası bileşenlerini reddet."""
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Kanıt yolu proje içinde olmalı.")
    candidate = root
    for part in relative.parts:
        if part.lower().startswith(".env") or part.lower() == "wp-config.php":
            raise ValueError("Sır dosyası kanıt kapsamına alınamaz.")
        candidate = candidate / part
        if candidate.is_symlink():
            raise ValueError("Kanıt yolunda sembolik bağlantı kullanılamaz.")
    return candidate


def _file_hash(root: Path, relative: Path) -> str | None:
    try:
        path = _safe_path(root, relative)
        with path.open("rb") as source:
            return hashlib.file_digest(source, "sha256").hexdigest()
    except (OSError, ValueError):
        return None


def _canonical_query(query: str | None) -> str | None:
    """Doğrulanmış tek genişlik koşulunu güvenli standart biçime getir."""
    if query is None:
        return None
    normalized = query.strip().lower()
    is_negated = normalized.startswith("not all and ")
    body = normalized.removeprefix("not all and ") if is_negated else normalized
    conditions = width_conditions((body,))
    if len(conditions) != 1:
        return None
    condition = conditions[0]
    direction = "max" if condition.is_maximum else "min"
    prefix = "not all and " if is_negated else ""
    return f"{prefix}({direction}-width: {condition.boundary}px)"


def _record(root: Path, capture: SiteCapture, theme: ThemeFiles) -> dict[str, object]:
    """Yalnız sözleşmenin izin verilen alanlarını üret."""
    folder = theme.folder.relative_to(root)
    _safe_path(root, folder)
    primary = capture.pages[0] if capture.pages else None
    variants = primary.variants if primary else ()
    queries = sorted({query for item in variants if (query := _canonical_query(item.media_query))})
    status = "verified_source_transition" if queries else "unverified_source_transition"
    files = {
        name: _file_hash(root, folder / name) for name in sorted(set(theme.files) & _TEMPLATE_FILES)
    }
    return {
        "version": 1,
        "primary_path": _public_path(primary.url) if primary else "/",
        "theme_folder": folder.as_posix(),
        "source_status": status if variants else "no_viewport_contract",
        "viewports": [
            {
                "width": item.width,
                "height": item.height,
                "signature_hash": hashlib.sha256(item.signature.encode()).hexdigest(),
            }
            for item in variants
        ],
        "verified_queries": queries,
        "rejection_count": sum(len(item.blocked) for item in variants)
        + (len(primary.responsive_problems) if primary else 0),
        "responsive_paths": sorted({_public_path(url) for url in theme.responsive_paths}),
        "rejections": [
            {"viewport_width": item.width, "code": "capture_blocked", "count": len(item.blocked)}
            for item in variants
            if item.blocked
        ]
        + (
            [{"code": "responsive_contract_problem", "count": len(primary.responsive_problems)}]
            if primary and primary.responsive_problems
            else []
        ),
        "generated_hashes": files,
    }


def _save(root: Path, capture: SiteCapture, theme: ThemeFiles) -> Path:
    record = _record(root, capture, theme)
    path = _safe_path(root, PROVENANCE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = _safe_path(root, PROVENANCE_PATH.with_suffix(".tmp"))
    temporary.write_text(json.dumps(record, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    temporary.replace(path)
    return path


async def save_capture_provenance(root: Path, capture: SiteCapture, theme: ThemeFiles) -> Path:
    """Tema ilk yazıldığında sınırlı başlangıç kanıtını kalıcılaştır."""
    return await asyncio.to_thread(_save, root, capture, theme)


def _check(root: Path, active_theme: Path) -> CaptureProvenanceCheck:
    record = json.loads(_safe_path(root, PROVENANCE_PATH).read_text(encoding="utf-8"))
    if not isinstance(record, dict) or record.get("version") != 1:
        raise ValueError("Yakalama kanıtı sürümü geçersiz.")
    status = record.get("source_status")
    hashes = record.get("generated_hashes")
    original_folder = record.get("theme_folder")
    paths = record.get("responsive_paths")
    if (
        not isinstance(status, str)
        or status not in _SOURCE_STATUSES
        or not isinstance(hashes, dict)
        or not isinstance(original_folder, str)
        or not isinstance(paths, list)
        or not all(isinstance(path, str) for path in paths)
    ):
        raise ValueError("Yakalama kanıtı şeması geçersiz.")
    folder = active_theme.relative_to(root)
    _safe_path(root, folder)
    _safe_path(root, Path(original_folder))
    changed, missing = [], []
    if not all(isinstance(name, str) and name in _TEMPLATE_FILES for name in hashes):
        raise ValueError("Tema hash kanıtı şeması geçersiz.")
    for name, original in sorted(hashes.items()):
        if name not in _TEMPLATE_FILES or (
            original is not None
            and (not isinstance(original, str) or not re.fullmatch(r"[a-f0-9]{64}", original))
        ):
            raise ValueError("Tema hash kanıtı şeması geçersiz.")
        current = _file_hash(root, folder / name)
        if current is None or original is None:
            missing.append(name)
        elif current != original:
            changed.append(name)
    return CaptureProvenanceCheck(
        status,
        bool(paths),
        tuple(changed),
        tuple(missing),
        folder.as_posix() == original_folder,
    )


async def check_capture_provenance(root: Path, active_theme: Path) -> CaptureProvenanceCheck:
    """Belirtilen etkin temayı ilk hashlerle karşılaştır; dosya veya tema değiştirme."""
    return await asyncio.to_thread(_check, root, active_theme)
