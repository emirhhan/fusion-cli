"""Sürümlü kontrol protokolü ve deneme başlangıcı kaynak manifesti."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from ..core.repair_ledger import FailureEvidence, SourceFingerprint
from ..core.tools import ToolArgs

FAILURE_PROTOCOL = "FUSION_FAILURE_V1:"
_SOURCE_SUFFIXES = frozenset(
    {
        ".tsx",
        ".ts",
        ".jsx",
        ".js",
        ".css",
        ".json",
        ".svg",
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".avif",
        ".woff",
        ".woff2",
        ".ttf",
        ".mp4",
        ".mp3",
        ".wav",
    }
)


@dataclass(frozen=True, slots=True)
class JobEvidenceManifest:
    """Kaynak kapsamı çağırandan açıkça gelir; komuttan tahmin edilmez."""

    check_id: str
    sources: tuple[SourceFingerprint, ...]


def _reject_secret_path(original: Path, resolved: Path) -> None:
    """Özgün yol ve bağlantı hedefinin her bileşeninde sır adını reddet."""
    if any(part.startswith(".env") for path in (original, resolved) for part in path.parts):
        raise ValueError("Kaynak kapsamı sır dosyası veya sır dizini içeremez.")


def prepare_manifest(args: ToolArgs, root: Path) -> JobEvidenceManifest | None:
    """İlgili açık dosya/dizin kapsamını süreç başlamadan özetle."""
    check = args.get("failure_check")
    paths = args.get("failure_sources")
    if check is None and paths is None:
        return None
    if not isinstance(check, str) or not check.strip() or not isinstance(paths, list) or not paths:
        raise ValueError("Kontrol kimliği ve ilgili kaynak listesi birlikte gerekli.")
    files: set[Path] = set()
    for raw in paths:
        if not isinstance(raw, str):
            raise ValueError("Kaynak yolları metin olmalı.")
        original_path = root / raw
        path = original_path.resolve()
        _reject_secret_path(original_path, path)
        if not path.is_relative_to(root.resolve()) or path.name.startswith(".env"):
            raise ValueError("Kaynak kapsamı proje içinde olmalı; sır dosyaları kullanılamaz.")
        candidates = path.rglob("*") if path.is_dir() else (path,)
        for candidate in candidates:
            resolved = candidate.resolve()
            _reject_secret_path(candidate, resolved)
            if any(
                part in {"node_modules", ".git", ".venv"}
                for part in candidate.relative_to(root.resolve()).parts
            ):
                continue
            if not resolved.is_relative_to(root.resolve()):
                raise ValueError("Kaynak bağlantısı proje dışına çıkamaz.")
            if candidate.is_file() and candidate.suffix in _SOURCE_SUFFIXES:
                files.add(resolved)
    if not files:
        raise ValueError("Kontrol kapsamında okunabilir kaynak dosyası yok.")
    sources = tuple(
        SourceFingerprint(
            path.relative_to(root.resolve()).as_posix(),
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for path in sorted(files)
    )
    return JobEvidenceManifest(f"{root.resolve().as_posix()}:{check}", sources)


def save_manifest(path: Path, manifest: JobEvidenceManifest) -> None:
    """Yalnız kimlik ve hash yaz; kaynak metni yok."""
    path.write_text(
        json.dumps(
            {
                "check_id": manifest.check_id,
                "sources": [[item.path, item.digest] for item in manifest.sources],
            }
        ),
        encoding="utf-8",
    )


def completed_evidence(folder: Path, attempt: str) -> tuple[FailureEvidence, ...]:
    """Yalnız açık manifestli işin sürümlü JSON kayıtlarını aktar."""
    proof = folder / f"{attempt}.proof.json"
    if not proof.exists():
        return ()
    manifest = json.loads(proof.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or not isinstance(manifest.get("check_id"), str):
        raise ValueError("İş kanıt manifesti geçersiz.")
    sources = manifest.get("sources")
    if not isinstance(sources, list):
        raise ValueError("İş kaynak manifesti geçersiz.")
    fingerprints: list[SourceFingerprint] = []
    for source in sources:
        if (
            not isinstance(source, list)
            or len(source) != 2
            or not all(isinstance(x, str) for x in source)
        ):
            raise ValueError("İş kaynak özeti geçersiz.")
        fingerprints.append(SourceFingerprint(source[0], source[1]))
    families: list[str] = []
    with (folder / f"{attempt}.log").open(encoding="utf-8", errors="replace") as log:
        for line in log:
            _, marker, payload = line.partition(FAILURE_PROTOCOL)
            if not marker:
                continue
            record = json.loads(payload)
            if not isinstance(record, dict) or record.get("version") != 1:
                raise ValueError("Kontrol kanıt sürümü geçersiz.")
            values = record.get("families")
            if (
                not isinstance(values, list)
                or not values
                or not all(isinstance(x, str) and x.strip() for x in values)
            ):
                raise ValueError("Kontrol hata ailesi geçersiz.")
            families.extend(values)
    return tuple(
        FailureEvidence(manifest["check_id"], family, attempt, tuple(fingerprints))
        for family in dict.fromkeys(families)
    )
