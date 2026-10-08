"""Kaynak kanıtı checkout iddiasını değil doğrulanan dosya kimliğini ölçer."""

from __future__ import annotations

import hashlib
from types import SimpleNamespace

import pytest
from evals.engine_proof import EngineSelection, SourceDigest, verify_imported_engine


def selection(root):
    package = root / "src/fusion_cli"
    (package / "cli").mkdir(parents=True)
    for name in ("__init__.py", "cli/__init__.py", "cli/app.py"):
        (package / name).write_text("# fixture\n")
    files = tuple(
        SourceDigest(
            path.relative_to(root).as_posix(), hashlib.sha256(path.read_bytes()).hexdigest()
        )
        for path in sorted(package.rglob("*.py"))
    )
    return EngineSelection(root, "a" * 40, files)


def test_source_and_import_proof_is_truthful_about_revision(tmp_path):
    chosen = selection(tmp_path)
    package = SimpleNamespace(__file__=str(tmp_path / "src/fusion_cli/__init__.py"))
    entry = SimpleNamespace(__file__=str(tmp_path / "src/fusion_cli/cli/app.py"), main=lambda: None)
    proof = verify_imported_engine(
        chosen, package, entry, {"fusion_cli": package, "fusion_cli.cli.app": entry}, pid=123
    )
    assert proof.pid == 123 and proof.bootstrap_compatible
    assert proof.requested_revision == "a" * 40
    assert proof.revision_provenance == "unverified"
    assert len(proof.source_digest) == 64


@pytest.mark.parametrize("change", ["dirty", "added", "missing", "mixed", "no_main"])
def test_invalid_source_or_import_rejected(tmp_path, change):
    chosen = selection(tmp_path)
    package = SimpleNamespace(__file__=str(tmp_path / "src/fusion_cli/__init__.py"))
    entry = SimpleNamespace(__file__=str(tmp_path / "src/fusion_cli/cli/app.py"), main=lambda: None)
    modules = {"fusion_cli": package, "fusion_cli.cli.app": entry}
    if change == "dirty":
        (tmp_path / "src/fusion_cli/cli/app.py").write_text("changed")
    if change == "added":
        (tmp_path / "src/fusion_cli/new.py").write_text("new")
    if change == "missing":
        (tmp_path / "src/fusion_cli/cli/app.py").unlink()
    if change == "mixed":
        modules["fusion_cli.other"] = SimpleNamespace(__file__="/outside/other.py")
    if change == "no_main":
        entry.main = None
    with pytest.raises(ValueError):
        verify_imported_engine(chosen, package, entry, modules, pid=123)


def test_secret_named_candidate_rejected_without_reading(tmp_path, monkeypatch):
    chosen = selection(tmp_path)
    (tmp_path / "src/fusion_cli/.env.json").write_text("fake-secret")
    from pathlib import Path

    original = Path.read_bytes

    def guarded(path):
        if path.name.startswith(".env"):
            raise AssertionError("Sır okundu.")
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", guarded)
    package = SimpleNamespace(__file__=str(tmp_path / "src/fusion_cli/__init__.py"))
    entry = SimpleNamespace(__file__=str(tmp_path / "src/fusion_cli/cli/app.py"), main=lambda: None)
    with pytest.raises(ValueError):
        verify_imported_engine(chosen, package, entry, {}, pid=123)


def test_manifest_path_escape_rejected(tmp_path):
    chosen = selection(tmp_path)
    with pytest.raises(ValueError):
        EngineSelection(
            tmp_path, chosen.requested_revision, (SourceDigest("../private", "a" * 64),)
        )


def test_outside_symlink_not_hashed(tmp_path, monkeypatch):
    chosen = selection(tmp_path)
    outside = tmp_path / "outside.py"
    outside.write_text("fixture-private")
    (tmp_path / "src/fusion_cli/link.py").symlink_to(outside)
    from pathlib import Path

    original = Path.read_bytes

    def guarded(path):
        if path.resolve() == outside:
            raise AssertionError("Paket dışı dosya okundu.")
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", guarded)
    package = SimpleNamespace(__file__=str(tmp_path / "src/fusion_cli/__init__.py"))
    entry = SimpleNamespace(__file__=str(tmp_path / "src/fusion_cli/cli/app.py"), main=lambda: None)
    with pytest.raises(ValueError):
        verify_imported_engine(chosen, package, entry, {}, pid=123)


def test_secret_target_symlink_not_hashed(tmp_path, monkeypatch):
    chosen = selection(tmp_path)
    secret = tmp_path / ".env.json"
    secret.write_text("fake-secret")
    (tmp_path / "src/fusion_cli/config.json").symlink_to(secret)
    from pathlib import Path

    original = Path.read_bytes

    def guarded(path):
        if path.resolve() == secret:
            raise AssertionError("Sır bağlantı hedefi okundu.")
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", guarded)
    package = SimpleNamespace(__file__=str(tmp_path / "src/fusion_cli/__init__.py"))
    entry = SimpleNamespace(__file__=str(tmp_path / "src/fusion_cli/cli/app.py"), main=lambda: None)
    with pytest.raises(ValueError):
        verify_imported_engine(chosen, package, entry, {}, pid=123)


def test_bool_schema_version_rejected(tmp_path):
    from evals.engine_proof import selection_from_manifest

    with pytest.raises(ValueError):
        selection_from_manifest(
            tmp_path,
            {
                "schema_version": True,
                "requested_revision": "a" * 40,
                "sources": [{"path": "src/fusion_cli/a.py", "digest": "a" * 64}],
            },
        )
