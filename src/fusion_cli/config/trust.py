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

import yaml

from ..core.errors import ConfigError
from .paths import user_config_dir

#: Proje kökünde yürütme ayarı taşıyabilen yapılandırma dosyası.
PROJECT_CONFIG_NAME = "config.yaml"
#: Fusion'ın ürettiği araçların proje altındaki dizini (`tools/forge.py` ile aynı).
FORGED_TOOLS_DIR = Path(".fusion") / "tools"
#: Claude Code'un proje-yerel izin dosyası; `Bash(...)` girdileri onaysız komut sayılır (L2-02).
PROJECT_PERMISSIONS_PATH = Path(".claude") / "settings.local.json"
#: Claude Code'un paylaşılan proje ayarı (P-001): izin kuralları yalnız güvenilince okunur.
PROJECT_SETTINGS_PATH = Path(".claude") / "settings.json"
#: Güven kaydındaki karma alanları (dosya → anahtar).
_DIGEST_KEYS: dict[Path, str] = {
    PROJECT_PERMISSIONS_PATH: "settings_sha256",
    PROJECT_SETTINGS_PATH: "project_settings_sha256",
}
_STORE_NAME = "trusted-projects.json"
#: Proje config'ine hiç güven verilmediğini söyleyen karma yer tutucusu (hiçbir dosyayla eşleşmez).
_NEVER_TRUSTED = ""
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
    # Boş metin karması "projeye hiç güvenilmedi" demektir (`record_permissions_digest`
    # yalnız izin dosyasını kaydeder); `None` ise "güvenildiğinde config.yaml yoktu".
    if record is None or record.get("config_sha256") == _NEVER_TRUSTED:
        return TrustState(False, REASON_UNKNOWN)
    if record.get("config_sha256") != _digest(root / PROJECT_CONFIG_NAME):
        return TrustState(False, REASON_CHANGED)
    return TrustState(True, REASON_TRUSTED)


def is_permissions_trusted(root: Path) -> bool:
    """`.claude/settings.local.json` güvenildiği andaki içerikle mi duruyor?

    Dosya yoksa güvenilecek bir şey yoktur (True). Dosya varsa kayıtta onun karması
    bulunmalı ve eşleşmelidir; `fusion trust` öncesinde yazılmış kayıtlarda alan
    olmadığından dosya yeniden güvenilene kadar yok sayılır.
    """
    return _is_digest_trusted(root, PROJECT_PERMISSIONS_PATH)


def is_project_settings_trusted(root: Path) -> bool:
    """`.claude/settings.json` güvenildiği andaki içerikle mi duruyor? (P-001)

    Eski kayıtlarda alan yoktur: dosya yeniden `fusion trust` ile güvenilene dek yok sayılır.
    """
    return _is_digest_trusted(root, PROJECT_SETTINGS_PATH)


def _is_digest_trusted(root: Path, relative: Path) -> bool:
    try:
        current = _digest(root / relative)
    except ConfigError:
        return False
    if current is None:
        return True
    record = _load().get(_key(root))
    return record is not None and record.get(_DIGEST_KEYS[relative]) == current


def record_permissions_digest(root: Path) -> None:
    """Fusion'ın BİZZAT yazdığı `.claude/settings.local.json`'ın karmasını tazele (P-003).

    Yalnız izin dosyası alanı değişir; config ve araç karmaları olduğu gibi kalır. Kayıt
    yoksa yalnız bu alanla açılır: config güveni bundan ÇIKARILMAZ (bkz. `approve_file`).
    """
    record = _load().get(_key(root))
    _update(
        root,
        config_sha256=record.get("config_sha256") if record is not None else _NEVER_TRUSTED,
        files=dict(record.get("files", {})) if record is not None else {},
        settings_sha256=_digest(root / PROJECT_PERMISSIONS_PATH),
        project_settings_sha256=record.get("project_settings_sha256") if record else None,
    )


def untrust_project(root: Path) -> bool:
    """Projenin güven kaydını sil; kayıt yoksa `False` (P-012)."""
    store = _load()
    if store.pop(_key(root), None) is None:
        return False
    _save(store)
    return True


@dataclass(frozen=True, slots=True)
class TrustReport:
    """Masaüstü güven kartı için durum + güvenilmeyince DÜŞÜRÜLEN bölümler (P-012)."""

    state: TrustState
    #: Proje config'inden düşürülen bölümler (`mcp_servers`, `runtime.verification_commands`…).
    dropped_sections: tuple[str, ...]
    #: Güvenilmediği için yok sayılan izin dosyaları (köke göreli).
    ignored_files: tuple[str, ...]
    #: Yüklenmeyen üretilmiş araç sayısı (`.fusion/tools/*.py`).
    forged_tools: int


def trust_report(root: Path) -> TrustReport:
    """Projenin güven durumu ve güvenilmezse nelerin devre dışı kaldığı."""
    state = resolve_project_trust(root)
    dropped: tuple[str, ...] = ()
    config_path = root / PROJECT_CONFIG_NAME
    if config_path.is_file():
        try:
            data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, yaml.YAMLError):
            data = None
        if isinstance(data, Mapping):
            _, dropped = without_execution_settings(data)
    ignored = tuple(
        relative.as_posix()
        for relative in (PROJECT_SETTINGS_PATH, PROJECT_PERMISSIONS_PATH)
        if (root / relative).is_file() and not _is_digest_trusted(root, relative)
    )
    tools = sum(
        1
        for path in (root / FORGED_TOOLS_DIR).glob("*.py")
        if path.is_file() and not path.is_symlink()
    )
    if state.trusted:
        dropped = ()
        tools = 0
    return TrustReport(state, dropped, ignored, tools)


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
    _update(
        root,
        config_sha256=_digest(root / PROJECT_CONFIG_NAME),
        files=files,
        settings_sha256=_digest(root / PROJECT_PERMISSIONS_PATH),
        project_settings_sha256=_digest(root / PROJECT_SETTINGS_PATH),
    )


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
    _update(
        root,
        config_sha256=record.get("config_sha256"),
        files=files,
        settings_sha256=record.get("settings_sha256"),
        project_settings_sha256=record.get("project_settings_sha256"),
    )


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


def _update(
    root: Path,
    *,
    config_sha256: str | None,
    files: dict[str, str],
    settings_sha256: str | None = None,
    project_settings_sha256: str | None = None,
) -> None:
    store = _load()
    record = {
        "config_sha256": config_sha256,
        "files": files,
        "settings_sha256": settings_sha256,
        "project_settings_sha256": project_settings_sha256,
    }
    _save({**store, _key(root): record})


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
