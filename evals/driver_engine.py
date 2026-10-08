"""Seçilmiş çekirdek için açık seçenekler ve aynı süreç receipt doğrulaması."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import MutableMapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TypeVar, cast

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

    imported: list[ImportedEngineProof] = []

    def emit(receipt: ImportedEngineProof) -> None:
        imported.append(receipt)
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
        _install_config_observer(imported[0])

    launch(Path(source_root), Path(manifest), Path(proof), receipt=emit, before_main=diagnose)


def _install_config_observer(proof: ImportedEngineProof) -> None:
    import importlib

    try:
        from evals.driver_config import ConfigObserver, ConfigReceipt, install

        session = importlib.import_module("fusion_cli.cli.session")
        engine = importlib.import_module("fusion_cli.engines.agent.loop")
        sequence: list[int] = [0]

        def emit(receipt: ConfigReceipt) -> None:
            sequence[0] += 1
            payload = {"sequence": sequence[0], "receipt": asdict(receipt)}
            print(json.dumps({"tip": "efektif_kanit", "veri": payload}), flush=True)

        install(ConfigObserver(proof, os.getpid, emit), session, engine)
    except (ImportError, ValueError, AttributeError):
        print(json.dumps({"tip": "efektif_desteklenmiyor", "veri": {}}), flush=True)


def consume_config(
    message: object, proof: dict[str, object], records: list[dict[str, object]]
) -> None:
    from evals.driver_config import validate_wire

    if not isinstance(message, dict) or set(message) != {"sequence", "receipt"}:
        raise ValueError("Efektif kanıt zarfı geçersiz.")
    if type(message["sequence"]) is not int or message["sequence"] != len(records) + 1:
        raise ValueError("Efektif kanıt sıra numarası yinelenmiş/geçersiz.")
    imported = ImportedEngineProof(
        cast(int, proof["pid"]),
        cast(str, proof["package_file"]),
        cast(str, proof["entry_file"]),
        cast(str, proof["source_root"]),
        cast(str, proof["source_digest"]),
        cast(str, proof["requested_revision"]),
    )
    receipt = validate_wire(message["receipt"], imported)
    records.append(asdict(receipt))


def handle_config(tip: object, data: object, record: dict[str, object]) -> bool:
    """Efektif tel kanıtını ve ilk model olayının sırasını kayda bağla."""
    if tip == "efektif_desteklenmiyor":
        record["efektif_durum"] = "unsupported"
        return True
    snapshots = cast(list[dict[str, object]], record.setdefault("efektif_kanitlar", []))
    if tip == "efektif_kanit":
        try:
            consume_config(data, cast(dict[str, object], record.get("motor_kaniti", {})), snapshots)
        except (ValueError, KeyError):
            record["hata"] = "Efektif ayar kanıtı doğrulanmadı."
        return True
    if (
        tip == "olay"
        and isinstance(data, dict)
        and data.get("olay") == "ModelCallStarted"
        and len(snapshots) <= cast(int, record.get("efektif_baslangic", 0))
    ):
        record["hata"] = "Model çağrısından önce efektif ayar kanıtı eksik."
    return False


_Response = TypeVar("_Response")


def invalidate_pending(pending: MutableMapping[str, asyncio.Future[_Response]], error: str) -> None:
    """Kanıt ihlalinden sonra sıradaki yanıt eski isteği başarılı yapamasın."""
    for future in pending.values():
        if not future.done():
            future.set_exception(ConnectionError(error))
    pending.clear()
