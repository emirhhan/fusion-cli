"""Motorun açık kaynak manifesti ve aynı süreçteki import kimliği.

Hash eşleşmesi talep edilen git SHA'sının kökenini kanıtlamaz; bu ayrı ve
bilinmeyen provenance olarak kalır. Yapılandırma veya kimlik deposu okunmaz.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import cast

_DIGEST = re.compile(r"[a-fA-F0-9]{64}\Z")
_REVISION = re.compile(r"[a-fA-F0-9]{40}\Z")


def _safe_path(path: str) -> None:
    parsed = PurePosixPath(path)
    if "\\" in path or parsed.is_absolute() or parsed.parts[:2] != ("src", "fusion_cli"):
        raise ValueError("Motor manifesti yalnız src/fusion_cli dosyalarını içerebilir.")
    if len(parsed.parts) < 3 or any(
        part in {"", ".", "..", "__pycache__"} or part.lower().startswith(".env")
        for part in path.split("/")
    ):
        raise ValueError("Motor manifestinde özel veya geçersiz yol var.")


@dataclass(frozen=True, slots=True)
class SourceDigest:
    """Ham kod yerine açık kaynak dosyasının SHA-256 özeti."""

    path: str
    digest: str

    def __post_init__(self) -> None:
        _safe_path(self.path)
        if not _DIGEST.fullmatch(self.digest):
            raise ValueError("Motor kaynak özeti SHA-256 olmalı.")


@dataclass(frozen=True, slots=True)
class EngineSelection:
    """Çağıranın açık kaynak seçimi; git kökeni doğrulanmış varsayılmaz."""

    source_root: Path
    requested_revision: str
    sources: tuple[SourceDigest, ...]

    def __post_init__(self) -> None:
        if not _REVISION.fullmatch(self.requested_revision):
            raise ValueError("Talep edilen revizyon tam git SHA biçiminde olmalı.")
        if not self.sources or len({source.path for source in self.sources}) != len(self.sources):
            raise ValueError("Motor kaynak manifesti boş veya yinelenen yol içeriyor.")


@dataclass(frozen=True, slots=True)
class ImportedEngineProof:
    """Bootstrap uyumu ve kaynak kimliği; RPC/kalite/auth uyumu değildir."""

    pid: int
    package_file: str
    entry_file: str
    source_root: str
    source_digest: str
    requested_revision: str
    bootstrap_compatible: bool = True
    revision_provenance: str = "unverified"


def _digest(sources: tuple[SourceDigest, ...]) -> str:
    payload = json.dumps(
        [(item.path, item.digest) for item in sorted(sources, key=lambda item: item.path)],
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _checked_file(path: Path, package_root: Path) -> Path:
    resolved = path.resolve()
    if any(
        part.lower().startswith(".env")
        for candidate in (path, resolved)
        for part in candidate.parts
    ):
        raise ValueError("Motor kanıtında sır dosyası veya sır dizini kullanılamaz.")
    if not resolved.is_relative_to(package_root):
        raise ValueError("Motor kaynak bağlantısı seçilmiş paket dışına çıkıyor.")
    return resolved


def verify_source(selection: EngineSelection) -> str:
    """İçe aktarmadan önce dosya kapsamı ve içerik eşitliğini doğrula."""
    root = selection.source_root.resolve()
    package = root / "src/fusion_cli"
    if not package.is_dir() or package.resolve() != package:
        raise ValueError("Seçilmiş motor paketi mevcut değil veya kökü bağlantı.")
    actual: set[str] = set()
    for path in package.rglob("*"):
        if "__pycache__" in path.parts:
            continue
        resolved = _checked_file(path, package)
        if resolved.is_file():
            relative = path.relative_to(root).as_posix()
            _safe_path(relative)
            actual.add(relative)
    expected = {item.path for item in selection.sources}
    if actual != expected:
        raise ValueError("Seçilmiş motorun dosya kapsamı manifestle eşleşmiyor.")
    for source in selection.sources:
        path = _checked_file(root / source.path, package)
        if hashlib.sha256(path.read_bytes()).hexdigest() != source.digest.lower():
            raise ValueError("Seçilmiş motor kaynak hash'i manifestle eşleşmiyor.")
    return _digest(selection.sources)


def _origin(module: object, package: Path) -> Path:
    origin = getattr(module, "__file__", None)
    if not isinstance(origin, str):
        raise ValueError("Motor modülünün dosya kimliği yok.")
    return _checked_file(Path(origin), package)


def verify_imported_engine(
    selection: EngineSelection,
    package_module: object,
    entry_module: object,
    modules: Mapping[str, object],
    *,
    pid: int,
) -> ImportedEngineProof:
    """Çağrılacak main ile aynı süreçteki paket/import kapsamını doğrula."""
    source_digest = verify_source(selection)
    root = selection.source_root.resolve()
    package = root / "src/fusion_cli"
    origin = _origin(package_module, package)
    entry = _origin(entry_module, package)
    if origin != package / "__init__.py" or entry != package / "cli/app.py":
        raise ValueError("Motor paket veya CLI giriş noktası beklenen dosya değil.")
    if not callable(getattr(entry_module, "main", None)):
        raise ValueError("Seçilmiş motorun CLI bootstrap sözleşmesi desteklenmiyor.")
    for name, module in tuple(modules.items()):
        if name == "fusion_cli" or name.startswith("fusion_cli."):
            _origin(module, package)
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        raise ValueError("Motor süreç kimliği geçersiz.")
    return ImportedEngineProof(
        pid, str(origin), str(entry), str(root), source_digest, selection.requested_revision
    )


def selection_from_manifest(root: Path, raw: object) -> EngineSelection:
    """Yalnız izinli manifest alanlarını tipli sözleşmeye al."""
    if (
        not isinstance(raw, dict)
        or isinstance(raw.get("schema_version"), bool)
        or raw.get("schema_version") != 1
    ):
        raise ValueError("Motor kaynak manifesti sürümü desteklenmiyor.")
    mapping = cast("dict[str, object]", raw)
    revision, sources = mapping.get("requested_revision"), mapping.get("sources")
    if not isinstance(revision, str) or not isinstance(sources, list):
        raise ValueError("Motor kaynak manifesti alanları geçersiz.")
    parsed = []
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError("Motor kaynak manifesti kaydı geçersiz.")
        path, digest = source.get("path"), source.get("digest")
        if not isinstance(path, str) or not isinstance(digest, str):
            raise ValueError("Motor kaynak manifesti yolu/hash'i geçersiz.")
        parsed.append(SourceDigest(path, digest))
    return EngineSelection(root, revision, tuple(parsed))
