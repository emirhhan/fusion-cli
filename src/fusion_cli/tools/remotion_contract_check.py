"""Üretim ve doğrulama için ortak değişmez host kit kaynak denetimi."""

from __future__ import annotations

import hashlib
from pathlib import Path

from ..core.remotion_contract import RegisteredKitContract
from .remotion_scaffold import check_kit_shadow


def project_root(root: Path, value: str) -> Path:
    original = Path(value)
    resolved = (root / original).resolve()
    if (
        original.is_absolute()
        or ".." in original.parts
        or "\\" in value
        or not resolved.is_relative_to(root.resolve())
        or any(part.startswith(".env") for path in (original, resolved) for part in path.parts)
    ):
        raise ValueError("Kit projesi sır içermeyen host kökü kapsamında olmalı.")
    return resolved


def check_packaged(root: Path, contract: RegisteredKitContract) -> None:
    check_kit_shadow(root)
    if not contract.packaged_sources:
        raise ValueError("Host paket kit hash kaydı eksik.")
    expected = {source.path for source in contract.packaged_sources} | {"src/kit/theme.ts"}
    kit = project_root(root, "src/kit")
    for path in kit.rglob("*"):
        if path.is_file() and str(path.relative_to(root)) not in expected:
            raise ValueError("Paket kitte gölgeleyici/tanımsız kaynak var.")
    for source in contract.packaged_sources:
        path = project_root(root, source.path)
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != source.digest:
            raise ValueError("Paket kit kaynakları değişti/eksik; özgün kit gerekli.")
