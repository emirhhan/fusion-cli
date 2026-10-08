"""Üretim başlatmadan açık girdileri donduran, eksikleri gizlemeyen sözleşme.

Bu modül loader, ortam, cache, kimlik deposu veya model okumaz/çağırmaz.
Kanıt özetleri public allowlist receipt'lerine aittir; credential hash'i değildir.
Donmuş girdiler ürün kalitesi, eş koşullu sonuç veya yüzde90 başarı kanıtı olmaz.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, fields
from enum import StrEnum
from pathlib import Path, PurePosixPath

from evals.kabul.model import Area

_DOMAIN_ALIASES = {"site_kopyasi_2": "site_kopyasi"}
_DOMAINS = ("html_oyun", "remotion", "site_kopyasi", "animasyon")
_DIGEST = re.compile(r"[a-f0-9]{64}\Z")
_REVISION = re.compile(r"[a-f0-9]{40}\Z")
_SECRET_NAMES = {
    "credentials",
    "credentials.json",
    "cookies",
    "cookies.json",
    "secrets",
    "secrets.json",
    "wp-config.php",
    "vault",
    "vault.json",
}


class FreezeStatus(StrEnum):
    UNVERIFIED = "unverified"
    FROZEN = "frozen"


@dataclass(frozen=True, slots=True)
class EngineInput:
    role: str
    requested_revision: str
    source_manifest_digest: str
    revision_provenance: str = "unverified"

    def __post_init__(self) -> None:
        if (
            not isinstance(self.role, str)
            or self.role not in {"reference", "current"}
            or self.revision_provenance != "unverified"
        ):
            raise ValueError("Motor rolü veya köken iddiası geçersiz.")
        if not isinstance(self.requested_revision, str) or not _REVISION.fullmatch(
            self.requested_revision
        ):
            raise ValueError("Motor revizyonu tam SHA olmalı.")
        _check_digest(self.source_manifest_digest)


@dataclass(frozen=True, slots=True)
class PublicAsset:
    name: str
    digest: str

    def __post_init__(self) -> None:
        _public_name(self.name)
        _check_digest(self.digest)


@dataclass(frozen=True, slots=True)
class PublicSources:
    root: Path
    allowlist: tuple[str, ...]

    def read(self, name: str) -> bytes:
        """Yalnız açık allowlist; sır, kök dışı veya symlink okuma başlamaz."""
        _public_name(name)
        if name not in self.allowlist:
            raise ValueError("Kaynak public allowlist içinde değil.")
        for candidate in (self.root, self.root.resolve()):
            _secret_parts(candidate.parts)
        path = self.root
        for part in PurePosixPath(name).parts:
            path /= part
            if path.is_symlink():
                raise ValueError("Public kaynak symlink olamaz.")
        if self.root.is_symlink() or not path.resolve().is_relative_to(self.root.resolve()):
            raise ValueError("Public kaynak kök dışına çıkamaz.")
        _secret_parts(path.resolve().parts)
        if not path.is_file():
            raise ValueError("Public kaynak normal dosya olmalı.")
        return path.read_bytes()

    def asset(self, name: str) -> PublicAsset:
        return PublicAsset(name, hashlib.sha256(self.read(name)).hexdigest())


@dataclass(frozen=True, slots=True)
class FreezeEvidence:
    """Her özet önceden hazırlanmış sır taşımayan receipt'in kimliğidir."""

    configuration: str | None = None
    inspection: str | None = None
    rubric: str | None = None
    memory: str | None = None
    authentication: str | None = None
    cache: str | None = None
    dynamic_context: str | None = None
    source_snapshot: str | None = None

    def __post_init__(self) -> None:
        for field in fields(self):
            value = getattr(self, field.name)
            if value is not None:
                _check_digest(value)

    @property
    def missing(self) -> tuple[str, ...]:
        return tuple(field.name for field in fields(self) if getattr(self, field.name) is None)


@dataclass(frozen=True, slots=True)
class FrozenRun:
    run_id: str
    area: str
    variant: str
    engine: EngineInput
    brief: bytes
    brief_digest: str
    timeout_s: float
    viewports: tuple[tuple[int, int], ...]
    assets: tuple[PublicAsset, ...]
    evidence: FreezeEvidence
    missing_inputs: tuple[str, ...]
    original_baseline_provenance: str = "unknown"
    authentication_status: str = "unknown"
    cache_initial_state: str = "unknown"
    dynamic_context_status: str = "unknown"

    @property
    def status(self) -> FreezeStatus:
        return FreezeStatus.UNVERIFIED if self.missing_inputs else FreezeStatus.FROZEN

    @property
    def runnable(self) -> bool:
        return self.status is FreezeStatus.FROZEN


@dataclass(frozen=True, slots=True)
class FrozenMatrix:
    records: tuple[FrozenRun, ...]
    missing_runs: tuple[str, ...]
    problems: tuple[str, ...]

    @property
    def status(self) -> FreezeStatus:
        return (
            FreezeStatus.UNVERIFIED if self.missing_runs or self.problems else FreezeStatus.FROZEN
        )

    @property
    def runnable(self) -> bool:
        return self.status is FreezeStatus.FROZEN


