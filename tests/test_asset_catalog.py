"""Ortak dosya kimliği: kapsam, kalıcılık ve sayfalama sözleşmesi."""

from pathlib import Path

import pytest

from fusion_cli.memory.asset_catalog import AssetCatalog, AssetCatalogError


def test_same_path_survives_restart_and_unknown_metadata_stays_unknown(tmp_path: Path) -> None:
    root = tmp_path / "gallery"
    root.mkdir()
    (root / "image.png").write_bytes(b"file")
    db = tmp_path / "assets.sqlite"
    first = AssetCatalog(db, "profile", {"gallery": root}).register(
        "gallery", "image.png", kind="image"
    )
    second = AssetCatalog(db, "profile", {"gallery": root}).register(
        "gallery", "image.png", kind="image"
    )
    assert first == second
    assert first["metadata_version"] == 1
    assert first["width"] is None and first["seed"] is None
    assert first["relative_path"] == "image.png"


def test_identity_does_not_grant_other_profile_or_root_access(tmp_path: Path) -> None:
    root = tmp_path / "gallery"
    root.mkdir()
    (root / "image.png").write_bytes(b"file")
    db = tmp_path / "assets.sqlite"
    owner = AssetCatalog(db, "first", {"gallery": root})
    item = owner.register("gallery", "image.png", kind="image")
    with pytest.raises(AssetCatalogError):
        AssetCatalog(db, "second", {"gallery": root}).resolve(item["asset_id"])
    with pytest.raises(AssetCatalogError):
        AssetCatalog(db, "first", {}).resolve(item["asset_id"])
    different = tmp_path / "other"
    different.mkdir()
    (different / "image.png").write_bytes(b"other")
    with pytest.raises(AssetCatalogError):
        AssetCatalog(db, "first", {"gallery": different}).resolve(item["asset_id"])


def test_escape_missing_and_deleted_parent_are_truthful(tmp_path: Path) -> None:
    root = tmp_path / "gallery"
    root.mkdir()
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"outside")
    (root / "link.png").symlink_to(outside)
    catalog = AssetCatalog(tmp_path / "assets.sqlite", "profile", {"gallery": root})
    for path in ("../outside.png", "link.png", str(outside)):
        with pytest.raises(AssetCatalogError):
            catalog.register("gallery", path, kind="image")
    (root / "parent.png").write_bytes(b"parent")
    (root / "child.png").write_bytes(b"child")
    parent = catalog.register("gallery", "parent.png", kind="image")
    child = catalog.register(
        "gallery", "child.png", kind="image", parent_asset_ids=(parent["asset_id"],)
    )
    (root / "parent.png").unlink()
    assert catalog.resolve(parent["asset_id"])["available"] is False
    assert catalog.resolve(child["asset_id"])["parent_asset_ids"] == [parent["asset_id"]]
    assert catalog.resolve(child["asset_id"])["available"] is True


def test_pages_have_total_order_and_do_not_repeat(tmp_path: Path) -> None:
    root = tmp_path / "gallery"
    root.mkdir()
    catalog = AssetCatalog(
        tmp_path / "assets.sqlite", "profile", {"gallery": root}, clock=lambda: 1.0
    )
    expected = set()
    for number in range(7):
        (root / f"{number}.png").write_bytes(b"image")
        expected.add(catalog.register("gallery", f"{number}.png", kind="image")["asset_id"])
    seen = []
    cursor = None
    while True:
        page = catalog.list_page(limit=2, cursor=cursor)
        seen.extend(item["asset_id"] for item in page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert len(seen) == len(set(seen)) == 7
    assert set(seen) == expected


def test_descending_pages_preserve_total_order_for_recent_gallery(tmp_path: Path) -> None:
    root = tmp_path / "gallery"
    root.mkdir()
    catalog = AssetCatalog(
        tmp_path / "assets.sqlite", "profile", {"gallery": root}, clock=lambda: 1.0
    )
    ids = []
    for number in range(5):
        (root / f"{number}.png").write_bytes(b"fixture")
        ids.append(catalog.register("gallery", f"{number}.png", kind="image")["asset_id"])
    first = catalog.list_page(limit=2, descending=True)
    second = catalog.list_page(limit=2, cursor=first["next_cursor"], descending=True)
    assert [item["asset_id"] for item in [*first["items"], *second["items"]]] == sorted(
        ids, reverse=True
    )[:4]


def test_listing_only_uses_current_allowed_roots(tmp_path: Path) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "a.txt").write_text("a")
    (second / "b.txt").write_text("b")
    db = tmp_path / "assets.sqlite"
    wide = AssetCatalog(db, "profile", {"first": first, "second": second})
    visible = wide.register("first", "a.txt", kind="document")
    wide.register("second", "b.txt", kind="document")
    narrow = AssetCatalog(db, "profile", {"first": first})
    assert [item["asset_id"] for item in narrow.list_page()["items"]] == [visible["asset_id"]]
    assert AssetCatalog(db, "profile", {}).list_page()["items"] == []


@pytest.mark.parametrize("change", ["missing", "wrong-kind", "false-size", "future", "wrong-time"])
def test_corrupt_metadata_fails_closed(tmp_path: Path, change: str) -> None:
    import json
    import sqlite3
    from contextlib import closing

    root = tmp_path / "gallery"
    root.mkdir()
    (root / "image.png").write_bytes(b"image")
    db = tmp_path / "assets.sqlite"
    catalog = AssetCatalog(db, "profile", {"gallery": root})
    item = catalog.register("gallery", "image.png", kind="image")
    with closing(sqlite3.connect(db)) as connection, connection:
        metadata = json.loads(connection.execute("SELECT metadata FROM assets").fetchone()[0])
        if change == "missing":
            del metadata["kind"]
        elif change == "wrong-kind":
            metadata["kind"] = ["image"]
        elif change == "false-size":
            metadata["width"] = "640"
        elif change == "future":
            metadata["metadata_version"] = 2
        else:
            metadata["created_at"] = -1
        connection.execute("UPDATE assets SET metadata=?", (json.dumps(metadata),))
    with pytest.raises(AssetCatalogError):
        catalog.resolve(item["asset_id"])
    with pytest.raises(AssetCatalogError):
        catalog.register("gallery", "image.png", kind="image")


def test_legacy_gallery_and_library_share_identity_without_rewriting_sidecar(
    tmp_path: Path,
) -> None:
    import json

    from fusion_cli.appserver.image_flows import list_gallery
    from fusion_cli.appserver.library import list_library

    root = tmp_path / "gallery"
    root.mkdir()
    image = root / "image.png"
    image.write_bytes(b"legacy file")
    sidecar = root / "image.png.json"
    original = json.dumps({"istem": "Eski istem", "saglayici": "eski"})
    sidecar.write_text(original)
    catalog = AssetCatalog(tmp_path / "assets.sqlite", "profile", {"gallery": root})
    gallery = list_gallery(root, catalog=catalog)["dosyalar"][0]
    library = list_library({}, tmp_path / "library", root, catalog=catalog)["dosyalar"][0]
    assert gallery["asset"]["asset_id"] == library["asset"]["asset_id"]
    assert gallery["yol"] == library["yol"] == str(image)
    assert gallery["istem"] == "Eski istem"
    assert sidecar.read_text() == original
    assert catalog.resolve(gallery["asset"]["asset_id"])["path"] == str(image)
