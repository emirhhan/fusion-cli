"""`sandbox:` yapılandırma bölümü ve çalışma anı politikasına çevirisi (P-010).

Kip anahtarı geri uyumlu olarak `runtime.shell_sandbox` (`off` | `write_root`) kalır;
bu bölüm kip açıkken NEYİN sınırlanacağını söyler. Eski yapılandırmada bölüm yoksa
varsayılanlar geçerlidir ve `write_root` eskisi gibi yalnız yazmayı sınırlar — artı
varsayılan okuma engeli listesi (`DEFAULT_DENY_READ`: `~/.ssh`, `~/.aws`…). Fusion'ın
kendi sır dosyaları (`.env`, şifreli kasa, tarayıcı/web oturum profilleri) listede yazılı
olmasa da her zaman okuma engeline eklenir.

Okuma engeli = `DEFAULT_DENY_READ` + `sandbox.deny_read` − `sandbox.allow_read` + Fusion
sırları. Ölçüldü (1 Kasım): `deny_read` yazan kullanıcının listesi varsayılanın YERİNE
geçiyordu; tek yol ekleyen `~/.ssh` korumasını sessizce kaybediyordu. Artık kullanıcı
listesi eklenir; varsayılandan bir yolu açmak için açıkça `allow_read` yazılır.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from ..core.errors import ConfigError
from ..core.sandbox_policy import NETWORK_MODES, SandboxPolicy, normalize_domain
from .paths import (
    base_config_dir,
    browser_profiles_dir,
    env_file_candidates,
    user_data_dir,
)

__all__ = [
    "DEFAULT_DENY_READ",
    "SandboxConfig",
    "effective_deny_read",
    "fusion_secret_paths",
    "sandbox_policy",
    "validate_sandbox",
]

#: Her zaman uygulanan okuma engeli (kullanıcının `deny_read`'i buna EKLENİR).
DEFAULT_DENY_READ: tuple[str, ...] = (
    "~/.ssh",
    "~/.aws",
    "~/.gnupg",
    "~/.azure",
    "~/.kube",
    "~/.config/gcloud",
    "~/.docker/config.json",
    "~/.netrc",
    "~/.git-credentials",
    "~/.password-store",
    "~/Library/Keychains",
    "~/.config/gh",
    "~/.config/git/credentials",
    "~/.pypirc",
)


@dataclass(frozen=True, slots=True)
class SandboxConfig:
    """`sandbox:` bölümü; alan açıklamaları `defaults.yaml`'da (tek kaynak)."""

    allow_write: tuple[str, ...] = ()
    deny_read: tuple[str, ...] = ()
    allow_read: tuple[str, ...] = ()
    network: str = "allowlist"
    allowed_domains: tuple[str, ...] = ()
    denied_domains: tuple[str, ...] = ()
    allow_localhost: bool = True
    fail_if_unavailable: bool = False
    allow_unsandboxed: bool = True
    excluded_commands: tuple[str, ...] = ()
    auto_allow: bool = True
    hide_secret_env: bool = True
    strict_allowlist: bool = False


def validate_sandbox(config: SandboxConfig) -> SandboxConfig:
    """Ağ kipini ve alan adlarını doğrula; alan adlarını kanonik biçime getirir."""
    if config.network not in NETWORK_MODES:
        raise ConfigError(
            f"sandbox.network: {config.network!r} geçersiz; geçerli: {', '.join(NETWORK_MODES)}."
        )
    domains: dict[str, tuple[str, ...]] = {}
    for name in ("allowed_domains", "denied_domains"):
        cleaned: list[str] = []
        for raw in getattr(config, name):
            value = normalize_domain(raw)
            if value is None:
                raise ConfigError(
                    f"sandbox.{name}: {raw!r} geçerli bir alan adı değil "
                    "(ör. github.com, *.npmjs.org, 127.0.0.1)."
                )
            cleaned.append(value)
        domains[name] = tuple(dict.fromkeys(cleaned))
    for command in config.excluded_commands:
        if not command.strip():
            raise ConfigError("sandbox.excluded_commands: boş önek olamaz.")
    _validate_allow_read(config)
    return replace(
        config, allowed_domains=domains["allowed_domains"], denied_domains=domains["denied_domains"]
    )


