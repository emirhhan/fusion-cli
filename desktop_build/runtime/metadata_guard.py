"""PyInstaller'ın kopyalayacağı proje metadata'sını kaynak sürümüyle eşleştir."""

import ast
from importlib import metadata
from pathlib import Path


def checkout_version(repo_root: str | Path) -> str:
    """Kurulu paketi import etmeden bu checkout'un tek sürüm sabitini oku."""
    source = Path(repo_root) / "src/fusion_cli/__init__.py"
    for node in ast.parse(source.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        if any(isinstance(target, ast.Name) and target.id == "__version__" for target in targets):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                return node.value.value
            break
    raise RuntimeError("Kaynak __version__ sabiti okunamadı; paketleme durduruldu.")


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
