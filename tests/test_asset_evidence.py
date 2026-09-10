"""Görsel asset kanıtının gerçek dosya ve lisans kaydı kuralları."""

from __future__ import annotations

import json
import struct
import zlib

import pytest

from fusion_cli.core.assets import (
    inspect_image_asset,
    validate_asset_inventory,
    validate_asset_manifest,
)
from fusion_cli.core.evidence import EvidenceStatus
from fusion_cli.core.execution_plan import VerificationCheck, VerificationCheckKind
from fusion_cli.engines.agent.step_verification import evaluate_file_check


def _png(width: int, height: int) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    rows = b"".join(b"\0" + b"\xff\0\0\xff" * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


def test_bos_bozuk_uzantisi_yanlis_ve_bir_piksellik_gorsel_reddedilir(tmp_path):
    empty = tmp_path / "empty.png"
    corrupt = tmp_path / "corrupt.png"
    mismatch = tmp_path / "wrong.jpg"
    placeholder = tmp_path / "pixel.png"
    empty.write_bytes(b"")
    corrupt.write_bytes(b"not-an-image")
    mismatch.write_bytes(_png(4, 4))
    placeholder.write_bytes(_png(1, 1))

    assert inspect_image_asset(empty).valid is False
    assert inspect_image_asset(corrupt).valid is False
    assert "uzant" in " ".join(inspect_image_asset(mismatch).findings)
    assert "1x1" in " ".join(inspect_image_asset(placeholder).findings)


def test_gercek_png_kaynak_ve_lisans_manifestiyle_kabul_edilir(tmp_path):
    target = tmp_path / "assets" / "player.png"
    target.parent.mkdir()
    target.write_bytes(_png(8, 12))
    (target.parent / "ASSETS.json").write_text(
        json.dumps(
            {
                "player.png": {
                    "source_url": "https://example.com/free-player",
                    "license": "CC0-1.0",
                }
            }
        ),
        encoding="utf-8",
    )

    inspected = inspect_image_asset(target)

    assert inspected.valid is True
    assert (inspected.format, inspected.width, inspected.height) == ("png", 8, 12)
    assert validate_asset_manifest(target, tmp_path) == ()


def test_manifest_olmadan_gorsel_asset_kanitlanmis_sayilmaz(tmp_path):
    target = tmp_path / "assets" / "player.png"
    target.parent.mkdir()
    target.write_bytes(_png(2, 2))

    assert "manifest" in " ".join(validate_asset_manifest(target, tmp_path)).casefold()


def test_plan_dogrulayici_sprite_kosulunda_manifesti_zorunlu_tutar(tmp_path):
    target = tmp_path / "assets" / "player.png"
    target.parent.mkdir()
    target.write_bytes(_png(4, 4))
    check = VerificationCheck(
        "oyuncu sprite asset mevcut",
        VerificationCheckKind.FILE_EXISTS,
        "assets/player.png",
    )

    missing = evaluate_file_check(check, tmp_path)
    (target.parent / "ASSETS.json").write_text(
        json.dumps(
            {
                "player.png": {
                    "source_url": "https://example.com/player",
                    "license": "CC0",
                }
            }
        ),
        encoding="utf-8",
    )
    valid = evaluate_file_check(check, tmp_path)

    assert missing.status is EvidenceStatus.FAILED
    assert valid.status is EvidenceStatus.PASSED


def test_asset_manifesti_var_ama_indirilen_dosya_yoksa_adim_gecmez(tmp_path):
    manifest = tmp_path / "ASSETS.json"
    manifest.write_text(
        json.dumps(
            {
                "assets": [
                    {
                        "path": "assets/player.png",
                        "source_url": "https://example.com/player",
                        "license": "CC0",
                    }
                ]
            }
        )
    )
    check = VerificationCheck(
        "Assetler indirildi", VerificationCheckKind.FILE_EXISTS, "ASSETS.json"
    )

    result = evaluate_file_check(check, tmp_path)

    assert result.status is EvidenceStatus.FAILED
    assert "assets/player.png" in result.summary


def test_liste_manifesti_gercek_gorsel_ve_kaynakla_gecer(tmp_path):
    (tmp_path / "player.png").write_bytes(_png(8, 8))
    manifest = tmp_path / "ASSETS.json"
    manifest.write_text(
        json.dumps(
            {
                "assets": [
                    {
                        "path": "player.png",
                        "source_url": "https://example.com/player",
                        "license": "CC0",
                    }
                ]
            }
        )
    )
    assert validate_asset_inventory(manifest, tmp_path) == ()


def test_manifestteki_kok_disi_asset_okunmaz(tmp_path):
    manifest = tmp_path / "ASSETS.json"
    manifest.write_text(json.dumps({"../outside.png": {"license": "CC0"}}))
    assert "çalışma kökü dışında" in " ".join(validate_asset_inventory(manifest, tmp_path))


@pytest.mark.parametrize("name", ["ASSETS.json", "LICENSES.json", "bad\x00.png"])
def test_manifest_kendisi_lisans_belgesi_ve_bozuk_yolu_asset_saymaz(tmp_path, name):
    manifest = tmp_path / "ASSETS.json"
    if name == "LICENSES.json":
        (tmp_path / name).write_text("{}")
    manifest.write_text(json.dumps({name: {"source_url": "https://example.com", "license": "CC0"}}))
    assert validate_asset_inventory(manifest, tmp_path)
