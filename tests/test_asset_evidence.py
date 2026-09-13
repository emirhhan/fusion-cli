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


def test_belge_duzeyi_manifesti_ortak_kaynak_ve_lisansla_gecer(tmp_path):
    """Tek paketten gelen dosyalar kaynağı ve lisansı PAYLAŞIR.

    Ölçüldü (13 Eylül, Godot koşusu): OpenGameArt paketi indirildi, açıldı ve
    manifest tam bu biçimde yazıldı; katı okuma onu "geçersiz asset kaydı: source"
    diye reddetti, geri alma dosyayı sildi ve adım kurtarılamadı.
    """
    (tmp_path / "player.png").write_bytes(_png(8, 8))
    (tmp_path / "enemy.png").write_bytes(_png(8, 8))
    manifest = tmp_path / "ASSETS.json"
    manifest.write_text(
        json.dumps(
            {
                "source": "https://opengameart.org/content/pixel-character",
                "license": "CC0",
                "author": "surt",
                "files": ["player.png", "enemy.png"],
            }
        )
    )

    assert validate_asset_inventory(manifest, tmp_path) == ()


def test_belge_duzeyi_manifesti_source_url_adiyla_da_gecer(tmp_path):
    (tmp_path / "player.png").write_bytes(_png(8, 8))
    manifest = tmp_path / "ASSETS.json"
    manifest.write_text(
        json.dumps(
            {
                "source_url": "https://example.com/pack",
                "license": "MIT",
                "files": ["player.png"],
            }
        )
    )

    assert validate_asset_inventory(manifest, tmp_path) == ()


def test_belge_duzeyi_manifestinde_lisans_yoksa_gecmez(tmp_path):
    """Tolerans BİÇİMdedir: eksik lisans yine düşer."""
    (tmp_path / "player.png").write_bytes(_png(8, 8))
    manifest = tmp_path / "ASSETS.json"
    manifest.write_text(
        json.dumps({"source": "https://example.com/pack", "files": ["player.png"]})
    )

    bulgular = " ".join(validate_asset_inventory(manifest, tmp_path))

    assert "lisans" in bulgular


def test_belge_duzeyi_manifesti_indirilmemis_dosyayi_gizlemez(tmp_path):
    manifest = tmp_path / "ASSETS.json"
    manifest.write_text(
        json.dumps(
            {"source": "https://example.com/p", "license": "CC0", "files": ["yok.png"]}
        )
    )

    bulgular = " ".join(validate_asset_inventory(manifest, tmp_path))

    assert "bulunamadı veya boş" in bulgular
    assert "download_file" in bulgular


def test_dosya_basina_alan_belge_duzeyini_ezebilir(tmp_path):
    (tmp_path / "player.png").write_bytes(_png(8, 8))
    manifest = tmp_path / "ASSETS.json"
    manifest.write_text(
        json.dumps(
            {
                "source": "https://example.com/paket",
                "license": "CC0",
                "files": [
                    {
                        "path": "player.png",
                        "source_url": "https://example.com/tek-dosya",
                        "license": "MIT",
                    }
                ],
            }
        )
    )

    assert validate_asset_inventory(manifest, tmp_path) == ()


def test_gecersiz_kayit_hatasi_beklenen_bicimi_soyler(tmp_path):
    manifest = tmp_path / "ASSETS.json"
    manifest.write_text(json.dumps({"player.png": "CC0"}))

    bulgular = " ".join(validate_asset_inventory(manifest, tmp_path))

    assert "geçersiz asset kaydı" in bulgular
    assert "files" in bulgular


def test_kok_tabanli_yol_yazan_manifest_diskteki_dosyayi_bulur(tmp_path):
    """Manifest `assets/` içinde ama yolları KÖKE göre yazılmış.

    Ölçüldü (13 Eylül, Godot koşusu): Kenney Platformer Kit indirildi (4,6 MB),
    777 dosya açıldı ve manifest `assets/Previews/grass.png` biçiminde yazıldı.
    Tek tabanlı çözüm `assets/assets/Previews/grass.png` arayıp "dosya bulunamadı"
    dedi; dosyalar diskte duruyordu ve adım kurtarılamadı.
    """
    (tmp_path / "assets/Previews").mkdir(parents=True)
    (tmp_path / "assets/Previews/grass.png").write_bytes(_png(8, 8))
    manifest = tmp_path / "assets/ASSETS.json"
    manifest.write_text(
        json.dumps(
            {
                "source_url": "https://kenney.nl/assets/platformer-kit",
                "license": "CC0",
                "files": ["assets/Previews/grass.png"],
            }
        )
    )

    assert validate_asset_inventory(manifest, tmp_path) == ()


def test_manifest_tabanli_yol_da_calismaya_devam_eder(tmp_path):
    (tmp_path / "assets/Previews").mkdir(parents=True)
    (tmp_path / "assets/Previews/grass.png").write_bytes(_png(8, 8))
    manifest = tmp_path / "assets/ASSETS.json"
    manifest.write_text(
        json.dumps(
            {
                "source_url": "https://kenney.nl/assets/platformer-kit",
                "license": "CC0",
                "files": ["Previews/grass.png"],
            }
        )
    )

    assert validate_asset_inventory(manifest, tmp_path) == ()


def test_kok_disina_cikan_yol_iki_tabanla_da_kabul_edilmez(tmp_path):
    """Tolerans yalnız TABAN seçimindedir; kök sınırı gevşemez."""
    manifest = tmp_path / "assets" / "ASSETS.json"
    manifest.parent.mkdir()
    manifest.write_text(
        json.dumps(
            {
                "source_url": "https://example.com/p",
                "license": "CC0",
                "files": ["../../x.png"],
            }
        )
    )

    bulgular = " ".join(validate_asset_inventory(manifest, tmp_path))

    assert "çalışma kökü dışında" in bulgular


