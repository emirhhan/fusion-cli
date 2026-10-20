"""Kayıtlı host kitini dosya araçlarının mutasyonundan önce korur."""

from __future__ import annotations

from pathlib import Path

from ..core.errors import PathAccessError
from ..core.tools import ToolContext


def guard_remotion_write(context: ToolContext, path: Path, raw: str) -> None:
    contract = context.remotion_contract.registered
    if contract is None:
        return
    project = (context.root / contract.project_dir).absolute()
    protected = {project / source.path for source in contract.packaged_sources}
    resolved_protected = {item.resolve() for item in protected}
    original = Path(raw)
    lexical = original if original.is_absolute() else context.root / original
    candidates = (lexical.absolute(), path.absolute(), path.resolve())
    for candidate in candidates:
        if candidate in protected or candidate in resolved_protected:
            _deny()
        for base in (project, project.resolve()):
            kit = base / "src/kit"
            if candidate == kit or (
                candidate.is_relative_to(kit) and candidate != kit / "theme.ts"
            ):
                _deny()
            if candidate.parent == base / "src":
                if candidate.stem == "kit" and candidate.suffix in (".ts", ".tsx", ".js", ".jsx"):
                    _deny()
                if (
                    any(source.path == "src/index.tsx" for source in contract.packaged_sources)
                    and candidate.stem in ("index", "Composition")
                    and candidate.suffix in (".ts", ".js", ".jsx")
                ):
                    _deny()


def _deny() -> None:
    raise PathAccessError(
        "Host Remotion giriş/kit kaynağı sabittir; kapıyı değiştirme. "
        "Sahneyi src/Composition.tsx veya marka temasını src/kit/theme.ts içinde düzelt."
    )
