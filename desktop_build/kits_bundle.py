"""Masaüstü paketindeki Kits bileşenini doğrular; Kits'siz paket hiçbir kapıdan geçmez.

Ölçüldü (31 Ekim): Kits'siz paket kurulunca uygulama "Bu Fusion paketinde Kits
bileşeni bulunamadı" hatası veriyordu. Kullanıcı kararı: indiren herkes Kits'i
kurulu alsın. Bu modül smoke, güncelleme ve yayın betiklerinin ortak kapısıdır.

Beklenen düzen (`app/scripts/prepare-kits.mjs` üretir, Tauri `kits/` altına koyar)::

    kits/kits-manifest.json
    kits/node | kits/node.exe
    kits/app/dist/server/server/index.js
    kits/app/dist/client/index.html
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

#: Uygulamanın (`kits_process.rs` → `SERVER_ENTRY`) başlattığı sunucu girişi.
SERVER_ENTRY = Path("app/dist/server/server/index.js")
CLIENT_INDEX = Path("app/dist/client/index.html")
MANIFEST_NAME = "kits-manifest.json"
#: Kits `package.json` `engines.node` alt sınırı (`kits_process.rs` → `MIN_NODE_MAJOR`).
MIN_NODE_MAJOR = 24
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_NODE_VERSION = re.compile(r"^v(\d+)\.\d+\.\d+")
#: Mach-O sihirli sayıları (32/64 bit, iki bayt sırası, evrensel ikili).
_MACH_O_MAGIC = {
    bytes.fromhex(item)
    for item in ("feedface", "feedfacf", "cefaedfe", "cffaedfe", "cafebabe", "bebafeca")
}
_SYSTEM_LIBRARY_PREFIXES = ("/usr/lib/", "/System/")
_OTOOL_TIMEOUT_SECONDS = 30

Otool = Callable[[Path], str]


class KitsBundleError(RuntimeError):
    """Pakette Kits eksik ya da bozuk; paket yayınlanamaz."""


def _run_otool(binary: Path) -> str:
    result = subprocess.run(
        ["otool", "-L", str(binary)],
        capture_output=True,
        text=True,
        timeout=_OTOOL_TIMEOUT_SECONDS,
        check=False,
    )
    if result.returncode != 0:
        raise KitsBundleError(f"Kits Node bağımlılıkları okunamadı: {binary}\n{result.stderr}")
    return result.stdout


def foreign_libraries(otool_output: str) -> list[str]:
    """`otool -L` çıktısında sistem dışı (Homebrew, @rpath...) kitaplıklar."""
    libraries = [line.strip().split(" (")[0] for line in otool_output.splitlines()[1:]]
    return [item for item in libraries if item and not item.startswith(_SYSTEM_LIBRARY_PREFIXES)]


def _require_file(path: Path, label: str) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        raise KitsBundleError(f"{label} pakette yok ya da boş: {path}")


def _check_node(node: Path, *, macos: bool, otool: Otool) -> None:
    _require_file(node, f"Kits Node ikilisi ({node.name})")
    if os.name != "nt" and not os.access(node, os.X_OK):
        raise KitsBundleError(f"Kits Node ikilisi çalıştırılabilir değil: {node}")
    if not macos:
        return
    with node.open("rb") as stream:
        if stream.read(4) not in _MACH_O_MAGIC:
            raise KitsBundleError(f"Kits Node ikilisi bir Mach-O ikilisi değil: {node}")
    foreign = foreign_libraries(otool(node))
    if foreign:
        raise KitsBundleError(
            f"Kits Node ikilisi taşınabilir değil; sistem dışı kitaplıklara bağlı: {foreign[:3]}"
        )


def _load_manifest(kits_dir: Path) -> dict[str, Any]:
    path = kits_dir / MANIFEST_NAME
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise KitsBundleError(f"{MANIFEST_NAME} pakette yok: {path}") from error
    except json.JSONDecodeError as error:
        raise KitsBundleError(f"{MANIFEST_NAME} okunamadı: {error}") from error
    if not isinstance(manifest, dict):
        raise KitsBundleError(f"{MANIFEST_NAME} bir nesne olmalı.")
    data = cast(dict[str, Any], manifest)
    if not _COMMIT.match(str(data.get("commit", ""))):
        raise KitsBundleError(f"{MANIFEST_NAME} geçerli bir Kits commit'i taşımıyor.")
    version = _NODE_VERSION.match(str(data.get("nodeVersion", "")))
    if not version or int(version.group(1)) < MIN_NODE_MAJOR:
        raise KitsBundleError(
            f"Kits Node {MIN_NODE_MAJOR} veya üzerini gerektirir: {data.get('nodeVersion')}"
        )
    return data


def inspect_kits(
    kits_dir: Path,
    *,
    node_name: str,
    macos: bool,
    otool: Otool | None = None,
) -> dict[str, Any]:
    """Kits paketini doğrula ve manifestini döndür; eksikse `KitsBundleError`."""
    if not kits_dir.is_dir():
        raise KitsBundleError(f"Pakette Kits bileşeni yok: {kits_dir}")
    _require_file(kits_dir / SERVER_ENTRY, "Kits sunucusu")
    _require_file(kits_dir / CLIENT_INDEX, "Kits istemcisi")
    _check_node(kits_dir / node_name, macos=macos, otool=otool or _run_otool)
    return _load_manifest(kits_dir)


def describe(manifest: dict[str, Any]) -> str:
    """Rapor satırı: kısa commit, commit tarihi ve Node sürümü."""
    return (
        f"Kits {str(manifest['commit'])[:12]} ({manifest.get('commitDate', '?')})"
        f" · Node {manifest['nodeVersion']}"
    )
