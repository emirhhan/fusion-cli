"""Proje güveni: çalışma dizinindeki dosyalar ne zaman yürütme ayarı açabilir?

İndirilmiş bir depo kendi `config.yaml`'ıyla MCP süreci, doğrulama komutu veya bir
sırrı uzak adrese taşıyan `token_env` tanımlayabilir; `.fusion/tools` altındaki
Python da araç olarak çalıştırılır. Bu dosyalar ancak kullanıcı projeye güvendikten
(veya Fusion dosyayı kendisi ürettikten) SONRA ve içerikleri o andaki hâliyle aynı
kaldıkça etkinleşir. Karar içerik karmasına bağlıdır: güvenden sonra değişen dosya
yeniden güvensiz sayılır.

Kayıt kullanıcı yapılandırma dizininde tutulur; proje kendi güvenini yazamaz.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..core.errors import ConfigError
from .paths import user_config_dir

#: Proje kökünde yürütme ayarı taşıyabilen yapılandırma dosyası.
PROJECT_CONFIG_NAME = "config.yaml"
#: Fusion'ın ürettiği araçların proje altındaki dizini (`tools/forge.py` ile aynı).
FORGED_TOOLS_DIR = Path(".fusion") / "tools"
_STORE_NAME = "trusted-projects.json"
_SCHEMA_VERSION = 1

#: Güvenilmeyen proje config'inden düşürülen, süreç/ağ/sır erişimi açan bölümler.
EXECUTION_SECTIONS = ("mcp_servers", "hosted_connectors")
#: Aynı gerekçeyle `runtime` altından düşürülen anahtarlar.
EXECUTION_RUNTIME_KEYS = ("verification_commands",)

REASON_TRUSTED = "güvenildi"
REASON_UNKNOWN = "proje için güven kaydı yok"
REASON_CHANGED = "proje yapılandırması güven kaydından sonra değişti"
REASON_REDIRECTED = "yapılandırma yolu proje .env dosyasıyla değiştirildi"


@dataclass(frozen=True, slots=True)
class TrustState:
    """Bir proje kökü için güven kararı."""

    trusted: bool
    reason: str


def trust_store_file() -> Path:
    """Güven kaydının yolu (kullanıcıya ait; projenin içinde DEĞİL)."""
    return user_config_dir() / _STORE_NAME


def resolve_project_trust(root: Path) -> TrustState:
    """Proje `config.yaml`'ı güvenildiği andaki içerikle mi duruyor?"""
    record = _load().get(_key(root))
    if record is None:
        return TrustState(False, REASON_UNKNOWN)
    if record.get("config_sha256") != _digest(root / PROJECT_CONFIG_NAME):
        return TrustState(False, REASON_CHANGED)
    return TrustState(True, REASON_TRUSTED)


def without_execution_settings(
    data: Mapping[str, object],
) -> tuple[dict[str, object], tuple[str, ...]]:
    """Yürütme açan ayarları çıkarılmış kopya ve çıkarılan ayarların adları."""
    removed = [name for name in EXECUTION_SECTIONS if data.get(name)]
    cleaned = {key: value for key, value in data.items() if key not in EXECUTION_SECTIONS}
    runtime = data.get("runtime")
    if isinstance(runtime, Mapping):
        dropped = [key for key in EXECUTION_RUNTIME_KEYS if runtime.get(key)]
        removed.extend(f"runtime.{key}" for key in dropped)
        cleaned["runtime"] = {k: v for k, v in runtime.items() if k not in EXECUTION_RUNTIME_KEYS}
    return cleaned, tuple(removed)


def trust_project(root: Path) -> None:
    """Projenin şu anki yapılandırmasına ve üretilmiş araçlarına güven."""
    files: dict[str, str] = {}
    for path in sorted((root / FORGED_TOOLS_DIR).glob("*.py")):
        # Kök dışını gösteren bağ ya da `.py` adlı klasör güvene alınmaz.
        if path.is_symlink() or not path.is_file():
            continue
        digest = _digest(path)
        if digest is not None:
            files[_relative(root, path)] = digest
    _update(root, config_sha256=_digest(root / PROJECT_CONFIG_NAME), files=files)


def approve_file(root: Path, path: Path) -> None:
    """Fusion'ın bizzat yazdığı dosyanın şu anki içeriğini güvenilir kaydet.

    Proje config'ine güven bundan ÇIKARILMAZ: kayıt yoksa config karması boş kalır,
    var olan bir `config.yaml` bu boş karmayla eşleşmez.
    """
    digest = _digest(path)
    if digest is None:
        return
    record = _load().get(_key(root), {})
    files = {**record.get("files", {}), _relative(root, path): digest}
    _update(root, config_sha256=record.get("config_sha256"), files=files)


def is_file_trusted(root: Path, path: Path, content: bytes | None = None) -> bool:
    """Dosyanın içeriği güven kaydındaki karmayla birebir aynı mı?

    `content` verilirse karma diskten yeniden okunmaz, VERİLEN baytlardan hesaplanır:
    çalıştırılacak içerikle denetlenen içerik arasında yarış kalmaz.
    """
    record = _load().get(_key(root))
    if record is None or path.is_symlink() or not path.is_file():
        return False
    try:
        expected = record.get("files", {}).get(_relative(root, path))
        actual = hashlib.sha256(content).hexdigest() if content is not None else _digest(path)
        return expected is not None and expected == actual
    except (ValueError, ConfigError):
        # Kök dışına çözülen ya da okunamayan dosya güvenilir değildir; çökme yok.
        return False


def _update(root: Path, *, config_sha256: str | None, files: dict[str, str]) -> None:
    store = _load()
    _save({**store, _key(root): {"config_sha256": config_sha256, "files": files}})


def _key(root: Path) -> str:
    return str(root.resolve())


def _relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _digest(path: Path) -> str | None:
    """Dosyanın SHA-256 karması; dosya yoksa None (yokluk da kaydedilen bir durumdur)."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ConfigError(f"Güven denetimi için dosya okunamadı ({path}): {exc}") from exc


def _load() -> dict[str, dict[str, Any]]:
    path = trust_store_file()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        # Bozuk kayıt hiçbir projeye güven VERMEZ; kullanıcı yeniden güvenebilir.
        return {}
    projects = raw.get("projects") if isinstance(raw, dict) else None
    return projects if isinstance(projects, dict) else {}


def _save(projects: dict[str, dict[str, Any]]) -> None:
    path = trust_store_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        {"version": _SCHEMA_VERSION, "projects": projects}, ensure_ascii=False, indent=2
    )
    handle, name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    temporary = Path(name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(payload)
        temporary.replace(path)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise ConfigError(f"Güven kaydı yazılamadı ({path}): {exc}") from exc