def _kenney_manifest(kok, files):
    manifest = kok / "ASSETS.json"
    manifest.write_text(
        json.dumps(
            {
                "source_url": "https://kenney.nl/assets/pixel-platformer",
                "license": "CC0",
                "files": list(files),
            }
        )
    )
    return manifest


def test_indirilip_hic_kullanilmayan_varlik_bildirilir(tmp_path):
    """İndirmek KULLANMAK değildir.

    Ölçüldü (13 Eylül, Godot koşusu): Kenney Pixel Platformer indirildi, 252 dosya
    açıldı, manifest doğru yazıldı ve plan "tamamlandı" dedi — ama sahnede tek
    sprite yoktu; oyun HealthBar ve Label'lardan oluşuyordu.
    """
    from fusion_cli.core.assets import unused_manifest_assets

    (tmp_path / "Tiles").mkdir()
    (tmp_path / "Tiles/tile_0000.png").write_bytes(_png(8, 8))
    (tmp_path / "main.tscn").write_text('[gd_scene format=3]\n[node name="Main" type="Node2D"]\n')
    # Manifestin kendisi taranmaz: dosyayı zaten listeler, onu "kullanım" saymak
    # kapıyı işlevsiz kılardı.
    manifest = _kenney_manifest(tmp_path, ["Tiles/tile_0000.png"])

    assert unused_manifest_assets(manifest, tmp_path) == ("Tiles/tile_0000.png",)


def test_sahnede_anilan_varlik_kullanilmis_sayilir(tmp_path):
    from fusion_cli.core.assets import unused_manifest_assets

    (tmp_path / "Tiles").mkdir()
    (tmp_path / "Tiles/tile_0000.png").write_bytes(_png(8, 8))
    (tmp_path / "main.tscn").write_text(
        '[gd_scene format=3]\n'
        '[ext_resource type="Texture2D" path="res://Tiles/tile_0000.png" id="1"]\n'
    )
    manifest = _kenney_manifest(tmp_path, ["Tiles/tile_0000.png"])

    assert unused_manifest_assets(manifest, tmp_path) == ()


def test_atlas_dosyasi_anilinca_tum_karolar_kullanilmis_sayilmaz(tmp_path):
    """Kapı dosya adı düzeyinde çalışır: anılan atlas geçer, anılmayan karo geçmez."""
    from fusion_cli.core.assets import unused_manifest_assets

    (tmp_path / "Tilemap").mkdir()
    for ad in ("tilemap.png", "tilemap-characters.png"):
        (tmp_path / "Tilemap" / ad).write_bytes(_png(8, 8))
    (tmp_path / "level.gd").write_text('const ATLAS = "res://Tilemap/tilemap.png"\n')
    manifest = _kenney_manifest(tmp_path, ["Tilemap/tilemap.png", "Tilemap/tilemap-characters.png"])

    assert unused_manifest_assets(manifest, tmp_path) == ("Tilemap/tilemap-characters.png",)


def test_kaynak_dosyasi_olmayan_projede_kullanim_iddia_edilmez(tmp_path):
    """Hiç kaynak dosya yoksa kapı SESSİZ kalır: ölçemediği şeyi suçlamaz."""
    from fusion_cli.core.assets import unused_manifest_assets

    (tmp_path / "a.png").write_bytes(_png(8, 8))
    manifest = _kenney_manifest(tmp_path, ["a.png"])

    assert unused_manifest_assets(manifest, tmp_path) == ()


def test_yol_yanlissa_gercek_konum_soylenir(tmp_path):
    """Dosya VAR, yol yanlış: model yeniden indirmeye kalkmamalı.

    Ölçüldü (13 Eylül, Godot koşusu): arşiv açıldıktan sonra manifest
    `assets/PNG/PNG/Player/Poses/player_fall.png` yazdı (bir segment iki kez);
    dosya `assets/PNG/Player/Poses/player_fall.png` altındaydı. "Bulunamadı"
    demek düzeltmeyi göstermiyordu; adım yeniden indirmeye kalkıp hakkını tüketti.
    """
    gercek = tmp_path / "assets/PNG/Player/Poses"
    gercek.mkdir(parents=True)
    (gercek / "player_fall.png").write_bytes(_png(8, 8))
    manifest = tmp_path / "ASSETS.json"
    manifest.write_text(
        json.dumps(
            {
                "source_url": "https://kenney.nl/assets/platformer-characters",
                "license": "CC0",
                "files": ["assets/PNG/PNG/Player/Poses/player_fall.png"],
            }
        )
    )

    bulgular = " ".join(validate_asset_inventory(manifest, tmp_path))

    assert "yol yanlış" in bulgular
    assert "assets/PNG/Player/Poses/player_fall.png" in bulgular
    assert "yeniden indirmeye gerek yok" in bulgular


def test_dosya_gercekten_yoksa_indirme_yonlendirmesi_kalir(tmp_path):
    manifest = tmp_path / "ASSETS.json"
    manifest.write_text(
        json.dumps(
            {
                "source_url": "https://example.com/p",
                "license": "CC0",
                "files": ["assets/hic_yok.png"],
            }
        )
    )

    bulgular = " ".join(validate_asset_inventory(manifest, tmp_path))

    assert "bulunamadı veya boş" in bulgular
    assert "download_file" in bulgular
