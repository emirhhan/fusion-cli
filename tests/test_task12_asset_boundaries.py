"""Paket 12: mevcut dosya API'lerinin kök sınırı için sınırlı hazırlık."""

from __future__ import annotations

from pathlib import Path

import pytest

from fusion_cli.appserver import library, workspace


@pytest.mark.parametrize("escape", ["relative", "absolute", "symlink"])
def test_generated_asset_cannot_register_outside_project(tmp_path: Path, escape: str) -> None:
    root = tmp_path / "proje"
    root.mkdir()
    outside = tmp_path / "disarida.txt"
    outside.write_text("yerel örnek", encoding="utf-8")
    link = root / "bag.txt"
    link.symlink_to(outside)
    paths = {"relative": "../disarida.txt", "absolute": str(outside), "symlink": "bag.txt"}
    base, gallery = tmp_path / "kitaplik", tmp_path / "galeri"

    recorded = library.record_generated(root, [paths[escape]], base)

    assert recorded == 0
    assert library.list_library({}, base, gallery)["dosyalar"] == []
    assert outside.read_text(encoding="utf-8") == "yerel örnek"


@pytest.mark.parametrize("raw", ["../disarida.txt", "bag.txt"])
def test_existing_workspace_resolver_rejects_escape(tmp_path: Path, raw: str) -> None:
    root = tmp_path / "proje"
    root.mkdir()
    outside = tmp_path / "disarida.txt"
    outside.write_text("yerel örnek", encoding="utf-8")
    (root / "bag.txt").symlink_to(outside)

    with pytest.raises(workspace.WorkspacePathError):
        workspace.resolve_workspace_path(root, raw)


def test_existing_library_hides_missing_generated_file(tmp_path: Path) -> None:
    root = tmp_path / "proje"
    root.mkdir()
    image = root / "resim.png"
    image.write_bytes(b"yerel listeleme ornegi")
    base, gallery = tmp_path / "kitaplik", tmp_path / "galeri"
    assert library.record_generated(root, ["resim.png"], base) == 1
    image.unlink()

    assert library.list_library({}, base, gallery) == {"ok": True, "dosyalar": [], "toplam": 0}


def test_registered_generated_file_replaced_with_outside_symlink_is_hidden(tmp_path):
    root = tmp_path / "proje"
    root.mkdir()
    asset = root / "rapor.txt"
    asset.write_text("yerel", encoding="utf-8")
    outside = tmp_path / "disarida.txt"
    outside.write_text("dışarıda", encoding="utf-8")
    base, gallery = tmp_path / "kitaplik", tmp_path / "galeri"
    assert library.record_generated(root, ["rapor.txt"], base) == 1
    asset.unlink()
    asset.symlink_to(outside)
    assert library.list_library({}, base, gallery)["dosyalar"] == []


@pytest.mark.parametrize("source", [[], {}])
def test_corrupt_index_source_does_not_break_valid_library_items(tmp_path, source):
    import json

    root = tmp_path / "proje"
    root.mkdir()
    (root / "rapor.txt").write_text("yerel", encoding="utf-8")
    base, gallery = tmp_path / "kitaplik", tmp_path / "galeri"
    library.record_generated(root, ["rapor.txt"], base)
    with (base / "kayitlar.jsonl").open("a", encoding="utf-8") as index:
        index.write(
            json.dumps({"yol": str(root / "bozuk.txt"), "kok": str(root), "kaynak": source}) + "\n"
        )
    assert [item["ad"] for item in library.list_library({}, base, gallery)["dosyalar"]] == [
        "rapor.txt"
    ]
