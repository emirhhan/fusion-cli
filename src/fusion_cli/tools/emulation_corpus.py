"""Mevcut corpus yükleyicisinin kaynak kabulü ve tipli geri okuma sınırı."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

from ..core.types import TokenUsage
from ..core.web_provenance import load_web_provenance
from .emulation_eval import (
    PROVENANCE_VALUES,
    RECORDED_HOLDOUT_CASES,
    RECORDED_SPLITS,
    RECORDED_TRAIN_CASES,
    EvalCase,
    ExpectedCall,
)


def load_corpus(path: Path, *, require_complete: bool = False) -> tuple[EvalCase, ...]:
    """Etiketli corpus'u yükle; gerçek kayıtların kaynağını ve ayrık bölünmesini doğrula."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("version") != 2:
        raise ValueError("Corpus sürümü 2 olmalı.")
    rows = payload.get("cases")
    if not isinstance(rows, list):
        raise ValueError("Corpus cases dizisi içermeli.")
    cases = tuple(
        _admit_case(_load_case(row), row, payload.get("capture_manifest")) for row in rows
    )
    if len({case.case_id for case in cases}) != len(cases):
        raise ValueError("Corpus case_id değerleri benzersiz olmalı.")
    recorded = tuple(case for case in cases if case.provenance == "recorded")
    if len({case.source_id for case in recorded}) != len(recorded):
        raise ValueError("Gerçek kaynak kaydı tekrarlanamaz veya iki bölüme kopyalanamaz.")
    admitted = tuple(case for case in recorded if case.is_admitted)
    groups: dict[str, str] = {}
    for case in admitted:
        if case.capture_group in groups and groups[case.capture_group] != case.split:
            raise ValueError("Aynı yakalama grubu iki bölüme dağıtılamaz.")
        groups[case.capture_group] = case.split
    train = sum(case.split == "train" for case in admitted)
    holdout = sum(case.split == "holdout" for case in admitted)
    if train > RECORDED_TRAIN_CASES or holdout > RECORDED_HOLDOUT_CASES:
        raise ValueError("Gerçek corpus bölünmesi 160 train / 40 holdout sınırını aşıyor.")
    if require_complete and (train != RECORDED_TRAIN_CASES or holdout != RECORDED_HOLDOUT_CASES):
        raise ValueError("Gerçek corpus kabulü için 160 train ve 40 holdout kaydı gerekli.")
    return cases


def _required_text(row: Mapping[str, object], name: str) -> str:
    """Eksik kimlik alanını sessiz varsayılanla doldurma."""
    value = row.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Corpus {name} alanı dolu metin olmalı.")
    return value


def load_expected_call(value: object) -> ExpectedCall:
    """Beklenen çağrı ve nesne argümanlarını doğrula."""
    if not isinstance(value, dict):
        raise ValueError("Beklenen çağrı bir nesne olmalı.")
    arguments, schema = value.get("arguments"), value.get("schema")
    if arguments is not None and not isinstance(arguments, dict):
        raise ValueError("Beklenen arguments bir nesne olmalı.")
    if schema is not None and not isinstance(schema, dict):
        raise ValueError("Beklenen schema bir nesne olmalı.")
    return ExpectedCall(_required_text(value, "name"), arguments, schema)


def _load_case(value: object) -> EvalCase:
    """Sentetik örneği gerçek kayıt diye saymadan tek satırı geri kur."""
    if not isinstance(value, dict):
        raise ValueError("Corpus satırı bir nesne olmalı.")
    identity = {
        name: _required_text(value, name)
        for name in (
            "case_id",
            "provider",
            "transport",
            "split",
            "provenance",
        )
    }
    provenance = identity["provenance"]
    if provenance not in PROVENANCE_VALUES:
        raise ValueError("Corpus provenance synthetic veya recorded olmalı.")
    source_id = ""
    if provenance == "recorded":
        source_id = _required_text(value, "source_id")
        if identity["split"] not in RECORDED_SPLITS or any(
            identity[name] in {"unknown", "synthetic"} for name in ("provider", "transport")
        ):
            raise ValueError("Gerçek kaydın sağlayıcısı, taşıması ve train/holdout bölümü gerekli.")
    output = value.get("output")
    expected = value.get("expected_calls")
    if not isinstance(output, str) or not isinstance(expected, list):
        raise ValueError("Corpus output metni ve expected_calls dizisi gerekli.")
    usage = _load_usage(value.get("usage"))
    return EvalCase(
        output=output,
        expected_tool=None,
        expected_calls=tuple(load_expected_call(item) for item in expected),
        case_id=identity["case_id"],
        provider=identity["provider"],
        transport=identity["transport"],
        split=identity["split"],
        provenance=provenance,
        source_id=source_id,
        usage=usage,
        protocol=_load_protocol(value.get("protocol", "v1")),
        web_provenance=load_web_provenance(value.get("web_provenance")),
        capture_group=str(value.get("capture_group", "")),
    )


