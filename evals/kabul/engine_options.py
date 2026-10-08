"""Seçilmiş motor seçenekleri ve ürün sonucundan ayrı karşılaştırma kanıtı.

Model preflight mevcut executable yolunda kalır; seçilmiş motor doğrulaması
bu modülle tüm koşulların eşitliğini veya yüzde90 gelişimi kanıtlamaz.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from evals.driver_config import validate_wire
from evals.driver_engine import DriverEngine, from_options, validate_receipt


@dataclass(frozen=True, slots=True)
class ComparisonValidity:
    """Yalnız import/config kanıtı; ürün kalitesi ve eş koşulluluk ayrı kalır."""

    schema_version: int = 1
    import_verified: bool = False
    config_verified: bool = False
    reasons: tuple[str, ...] = ()
    source_digest: str | None = None
    config_digests: tuple[str, ...] = ()
    revision_provenance: str = "unverified"
    authentication_status: str = "unknown"
    cache_initial_state: str = "unknown"
    dynamic_context_status: str = "unknown"
    equal_conditions_verified: bool = False
    selected_model_preflight_verified: bool = False


def check_pair(source: Path | None, manifest: Path | None) -> None:
    if (source is None) != (manifest is None):
        raise ValueError("Motor kaynak ve manifest seçenekleri birlikte gerekli.")


def engine_flags(source: Path | None, manifest: Path | None, workdir: Path) -> list[str]:
    check_pair(source, manifest)
    if source is None or manifest is None:
        return []
    return [
        "--engine-source",
        str(source.resolve()),
        "--engine-manifest",
        str(manifest.resolve()),
        "--engine-proof",
        str((workdir / "engine-proof.json").resolve()),
    ]


def selected_engine(
    source: Path | None, manifest: Path | None, workdir: Path
) -> DriverEngine | None:
    check_pair(source, manifest)
    return from_options(
        argparse.Namespace(
            engine_source=str(source) if source is not None else "",
            engine_manifest=str(manifest) if manifest is not None else "",
            engine_proof=str(workdir / "engine-proof.json") if source is not None else "",
        )
    )


def comparison_validity(driver: object, engine: DriverEngine) -> ComparisonValidity:
    """Disk receipt, sürücü receipt ve seçilmiş manifest aynı kimliği göstermeli."""
    try:
        if not isinstance(driver, dict):
            raise ValueError("Sürücü kanıtı yok.")
        disk = json.loads(engine.proof_path.read_text(encoding="utf-8"))
        if not isinstance(disk, dict) or disk != driver.get("motor_kaniti"):
            raise ValueError("Disk/sürücü motor kanıtları eşleşmiyor.")
        pid = disk.get("pid")
        if type(pid) is not int or pid <= 0:
            raise ValueError("Motor süreç kimliği geçersiz.")
        proof = validate_receipt(disk, engine, pid)
    except (ValueError, OSError):
        return ComparisonValidity(reasons=("Motor import kanıtı doğrulanmadı.",))
    try:
        if driver.get("kontrollu_ayar_kaniti") is not True or driver.get("hata"):
            raise ValueError("Kontrollü ayar kanıtı yok.")
        snapshots = driver.get("efektif_kanitlar")
        if not isinstance(snapshots, list) or not snapshots:
            raise ValueError("Efektif snapshot yok.")
        receipts = tuple(validate_wire(item, proof) for item in snapshots)
        if any(receipt.effective.missing_fields for receipt in receipts):
            raise ValueError("Efektif ayar alanları eksik.")
    except ValueError:
        return ComparisonValidity(
            import_verified=True,
            source_digest=proof.source_digest,
            reasons=("Efektif ayar kanıtı eksik/geçersiz.",),
        )
    return ComparisonValidity(
        import_verified=True,
        config_verified=True,
        source_digest=proof.source_digest,
        config_digests=tuple(item.effective.digest for item in receipts),
    )
