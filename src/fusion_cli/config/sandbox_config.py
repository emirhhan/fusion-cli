"""`sandbox:` yapılandırma bölümü ve çalışma anı politikasına çevirisi (P-010).

Claude Code gibi (sandboxing, Filesystem defaults; #348, #349): sandbox makinenin tamamını
okuyabilir, yerleşik kimlik bilgisi listesi yoktur; yalnız `filesystem.denyRead` yolları
engellenir. `filesystem.allowRead` engellenmiş bir bölgenin içini yeniden açar; kurallar
çakışınca dar yol kazanır (`core.sandbox_policy.read_rules`). Fusion'ın kendi sır dosyaları
(`.env`, şifreli kasa, tarayıcı/web oturum profilleri) her zaman engellidir ve `allowRead`
ile açılamaz.

Eski davranış (1 Kasım öncesi): 14 yollu yerleşik okuma engeli (`~/.ssh`, `~/.aws`…) vardı ve
`allow_read` yalnız bu listedeki bir yolu birebir açabiliyordu.
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

#: Claude Code'da yerleşik okuma engeli listesi yoktur (sandboxing, "Reads: most of the
#: machine, including credential files such as ~/.ssh"; #348). Ad, eski içe aktarmalar için
#: boş demet olarak kalır; Fusion'ın kendi sır dosyaları `fusion_secret_paths` ile ayrıca ve
#: her zaman engellidir.
DEFAULT_DENY_READ: tuple[str, ...] = ()


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
    hide_secret_env: bool = False
    strict_allowlist: bool = False
    #: Claude `sandbox.credentials.envVars` (deny): sandbox ortamından çıkarılan adlar (#368).
    credential_env: tuple[str, ...] = ()
    #: Claude `sandbox.credentials.files` (deny): sandbox içinde okunamayan yollar.
    credential_files: tuple[str, ...] = ()


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
    return replace(
        config, allowed_domains=domains["allowed_domains"], denied_domains=domains["denied_domains"]
    )


def effective_deny_read(config: SandboxConfig) -> tuple[str, ...]:
    """Kullanıcının `denyRead` listesi (Fusion sırları hariç; yinelenenler birleşir)."""
    return tuple(dict.fromkeys(config.deny_read))


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
                (
                    *(_expand(raw, home, root) for raw in effective_deny_read(config)),
                    *(_expand(raw, home, root) for raw in config.credential_files),
                    *extra_deny,
                )
            )
        ),
        allow_read=tuple(_expand(raw, home, root) for raw in config.allow_read),
        locked_read=tuple(dict.fromkeys(extra_deny)),
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
        deny_env=tuple(dict.fromkeys(config.credential_env)),
    )
