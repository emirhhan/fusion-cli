"""Onarım checkpoint'inin içerik taşımayan, doğrulanmış JSON sözleşmesi."""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import cast

from ..core.checkpoint import TurnRepairCheckpoint
from ..core.failure_identity import is_safe_failure_identity
from ..core.repair_ledger import FailureEvidence, FailureOrigin, RepairSnapshot, SourceFingerprint

_DIGEST = re.compile(r"[a-fA-F0-9]{64}\Z")


def _mapping(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict) or not all(isinstance(key, str) for key in raw):
        raise ValueError("Onarım kaydı nesne olmalı.")
    return cast("dict[str, object]", raw)


def _identifier(raw: object, *, root: str = "") -> str:
    if not isinstance(raw, str):
        raise ValueError("Onarım kimliği metin olmalı.")
    checked = raw.removeprefix(root.rstrip("/") + ":") if root else raw
    if not is_safe_failure_identity(checked):
        raise ValueError("Onarım kimliği yalnız kontrol kimliği taşımalı.")
    return raw


def _source(raw: object) -> SourceFingerprint:
    item = _mapping(raw)
    path, digest = item.get("path"), item.get("digest")
    if not isinstance(path, str) or "\\" in path:
        raise ValueError("Onarım kaynak yolu geçersiz.")
    parsed = PurePosixPath(path)
    if (
        parsed.is_absolute()
        or not parsed.parts
        or any(part in {"..", "."} or part.lower().startswith(".env") for part in path.split("/"))
    ):
        raise ValueError("Onarım kaynak yolu özel veya proje dışı olamaz.")
    if not isinstance(digest, str) or not _DIGEST.fullmatch(digest):
        raise ValueError("Onarım kaynağı yalnız SHA-256 özeti taşımalı.")
    return SourceFingerprint(path, digest)


def _failure(raw: object, root: str) -> FailureEvidence:
    item = _mapping(raw)
    sources = item.get("sources")
    if not isinstance(sources, list):
        raise ValueError("Onarım kaynakları liste olmalı.")
    origin = item.get("origin")
    if not isinstance(origin, str):
        raise ValueError("Onarım kökeni metin olmalı.")
    return FailureEvidence(
        _identifier(item.get("check_id"), root=root),
        _identifier(item.get("family")),
        _identifier(item.get("attempt_id")),
        tuple(_source(source) for source in sources),
        FailureOrigin(origin),
    )


def parse_repair(raw: object, root: str) -> TurnRepairCheckpoint | None:
    """Eski checkpoint için hak veya deneme uydurma; bozuk kaydı reddet."""
    if raw is None:
        return None
    item = _mapping(raw)
    count, failures = item.get("verify_rounds"), item.get("failures")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError("Onarım harcaması geçersiz.")
    if not isinstance(failures, list):
        raise ValueError("Onarım denemeleri liste olmalı.")
    records = tuple(_failure(failure, root) for failure in failures)
    keys = {(record.check_id, record.family, record.attempt_id) for record in records}
    if len(keys) != len(records) or any(
        record.origin is not FailureOrigin.PRODUCT for record in records
    ):
        raise ValueError("Onarım kaydı yinelenen veya ürün dışı deneme içeriyor.")
    return TurnRepairCheckpoint(RepairSnapshot(records), count)


def repair_payload(saved: TurnRepairCheckpoint | None, root: str) -> dict[str, object] | None:
    """Yalnız kimlik, kaynak özeti ve tüketimi yaz; not/çıktı/argüman yok."""
    if saved is None:
        return None
    payload: dict[str, object] = {
        "verify_rounds": saved.verify_rounds,
        "failures": [
            {
                "check_id": item.check_id,
                "family": item.family,
                "attempt_id": item.attempt_id,
                "origin": item.origin.value,
                "sources": [
                    {"path": source.path, "digest": source.digest} for source in item.sources
                ],
            }
            for item in saved.snapshot.failures
        ],
    }
    parse_repair(payload, root)
    return payload
