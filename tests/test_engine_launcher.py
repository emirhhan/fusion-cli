"""Aynı kısa fixture süreci önce kanıt yazıp sonra seçilmiş main'i çağırır."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys

import pytest


def launch(tmp_path, *, change=""):
    root = tmp_path / "engine"
    package = root / "src/fusion_cli"
    (package / "cli").mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "cli/__init__.py").write_text("")
    proof = tmp_path / "proof.json"
    marker = tmp_path / "entry.json"
    (package / "cli/app.py").write_text(
        "import json,os\nfrom pathlib import Path\n"
        f"def main():\n p=Path({str(proof)!r})\n assert p.exists()\n"
        " result={'pid':os.getpid(),'argv':__import__('sys').argv}\n"
        f" Path({str(marker)!r}).write_text(json.dumps(result))\n"
    )
    manifest = tmp_path / "manifest.json"
    payload = {
        "schema_version": 1,
        "requested_revision": "a" * 40,
        "sources": [
            {
                "path": file.relative_to(root).as_posix(),
                "digest": hashlib.sha256(file.read_bytes()).hexdigest(),
            }
            for file in sorted(package.rglob("*.py"))
        ],
    }
    manifest.write_text(json.dumps(payload))
    if change == "stale_dirty":
        proof.write_text("old proof")
        change = "dirty"
    if change == "dirty":
        (package / "cli/app.py").write_text("raise AssertionError('main should not import')")
    if change == "unsupported":
        (package / "cli/app.py").write_text("main = None")
        payload["sources"][-1]["digest"] = hashlib.sha256(
            (package / "cli/app.py").read_bytes()
        ).hexdigest()
        manifest.write_text(json.dumps(payload))
    if change == "stale_bytecode":
        import os
        import py_compile

        source = package / "cli/app.py"
        fresh = source.read_text()
        stale = fresh.replace("'argv'", "'OLD!'", 1)
        assert len(fresh.encode()) == len(stale.encode())
        source.write_text(stale)
        py_compile.compile(str(source), doraise=True)
        timestamp = source.stat().st_mtime
        source.write_text(fresh)
        os.utime(source, (timestamp, timestamp))
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "evals.engine_launcher",
            "--source-root",
            str(root),
            "--manifest",
            str(manifest),
            "--proof",
            str(proof),
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    return result, proof, marker


def test_same_process_proof_precedes_reference_style_entry(tmp_path):
    result, proof, marker = launch(tmp_path)
    assert result.returncode == 0, result.stderr
    recorded = json.loads(proof.read_text())
    entry = json.loads(marker.read_text())
    assert recorded["pid"] == entry["pid"]
    assert entry["argv"] == ["fusion", "app"]
    assert recorded["revision_provenance"] == "unverified"
    assert recorded["bootstrap_compatible"] is True


@pytest.mark.parametrize("change", ["dirty", "unsupported", "stale_dirty"])
def test_rejected_selection_never_starts_entry(tmp_path, change):
    result, proof, marker = launch(tmp_path, change=change)
    assert result.returncode != 0
    assert not marker.exists()
    assert not proof.exists()


def test_manifest_source_executes_instead_of_timestamp_valid_stale_pyc(tmp_path):
    result, proof, marker = launch(tmp_path, change="stale_bytecode")
    assert result.returncode == 0, result.stderr
    entry = json.loads(marker.read_text())
    assert "argv" in entry and "OLD!" not in entry
    assert entry["pid"] == json.loads(proof.read_text())["pid"]
