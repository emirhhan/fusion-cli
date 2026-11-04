"""Teslim dosyalarının türüne göre açılabilirlik kontrolü; anlamsal kalite ayrı kalır."""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

from PIL import Image, UnidentifiedImageError

from ...core.artifact_kind import IMAGE_SUFFIXES, artifact_only
from ...core.constants import (
    ARTIFACT_ARCHIVE_MAX_BYTES,
    ARTIFACT_IMAGE_MAX_PIXELS,
    ARTIFACT_INSPECTION_MAX_BYTES,
)
from ...core.evidence import CriterionEvidence, EvidenceStatus
from ...core.execution_plan import VerificationCheckKind
from ...core.tools import ToolContext
from ...core.verification import VerificationResult

FORMAT_TIMEOUT_S = 15.0
TEXT_SUFFIXES = frozenset({".txt", ".md", ".html", ".css", ".js", ".ts", ".py", ".csv", ".svg"})

OFFICE_MEMBERS = {
    ".docx": "word/document.xml",
    ".xlsx": "xl/workbook.xml",
    ".pptx": "ppt/presentation.xml",
}


@dataclass(frozen=True)
class ArtifactInspection:
    problem: str = ""
    warning: str = ""


def inspect_artifact(path: Path) -> ArtifactInspection:
    """Gerçek dosyayı format okuyucusuyla aç; destek yoksa ölçülmedi olarak bildir."""
    try:
        if not path.is_file():
            return ArtifactInspection(problem="Teslim hedefi normal bir dosya değil.")
        size = path.stat().st_size
        if size == 0:
            return ArtifactInspection(problem="Teslim dosyası boş.")
        if size > ARTIFACT_INSPECTION_MAX_BYTES:
            return ArtifactInspection(warning="Dosya biçim inceleme bütçesini aşıyor; ölçülmedi.")
        suffix = path.suffix.lower()
        if suffix in IMAGE_SUFFIXES:
            with Image.open(path) as image:
                if image.width * image.height > ARTIFACT_IMAGE_MAX_PIXELS:
                    return ArtifactInspection(warning="Görsel piksel bütçesini aşıyor; ölçülmedi.")
                image.load()
        elif suffix == ".json":
            json.loads(path.read_text(encoding="utf-8"))
        elif suffix in OFFICE_MEMBERS:
            with zipfile.ZipFile(path) as package:
                members = package.infolist()
                if sum(member.file_size for member in members) > ARTIFACT_ARCHIVE_MAX_BYTES or any(
                    member.file_size > ARTIFACT_INSPECTION_MAX_BYTES for member in members
                ):
                    return ArtifactInspection(warning="Office açılım bütçesini aşıyor; ölçülmedi.")
                if package.testzip() is not None:
                    return ArtifactInspection(problem="Office arşivinin sağlama toplamı bozuk.")
                ElementTree.fromstring(package.read(OFFICE_MEMBERS[suffix]))
        elif suffix == ".pdf":
            return _inspect_pdf(path)
        elif suffix in TEXT_SUFFIXES:
            path.read_text(encoding="utf-8")
        else:
            return ArtifactInspection(warning="Bu dosya türünün açılabilirliği ölçülmedi.")
    except (
        OSError,
        ValueError,
        KeyError,
        zipfile.BadZipFile,
        ElementTree.ParseError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
    ) as error:
        return ArtifactInspection(problem=f"Dosya biçimi okunamadı ({type(error).__name__}).")
    return ArtifactInspection()


def _inspect_pdf(path: Path) -> ArtifactInspection:
    with path.open("rb") as stream:
        if not stream.read(8).startswith(b"%PDF-"):
            return ArtifactInspection(problem="PDF başlığı geçersiz.")
    reader = shutil.which("pdfinfo")
    if reader is None:
        return ArtifactInspection(warning="PDF okuyucu bulunamadı; açılabilirlik ölçülmedi.")
    try:
        result = subprocess.run(
            [reader, str(path)], capture_output=True, timeout=FORMAT_TIMEOUT_S, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return ArtifactInspection(warning="PDF okuyucu çalıştırılamadı; açılabilirlik ölçülmedi.")
    return ArtifactInspection(problem="PDF okuyucu dosyayı açamadı." if result.returncode else "")


async def verify_artifact_changes(context: ToolContext) -> VerificationResult:
    """Görsel/belge görevinde dosyaları aç, görev sonucuna sahte kod kanıtı bağlama."""
    findings: list[str] = []
    warnings: list[str] = []
    for path in context.changes.paths:
        if not path.resolve().is_relative_to(context.root.resolve()):
            findings.append("Teslim dosyası çalışma kökü dışında; okunmadı.")
            continue
        inspection = await asyncio.to_thread(inspect_artifact, path)
        if inspection.problem:
            findings.append(f"{path.name}: {inspection.problem}")
        if inspection.warning:
            warnings.append(f"{path.name}: {inspection.warning}")
    summary = "Görsel / belge dosyası kaydı incelendi; görev sonucu içerik üzerinden ölçülmedi."
    warnings.append(summary)
    return VerificationResult(
        ok=not findings,
        findings=tuple(findings),
        warnings=tuple(warnings),
        evidence=(
            CriterionEvidence(
                criterion_id="artifact_gorev_sonucu",
                kind=VerificationCheckKind.TOOL,
                status=EvidenceStatus.FAILED if findings else EvidenceStatus.UNVERIFIED,
                summary=summary,
            ),
        ),
    )


class ArtifactChangeVerifier:
    """Yalnız artifact değişen turda dosya ve görev sonucu kanıtlarını ayırır."""

    def __init__(self, context: ToolContext) -> None:
        self._context = context

    async def verify(self) -> VerificationResult:
        if not artifact_only(self._context.changes.paths):
            return VerificationResult(ok=True)
        return await verify_artifact_changes(self._context)
