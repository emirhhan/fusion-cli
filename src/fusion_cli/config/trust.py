"""Proje güveni: çalışma dizinindeki dosyalar ne zaman yürütme ayarı açabilir?

İndirilmiş bir depo kendi `config.yaml`'ıyla MCP süreci, doğrulama komutu veya bir
sırrı uzak adrese taşıyan `token_env` tanımlayabilir; `.fusion/tools` altındaki
Python da araç olarak çalıştırılır; `.fusion/launch.json` ve `.claude/launch.json`
içindeki `runtimeExecutable` önizleme sunucusu diye çalıştırılır (ölçüldü 31 Ekim:
bu dosyalar güven kaydına hiç bağlı değildi). Bu dosyalar ancak kullanıcı projeye güvendikten
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
from .local_settings_location import local_settings_path
from .paths import user_config_dir

#: Proje kökünde yürütme ayarı taşıyabilen yapılandırma dosyası.
PROJECT_CONFIG_NAME = "config.yaml"
#: Fusion'ın ürettiği araçların proje altındaki dizini (`tools/forge.py` ile aynı).
FORGED_TOOLS_DIR = Path(".fusion") / "tools"
#: Claude Code'un proje-yerel izin dosyası; `Bash(...)` girdileri onaysız komut sayılır (L2-02).
PROJECT_PERMISSIONS_PATH = Path(".claude") / "settings.local.json"
#: Proje kapsamlı MCP kaydı (Claude Code ile ortak); stdio süreci başlatabilir (P-049).
PROJECT_MCP_PATH = Path(".mcp.json")
#: Önizleme sunucusu komutu taşıyan dosyalar (`tools/preview_launch` okur; Fusion'ınki önce).
#: Komutlu yapılandırma yalnız dosya karması güven kaydındaysa çalışır; `url` ile bağlanma serbest.
PROJECT_LAUNCH_FILES: tuple[Path, ...] = (
    Path(".fusion") / "launch.json",
    Path(".claude") / "launch.json",
)
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
#: `sandbox` (P-010): güvenilmeyen proje sandbox'ı gevşetemesin (alan adı, sandbox dışı komut).
EXECUTION_SECTIONS = ("mcp_servers", "hosted_connectors", "sandbox")
#: Aynı gerekçeyle `runtime` altından düşürülen anahtarlar. `status_line_command` tur sonunda
#: kabukla çalışır (P-069); güvensiz projeden gelirse `fusion trust` olmadan kod yürütme olur.
#: `voice_listener` (P-072) `/voice` ile alt süreç olarak başlatılır; aynı gerekçe.
EXECUTION_RUNTIME_KEYS = (
    "verification_commands",
    "status_line_command",
    "voice_listener",
    "lsp_server",
    "symbol_query_enabled",
    # Kanca HTTP isteğinin iç ağa gitmesi (P-009): güvenilmeyen depo açamaz.
    "hook_http_allow_private",
)

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


def was_project_trusted(root: Path) -> bool:
    """Klasöre `fusion trust` ile en az bir kez güvenildi mi? (Claude çalışma alanı güveni, #246)

    İçerik karmasına bakılmaz: Claude'un klasör güveni gibi sonraki dosya değişikliğiyle düşmez.
    """
    record = _load().get(_key(root))
    return record is not None and record.get("config_sha256") != _NEVER_TRUSTED


def is_permissions_trusted(root: Path) -> bool:
    """`.claude/settings.local.json` allow kuralları uygulanabilir mi? (Claude, #67)

    Dosya yoksa ya da ev dizinindeyse güven gerekmez; öteki yerde klasör güveni yeter
    (içerik karması aranmaz, dosya değişince güven düşmez).
    """
    from .workspace_trust import is_config_home, is_folder_trusted

    if not (local_settings_path(root)).is_file() or is_config_home(root):
        return True
    # Fusion'ın kendi yazdığı ("bir daha sorma") dosya, karması tutuyorsa güven sorusu
    # olmadan da geçerlidir (güven iletişim kutusu henüz yok, #71).
    return is_folder_trusted(root) or _written_by_fusion(root)


def _written_by_fusion(root: Path) -> bool:
    try:
        current = _digest(local_settings_path(root))
    except ConfigError:
        return False
    record = _load().get(_key(root))
    return record is not None and record.get("settings_sha256") == current


def is_project_settings_trusted(root: Path) -> bool:
    """`.claude/settings.json` allow kuralları uygulanabilir mi? (Claude, #71)

    Dosya yoksa güvenilecek bir şey yoktur. Varsa klasöre (ya da git köküne) bir kez
    güvenilmiş olması yeter; içerik değişince güven düşmez.
    """
    from .workspace_trust import is_folder_trusted

    if not (root / PROJECT_SETTINGS_PATH).is_file():
        return True
    return is_folder_trusted(root)


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
        settings_sha256=_digest(local_settings_path(root)),
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
    checks = (
        (PROJECT_SETTINGS_PATH, is_project_settings_trusted),
        (PROJECT_PERMISSIONS_PATH, is_permissions_trusted),
    )
    ignored = tuple(relative.as_posix() for relative, trusted in checks if not trusted(root))
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
    """Projenin şu anki yapılandırmasına, üretilmiş araçlarına ve launch.json'una güven."""
    files: dict[str, str] = {}
    adaylar = [
        *sorted((root / FORGED_TOOLS_DIR).glob("*.py")),
        *(root / relative for relative in PROJECT_LAUNCH_FILES),
        *_project_agent_files(root),
    ]
    for path in adaylar:
        # Kök dışını gösteren bağ ya da `.py` adlı klasör güvene alınmaz.
        if path.is_symlink() or not path.is_file():
            continue
        digest = _digest(path)
        if digest is not None:
            files[_relative(root, path)] = digest
    # `.mcp.json` da yürütme açar; `fusion trust` onu da şu anki içeriğiyle güvene alır.
    mcp_path = root / PROJECT_MCP_PATH
    if mcp_path.is_file() and not mcp_path.is_symlink():
        mcp_digest = _digest(mcp_path)
        if mcp_digest is not None:
            files[_relative(root, mcp_path)] = mcp_digest
    _update(
        root,
        config_sha256=_digest(root / PROJECT_CONFIG_NAME),
        files=files,
        settings_sha256=_digest(local_settings_path(root)),
        project_settings_sha256=_digest(root / PROJECT_SETTINGS_PATH),
    )


#: Keşifte desteklenen proje ajanı biçimleri; güven yalnız bu belirli kökü kapsar.
_AGENT_TRUST_SUFFIXES = frozenset({".md", ".toml"})
_AGENT_TRUST_LIMIT = 512


def _project_agent_files(root: Path) -> tuple[Path, ...]:
    """Tanım kökünden çıkmayan, bağlantısız ajan dosyalarını sınırlı sayıda seç."""
    folder = root / ".claude" / "agents"
    if folder.is_symlink() or folder.parent.is_symlink() or not folder.is_dir():
        return ()
    found: list[Path] = []
    for path in folder.rglob("*"):
        if path.suffix not in _AGENT_TRUST_SUFFIXES or path.is_symlink() or not path.is_file():
            continue
        if any(
            parent.is_symlink()
            for parent in path.parents
            if parent != root and root in parent.parents
        ):
            continue
        try:
            path.resolve().relative_to(root.resolve())
        except ValueError:
            continue
        found.append(path)
        if len(found) > _AGENT_TRUST_LIMIT:
            raise ConfigError("Proje ajanı güven sınırı aşıldı; ajan tanımlarını sadeleştirin.")
    return tuple(sorted(found))


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
