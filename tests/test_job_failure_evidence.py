"""Arka plan kanıtı deneme başındaki kaynak özetine bağlıdır."""

from __future__ import annotations

import json

from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import jobs, shell


def test_attempt_start_hash_survives_source_edit_and_poll(tmp_path) -> None:
    source = tmp_path / "src.tsx"
    source.write_text("before")
    record = json.dumps({"version": 1, "families": ["overflow"]})
    command = f"echo 'FUSION_FAILURE_V1:{record}'; exit 1"
    context = ToolContext(root=tmp_path)
    started = shell.run_shell(
        {
            "command": command,
            "background": True,
            "failure_check": "layout",
            "failure_sources": ["src.tsx"],
        },
        context,
    )
    job = started.output.split("başladı: ")[1].split()[0]
    source.write_text("after")
    result = jobs.job_status({"id": job, "wait_s": 10}, context)
    assert len(result.failure_evidence) == 1
    item = result.failure_evidence[0]
    assert item.attempt_id == job and item.family == "overflow"
    import hashlib

    assert item.sources[0].digest == hashlib.sha256(b"before").hexdigest()
    assert jobs.job_status({"id": job}, context).failure_evidence == result.failure_evidence


def test_untyped_stderr_never_becomes_product_family(tmp_path) -> None:
    context = ToolContext(root=tmp_path)
    started = shell.run_shell(
        {"command": "echo 'layout overflow'; exit 1", "background": True}, context
    )
    job = started.output.split("başladı: ")[1].split()[0]
    assert not jobs.job_status({"id": job, "wait_s": 10}, context).failure_evidence


def test_source_outside_project_or_secret_is_rejected_before_launch(tmp_path) -> None:
    context = ToolContext(root=tmp_path)
    for path in ("../outside.tsx", ".env"):
        result = shell.run_shell(
            {
                "command": "true",
                "background": True,
                "failure_check": "layout",
                "failure_sources": [path],
            },
            context,
        )
        assert not result.ok
    assert not (tmp_path / jobs.JOBS_DIR).exists()


def test_malformed_protocol_is_visible_but_not_invented_product_failure(tmp_path) -> None:
    context = ToolContext(root=tmp_path)
    (tmp_path / "a.tsx").write_text("code")
    started = shell.run_shell(
        {
            "command": "echo 'FUSION_FAILURE_V1:broken'; exit 1",
            "background": True,
            "failure_check": "layout",
            "failure_sources": ["a.tsx"],
        },
        context,
    )
    job = started.output.split("başladı: ")[1].split()[0]
    result = jobs.job_status({"id": job, "wait_s": 10}, context)
    assert not result.failure_evidence and not result.ok
    assert "kontrol kanıtı okunamadı" in result.output


def test_directory_secret_candidate_is_rejected_before_read(tmp_path, monkeypatch) -> None:
    from pathlib import Path

    import pytest

    from fusion_cli.tools.job_evidence import prepare_manifest

    folder = tmp_path / "src"
    folder.mkdir()
    secret = folder / ".env.json"
    secret.write_text("fixture-only")
    original = Path.read_bytes

    def read(path):
        assert path != secret, "Sır adayı hashlenmemeli"
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", read)
    with pytest.raises(ValueError, match="sır"):
        prepare_manifest({"failure_check": "layout", "failure_sources": ["src"]}, tmp_path)


def test_directory_symlink_to_secret_is_rejected_before_read(tmp_path, monkeypatch) -> None:
    from pathlib import Path

    import pytest

    from fusion_cli.tools.job_evidence import prepare_manifest

    folder = tmp_path / "src"
    folder.mkdir()
    secret = tmp_path / ".env.json"
    secret.write_text("fixture-only")
    (folder / "config.json").symlink_to(secret)
    original = Path.read_bytes

    def read(path):
        assert path != secret, "Bağlantının sır hedefi hashlenmemeli"
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", read)
    with pytest.raises(ValueError, match="sır"):
        prepare_manifest({"failure_check": "layout", "failure_sources": ["src"]}, tmp_path)
