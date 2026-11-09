"""Trusted verifier signatures and exact frozen bytes are required for publication."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from scripts import release_attestation, release_manifest
from scripts.release_runtime import extract_runtime


def _key(path: Path) -> None:
    path.write_bytes(
        Ed25519PrivateKey.generate().private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        )
    )


@pytest.mark.parametrize(
    "mutation",
    [None, "report", "key", "fingerprint", "signature", "single_target", "duplicate_target"],
)
def test_only_pinned_independent_signature_grants_authority(tmp_path, monkeypatch, mutation):
    metadata = {
        "source_digest": "a" * 64,
        "scorer_digest": "b" * 64,
        "effective_config_digest": "c" * 64,
        "model": "approved",
        "repeat": 3,
    }
    monkeypatch.setattr(release_manifest, "_release_expectations", lambda: metadata)
    monkeypatch.setattr(release_manifest, "_validate_live_measurement", lambda *args: None)
    report = tmp_path / "report.json"
    payload = {
        "targets": ["aarch64-apple-darwin", "x86_64-apple-darwin", "x86_64-pc-windows-msvc"],
        "scope": "frozen-runtime",
        "binding": {
            "commit": "d" * 40,
            "version": "1.2.3",
            "measured_at": 1000,
            "artifacts": {"runtime.tar.gz": "e" * 64},
        },
        "metadata": metadata,
        "results": [],
    }
    if mutation == "single_target":
        payload["targets"] = payload["targets"][:1]
    if mutation == "duplicate_target":
        payload["targets"].append(payload["targets"][0])
    report.write_text(json.dumps(payload))
    private = tmp_path / "private"
    _key(private)
    public = tmp_path / "public"
    signature = tmp_path / "sig"
    fingerprint = release_attestation.sign(report, private, signature, public)
    if mutation == "report":
        payload["actor_declared_pass"] = True
        report.write_text(json.dumps(payload))
    if mutation == "key":
        _key(private)
        # An actor signing the report with their own key cannot gain authority.
        release_attestation.sign(report, private, signature, public)
    if mutation == "fingerprint":
        fingerprint = "0" * 64
    if mutation == "signature":
        signature.write_bytes(b"fake")
    kwargs = {
        "required": True,
        "version": "1.2.3",
        "signature": signature,
        "public_key": public,
        "trusted_key_sha256": fingerprint,
    }
    if mutation is None:
        assert (
            release_manifest.live_acceptance(
                report,
                [{"name": "runtime.tar.gz", "sha256": "e" * 64}],
                "d" * 40,
                now=1001,
                **kwargs,
            )["status"]
            == "passed"
        )
    else:
        with pytest.raises(
            SystemExit,
            match="K29" if mutation in {"single_target", "duplicate_target"} else "Bağımsız",
        ):
            release_manifest.live_acceptance(
                report,
                [{"name": "runtime.tar.gz", "sha256": "e" * 64}],
                "d" * 40,
                now=1001,
                **kwargs,
            )


def test_extract_runtime_checks_actual_archive_and_file_map(tmp_path):
    import tarfile

    root = tmp_path / "tree"
    root.mkdir()
    (root / "fusion").write_bytes(b"frozen-executable-fixture")
    archive = tmp_path / "runtime.tar.gz"
    with tarfile.open(archive, "w:gz") as stream:
        stream.add(root / "fusion", arcname="fusion")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                "entrypoint": "fusion",
                "files": [
                    {
                        "path": "fusion",
                        "kind": "file",
                        "sha256": hashlib.sha256((root / "fusion").read_bytes()).hexdigest(),
                    }
                ],
            }
        )
    )
    executable, _ = extract_runtime(archive, manifest, tmp_path / "extracted")
    assert executable.read_bytes() == b"frozen-executable-fixture"
    archive.write_bytes(b"changed")
    with pytest.raises(ValueError, match="arşivi"):
        extract_runtime(archive, manifest, tmp_path / "rejected")


def test_source_identity_covers_frozen_control_plane_and_tests(tmp_path):
    from evals.profiles import _digest_entries, _source_entries

    names = [
        "src/fusion_cli/engine.py",
        "src/fusion_cli/config/defaults.yaml",
        "scripts/release_live.py",
        "desktop_build/runtime/entrypoint.py",
        "desktop_build/runtime/fusion_runtime.spec",
        "evals/frozen_engine.py",
        "tests/test_release_handoff.py",
        ".github/workflows/desktop.yml",
        ".gitattributes",
    ]
    for name in names:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"frozen-source")
    entries = _source_entries(tmp_path)
    assert {name for name, digest in entries} == set(names)
    before = _digest_entries(entries)
    (tmp_path / "scripts/release_live.py").write_bytes(b"changed-runner")
    assert _digest_entries(_source_entries(tmp_path)) != before
