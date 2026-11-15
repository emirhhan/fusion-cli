from pathlib import Path

from desktop_build.macos.write_runtime_report import human_size


def test_insan_okunur_boyut_dosya_ve_dizin_icin_hesaplanir(tmp_path: Path):
    file = tmp_path / "archive"
    file.write_bytes(b"x" * 2048)
    assert human_size(file) == "2.0 KiB"

    directory = tmp_path / "Fusion.app"
    directory.mkdir()
    (directory / "one").write_bytes(b"x" * 1024)
    (directory / "two").write_bytes(b"x" * 1024)
    assert human_size(directory) == "2.0 KiB"


def _sahte_kok(tmp_path: Path) -> Path:
    import json

    runtime = tmp_path / "app/src-tauri/resources/runtime"
    runtime.mkdir(parents=True)
    (runtime / "arsiv.tar.zst").write_bytes(b"x" * 1024)
    (runtime / "runtime-manifest.json").write_text(
        json.dumps(
            {
                "target": "aarch64-apple-darwin",
                "runtime_version": "1.2.3",
                "archive": "arsiv.tar.zst",
                "files": ["a", "b"],
            }
        ),
        encoding="utf-8",
    )
    bundle = tmp_path / "app/src-tauri/target/release/bundle"
    (bundle / "macos/Fusion.app").mkdir(parents=True)
    (bundle / "macos/Fusion.app/bin").write_bytes(b"x" * 1024)
    (bundle / "dmg").mkdir()
    (bundle / "dmg/Fusion.dmg").write_bytes(b"x" * 2048)
    return tmp_path


def test_rapor_olculmemis_sonucu_gecti_diye_yazmaz(tmp_path: Path, monkeypatch):
    """Q1-04: kalite kapısı satırları sabit dizgiydi, hiçbir sonuç okunmuyordu.

    Ölçüldü (30 Ekim): rapor "Python kalite kapısı: geçti (2.514 test)" gibi
    satırları, hiçbir test çalışmadan ve bayat sayılarla yazıyordu.
    """
    import subprocess

    from desktop_build.macos.write_runtime_report import write_report

    monkeypatch.setattr(subprocess, "check_output", lambda *a, **k: "abc1234\n")
    cikti = tmp_path / "rapor.md"

    write_report(_sahte_kok(tmp_path), cikti)

    metin = cikti.read_text(encoding="utf-8")
    assert "geçti" not in metin
    assert "2.514" not in metin
    assert "Runtime sürümü: `1.2.3`" in metin
    assert "Ölçülmedi" in metin


def test_rapor_yalniz_cagirandan_gelen_sonuclari_yazar(tmp_path: Path, monkeypatch):
    import subprocess

    from desktop_build.macos.write_runtime_report import write_report

    monkeypatch.setattr(subprocess, "check_output", lambda *a, **k: "abc1234\n")
    cikti = tmp_path / "rapor.md"

    write_report(_sahte_kok(tmp_path), cikti, results=["Python kalite kapısı=geçti (7 test)"])

    metin = cikti.read_text(encoding="utf-8")
    assert "- Python kalite kapısı: geçti (7 test)" in metin


def test_sonuc_argumani_ad_esittir_deger_ister():
    import pytest
    from desktop_build.macos.write_runtime_report import parse_results

    assert parse_results(["A=b c"]) == ["A=b c"]
    with pytest.raises(ValueError):
        parse_results(["degersiz"])
