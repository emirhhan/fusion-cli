"""Galeri kimlik indeksi: bounded sayfa, eski yol migration ve güncel dosya sahipliği."""

from fusion_cli.appserver import asset_bridge


def test_gallery_pages_keep_identity_and_notice_new_files_without_duplicate(tmp_path, monkeypatch):
    gallery = tmp_path / "gallery"
    gallery.mkdir()
    monkeypatch.setattr(asset_bridge, "gallery_dir", lambda: gallery)
    for n in range(5):
        (gallery / f"{n}.png").write_bytes(b"fixture")
    seen = set()
    cursor = None
    for _ in range(3):
        page = asset_bridge.asset_page({"sinir": 2, "cursor": cursor}, tmp_path / "profile")
        assert page["ok"]
        assert len(page["items"]) <= 2
        for item in page["items"]:
            assert "path" not in item
            assert item["asset_id"] not in seen
            seen.add(item["asset_id"])
        cursor = page["next_cursor"]
    assert len(seen) == 5 and cursor is None
    (gallery / "new.png").write_bytes(b"fixture")
    page = asset_bridge.asset_page({"sinir": 100}, tmp_path / "profile")
    assert len(page["items"]) == 6
    assert seen.issubset({item["asset_id"] for item in page["items"]})


def test_gallery_page_rejects_invalid_cursor_and_external_symlink(tmp_path, monkeypatch):
    gallery = tmp_path / "gallery"
    gallery.mkdir()
    outside = tmp_path / "secret.png"
    outside.write_bytes(b"outside")
    (gallery / "link.png").symlink_to(outside)
    monkeypatch.setattr(asset_bridge, "gallery_dir", lambda: gallery)
    assert asset_bridge.asset_page({"sinir": 50}, tmp_path / "profile")["items"] == []
    for data in ({"sinir": True}, {"sinir": 1000}, {"cursor": ["bad", "id"]}, {"cursor": {}}):
        assert asset_bridge.asset_page(data, tmp_path / "profile")["ok"] is False


def test_recreated_index_is_rescanned_but_unchanged_pages_do_not_scan(tmp_path, monkeypatch):
    gallery = tmp_path / "gallery"
    gallery.mkdir()
    (gallery / "image.png").write_bytes(b"fixture")
    monkeypatch.setattr(asset_bridge, "gallery_dir", lambda: gallery)
    original = asset_bridge.scoped_files
    calls = []

    def scan(*args):
        calls.append(True)
        return original(*args)

    monkeypatch.setattr(asset_bridge, "scoped_files", scan)
    profile = tmp_path / "profile"
    assert len(asset_bridge.asset_page({}, profile)["items"]) == 1
    assert len(asset_bridge.asset_page({}, profile)["items"]) == 1
    assert len(calls) == 1
    # Linux dosya sistemleri silinen dosyanın inode numarasını hemen yeniden verebilir;
    # eski inode'u tutmak, yeniden oluşturulan veritabanının ayırt edilmesini sağlar.
    (profile / "eski-inode").hardlink_to(profile / "assets.sqlite3")
    (profile / "assets.sqlite3").unlink()
    assert len(asset_bridge.asset_page({}, profile)["items"]) == 1
    assert len(calls) == 2


def test_asset_preview_uses_real_bytes_and_rejects_other_profile_missing_and_html(
    tmp_path, monkeypatch
):
    from PIL import Image

    gallery = tmp_path / "gallery"
    gallery.mkdir()
    monkeypatch.setattr(asset_bridge, "gallery_dir", lambda: gallery)
    image = gallery / "image.png"
    Image.new("RGBA", (640, 480), (30, 60, 220, 120)).save(image)
    profile = tmp_path / "profile"
    asset_id = asset_bridge.asset_page({}, profile)["items"][0]["asset_id"]
    result = asset_bridge.asset_preview({"asset_id": asset_id}, profile)
    assert result["ok"] and result["width"] == 640 and result["height"] == 480
    assert result["data_url"].startswith("data:image/png;base64,")
    assert len(result["data_url"]) < 1500000 and "path" not in result
    assert asset_bridge.asset_preview({"asset_id": asset_id}, tmp_path / "other")["ok"] is False
    image.write_text("<html>login</html>")
    assert asset_bridge.asset_preview({"asset_id": asset_id}, profile)["ok"] is False
    image.unlink()
    assert asset_bridge.asset_preview({"asset_id": asset_id}, profile)["ok"] is False


def test_noisy_preview_fits_existing_one_megabyte_transport_limit(tmp_path, monkeypatch):
    import random

    from PIL import Image

    gallery = tmp_path / "gallery"
    gallery.mkdir()
    monkeypatch.setattr(asset_bridge, "gallery_dir", lambda: gallery)
    Image.frombytes("RGBA", (512, 512), random.Random(1).randbytes(512 * 512 * 4)).save(
        gallery / "noise.png"
    )
    profile = tmp_path / "profile"
    asset_id = asset_bridge.asset_page({}, profile)["items"][0]["asset_id"]
    preview = asset_bridge.asset_preview({"asset_id": asset_id}, profile)
    assert preview["ok"] and len(preview["data_url"]) < 750000


def test_native_gallery_pages_keep_legacy_prompt_and_stable_id(tmp_path, monkeypatch):
    from fusion_cli.appserver.image_flows import write_sidecar

    gallery = tmp_path / "gallery"
    gallery.mkdir()
    monkeypatch.setattr(asset_bridge, "gallery_dir", lambda: gallery)
    for number in range(3):
        image = gallery / f"{number}.png"
        image.write_bytes(b"fixture")
        write_sidecar(image, prompt=f"İstem {number}", provider="Fixture")
    page = asset_bridge.gallery_page({"sinir": 2}, tmp_path / "profile")
    assert page["ok"] and len(page["dosyalar"]) == 2 and page["next_cursor"]
    assert all(
        item["istem"].startswith("İstem ") and item["asset"]["asset_id"]
        for item in page["dosyalar"]
    )
    second = asset_bridge.gallery_page(
        {"sinir": 2, "cursor": page["next_cursor"]}, tmp_path / "profile"
    )
    assert len(second["dosyalar"]) == 1 and second["next_cursor"] is None
