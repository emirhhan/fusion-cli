"""Kit kopyasını ve açık sahne beklentisini üretimden önce hostta sabitler."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from ..config.paths import bundled_skills_dir
from ..core.errors import FusionError
from ..core.remotion_contract import (
    KitFramePlan,
    KitScenePlan,
    KitVerificationPlan,
    RegisteredKitContract,
)
from ..core.repair_ledger import SourceFingerprint
from ..core.tools import ToolArgs, ToolContext, ToolResult
from .args import require_list, require_str
from .files import writable_path

_IDENTIFIER = re.compile(r"[A-Za-z0-9_-]+")


@dataclass(frozen=True, slots=True)
class _KitFile:
    name: str
    content: bytes


async def scaffold_remotion(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Var olan dosyayı ezmeden kit kur; JSON'a değil oturum kaydına güven."""
    try:
        contract = await asyncio.to_thread(_install, args, context)
        context.remotion_contract.register(contract)
    except (OSError, ValueError, FusionError) as error:
        return ToolResult.failure(f"Remotion kit iskelesi kurulamadı: {error}")
    return ToolResult(
        f"Kit hazır: {contract.project_dir}/src/kit; host sözleşmesi kayıtlı. "
        f"{len(contract.scenes)} sahne, {len(contract.plan.samples)} örnek kare. "
        "src/index.ts ve Composition'u bu planla oluştur; kit içini kopyalama/değiştirme. "
        "Bu kayıt render veya kalite başarısı değildir."
    )


def _scene_plans(args: ToolArgs) -> tuple[KitScenePlan, ...]:
    scenes = []
    for raw in require_list(args, "scenes"):
        if not isinstance(raw, dict):
            raise ValueError("Her sahne id/kind/duration nesnesi olmalı.")
        if set(raw) - {"id", "kind", "duration"}:
            raise ValueError("Sahne yalnız id/kind/duration alanlarını kabul eder.")
        scene_id, kind, duration = raw.get("id"), raw.get("kind"), raw.get("duration")
        if (
            not isinstance(scene_id, str)
            or not _IDENTIFIER.fullmatch(scene_id)
            or kind not in ("feature", "custom")
            or type(duration) is not int
            or duration <= 0
        ):
            raise ValueError("Sahne kimliği, türü ve pozitif tam kare süresi gerekli.")
        scenes.append(KitScenePlan(scene_id, str(kind), duration))
    if len({scene.scene_id for scene in scenes}) != len(scenes):
        raise ValueError("Sahne kimlikleri benzersiz olmalı.")
    return tuple(scenes)


def _target(args: ToolArgs, context: ToolContext) -> Path:
    raw = require_str(args, "path")
    original = Path(raw)
    target = writable_path(context, raw).resolve()
    if (
        original.is_absolute()
        or ".." in original.parts
        or "\\" in raw
        or not target.is_relative_to(context.root.resolve())
        or any(part.startswith(".env") for path in (original, target) for part in path.parts)
    ):
        raise ValueError("Kit hedefi sır içermeyen göreli proje dizini olmalı.")
    return target


def _samples(scenes: tuple[KitScenePlan, ...], composition: str) -> tuple[KitFramePlan, ...]:
    samples = []
    start = 0
    for scene in scenes:
        # İlk/orta/son kareler süreye göre türetilir; kısa sahnede tekrar edilmez.
        for frame in dict.fromkeys(
            (start, start + scene.duration // 2, start + scene.duration - 1)
        ):
            samples.append(
                KitFramePlan(
                    frame,
                    scene.scene_id,
                    f".fusion-proof/{composition}-{scene.scene_id}-{frame}.png",
                    scene.kind == "feature",
                )
            )
        start += scene.duration
    return tuple(samples)


def _kit_files() -> tuple[_KitFile, ...]:
    folder = bundled_skills_dir() / "remotion-video/kit"
    return tuple(
        _KitFile(str(path.relative_to(folder)), path.read_bytes())
        for path in sorted(folder.rglob("*"))
        if path.is_file()
    )


def _contract(
    args: ToolArgs, context: ToolContext, target: Path, files: tuple[_KitFile, ...]
) -> RegisteredKitContract:
    composition = require_str(args, "composition_id")
    timeout = args.get("timeout_s")
    if (
        not _IDENTIFIER.fullmatch(composition)
        or type(timeout) not in (int, float)
        or not isinstance(timeout, int | float)
        or not math.isfinite(timeout)
        or timeout <= 0
    ):
        raise ValueError("Composition kimliği ve sonlu pozitif süre gerekli.")
    scenes = _scene_plans(args)
    plan = KitVerificationPlan(
        "src/index.ts",
        composition,
        ("src", "public", "package.json"),
        float(timeout),
        _samples(scenes, composition),
    )
    hashes = tuple(
        SourceFingerprint(f"src/kit/{file.name}", hashlib.sha256(file.content).hexdigest())
        for file in files
        if file.name != "theme.ts"
    )
    return RegisteredKitContract(
        plan, scenes, hashes, str(target.relative_to(context.root.resolve()))
    )


def _preflight(target: Path, files: tuple[_KitFile, ...], payload: bytes) -> None:
    kit = target / "src/kit"
    expected = {file.name for file in files}
    for existing in kit.rglob("*"):
        if existing.is_file() and str(existing.relative_to(kit)) not in expected:
            raise ValueError("Paket kitte tanımsız dosya var; korunuyor, sözleşme kaydedilmez.")
    for file in files:
        path = target / "src/kit" / file.name
        _safe_file(target, path)
        if path.exists() and file.name != "theme.ts" and path.read_bytes() != file.content:
            raise ValueError(f"Mevcut kit dosyası farklı; üzerine yazılmaz: {file.name}")
    check_kit_shadow(target)
    metadata = target / "fusion-contract.json"
    _safe_file(target, metadata)
    if metadata.exists() and metadata.read_bytes() != payload:
        raise ValueError("Mevcut sözleşme JSON'u farklı; üzerine yazılmaz.")


def check_kit_shadow(project: Path) -> None:
    """İskele ve kapanışın aynı worker I/O sınırında import gölgesini reddet."""
    for suffix in (".ts", ".tsx", ".js", ".jsx"):
        if (project / "src" / f"kit{suffix}").exists():
            raise ValueError("src/kit adını gölgeleyen mevcut modül var; korunuyor.")


def _safe_file(target: Path, path: Path) -> None:
    resolved = path.resolve()
    if not resolved.is_relative_to(target) or any(
        part.startswith(".env") for item in (path, resolved) for part in item.parts
    ):
        raise ValueError("Kit dosyası bağlantıyla proje dışına veya sır yoluna çıkamaz.")


def _install(args: ToolArgs, context: ToolContext) -> RegisteredKitContract:
    if context.cancelled.is_set():
        raise ValueError("İptal edilen oturum kit oluşturamaz.")
    target, files = _target(args, context), _kit_files()
    contract = _contract(args, context, target, files)
    previous = context.remotion_contract.registered
    if previous is not None and previous != contract:
        raise ValueError("Bu oturumda farklı kit sözleşmesi zaten kayıtlı.")
    payload = json.dumps(asdict(contract), ensure_ascii=False, indent=2).encode()
    _preflight(target, files, payload)
    writes = [(target / "src/kit" / file.name, file.content) for file in files]
    writes.append((target / "fusion-contract.json", payload))
    for path, content in writes:
        if context.cancelled.is_set():
            raise ValueError("İptal edilen oturum kit yazımını durdurdu.")
        if path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        context.changes.record(path)
        with path.open("xb") as stream:
            stream.write(content)
        context.touched.add(path)
    return contract
