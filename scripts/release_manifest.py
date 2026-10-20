#!/usr/bin/env python3
"""Sürüm kanıt paketi üretir: SHA256SUMS, CycloneDX SBOM ve release manifest.

Yalnız standart kütüphane kullanır; CI'da ve yerelde aynı çalışır. Üretilen manifest
"hazır" iddiası taşımaz: bilinen eksikler `release/known-gaps.json` dosyasından gelir
ve manifestte her zaman yer alır.

Kullanım:
    python scripts/release_manifest.py --version 0.5.0 --commit <sha> \
        --artifacts dist/ --out release-out/
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tomllib
from importlib import metadata
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = 1


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect_artifacts(directory: Path) -> list[dict[str, Any]]:
    """Klasördeki dosyaların adı, boyutu ve özeti (kararlı sırada)."""
    if not directory.is_dir():
        raise SystemExit(f"Artefakt klasörü yok: {directory}")
    files = sorted(item for item in directory.rglob("*") if item.is_file())
    if not files:
        raise SystemExit(f"Artefakt klasörü boş: {directory}")
    return [
        {
            "name": item.relative_to(directory).as_posix(),
            "size": item.stat().st_size,
            "sha256": sha256_file(item),
        }
        for item in files
    ]


def checksums_text(artifacts: list[dict[str, Any]]) -> str:
    """`sha256sum -c` ile doğrulanabilir biçim."""
    return "".join(f"{item['sha256']}  {item['name']}\n" for item in artifacts)


def _npm_components(lock: Path) -> list[dict[str, str]]:
    if not lock.is_file():
        return []
    packages = json.loads(lock.read_text(encoding="utf-8")).get("packages", {})
    return [
        {
            "name": key.rsplit("node_modules/", 1)[-1],
            "version": value["version"],
            "ecosystem": "npm",
        }
        for key, value in packages.items()
        if key and "version" in value
    ]


def _cargo_components(lock: Path) -> list[dict[str, str]]:
    if not lock.is_file():
        return []
    data = tomllib.loads(lock.read_text(encoding="utf-8"))
    return [
        {"name": item["name"], "version": item["version"], "ecosystem": "cargo"}
        for item in data.get("package", [])
    ]


def _python_components() -> list[dict[str, str]]:
    return sorted(
        (
            {"name": dist.metadata["Name"], "version": dist.version, "ecosystem": "pypi"}
            for dist in metadata.distributions()
            if dist.metadata["Name"]
        ),
        key=lambda item: item["name"].lower(),
    )


def build_sbom(version: str, root: Path = ROOT) -> dict[str, Any]:
    """CycloneDX 1.5 SBOM: Python, npm ve Cargo bağımlılıkları."""
    found = (
        _python_components()
        + _npm_components(root / "app" / "package-lock.json")
        + _cargo_components(root / "app" / "src-tauri" / "Cargo.lock")
    )
    unique = {(c["ecosystem"], c["name"], c["version"]): c for c in found}
    components = [
        {
            "type": "library",
            "name": item["name"],
            "version": item["version"],
            "purl": f"pkg:{item['ecosystem']}/{item['name']}@{item['version']}",
        }
        for _key, item in sorted(unique.items())
    ]
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {"component": {"type": "application", "name": "fusion", "version": version}},
        "components": components,
    }


def load_known_gaps(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    gaps = data.get("gaps")
    if not isinstance(gaps, list) or not all(isinstance(item, str) for item in gaps):
        raise SystemExit("known-gaps.json 'gaps' metin listesi olmalı.")
    return gaps


def build_manifest(
    *,
    version: str,
    commit: str,
    kits_commit: str,
    artifacts: list[dict[str, Any]],
    gaps: list[str],
    evidence: list[str],
    rollback: str,
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "version": version,
        "commit": commit,
        "bundled": {"core": version, "kitsCommit": kits_commit},
        "artifacts": artifacts,
        "evidence": evidence,
        "knownGaps": gaps,
        "rollback": rollback,
        "claimsReady": False,  # hazır etiketi insan kabulüyle verilir, araçla değil
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--kits-commit", default="")
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--gaps", type=Path, default=ROOT / "release" / "known-gaps.json")
    parser.add_argument("--evidence", action="append", default=[])
    parser.add_argument(
        "--rollback",
        default="Önceki sürümün SHA256SUMS ile doğrulanmış paketini kur; kullanıcı verisi korunur.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    artifacts = collect_artifacts(args.artifacts)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "SHA256SUMS").write_text(checksums_text(artifacts), encoding="utf-8")
    (args.out / "sbom.cdx.json").write_text(
        json.dumps(build_sbom(args.version), indent=2), encoding="utf-8"
    )
    manifest = build_manifest(
        version=args.version,
        commit=args.commit,
        kits_commit=args.kits_commit,
        artifacts=artifacts,
        gaps=load_known_gaps(args.gaps),
        evidence=args.evidence,
        rollback=args.rollback,
    )
    (args.out / "release-manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
