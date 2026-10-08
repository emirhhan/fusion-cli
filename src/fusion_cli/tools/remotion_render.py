"""Değişmez host planını yerel derleyici ve mevcut iş otoritesine bağlar."""

from __future__ import annotations

import asyncio
import os
import shlex
from pathlib import Path

from ..core.errors import FusionError
from ..core.remotion_contract import RegisteredKitContract
from ..core.tools import ToolArgs, ToolContext, ToolResult
from .args import require_list, require_str
from .files import writable_path
from .remotion_contract_check import check_packaged, project_root
from .shell import run_shell


async def render_remotion(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Başlangıç iş kaydı döner; çıkış veya video kalitesi başarısı iddia etmez."""
    try:
        prepared = await asyncio.to_thread(_prepare, args, context)
        return await asyncio.to_thread(_launch, prepared, context)
    except (OSError, ValueError, FusionError) as error:
        return ToolResult.failure(f"Remotion render başlatılamadı: {error}")


def _output(context: ToolContext, raw: str) -> Path:
    original = Path(raw)
    _check_cancelled(context)
    writable_path(context, raw)
    path = project_root(context.root, raw)
    if original.suffix.lower() != ".mp4" or path.exists() or path.is_symlink():
        raise ValueError("Çıktı yeni göreli MP4 dosyası olmalı; var olan dosya ezilmez.")
    _check_cancelled(context)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _executable(path: Path) -> Path:
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError(
            "Mevcut çalıştırılabilir yerel tsc/Remotion/browser gerekli; kurulum yapılmaz."
        )
    return path


def _command(
    root: Path, contract: RegisteredKitContract, output: Path, context: ToolContext
) -> str:
    browser = context.remotion_browser
    if browser is None:
        raise ValueError("Render için trusted host browser seçimi gerekli; model seçemez.")
    tsc = _executable(root / "node_modules/.bin/tsc")
    remotion = _executable(root / "node_modules/.bin/remotion")
    executable = _executable(browser.executable)
    entry = project_root(root, contract.plan.entry)
    if not entry.is_file():
        raise ValueError("Kayıtlı Remotion giriş kaynağı eksik.")
    strict = [
        str(tsc),
        "--noEmit",
        "--strict",
        "--noUnusedLocals",
        "--noUnusedParameters",
        "--jsx",
        "react",
        "--esModuleInterop",
        "--skipLibCheck",
        "--lib",
        "ES2020,DOM",
        "--target",
        "ES2020",
        "--moduleResolution",
        "node",
        str(entry),
    ]
    render = [
        str(remotion),
        "render",
        str(entry),
        contract.plan.composition_id,
        str(output),
        "--browser-executable",
        str(executable),
        f"--chrome-mode={browser.mode}",
    ]
    return f"cd {shlex.quote(str(root))} && {shlex.join(strict)} && {shlex.join(render)}"


def _prepare(args: ToolArgs, context: ToolContext) -> dict[str, object]:
    _check_cancelled(context)
    if set(args) != {"output"}:
        raise ValueError("Render aracı yalnız output kabul eder; plan/browser hosttan gelir.")
    contract = context.remotion_contract.registered
    if contract is None:
        raise ValueError("Önce scaffold_remotion ile host kit planı kaydet.")
    root = project_root(context.root, contract.project_dir)
    check_packaged(root, contract)
    output = _output(context, require_str(args, "output"))
    command = _command(root, contract, output, context)
    sources = [
        str((root / item).relative_to(context.root.resolve())) for item in contract.plan.sources
    ]
    return {
        "command": command,
        "background": True,
        "failure_check": "remotion/render",
        "failure_sources": sources,
        "expected_outputs": [str(output.relative_to(context.root.resolve()))],
    }


def _check_cancelled(context: ToolContext) -> None:
    if context.cancelled.is_set():
        raise ValueError("İptal edilen oturum render başlatamaz.")


def _launch(args: ToolArgs, context: ToolContext) -> ToolResult:
    _check_cancelled(context)
    output = require_list(args, "expected_outputs")[0]
    if not isinstance(output, str):
        raise ValueError("Render çıktı kaydı metin olmalı.")
    writable_path(context, output)
    return run_shell(args, context)
