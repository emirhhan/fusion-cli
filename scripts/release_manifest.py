#!/usr/bin/env python3
"""Sürüm kanıt paketi üretir: SHA256SUMS, CycloneDX SBOM ve release manifest.

Yalnız standart kütüphane kullanır; CI'da ve yerelde aynı çalışır. Üretilen manifest
"hazır" iddiası taşımaz: bilinen eksikler `release/known-gaps.json` dosyasından gelir
ve manifestte her zaman yer alır.

Kullanım:
    python scripts/release_manifest.py --version 0.5.0 --commit <sha> \
        --kits-manifest app/src-tauri/resources/kits/kits-manifest.json \
        --artifacts dist/ --out release-out/

Masaüstü paketi Kits'i HER ZAMAN içerir; Kits commit'i (`--kits-commit` ya da
`prepare-kits.mjs`'in yazdığı `--kits-manifest`) verilmeden manifest üretilmez.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import tomllib
from importlib import metadata
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = 2
LIVE_ACCEPTANCE_MAX_AGE_S = 48 * 60 * 60
LIVE_ACCEPTANCE_MIN_REPEAT = 3
_KITS_COMMIT = re.compile(r"^[0-9a-f]{40}$")


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


def _uv_lock_components(lock: Path) -> list[dict[str, str]]:
    """`uv.lock` içindeki kilitli Python paketleri (projenin kendisi hariç)."""
    data = tomllib.loads(lock.read_text(encoding="utf-8"))
    return sorted(
        (
            {"name": item["name"], "version": item["version"], "ecosystem": "pypi"}
            for item in data.get("package", [])
            if "version" in item and not {"editable", "virtual"} & set(item.get("source", {}))
        ),
        key=lambda item: item["name"].lower(),
    )


def _python_components(root: Path) -> list[dict[str, str]]:
    """Python bileşenleri: kilit dosyası varsa ondan, yoksa kurulu paketlerden.

    Ölçüldü (30 Ekim, Q1-05): yalnız `importlib.metadata.distributions()` vardı;
    bu, kilit dosyasını değil CI runner'ında o an kurulu her şeyi (build, pip,
    setuptools...) listeliyordu. Kilit dosyası yoksa eski davranış yedek kalır.
    """
    lock = root / "uv.lock"
    if lock.is_file():
        return _uv_lock_components(lock)
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
        _python_components(root)
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


def resolve_kits_commit(kits_commit: str, kits_manifest: Path | None) -> str:
    """Paketlenen Kits commit'i; yoksa ya da geçersizse yayın reddedilir."""
    if kits_manifest is not None:
        try:
            data = json.loads(kits_manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise SystemExit(f"Kits manifesti okunamadı: {kits_manifest} ({error})") from error
        from_manifest = str(data.get("commit", "")) if isinstance(data, dict) else ""
        if kits_commit and kits_commit != from_manifest:
            raise SystemExit(
                f"Kits commit'i manifestle uyuşmuyor: {kits_commit} != {from_manifest}"
            )
        kits_commit = from_manifest
    if not _KITS_COMMIT.match(kits_commit):
        raise SystemExit(
            "Kits commit'i yok ya da geçersiz; Kits'siz masaüstü paketi yayınlanmaz "
            "(--kits-manifest veya 40 haneli --kits-commit verin)."
        )
    return kits_commit


def live_acceptance(
    path: Path | None, artifacts: list[dict[str, Any]], commit: str, *, now: float
) -> dict[str, Any]:
    """Canlı rapor yoksa ölçülmedi; verilmiş ama eski/uyumsuz rapor yayını durdurur."""
    if path is None:
        return {"status": "not_measured", "reason": "Paket kimliğine bağlı canlı kabul raporu yok."}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        binding = payload["binding"]
        metadata = payload["metadata"]
        results = payload["results"]
        measured_at = binding["measured_at"]
        hashes = {item["name"]: item["sha256"] for item in artifacts}
        if binding["commit"] != commit or binding["artifacts"] != hashes:
            raise ValueError("Canlı rapor bu commit/paket özetlerine ait değil.")
        if type(measured_at) not in (int, float) or not (
            0 <= now - measured_at <= LIVE_ACCEPTANCE_MAX_AGE_S
        ):
            raise ValueError("Canlı rapor eski veya gelecek tarihli.")
        _validate_live_measurement(metadata, results)
    except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError) as error:
        raise SystemExit(f"Canlı kabul kanıtı geçersiz: {error}") from error
    return {
        "status": "passed",
        "sha256": sha256_file(path),
        "measuredAt": measured_at,
        "model": metadata["model"],
        "effectiveConfigDigest": metadata["effective_config_digest"],
        "sourceDigest": metadata["source_digest"],
        "repeat": metadata["repeat"],
    }


