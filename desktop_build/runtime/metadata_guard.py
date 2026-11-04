"""PyInstaller'ın kopyalayacağı proje metadata'sını kaynak sürümüyle eşleştir."""

from importlib import metadata


def require_project_metadata_version(expected: str) -> None:
    """Eski editable metadata veya eksik kurulumla paket üretimini başlatma."""
    try:
        installed = metadata.version("fusion-cli")
    except metadata.PackageNotFoundError:
        installed = "eksik"
    if installed != expected:
        raise RuntimeError(
            f"fusion-cli metadata sürümü {installed}; kaynak sürümü {expected}. "
            "Paketleme durduruldu. Aynı Python ortamında proje metadata'sını yenile: "
            "python -m pip install --no-index --no-deps --no-build-isolation -e . "
            "PYTHONPATH=src altında sürümü tekrar doğrula; eski src/fusion_cli.egg-info "
            "yeni dağıtımı gölgeliyorsa önce geri alınabilir biçimde yedekle."
        )
