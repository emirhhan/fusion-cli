"""Donmuş girdi planı kalite veya eş koşullu koşu başarısı sayılmaz."""

import hashlib
from pathlib import Path

import pytest
from evals.kabul.model import Area, Inspection
from evals.kabul.run_manifest import (
    EngineInput,
    FreezeEvidence,
    FreezeStatus,
    PublicSources,
    freeze_matrix,
    freeze_run,
)


def area(name="html_oyun"):
    return Area(name, "Original A", 3600.0, lambda root, values: Inspection())


def engine(role="current"):
    return EngineInput(role, "a" * 40 if role == "current" else "b" * 40, "c" * 64)


def run(identifier="html_oyun.curA", variant="A", final=True):
    return freeze_run(
        area(),
        run_id=identifier,
        variant=variant,
        engine=engine(),
        brief=b"Exact\r\nA\n",
        final_brief=final,
        viewports=((1280, 800),),
        assets=(),
        evidence=FreezeEvidence(),
    )


def test_exact_bytes_original_budget_and_unknowns_are_preserved():
    record = run()
    assert record.brief == b"Exact\r\nA\n"
    assert record.brief_digest == hashlib.sha256(record.brief).hexdigest()
    assert record.timeout_s == area().timeout_s
    assert record.status is FreezeStatus.UNVERIFIED
    assert "authentication" in record.missing_inputs
    assert record.original_baseline_provenance == "unknown"
    assert not record.runnable


def test_draft_b_is_never_promoted():
    record = run("html_oyun.curB", "B", False)
    assert "final_brief" in record.missing_inputs
    assert record.status is FreezeStatus.UNVERIFIED


@pytest.mark.parametrize("name", [".env", ".env.json", "credentials.json", "outside.md"])
def test_public_allowlist_rejects_secrets_and_outside_before_read(tmp_path, monkeypatch, name):
    root = tmp_path / "public"
    root.mkdir()
    (root / name).write_text("fixture only")
    sources = PublicSources(root, ("brief.md", name))
    requested = "../outside.md" if name == "outside.md" else name
    monkeypatch.setattr(Path, "read_bytes", lambda path: pytest.fail("Okuma başlamamalı."))
    with pytest.raises(ValueError):
        sources.read(requested)


def test_public_symlink_and_unlisted_source_rejected_before_read(tmp_path, monkeypatch):
    (tmp_path / "fixture.md").write_text("public")
    (tmp_path / "brief.md").symlink_to(tmp_path / "fixture.md")
    sources = PublicSources(tmp_path, ("brief.md",))
    monkeypatch.setattr(Path, "read_bytes", lambda path: pytest.fail("Okuma başlamamalı."))
    for name in ("brief.md", "fixture.md"):
        with pytest.raises(ValueError):
            sources.read(name)


def test_public_asset_and_brief_hash_are_exact(tmp_path):
    data = b"public\r\nbytes"
    (tmp_path / "brief.md").write_bytes(data)
    sources = PublicSources(tmp_path, ("brief.md",))
    assert sources.read("brief.md") == data
    assert sources.asset("brief.md").digest == hashlib.sha256(data).hexdigest()


def test_incomplete_matrix_cannot_run():
    matrix = freeze_matrix((run(),))
    assert matrix.status is FreezeStatus.UNVERIFIED
    assert len(matrix.missing_runs) == 11
    assert not matrix.runnable


def test_twelve_unknown_records_still_unverified_and_a_difference_is_reported():
    records = []
    for domain in ("html_oyun", "remotion", "site_kopyasi", "animasyon"):
        for suffix, role, variant in (
            ("refA", "reference", "A"),
            ("curA", "current", "A"),
            ("curB", "current", "B"),
        ):
            records.append(
                freeze_run(
                    area(domain),
                    run_id=domain + "." + suffix,
                    variant=variant,
                    engine=engine(role),
                    brief=b"same A" if variant == "A" else b"B",
                    final_brief=True,
                    viewports=((1280, 800),),
                    assets=(),
                    evidence=FreezeEvidence(),
                )
            )
    matrix = freeze_matrix(tuple(records))
    assert not matrix.missing_runs
    assert matrix.status is FreezeStatus.UNVERIFIED
    assert not matrix.runnable
    changed = freeze_run(
        area("html_oyun"),
        run_id="html_oyun.curA",
        variant="A",
        engine=engine(),
        brief=b"different",
        final_brief=True,
        viewports=((1280, 800),),
        assets=(),
        evidence=FreezeEvidence(),
    )
    records[1] = changed
    assert "html_oyun: A girdileri eş değil" in freeze_matrix(tuple(records)).problems


def test_desa_b_preserves_original_area_and_budget():
    desa = Area("site_kopyasi_2", "Desa source", 5400.0, lambda root, values: Inspection())
    record = freeze_run(
        desa,
        run_id="site_kopyasi.curB",
        variant="B",
        engine=engine(),
        brief=b"Desa source",
        final_brief=False,
        viewports=((1440, 900), (390, 844)),
        assets=(),
        evidence=FreezeEvidence(),
    )
    assert record.area == "site_kopyasi_2"
    assert record.timeout_s == 5400.0
    assert record.status is FreezeStatus.UNVERIFIED


@pytest.mark.parametrize("viewports", [((True, 800),), ((1280, 0),), (1280,), [(1280, 800)]])
def test_invalid_viewport_rejected_explicitly(viewports):
    with pytest.raises(ValueError):
        freeze_run(
            area(),
            run_id="html_oyun.curA",
            variant="A",
            engine=engine(),
            brief=b"A",
            final_brief=True,
            viewports=viewports,
            assets=(),
            evidence=FreezeEvidence(),
        )
