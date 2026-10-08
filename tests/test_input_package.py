"""Açık karşılaştırma girdileri çalıştırılmadan ve eksikler gizlenmeden paketlenir."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from evals.kabul.input_package import extract_task, materialize_package
from evals.kabul.run_manifest import PublicSources


def test_literal_task_keeps_exact_utf8_without_executing_module() -> None:
    source = b"raise RuntimeError('asla calisma')\nTASK = ('Bir ' 'oyun\\n')\nTIMEOUT_S=3600.0"
    task = extract_task(source)
    assert task.brief == b"Bir oyun\n"
    assert task.timeout_s == 3600.0


def test_dynamic_task_is_rejected_instead_of_executed() -> None:
    with pytest.raises(ValueError, match="literal"):
        extract_task(b"TASK = open('.env').read()\nTIMEOUT_S=3600")


def test_site_template_uses_public_url_and_original_area_budget() -> None:
    source = (
        b"SOURCE_URL='https://example.test'\nTASK_TEMPLATE='Kopyala {source}'\n"
        b"TASK=TASK_TEMPLATE.format(source=SOURCE_URL)\n"
        b"def make_area():\n return Area(timeout_s=5400)"
    )
    task = extract_task(source)
    assert task.brief == b"Kopyala https://example.test"
    assert task.timeout_s == 5400


def test_package_writes_exact_bytes_and_twelve_blocked_records(tmp_path: Path) -> None:
    (tmp_path / "area.py").write_text("TASK='A\\n'\nTIMEOUT_S=3600", encoding="utf-8")
    output = tmp_path / "output"
    proof = materialize_package(
        PublicSources(tmp_path, ("area.py",)),
        output,
        (("html_oyun", "area.py", b"Platform B\n"),),
        (),
    )
    assert (output / "briefs/html_oyun-A.txt").read_bytes() == b"A\n"
    record = json.loads((output / "manifest.json").read_text())
    assert record["status"] == "unverified"
    assert len(record["runs"]) == 12
    assert all(not run["runnable"] for run in record["runs"])
    assert record["briefs"][0]["digest"] == hashlib.sha256(b"A\n").hexdigest()
    assert (
        proof.manifest_digest == hashlib.sha256((output / "manifest.json").read_bytes()).hexdigest()
    )
    assert "animasyon:brief" in proof.missing_inputs


def test_missing_asset_is_explicit_and_not_silently_skipped(tmp_path: Path) -> None:
    proof = materialize_package(
        PublicSources(tmp_path, ("missing.svg",)),
        tmp_path / "out",
        (),
        (("assets/logo.svg", "missing.svg"),),
    )
    assert "asset:assets/logo.svg" in proof.missing_inputs


def test_symlink_secret_cannot_be_packaged(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("fake test sentinel")
    (tmp_path / "public.svg").symlink_to(tmp_path / ".env")
    with pytest.raises(ValueError, match="symlink"):
        materialize_package(
            PublicSources(tmp_path, ("public.svg",)),
            tmp_path / "out",
            (),
            (("assets/logo.svg", "public.svg"),),
        )


def test_output_refuses_existing_package_and_path_escape(tmp_path: Path) -> None:
    (tmp_path / "asset.svg").write_bytes(b"public")
    with pytest.raises(ValueError, match="hedef"):
        materialize_package(
            PublicSources(tmp_path, ("asset.svg",)),
            tmp_path / "out",
            (),
            (("../escape", "asset.svg"),),
        )
    assert not (tmp_path / "escape").exists()


def test_asset_cannot_overwrite_reserved_manifest_before_output_creation(tmp_path: Path) -> None:
    (tmp_path / "public.txt").write_bytes(b"public asset")
    output = tmp_path / "out"
    with pytest.raises(ValueError, match="manifest"):
        materialize_package(
            PublicSources(tmp_path, ("public.txt",)),
            output,
            (),
            (("manifest.json", "public.txt"),),
        )
    assert not output.exists()


@pytest.mark.parametrize("target", ["./manifest.json", "manifest.json/", "a//b", "a/./b"])
def test_noncanonical_asset_target_is_rejected_before_output_creation(
    tmp_path: Path,
    target: str,
) -> None:
    (tmp_path / "public.txt").write_bytes(b"public asset")
    output = tmp_path / "out"
    with pytest.raises(ValueError, match="hedef"):
        materialize_package(
            PublicSources(tmp_path, ("public.txt",)),
            output,
            (),
            ((target, "public.txt"),),
        )
    assert not output.exists()