def freeze_run(
    area: Area,
    *,
    run_id: str,
    variant: str,
    engine: EngineInput,
    brief: bytes,
    final_brief: bool,
    viewports: tuple[tuple[int, int], ...],
    assets: tuple[PublicAsset, ...],
    evidence: FreezeEvidence,
) -> FrozenRun:
    """Aynı Area bütçesi; metin normalize edilmez, B taslağı nihai sayılmaz."""
    if (
        not isinstance(variant, str)
        or variant not in {"A", "B"}
        or (engine.role == "reference" and variant != "A")
    ):
        raise ValueError("Koşu rolü/brief varyantı geçersiz.")
    suffix = "refA" if engine.role == "reference" else "cur" + variant
    domain = _DOMAIN_ALIASES.get(area.name, area.name)
    if area.name in _DOMAIN_ALIASES and variant != "B":
        raise ValueError("İkinci site kaynağı yalnız B brief'i olabilir.")
    if domain not in _DOMAINS or run_id != domain + "." + suffix:
        raise ValueError("Koşu kimliği alan/rol/varyant ile eşleşmiyor.")
    _validate_content(area, brief, final_brief, viewports, assets)
    missing = evidence.missing + (() if final_brief else ("final_brief",))
    return FrozenRun(
        run_id,
        area.name,
        variant,
        engine,
        brief,
        hashlib.sha256(brief).hexdigest(),
        float(area.timeout_s),
        viewports,
        tuple(sorted(assets, key=lambda item: item.name)),
        evidence,
        missing,
    )


def _validate_content(
    area: Area,
    brief: bytes,
    final_brief: bool,
    viewports: tuple[tuple[int, int], ...],
    assets: tuple[PublicAsset, ...],
) -> None:
    if not isinstance(brief, bytes) or not brief or type(final_brief) is not bool:
        raise ValueError("Exact brief bytes ve nihai/taslak durumu gerekli.")
    brief.decode("utf-8")
    if (
        type(area.timeout_s) not in {int, float}
        or not math.isfinite(area.timeout_s)
        or area.timeout_s <= 0
    ):
        raise ValueError("Özgün Area bütçesi sonlu ve pozitif olmalı.")
    if (
        not isinstance(viewports, tuple)
        or not viewports
        or any(
            not isinstance(size, tuple)
            or len(size) != 2
            or any(type(n) is not int or n <= 0 for n in size)
            for size in viewports
        )
    ):
        raise ValueError("Viewport boyutları immutable pozitif tam sayı çifti olmalı.")
    if not isinstance(assets, tuple) or not all(isinstance(asset, PublicAsset) for asset in assets):
        raise ValueError("Public varlıklar immutable ve tipli olmalı.")
    if len({asset.name for asset in assets}) != len(assets):
        raise ValueError("Public varlık adları yinelenemez.")


def freeze_matrix(records: tuple[FrozenRun, ...]) -> FrozenMatrix:
    """12 koşu planı; eş A girdiler ve tek motor revizyonu açıkça sınanır."""
    expected = tuple(
        area + "." + suffix for area in _DOMAINS for suffix in ("refA", "curA", "curB")
    )
    by_id = {record.run_id: record for record in records}
    if len(by_id) != len(records) or any(name not in expected for name in by_id):
        raise ValueError("Koşu matrisi kimlikleri yinelenmiş veya beklenmiyor.")
    problems = [record.run_id + ": eksik girdiler" for record in records if record.missing_inputs]
    for role in ("reference", "current"):
        engines = {record.engine for record in records if record.engine.role == role}
        if len(engines) > 1:
            problems.append(role + ": motor girdileri farklı")
    for area in _DOMAINS:
        left, right = by_id.get(area + ".refA"), by_id.get(area + ".curA")
        if (
            left is not None
            and right is not None
            and (left.brief, left.timeout_s, left.viewports, left.assets, left.evidence)
            != (
                right.brief,
                right.timeout_s,
                right.viewports,
                right.assets,
                right.evidence,
            )
        ):
            problems.append(area + ": A girdileri eş değil")
    return FrozenMatrix(
        records, tuple(name for name in expected if name not in by_id), tuple(problems)
    )


def _check_digest(value: object) -> None:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise ValueError("Public kanıt özeti SHA-256 olmalı.")


def _secret_parts(parts: tuple[str, ...]) -> None:
    if any(part.lower().startswith(".env") or part.lower() in _SECRET_NAMES for part in parts):
        raise ValueError("Sır/kimlik kaynağı public girdi olamaz.")


def _public_name(name: object) -> None:
    if not isinstance(name, str) or not name or "\\" in name:
        raise ValueError("Public kaynak adı geçersiz.")
    parts = name.split("/")
    if PurePosixPath(name).is_absolute() or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("Public kaynak göreli ve kök içinde olmalı.")
    _secret_parts(tuple(parts))