def _load_usage(value: object) -> TokenUsage:
    """Ölçümün otoritesi yalnız TokenUsage bayraklarıdır; eksik değer bilinmiyor kalır."""
    if value is None:
        return TokenUsage()
    if not isinstance(value, dict):
        raise ValueError("Corpus usage bir nesne olmalı.")
    prompt, completion, cost = (
        value.get("prompt_tokens", 0),
        value.get("completion_tokens", 0),
        value.get("cost_usd", 0.0),
    )
    if (
        not isinstance(prompt, int)
        or isinstance(prompt, bool)
        or prompt < 0
        or not isinstance(completion, int)
        or isinstance(completion, bool)
        or completion < 0
        or not isinstance(cost, (float, int))
        or isinstance(cost, bool)
        or cost < 0
    ):
        raise ValueError("Corpus usage negatif olmayan sayılar içermeli.")
    for flag, metric in (
        ("prompt_measured", "prompt_tokens"),
        ("completion_measured", "completion_tokens"),
        ("cost_known", "cost_usd"),
    ):
        if flag in value and not isinstance(value[flag], bool):
            raise ValueError("Corpus usage ölçüm bayrakları boolean olmalı.")
        if value.get(flag) is True and metric not in value:
            raise ValueError("Corpus ölçülmüş usage değeri eksik.")
    return TokenUsage(
        prompt_tokens=prompt,
        completion_tokens=completion,
        cost_usd=float(cost),
        prompt_measured=value.get("prompt_measured") is True,
        completion_measured=value.get("completion_measured") is True,
        cost_known=value.get("cost_known") is True,
    )


def _load_protocol(value: object) -> str:
    """Corpus şema sürümüyle araç protokol sürümünü karıştırma."""
    if value not in ("v1", "v2"):
        raise ValueError("Corpus araç protokolü v1 veya v2 olmalı.")
    return str(value)


def _admit_case(case: EvalCase, row: object, manifest: object) -> EvalCase:
    """Schema-valid recorded beyanı genuine kanıt değildir; yakalama receipt'i gerekir."""
    if case.provenance != "recorded" or not isinstance(row, dict) or not isinstance(manifest, dict):
        return case
    receipt = row.get("capture_receipt")
    origin = case.web_provenance
    if not isinstance(receipt, dict) or origin is None:
        return case
    required = {
        "source_kind": "controlled_browser_probe",
        "capture_path": "explicit_probe",
        "body_stage": "adapter_preparse_text",
        "redaction_policy": "central-v1",
        "label_review": "reviewed",
        "status": "complete",
    }
    is_manifest_valid = all(manifest.get(key) == item for key, item in required.items())
    is_source_valid = all(
        isinstance(manifest.get(key), str)
        and bool(manifest[key])
        and manifest[key] not in {"unknown", "pending"}
        for key in ("run_id", "source_reference", "license_id", "rights_holder")
    )
    is_receipt_valid = (
        receipt.get("run_id") == manifest.get("run_id")
        and receipt.get("source_id") == case.source_id
        and receipt.get("redaction_status") == "unchanged"
        and receipt.get("body_digest") == hashlib.sha256(case.output.encode()).hexdigest()
    )
    is_origin_valid = (
        origin.provider_id == case.provider
        and case.transport == "browser"
        and origin.has_current_assistant_origin(origin.call_context)
        and bool(origin.selector_bundle_digest and origin.adapter_revision)
    )
    return replace(
        case,
        is_admitted=bool(
            is_manifest_valid
            and is_source_valid
            and is_receipt_valid
            and is_origin_valid
            and case.capture_group
        ),
    )
