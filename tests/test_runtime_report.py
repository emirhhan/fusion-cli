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
