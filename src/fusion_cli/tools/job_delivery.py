"""İş teslim kaydını kaynak/çıktı hashleriyle taşır; render kalitesini tahmin etmez."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

from ..core.job_evidence import ArtifactReceipt, JobCompletion, JobPhase
from ..core.repair_ledger import SourceFingerprint
from ..core.tools import ToolArgs
from .job_evidence import JobEvidenceManifest, _reject_secret_path, prepare_manifest


def _safe_path(root: Path, raw: str) -> Path:
    original = root / raw
    resolved = original.resolve()
    _reject_secret_path(original, resolved)
    if not resolved.is_relative_to(root.resolve()) or resolved == root.resolve():
        raise ValueError("İş teslim yolu proje içinde bir dosya olmalı.")
    return resolved


def _hash(path: Path) -> str | None:
    if not path.exists():
        return None
    if not path.is_file():
        raise ValueError("İş teslim yolu dosya değil.")
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def prepare_outputs(args: ToolArgs, root: Path) -> tuple[ArtifactReceipt, ...]:
    """Açık beklenen çıktı kapsamını launch öncesi al."""
    values = args.get("expected_outputs", [])
    if not isinstance(values, list) or not all(isinstance(path, str) for path in values):
        raise ValueError("Beklenen çıktılar dosya yolu listesi olmalı.")
    outputs: list[ArtifactReceipt] = []
    for raw in values:
        path = _safe_path(root, raw)
        outputs.append(
            ArtifactReceipt(path.relative_to(root.resolve()).as_posix(), _hash(path), None)
        )
    return tuple(outputs)


def save_delivery(
    folder: Path,
    job_id: str,
    command: str,
    manifest: JobEvidenceManifest | None,
    outputs: tuple[ArtifactReceipt, ...],
) -> JobCompletion:
    """Launch kanıtını süreç başlamadan yaz."""
    before = manifest.sources if manifest is not None else ()
    value = {
        "command": command,
        "sources": [[item.path, item.digest] for item in before],
        "source_scopes": list(manifest.scopes) if manifest is not None else [],
        "outputs": [[item.path, item.before_hash] for item in outputs],
    }
    (folder / f"{job_id}.delivery.json").write_text(json.dumps(value), encoding="utf-8")
    return JobCompletion(
        job_id,
        command,
        JobPhase.STARTED,
        sources_before=before,
        outputs=outputs,
        source_scopes=manifest.scopes if manifest is not None else (),
    )


def _pairs(value: object) -> list[list[str | None]]:
    if not isinstance(value, list):
        raise ValueError("İş teslim manifesti geçersiz.")
    pairs: list[list[str | None]] = []
    for pair in value:
        if not isinstance(pair, list) or len(pair) != 2 or not isinstance(pair[0], str):
            raise ValueError("İş teslim manifesti geçersiz.")
        if pair[1] is not None and not isinstance(pair[1], str):
            raise ValueError("İş teslim hash kaydı geçersiz.")
        pairs.append([pair[0], pair[1]])
    return pairs


def snapshot_delivery(folder: Path, root: Path, job_id: str, code: int | None) -> JobCompletion:
    """Gerçek exit ile kaynak/çıktı kapsamını eşleştir; eksik legacy kayıt sınırlıdır."""
    phase = JobPhase.RUNNING if code is None else JobPhase.COMPLETED
    path = folder / f"{job_id}.delivery.json"
    if not path.exists():
        return JobCompletion(job_id, (folder / f"{job_id}.cmd").read_text(), phase, code)
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("command"), str):
        raise ValueError("İş teslim manifesti geçersiz.")
    before: list[SourceFingerprint] = []
    after: list[SourceFingerprint] = []
    for raw, digest in _pairs(value.get("sources")):
        if raw is None or digest is None:
            raise ValueError("İş kaynak hash kaydı eksik.")
        before.append(SourceFingerprint(raw, digest))
        if code is not None:
            after.append(SourceFingerprint(raw, _hash(_safe_path(root, raw)) or "missing"))
    scopes = value.get("source_scopes", [])
    if scopes and code is not None:
        manifest = prepare_manifest(
            {"failure_check": "completion", "failure_sources": scopes}, root
        )
        if manifest is not None:
            after = list(manifest.sources)
    outputs: list[ArtifactReceipt] = []
    for raw, digest in _pairs(value.get("outputs")):
        if raw is None:
            raise ValueError("İş çıktı yolu eksik.")
        current = _hash(_safe_path(root, raw)) if code is not None else None
        outputs.append(ArtifactReceipt(raw, digest, current))
    return JobCompletion(
        job_id,
        value["command"],
        phase,
        code,
        tuple(before),
        tuple(after),
        tuple(outputs),
        _scopes(value.get("source_scopes", [])),
    )


def save_completion(folder: Path, root: Path, job_id: str, code: int) -> None:
    """Sarmalayıcı süreç exit dosyasından önce tamamlanma anını sabitler."""
    path = folder / f"{job_id}.receipt.json"
    if path.exists():
        return
    result = snapshot_delivery(folder, root, job_id, code)
    value = {
        "command": result.command,
        "exit_code": code,
        "source_scopes": list(result.source_scopes),
        "sources_before": [[item.path, item.digest] for item in result.sources_before],
        "sources_after": [[item.path, item.digest] for item in result.sources_after],
        "outputs": [[item.path, item.before_hash, item.after_hash] for item in result.outputs],
    }
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value), encoding="utf-8")
    temporary.replace(path)


def observe_delivery(folder: Path, root: Path, job_id: str, code: int | None) -> JobCompletion:
    """Polling tamamlanma receipt'ini okur; mevcut diski yeniden ölçmez."""
    if code is None:
        return snapshot_delivery(folder, root, job_id, code)
    path = folder / f"{job_id}.receipt.json"
    if not path.exists():
        if (folder / f"{job_id}.delivery.json").exists():
            if code != 0:
                pending = snapshot_delivery(folder, root, job_id, None)
                return replace(pending, phase=JobPhase.COMPLETED, exit_code=code)
            raise ValueError("İş tamamlanma anı receipt'i yok; sonraki disk kanıt sayılamaz.")
        return JobCompletion(
            job_id, (folder / f"{job_id}.cmd").read_text(), JobPhase.COMPLETED, code
        )
    value = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(value, dict)
        or not isinstance(value.get("command"), str)
        or value.get("exit_code") != code
    ):
        raise ValueError("İş tamamlanma receipt'i geçersiz.")
    before = _source_records(value.get("sources_before"))
    after = _source_records(value.get("sources_after"))
    outputs = _output_records(value.get("outputs"))
    return JobCompletion(
        job_id,
        value["command"],
        JobPhase.COMPLETED,
        code,
        before,
        after,
        outputs,
        _scopes(value.get("source_scopes", [])),
    )


def _source_records(value: object) -> tuple[SourceFingerprint, ...]:
    sources: list[SourceFingerprint] = []
    for raw, digest in _pairs(value):
        if raw is None or digest is None:
            raise ValueError("İş kaynak receipt'i eksik.")
        sources.append(SourceFingerprint(raw, digest))
    return tuple(sources)


def _output_records(value: object) -> tuple[ArtifactReceipt, ...]:
    if not isinstance(value, list):
        raise ValueError("İş çıktı receipt'i geçersiz.")
    receipts: list[ArtifactReceipt] = []
    for record in value:
        if not isinstance(record, list) or len(record) != 3 or not isinstance(record[0], str):
            raise ValueError("İş çıktı receipt'i geçersiz.")
        if not all(item is None or isinstance(item, str) for item in record[1:]):
            raise ValueError("İş çıktı hash receipt'i geçersiz.")
        receipts.append(ArtifactReceipt(record[0], record[1], record[2]))
    return tuple(receipts)


def _scopes(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError("İş kaynak kapsamı geçersiz.")
    return tuple(value)
