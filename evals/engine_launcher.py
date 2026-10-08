"""Aynı çekirdek süreçte önce kaynak/import kanıtı, sonra seçilmiş CLI main."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.abc
import importlib.machinery
import json
import os
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from types import CodeType, ModuleType

from evals.engine_proof import (
    EngineSelection,
    selection_from_manifest,
    verify_imported_engine,
    verify_source,
)


class _ManifestSourceLoader(importlib.machinery.SourceFileLoader):
    """Seçilmiş kaynak byte'larını derle; timestamp geçerli pyc bile okunmaz."""

    def __init__(self, name: str, path: str, expected_digest: str) -> None:
        super().__init__(name, path)
        self._expected_digest = expected_digest

    def get_code(self, fullname: str) -> CodeType:
        source = self.get_data(self.path)
        if hashlib.sha256(source).hexdigest() != self._expected_digest.lower():
            raise ValueError("İçe aktarılan motor kaynağı manifestten değişti.")
        return self.source_to_code(source, self.path)


class _ManifestSourceFinder(importlib.abc.MetaPathFinder):
    """Yalnız Fusion namespace'ini kaynak manifesti üzerinden içe aktar."""

    def __init__(self, selection: EngineSelection) -> None:
        self._root = selection.source_root.resolve()
        self._digests = {item.path: item.digest for item in selection.sources}

    def find_spec(
        self,
        fullname: str,
        path: Sequence[str] | None = None,
        target: ModuleType | None = None,
    ) -> importlib.machinery.ModuleSpec | None:
        if fullname != "fusion_cli" and not fullname.startswith("fusion_cli."):
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is None or not isinstance(spec.loader, importlib.machinery.SourceFileLoader):
            raise ImportError(
                "Seçilmiş motor için yalnız manifestli Python kaynakları destekleniyor."
            )
        if not isinstance(spec.origin, str):
            raise ImportError("Seçilmiş motor modülünün kaynak kimliği yok.")
        origin = Path(spec.origin).resolve()
        if not origin.is_relative_to(self._root / "src/fusion_cli"):
            raise ImportError("İçe aktarılan motor kaynağı seçilmiş paket dışına çıkıyor.")
        relative = origin.relative_to(self._root).as_posix()
        digest = self._digests.get(relative)
        if digest is None:
            raise ImportError("İçe aktarılan motor kaynağı manifestte yok.")
        spec.loader = _ManifestSourceLoader(fullname, str(origin), digest)
        return spec


def _safe_input(path: Path) -> Path:
    resolved = path.resolve()
    if any(
        part.lower().startswith(".env")
        for candidate in (path, resolved)
        for part in candidate.parts
    ):
        raise ValueError("Motor kanıtı sır dosyasından okunamaz veya sır yoluna yazılamaz.")
    return resolved


def _write_proof(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", dir=path.parent, encoding="utf-8", delete=False
        ) as stream:
            temporary = Path(stream.name)
            json.dump(payload, stream, ensure_ascii=False, sort_keys=True)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def launch(source_root: Path, manifest: Path, proof: Path) -> None:
    """Kayıtlı manifest ve aynı import edilen entry ile doğrudan çalıştır."""
    root = source_root.resolve()
    manifest_path, proof_path = _safe_input(manifest), _safe_input(proof)
    if proof_path == manifest_path or proof_path.is_relative_to(root):
        raise ValueError("Motor kanıtı kaynak veya manifest dosyasını değiştiremez.")
    proof_path.unlink(missing_ok=True)
    selection = selection_from_manifest(root, json.loads(manifest_path.read_text(encoding="utf-8")))
    verify_source(selection)
    if any(name == "fusion_cli" or name.startswith("fusion_cli.") for name in sys.modules):
        raise ValueError("Motor seçilmeden önce Fusion modülü yüklenmiş; süreç desteklenmiyor.")
    sys.path.insert(0, str(root / "src"))
    sys.meta_path.insert(0, _ManifestSourceFinder(selection))
    package = importlib.import_module("fusion_cli")
    entry = importlib.import_module("fusion_cli.cli.app")
    result = verify_imported_engine(selection, package, entry, sys.modules, pid=os.getpid())
    _write_proof(proof_path, asdict(result))
    sys.argv = ["fusion", "app"]
    entry.main()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seçilmiş motorun aynı süreçte import kanıtı")
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--proof", type=Path, required=True)
    args = parser.parse_args()
    try:
        launch(args.source_root, args.manifest, args.proof)
    except (OSError, ValueError, ImportError) as error:
        sys.stderr.write(f"Motor kanıtı reddedildi: {type(error).__name__}\n")
        raise SystemExit(2) from error


if __name__ == "__main__":
    main()
