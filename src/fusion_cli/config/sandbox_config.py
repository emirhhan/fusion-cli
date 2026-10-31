"""`sandbox:` yapılandırma bölümü ve çalışma anı politikasına çevirisi (P-010).

Kip anahtarı geri uyumlu olarak `runtime.shell_sandbox` (`off` | `write_root`) kalır;
bu bölüm kip açıkken NEYİN sınırlanacağını söyler. Eski yapılandırmada bölüm yoksa
varsayılanlar geçerlidir ve `write_root` eskisi gibi yalnız yazmayı sınırlar — artı
varsayılan okuma engeli listesi (`~/.ssh`, `~/.aws`…). Fusion'ın kendi sır dosyaları
(`.env`, şifreli kasa, tarayıcı/web oturum profilleri) listede yazılı olmasa da her
zaman okuma engeline eklenir.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from ..core.errors import ConfigError
from ..core.sandbox_policy import NETWORK_MODES, SandboxPolicy, normalize_domain
from .paths import browser_profiles_dir, user_config_dir, user_data_dir

__all__ = ["SandboxConfig", "fusion_secret_paths", "sandbox_policy", "validate_sandbox"]


@dataclass(frozen=True, slots=True)
class SandboxConfig:
    """`sandbox:` bölümü; alan açıklamaları `defaults.yaml`'da (tek kaynak)."""

    allow_write: tuple[str, ...] = ()
    deny_read: tuple[str, ...] = (
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
    )
    network: str = "open"
    allowed_domains: tuple[str, ...] = ()
    denied_domains: tuple[str, ...] = ()
    allow_localhost: bool = True
    fail_if_unavailable: bool = False
    allow_unsandboxed: bool = True
    excluded_commands: tuple[str, ...] = ()
    auto_allow: bool = False
    hide_secret_env: bool = True


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


def fusion_secret_paths() -> tuple[Path, ...]:
    """Sandbox içindeki komutun hiçbir zaman okumaması gereken Fusion dosyaları."""
    data = user_data_dir()
    return (
        user_config_dir() / ".env",
        data / "vault",
        data / "secrets.enc",
        data / "web_profiles",
        browser_profiles_dir(),
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
            dict.fromkeys((*(_expand(raw, home, root) for raw in config.deny_read), *extra_deny))
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
    )
