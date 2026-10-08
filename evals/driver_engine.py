"""Seçilmiş çekirdek için açık seçenekler ve aynı süreç receipt doğrulaması."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from evals.engine_proof import (
    EngineSelection,
    ImportedEngineProof,
    selection_from_manifest,
    verify_source,
)


@dataclass(frozen=True, slots=True)
class DriverEngine:
    selection: EngineSelection
    manifest: Path
    proof_path: Path
    source_digest: str


def from_options(args: argparse.Namespace) -> DriverEngine | None:
    values = tuple(
        getattr(args, name, "") for name in ("engine_source", "engine_manifest", "engine_proof")
    )
    if not any(values):
        return None
    if not all(isinstance(value, str) and value for value in values):
        raise ValueError("Motor kaynak, manifest ve kanıt yolları birlikte gerekli.")
    root, manifest, proof = (Path(value).resolve() for value in values)
    for value in values:
        path = Path(value)
        if any(
            part.lower().startswith(".env")
            for candidate in (path, path.resolve())
            for part in candidate.parts
        ):
            raise ValueError("Motor seçenekleri sır yoluna erişemez.")
    if proof == manifest or proof.is_relative_to(root):
        raise ValueError("Motor kanıtı kaynak/manifest üstüne yazılamaz.")
    selection = selection_from_manifest(root, json.loads(manifest.read_text(encoding="utf-8")))
    return DriverEngine(selection, manifest, proof, verify_source(selection))


def command(engine: DriverEngine, *, logging: bool) -> list[str]:
    evals_root = str(Path(__file__).resolve().parent.parent)
    code = (
        "import sys;"
        f"sys.path.insert(0,{evals_root!r});"
        "from evals.driver_engine import bootstrap;"
        f"bootstrap({str(engine.selection.source_root)!r},{str(engine.manifest)!r},"
        f"{str(engine.proof_path)!r},{logging!r})"
    )
    return [sys.executable, "-c", code]


def validate_receipt(raw: object, engine: DriverEngine, child_pid: int) -> ImportedEngineProof:
    if not isinstance(raw, dict) or set(raw) != {
        "pid",
        "package_file",
        "entry_file",
        "source_root",
        "source_digest",
        "requested_revision",
        "bootstrap_compatible",
        "revision_provenance",
    }:
        raise ValueError("Motor receipt sözleşmesi geçersiz.")
    root = engine.selection.source_root
    expected = {
        "package_file": str(root / "src/fusion_cli/__init__.py"),
        "entry_file": str(root / "src/fusion_cli/cli/app.py"),
        "source_root": str(root),
        "source_digest": engine.source_digest,
        "requested_revision": engine.selection.requested_revision,
        "revision_provenance": "unverified",
    }
    if isinstance(raw["pid"], bool) or not isinstance(raw["pid"], int) or raw["pid"] != child_pid:
        raise ValueError("Motor receipt gerçek çocuk süreç kimliğiyle eşleşmiyor.")
    if raw["bootstrap_compatible"] is not True or any(
        raw[key] != value for key, value in expected.items()
    ):
        raise ValueError("Motor receipt seçilmiş kaynak manifestiyle eşleşmiyor.")
    return ImportedEngineProof(
        child_pid,
        expected["package_file"],
        expected["entry_file"],
        expected["source_root"],
        expected["source_digest"],
        expected["requested_revision"],
    )


def bootstrap(source_root: str, manifest: str, proof: str, logging: bool) -> None:
    from evals.engine_launcher import launch

    def emit(receipt: ImportedEngineProof) -> None:
        sys.stdout.write(json.dumps({"tip": "motor_kaniti", "veri": asdict(receipt)}) + "\n")
        sys.stdout.flush()

    def diagnose() -> None:
        # Mevcut sabit teşhis kodu yalnız seçilmiş kaynak importer'ı kurulduktan
        # sonra çalışır. Paket/CLI main'i ikinci kez içe aktarılmaz veya çağrılmaz.
        from evals.live_drive import _LOG_LAUNCHER, _TESHIS_LAUNCHER

        script = _LOG_LAUNCHER if logging else _TESHIS_LAUNCHER
        setup, marker, _ = script.partition("sys.argv = ['fusion', 'app']")
        if not marker:
            raise ValueError("Sürücü teşhis bootstrap sözleşmesi desteklenmiyor.")
        exec(compile(setup, "<fusion-driver-diagnostics>", "exec"), {})

    launch(Path(source_root), Path(manifest), Path(proof), receipt=emit, before_main=diagnose)
