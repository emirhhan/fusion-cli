"""Sandbox anahtarlarının hangi ayar kapsamından okunabildiği (Claude settings-reference › sandbox).

Katman türleri: `kullanici` (`~/.claude/settings.json`), `proje` (`.claude/settings*.json`),
`bayrak` (`--settings`), `managed`. Claude Code:

- `bwrapPath`, `socatPath` yalnız managed ayardan okunur (başka bir dosya sandbox'ı farklı bir
  ikiliye yönlendiremez).
- Proje dosyaları `tlsTerminate`, mask girdileri, `allowPlaintextInject`, `filesystem.disabled`,
  `allowNestedUserNamespaces`, `ripgrep` ayarlayamaz (`PROJECT_IGNORED`).
- Sandbox "admin-required" iken (managed ya da `--settings` `allowUnsandboxedCommands: false` —
  managed `true` demedikçe — veya managed `network.allowManagedDomainsOnly: true`) yalıtımı
  gevşeten ayarlar yalnız managed, `--settings` ve kullanıcı ayarından alınır; proje dosyasının
  `false` değeri yine uygulanır.
- `allowManagedDomainsOnly` açıkken proxy portları yalnız managed ayardan okunur.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence

__all__ = [
    "ADMIN_LOOSENING",
    "MANAGED_ONLY",
    "PROJECT_IGNORED",
    "admin_required",
    "scope_filter",
]

_LOG = logging.getLogger(__name__)

MANAGED = "managed"
FLAG = "bayrak"
PROJECT = "proje"

#: Yalnız managed ayardan okunan alanlar.
MANAGED_ONLY = frozenset({"bwrap_path", "socat_path"})
#: Proje ayar dosyalarından hiç okunmayan alanlar: depo CA veremez, mask kaydı açamaz.
PROJECT_IGNORED = frozenset(
    {
        "tls_terminate",
        "tls_ca_cert",
        "tls_ca_key",
        "credential_mask",
        "allow_plaintext_inject",
        "filesystem_disabled",
        "allow_nested_user_namespaces",
        "ripgrep_command",
        "ripgrep_args",
    }
)
#: Admin-required iken proje dosyasından alınmayan gevşetmeler (her değerde).
ADMIN_LOOSENING = frozenset(
    {
        "excluded_commands",
        "allowed_domains",
        "allow_write",
        "allow_unix_sockets",
        "http_proxy_port",
        "socks_proxy_port",
    }
)
#: Admin-required iken proje dosyasından yalnız `true` değeri alınmayan anahtarlar.
_ADMIN_LOOSENING_TRUE = frozenset({"allow_all_unix_sockets", "enable_weaker_nested_sandbox"})
_PROXY_PORTS = frozenset({"http_proxy_port", "socks_proxy_port"})
_WARNED: set[str] = set()


def _sandbox(data: Mapping[str, object]) -> Mapping[str, object]:
    section = data.get("sandbox")
    return section if isinstance(section, Mapping) else {}


def _domains_only(data: Mapping[str, object]) -> bool:
    network = _sandbox(data).get("network")
    return isinstance(network, Mapping) and network.get("allowManagedDomainsOnly") is True


def managed_domains_only(layers: Sequence[tuple[str, Mapping[str, object]]]) -> bool:
    """Managed katmanlardan biri `network.allowManagedDomainsOnly: true` diyor mu?"""
    return any(kind == MANAGED and _domains_only(data) for kind, data in layers)


def admin_required(layers: Sequence[tuple[str, Mapping[str, object]]]) -> bool:
    """Claude'un "admin-required" sandbox durumu (ham `(tür, içerik)` katmanlarından)."""
    managed_unsandboxed: bool | None = None
    flag_false = False
    for kind, data in layers:
        value = _sandbox(data).get("allowUnsandboxedCommands")
        if kind == MANAGED and isinstance(value, bool):
            managed_unsandboxed = value
        elif kind == FLAG and value is False:
            flag_false = True
    return (
        managed_domains_only(layers)
        or managed_unsandboxed is False
        or (flag_false and managed_unsandboxed is not True)
    )


def _dropped(kind: str, section: Mapping[str, object], *, admin: bool, domains: bool) -> set[str]:
    if kind == MANAGED:
        return set()
    dropped = set(MANAGED_ONLY)
    if domains:
        dropped |= _PROXY_PORTS
    if kind == PROJECT:
        dropped |= PROJECT_IGNORED
        if admin:
            dropped |= ADMIN_LOOSENING
            dropped |= {key for key in _ADMIN_LOOSENING_TRUE if section.get(key) is True}
    return dropped


def scope_filter(
    kind: str, section: Mapping[str, object], source: object, *, admin: bool, domains: bool
) -> dict[str, object]:
    """Katman türünün okuyamadığı alanları çıkar; dolu her alan için bir kez uyarır."""
    dropped = _dropped(kind, section, admin=admin, domains=domains)
    for key in sorted(dropped & {key for key, value in section.items() if value}):
        marker = f"{kind}:{key}"
        if marker not in _WARNED:
            _WARNED.add(marker)
            _LOG.warning(
                "sandbox.%s %s ayarında yok sayıldı (Claude kapsam kuralı: %s): %s",
                key,
                kind,
                _reason(key, kind),
                source,
            )
    return {key: value for key, value in section.items() if key not in dropped}


def _reason(key: str, kind: str) -> str:
    if key in MANAGED_ONLY:
        return "yalnız managed"
    if key in PROJECT_IGNORED:
        return "yalnız kullanıcı, managed ya da --settings"
    if kind == PROJECT:
        return "sandbox yönetici zorunlu (admin-required); depo gevşetemez"
    return "allowManagedDomainsOnly açık; yalnız managed"
