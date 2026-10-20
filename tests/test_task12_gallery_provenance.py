"""Paket 12: galeri sınırı ve eski provenance için çevrimdışı örnekler."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fusion_cli.appserver import image_flows, library


@pytest.mark.parametrize("api", ["gallery", "library"])
def test_gallery_does_not_publish_outside_symlink(tmp_path: Path, api: str) -> None:
    gallery = tmp_path / "galeri"
    gallery.mkdir()
    outside = tmp_path / "disarida.png"
    outside.write_bytes(b"yerel listeleme ornegi")
    (gallery / "bag.png").symlink_to(outside)

    result = (
        image_flows.list_gallery(gallery)
        if api == "gallery"
        else library.list_library({}, tmp_path / "kitaplik", gallery)
    )
    assert result["dosyalar"] == []


def test_gallery_does_not_publish_dangling_symlink(tmp_path: Path) -> None:
    gallery = tmp_path / "galeri"
    gallery.mkdir()
    (gallery / "eksik.png").symlink_to(tmp_path / "eksik-hedef.png")

    assert image_flows.list_gallery(gallery) == {"ok": True, "dosyalar": []}


def test_gallery_preserves_legacy_sidecar_provenance(tmp_path: Path) -> None:
    image = tmp_path / "resim.png"
    image.write_bytes(b"yerel listeleme ornegi")
    image_flows.write_sidecar(image, prompt="yerel istem", provider="yerel saglayici")

    assert image_flows.list_gallery(tmp_path)["dosyalar"] == [
        {"yol": str(image), "istem": "yerel istem", "saglayici": "yerel saglayici"}
    ]
    assert json.loads(image.with_suffix(".png.json").read_text(encoding="utf-8")) == {
        "istem": "yerel istem",
        "saglayici": "yerel saglayici",
    }


def test_gallery_unknown_provenance_stays_empty(tmp_path: Path) -> None:
    image = tmp_path / "resim.png"
    image.write_bytes(b"yerel listeleme ornegi")

    assert image_flows.list_gallery(tmp_path)["dosyalar"] == [
        {"yol": str(image), "istem": "", "saglayici": ""}
    ]


def test_sidecar_write_never_follows_existing_symlink(tmp_path: Path) -> None:
    image = tmp_path / "resim.png"
    image.write_bytes(b"yerel gorsel")
    outside = tmp_path / "kullanici-belgesi.txt"
    outside.write_text("korunacak içerik", encoding="utf-8")
    sidecar = image.with_suffix(".png.json")
    sidecar.symlink_to(outside)
    image_flows.write_sidecar(image, prompt="yeni istem", provider="yerel")
    assert outside.read_text(encoding="utf-8") == "korunacak içerik"
    assert not sidecar.is_symlink()
    assert json.loads(sidecar.read_text(encoding="utf-8"))["istem"] == "yeni istem"


def test_sidecar_failed_commit_keeps_previous_provenance(tmp_path: Path, monkeypatch) -> None:
    image = tmp_path / "resim.png"
    image.write_bytes(b"yerel gorsel")
    image_flows.write_sidecar(image, prompt="eski istem", provider="yerel")
    sidecar = image.with_suffix(".png.json")
    previous = sidecar.read_bytes()

    def fail_replace(source, target):
        raise OSError("kontrollü commit hatası")

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(OSError, match="kontrollü commit"):
        image_flows.write_sidecar(image, prompt="yeni istem", provider="yerel")
    assert sidecar.read_bytes() == previous
    assert not tuple(tmp_path.glob("*.tmp"))