def _validate_live_measurement(metadata: dict[str, Any], results: list[dict[str, Any]]) -> None:
    required = set(
        json.loads((ROOT / "release/live-acceptance-policy.json").read_text())["task_ids"]
    )
    if not isinstance(results, list) or {item["task_id"] for item in results} != required:
        raise ValueError("Tam production görev seti ölçülmeli.")
    if len(results) != len(required) or set(metadata["task_ids"]) != required:
        raise ValueError("Görev kimlikleri eksik veya yinelenmiş.")
    if metadata["split_digest"] != sha256_file(ROOT / "evals/suite/production.yaml"):
        raise ValueError("Rapor güncel production görev setine ait değil.")
    if metadata["profile"] != "production" or not metadata["model"]:
        raise ValueError("Canlı kabul production profili ve model kimliği gerektirir.")
    if type(metadata["repeat"]) is not int or metadata["repeat"] < LIVE_ACCEPTANCE_MIN_REPEAT:
        raise ValueError("Canlı kabul en az üç tekrar gerektirir.")
    if not metadata["effective_config_digest"] or not metadata["source_digest"]:
        raise ValueError("Kaynak/yapılandırma kimliği eksik.")
    calls = metadata["calls"]
    if len(calls) < len(results) * LIVE_ACCEPTANCE_MIN_REPEAT or any(
        not isinstance(call.get("served_model"), str) or not call["served_model"] for call in calls
    ):
        raise ValueError("Gerçek sunulan model çağrısı kimliği eksik.")
    if not results or any(
        item["success"] is not True
        or item.get("false_success")
        or item.get("rate_limited")
        or item["model_calls"] <= 0
        or item["runs"] < LIVE_ACCEPTANCE_MIN_REPEAT
        or item["passes"] != item["runs"]
        for item in results
    ):
        raise ValueError("Kabul başarısız veya sağlayıcı yüzünden ölçülememiş.")
    budgets = metadata["task_budgets"]
    if {item[0] for item in budgets} != {item["task_id"] for item in results} or any(
        type(item[1]) is not int
        or item[1] <= 0
        or type(item[2]) not in (int, float)
        or not 0 < item[2] < float("inf")
        for item in budgets
    ):
        raise ValueError("Her görev için sınırlı çağrı/süre bütçesi gerekli.")


def build_manifest(
    *,
    version: str,
    commit: str,
    kits_commit: str,
    artifacts: list[dict[str, Any]],
    gaps: list[str],
    evidence: list[str],
    rollback: str,
    live: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "version": version,
        "commit": commit,
        "bundled": {"core": version, "kitsCommit": kits_commit},
        "artifacts": artifacts,
        "evidence": evidence,
        "knownGaps": gaps,
        "liveAcceptance": live or {"status": "not_measured"},
        "rollback": rollback,
        "claimsReady": False,  # hazır etiketi insan kabulüyle verilir, araçla değil
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--kits-commit", default="")
    parser.add_argument(
        "--kits-manifest",
        type=Path,
        help="prepare-kits.mjs'in yazdığı kits-manifest.json (Kits commit'i buradan okunur)",
    )
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--gaps", type=Path, default=ROOT / "release" / "known-gaps.json")
    parser.add_argument("--evidence", action="append", default=[])
    parser.add_argument("--live-acceptance", type=Path)
    parser.add_argument(
        "--rollback",
        default="Önceki sürümün SHA256SUMS ile doğrulanmış paketini kur; kullanıcı verisi korunur.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    kits_commit = resolve_kits_commit(args.kits_commit, args.kits_manifest)
    artifacts = collect_artifacts(args.artifacts)
    live = live_acceptance(args.live_acceptance, artifacts, args.commit, now=time.time())
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "SHA256SUMS").write_text(checksums_text(artifacts), encoding="utf-8")
    (args.out / "sbom.cdx.json").write_text(
        json.dumps(build_sbom(args.version), indent=2), encoding="utf-8"
    )
    manifest = build_manifest(
        version=args.version,
        commit=args.commit,
        kits_commit=kits_commit,
        artifacts=artifacts,
        gaps=load_known_gaps(args.gaps),
        evidence=args.evidence,
        rollback=args.rollback,
        live=live,
    )
    (args.out / "release-manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