def _read_key(raw: str) -> str:
    """Yol girdisinin karşılaştırma biçimi: `$HOME` → `~`, sondaki `/` atılır."""
    text = raw.strip()
    if text.startswith("$HOME"):
        text = "~" + text.removeprefix("$HOME")
    return text.rstrip("/") or text


def _validate_allow_read(config: SandboxConfig) -> None:
    """`allow_read` yalnız okuma engelindeki bir yolu açabilir (yazım hatası sessiz kalmasın).

    Fusion'ın kendi sır dosyaları (`fusion_secret_paths`) bu listeyle açılamaz.
    """
    known = {_read_key(raw) for raw in (*DEFAULT_DENY_READ, *config.deny_read)}
    for raw in config.allow_read:
        if _read_key(raw) not in known:
            raise ConfigError(
                f"sandbox.allow_read: {raw!r} okuma engelinde değil; yalnız varsayılan listeden "
                f"ya da sandbox.deny_read'den bir yol açılabilir (varsayılan: "
                f"{', '.join(DEFAULT_DENY_READ)})."
            )


def effective_deny_read(config: SandboxConfig) -> tuple[str, ...]:
    """Varsayılan + kullanıcı listesi − `allow_read` (ham yazımla; Fusion sırları hariç)."""
    opened = {_read_key(raw) for raw in config.allow_read}
    merged = {_read_key(raw): raw for raw in (*DEFAULT_DENY_READ, *config.deny_read)}
    return tuple(raw for key, raw in merged.items() if key not in opened)


def fusion_secret_paths() -> tuple[Path, ...]:
    """Sandbox içindeki komutun hiçbir zaman okumaması gereken Fusion dosyaları.

    Yüklenen her `.env` adayı (`FUSION_HOME/.env`, hesap ve hesapsız kök) dahildir; proje
    kökündeki `.env` projenin kendisidir, dışarıda kalır. Ölçüldü (31 Ekim):
    `FUSION_HOME/.env` ve hesap etkinken temel dizinin `.env`'i listede yoktu.
    """
    data = user_data_dir()
    project_env = Path.cwd() / ".env"
    env_files = (
        *(path for path in env_file_candidates() if path != project_env),
        base_config_dir() / ".env",
    )
    return tuple(
        dict.fromkeys(
            (
                *env_files,
                data / "vault",
                data / "secrets.enc",
                data / "web_profiles",
                browser_profiles_dir(),
            )
        )
    )


def _expand(raw: str, home: Path, root: Path) -> Path:
    path = Path(raw.replace("$HOME", str(home), 1)) if raw.startswith("$HOME") else Path(raw)
    if raw.startswith("~"):
        path = home / raw[1:].lstrip("/")
    return path if path.is_absolute() else root / path


def sandbox_policy(
    config: SandboxConfig,
    *,
    home: Path,
    root: Path,
    extra_deny: tuple[Path, ...] = (),
) -> SandboxPolicy:
    """Yapılandırmayı çalışma anı politikasına çevir (`~`/göreli yollar çözülür)."""
    return SandboxPolicy(
        extra_write=tuple(_expand(raw, home, root) for raw in config.allow_write),
        deny_read=tuple(
            dict.fromkeys(
                (*(_expand(raw, home, root) for raw in effective_deny_read(config)), *extra_deny)
            )
        ),
        network=config.network,
        allowed_domains=config.allowed_domains,
        denied_domains=config.denied_domains,
        allow_localhost=config.allow_localhost,
        fail_if_unavailable=config.fail_if_unavailable,
        allow_unsandboxed=config.allow_unsandboxed,
        excluded_commands=tuple(item.strip() for item in config.excluded_commands),
        auto_allow=config.auto_allow,
        hide_secret_env=config.hide_secret_env,
        strict_allowlist=config.strict_allowlist,
    )
