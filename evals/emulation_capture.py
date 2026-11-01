"""Mevcut sondanın açık, sınırlı corpus export'u; normal trafik kaydı yoktur."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from fusion_cli.config.models import Config
from fusion_cli.core.atomic_file import AtomicCommitUncertainError, atomic_create_bytes
from fusion_cli.core.errors import FusionError
from fusion_cli.core.protocols import Clock
from fusion_cli.core.redaction import contains_sensitive
from fusion_cli.core.web_provenance import WebCallContext, safe_observed_identifier
from fusion_cli.engines.emulation_probe import (
    ProbeLimits,
    ProbeReport,
    ProbeScenario,
    probe_emulation,
)
from fusion_cli.providers.web_registry import WebSessionRegistry
from fusion_cli.tools.emulation_corpus import load_expected_call
from fusion_cli.tools.emulation_eval import EvalCase, ExpectedCall

CAPTURE_FILE = "corpus.json"
MANIFEST_MAX_BYTES = 262_144
_FORBIDDEN_PARTS = frozenset({".ssh", ".aws", ".config", ".fusion", ".env", "Keychains"})


@dataclass(frozen=True, slots=True)
class CaptureManifest:
    """Senaryo ve hak beyanı operatörden; kimlikler uygulamadan gelir."""

    model: str
    provider: str
    scenarios: tuple[ProbeScenario, ...]
    limits: ProbeLimits
    source_reference: str
    rights_holder: str
    license_id: str
    split: str
    capture_group: str
    label_review: str
    source_kind: str
    protocol: str

    def validate(self) -> None:
        self.limits.validate(len(self.scenarios))
        if not self.scenarios or not self.model:
            raise ValueError("Model ve en az bir açık senaryo gerekli.")
        if self.split not in {"train", "holdout"} or self.protocol not in {"v1", "v2"}:
            raise ValueError("Kayıt bölümü veya protokol sürümü geçersiz.")
        if self.source_kind not in {"synthetic", "controlled_browser_probe"}:
            raise ValueError("Kaynak türü synthetic veya controlled_browser_probe olmalı.")
        if self.label_review not in {"pending", "reviewed"}:
            raise ValueError("Etiket incelemesi pending veya reviewed olmalı.")
        identifiers = (
            self.provider,
            self.capture_group,
            self.source_reference,
            self.rights_holder,
            self.license_id,
        )
        if any(safe_observed_identifier(item) is None for item in identifiers):
            raise ValueError("Kaynak ve hak kimlikleri sır, kişisel veri veya URL içermemeli.")
        if any(contains_sensitive(item.prompt) for item in self.scenarios):
            raise ValueError("Kontrollü senaryolar sır veya kişisel veri içeremez.")


@dataclass(frozen=True, slots=True)
class CaptureExportResult:
    """Tam yazma ile belirsiz commit birbirinden ayrılır."""

    ok: bool
    path: Path | None = None
    cases: int = 0
    error: str = ""
    is_commit_uncertain: bool = False


def _manifest_text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Kayıt manifestinde {key} metni gerekli.")
    return value


def _load_scenario(value: object) -> ProbeScenario:
    """Liste tek otoritedir; eski dolu etiket yalnız aynı tek çağrıyla birlikte geçer."""
    if not isinstance(value, dict) or set(value) - {
        "prompt",
        "expected_tool",
        "expected_arguments",
        "expected_calls",
    }:
        raise ValueError("Kayıt senaryosu geçersiz alan içeriyor.")
    tool, arguments = value.get("expected_tool"), value.get("expected_arguments")
    has_calls = "expected_calls" in value
    if (not has_calls and "expected_tool" not in value) or (
        tool is not None and (not isinstance(tool, str) or not tool.strip())
    ):
        raise ValueError("Senaryoda bağımsız expected_tool veya expected_calls etiketi gerekli.")
    if arguments is not None and (not isinstance(arguments, dict) or tool is None):
        raise ValueError("Senaryo expected_arguments nesnesi dolu expected_tool gerektirir.")
    expected = None
    if has_calls:
        raw = value["expected_calls"]
        if not isinstance(raw, list):
            raise ValueError("Senaryo expected_calls dizi olmalı.")
        expected = tuple(load_expected_call(item) for item in raw)
        # null eski araç adı, çoklu biçimde boş yer tutucudur; negatif etiket [] olur.
        if tool is not None and (
            len(expected) != 1
            or expected[0].name != tool
            or (arguments is not None and expected[0].arguments != arguments)
        ):
            raise ValueError("Eski etiket ile expected_calls çelişiyor.")
    return ProbeScenario(_manifest_text(value, "prompt"), tool, arguments, expected)


def _load_manifest(path: Path) -> CaptureManifest:
    if path.stat().st_size > MANIFEST_MAX_BYTES:
        raise ValueError("Kayıt manifesti boyut sınırını aşıyor.")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or set(payload) != set(CaptureManifest.__dataclass_fields__):
        raise ValueError("Kayıt manifesti eksik veya bilinmeyen alan içeriyor.")
    limits, scenarios = payload.get("limits"), payload.get("scenarios")
    if not isinstance(limits, dict) or set(limits) != set(ProbeLimits.__dataclass_fields__):
        raise ValueError("Kayıt bütçesi tüm açık sınırları içermeli.")
    if any(
        isinstance(item, bool) or not isinstance(item, (int, float)) for item in limits.values()
    ):
        raise ValueError("Kayıt bütçeleri sayı olmalı.")
    if any(
        not isinstance(limits[key], int)
        for key in ("max_calls", "max_response_bytes", "max_total_bytes")
    ):
        raise ValueError("Çağrı ve bayt bütçeleri tamsayı olmalı.")
    if not isinstance(scenarios, list):
        raise ValueError("Kayıt senaryoları dizi olmalı.")
    text_fields = {
        key: _manifest_text(payload, key) for key in payload if key not in {"limits", "scenarios"}
    }
    manifest = CaptureManifest(
        **text_fields, scenarios=tuple(map(_load_scenario, scenarios)), limits=ProbeLimits(**limits)
    )
    manifest.validate()
    return manifest


async def load_capture_manifest(path: Path) -> CaptureManifest:
    """Canlı yapılandırma/kimlik bilgisi açılmadan yerel manifesti doğrula."""
    return await asyncio.to_thread(_load_manifest, path)


def validate_capture_destination(directory: Path) -> None:
    """Güvenilir seçilmiş parent altında yeni dizin; hostile yarış garantisi vermez."""
    if ".." in directory.parts or any(part in _FORBIDDEN_PARTS for part in directory.parts):
        raise ValueError("Kayıt yolu özel yapılandırma dizini veya üst dizin geçişi içeremez.")
    if directory.exists() or directory.is_symlink():
        raise ValueError("Kayıt için yeni bir çıktı dizini seçilmeli.")
    if not directory.parent.is_dir():
        raise ValueError("Kayıt üst dizini önceden oluşturulmuş olmalı.")
    if any(parent.is_symlink() for parent in directory.parents):
        raise ValueError("Kayıt yolunda sembolik bağ kullanılamaz.")


def _case_payload(
    case: EvalCase, manifest: CaptureManifest, run_id: str, index: int
) -> dict[str, object]:
    expected = case.expected_calls
    if expected is None:
        expected = (
            ()
            if case.expected_tool is None
            else (ExpectedCall(case.expected_tool, case.expected_arguments, case.schema),)
        )
    source_id = f"{run_id}:{index}"
    is_browser = (
        manifest.source_kind == "controlled_browser_probe" and case.web_provenance is not None
    )
    return {
        "case_id": source_id,
        "source_id": source_id,
        "provider": manifest.provider,
        "transport": "browser" if is_browser else "fixture",
        "split": manifest.split,
        "provenance": "recorded" if is_browser else "synthetic",
        "protocol": manifest.protocol,
        "output": case.output,
        "expected_calls": [asdict(call) for call in expected],
        "usage": asdict(case.usage),
        "capture_group": manifest.capture_group,
        "web_provenance": asdict(case.web_provenance) if case.web_provenance else None,
    }


def _bundle(
    report: ProbeReport,
    manifest: CaptureManifest,
    run_id: str,
    captured_at: float,
    selected_model: str | None = None,
    is_controlled_capture: bool = False,
) -> dict[str, object]:
    # Merkezi yardımcı JSON encode'dan ÖNCE yaprak ve anahtarları temizler.
    from fusion_cli.core.redaction import redact_value

    rows: list[object] = []
    has_changes = False
    for index, case in enumerate(report.cases):
        raw = _case_payload(case, manifest, run_id, index)
        cleaned = redact_value(raw)
        assert isinstance(cleaned, dict)
        changed = cleaned != raw
        has_changes = has_changes or changed
        cleaned["capture_receipt"] = {
            "run_id": run_id,
            "source_id": cleaned["source_id"],
            "redaction_status": "changed" if changed else "unchanged",
            "body_digest": hashlib.sha256(str(cleaned["output"]).encode()).hexdigest(),
        }
        rows.append(cleaned)
    return {
        "version": 2,
        "cases": rows,
        "capture_manifest": {
            "run_id": run_id,
            "captured_at": captured_at,
            "requested_model": safe_observed_identifier(manifest.model.rsplit("/", 1)[-1]),
            "selected_model": safe_observed_identifier(selected_model),
            "source_kind": manifest.source_kind,
            "capture_path": "explicit_probe" if is_controlled_capture else "local_export",
            "source_reference": manifest.source_reference,
            "rights_holder": manifest.rights_holder,
            "license_id": manifest.license_id,
            "redistribution": "not_authorized",
            "label_review": manifest.label_review,
            "body_stage": "adapter_preparse_text",
            "redaction_policy": "central-v1",
            "redaction_status": "changed" if has_changes else "unchanged",
            "status": "complete",
            "limits": asdict(manifest.limits),
            "retention_boundary": "after_adapter_allocation",
            "protocol": manifest.protocol,
        },
    }


def _write_bundle(directory: Path, encoded: bytes) -> None:
    validate_capture_destination(directory)
    directory.mkdir(mode=0o700)
    receipt = atomic_create_bytes(directory / CAPTURE_FILE, encoded)
    if not receipt.directory_synced:
        raise AtomicCommitUncertainError("Kayıt kalıcılığı doğrulanamadı.")


async def export_capture(
    report: ProbeReport,
    manifest: CaptureManifest,
    directory: Path,
    *,
    run_id: str,
    captured_at: float,
    selected_model: str | None = None,
    is_controlled_capture: bool = False,
) -> CaptureExportResult:
    """Tek atomik bundle yayımla; yarım/taşmış veya üzerine yazılmış kabul yok."""
    try:
        manifest.validate()
        if safe_observed_identifier(run_id) is None or len(report.cases) != len(manifest.scenarios):
            raise ValueError("Eksik koşu veya geçersiz uygulama kimliği kaydedilemez.")
        if any(
            len(case.output.encode()) > manifest.limits.max_response_bytes for case in report.cases
        ):
            raise ValueError("Tek yanıt saklama bütçesini aşıyor.")
        encoded = json.dumps(
            _bundle(report, manifest, run_id, captured_at, selected_model, is_controlled_capture),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
        if len(encoded) > manifest.limits.max_total_bytes:
            raise ValueError("Artifact toplam bayt bütçesini aşıyor.")
        await asyncio.to_thread(_write_bundle, directory, encoded)
    except AtomicCommitUncertainError:
        return CaptureExportResult(
            False,
            error="Kayıt yayımlanmış olabilir; kalıcılık belirsiz, tekrar edilmedi.",
            is_commit_uncertain=True,
        )
    except (OSError, ValueError, FusionError):
        return CaptureExportResult(False, error="Kayıt doğrulama veya yazma sınırında durduruldu.")
    return CaptureExportResult(True, directory / CAPTURE_FILE, len(report.cases))


async def record_emulation(
    config: Config,
    manifest: CaptureManifest,
    directory: Path,
    *,
    clock: Clock,
    id_factory: Callable[[], str],
    registry: WebSessionRegistry | None = None,
) -> CaptureExportResult:
    """Yalnız manifest senaryolarını mevcut sondayla sor; araç yürütme açılmaz."""
    manifest.validate()
    if registry is not None:
        manifest = replace(manifest, source_kind="synthetic")
    await asyncio.to_thread(validate_capture_destination, directory)
    session = next((item for item in config.web_sessions if item.model == manifest.model), None)
    if session is None or session.provider != manifest.provider or session.transport != "browser":
        raise FusionError("Manifest ile seçilen browser oturumu uyuşmuyor.")
    run_id, session_id, turn_id, attempt_id = (id_factory() for _ in range(4))
    contexts = tuple(
        WebCallContext(session_id, turn_id, attempt_id, id_factory()) for _ in manifest.scenarios
    )
    report = await probe_emulation(
        config,
        manifest.model,
        registry=registry,
        scenarios=manifest.scenarios,
        limits=manifest.limits,
        call_contexts=contexts,
        protocol=manifest.protocol,
    )
    return await export_capture(
        report,
        manifest,
        directory,
        run_id=run_id,
        captured_at=clock.now(),
        selected_model=session.selected_model,
        is_controlled_capture=registry is None,
    )
