"""Açık sahne revizyonu; JSON beyanı değil typed host CAS otoritesi."""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import asdict, replace
from pathlib import Path

from ..core.errors import FusionError
from ..core.remotion_contract import RegisteredKitContract
from ..core.repair_ledger import SourceFingerprint
from ..core.tools import ToolArgs, ToolContext, ToolResult
from .files import atomic_write, writable_path
from .remotion_bootstrap import BOOTSTRAP_ENTRY, bootstrap_source
from .remotion_contract_check import check_packaged, project_root
from .remotion_scaffold import _safe_file, _samples, _scene_plans


async def revise_remotion_scenes(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Aynı toplam sürede açık yeni sahne planı; yeni render/kareler hâlâ gerekli."""
    try:
        replacement = await asyncio.to_thread(_revise, args, context)
    except (OSError, ValueError, FusionError) as error:
        return ToolResult.failure(f"Host sahne revizyonu uygulanamadı: {error}")
    return ToolResult(
        f"Host sahne planı yenilendi: {len(replacement.scenes)} sahne, "
        f"{len(replacement.plan.samples)} örnek kare. Önceki kanıt başarı değildir; "
        "Composition içeriğini bu plana uyarla, yeni render ve tüm kareleri doğrula."
    )


def _replacement(args: ToolArgs, old: RegisteredKitContract) -> RegisteredKitContract:
    if set(args) != {"scenes"}:
        raise ValueError("Revizyon yalnız scenes kabul eder; host girişini model seçemez.")
    scenes = _scene_plans(args)
    if not scenes or sum(scene.duration for scene in scenes) != sum(s.duration for s in old.scenes):
        raise ValueError("Yeni sahneler kayıtlı toplam kare süresini korumalı.")
    if old.plan.entry != BOOTSTRAP_ENTRY or not any(
        source.path == BOOTSTRAP_ENTRY for source in old.packaged_sources
    ):
        raise ValueError("Revizyon için değişmez host bootstrap kaydı gerekli.")
    digest = hashlib.sha256(bootstrap_source(old.plan.composition_id, scenes)).hexdigest()
    sources = tuple(
        SourceFingerprint(source.path, digest) if source.path == BOOTSTRAP_ENTRY else source
        for source in old.packaged_sources
    )
    plan = replace(old.plan, samples=_samples(scenes, old.plan.composition_id))
    return replace(old, plan=plan, scenes=scenes, packaged_sources=sources)


def _revise(args: ToolArgs, context: ToolContext) -> RegisteredKitContract:
    old = context.remotion_contract.registered
    if old is None or context.cancelled.is_set():
        raise ValueError("Etkin host kaydı gerekli; iptal edilmiş oturum revizyon yapamaz.")
    new = _replacement(args, old)
    writable_path(context, old.project_dir)
    root = project_root(context.root, old.project_dir)
    context.remotion_contract.revise(old, new, lambda: _apply(root, old, new, context))
    return new


def _apply(
    root: Path, old: RegisteredKitContract, new: RegisteredKitContract, context: ToolContext
) -> None:
    if context.cancelled.is_set():
        raise ValueError("İptal edilen oturum sahne revizyonu yazamaz.")
    check_packaged(root, old)
    entry, metadata = root / BOOTSTRAP_ENTRY, root / "fusion-contract.json"
    for path in (entry, metadata):
        _safe_file(root, path)
        context.changes.record(path)
    originals = ((entry, entry.read_text()), (metadata, metadata.read_text()))
    if new == old:
        return
    try:
        atomic_write(entry, bootstrap_source(new.plan.composition_id, new.scenes).decode())
        if context.cancelled.is_set():
            raise ValueError("İptal edilen oturum revizyonu durdurdu.")
        atomic_write(metadata, json.dumps(asdict(new), ensure_ascii=False, indent=2))
    except (OSError, ValueError):
        for path, content in originals:
            atomic_write(path, content)
        raise
    context.touched.update((entry, metadata))
