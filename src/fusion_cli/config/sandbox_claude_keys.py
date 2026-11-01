"""Claude Code `sandbox.*` ayar adlarını Fusion'ın iç modeline çevir (#321, #322).

Claude Code sandbox ayarları iç içe ve camelCase'tir (settings-reference):

    sandbox:
      enabled: true
      autoAllowBashIfSandboxed: true
      excludedCommands: ["docker *"]
      allowUnsandboxedCommands: false
      failIfUnavailable: true
      filesystem: {allowWrite: [...], denyRead: [...], allowRead: [...]}
      network: {allowedDomains: [...], deniedDomains: [...]}

Bu adlar BİRİNCİLDİR. Fusion'ın eski düz snake_case adları (`allow_write`, `network: open`,
`auto_allow`…) ve `runtime.shell_sandbox` bir sürüm boyunca kullanımdan kalkmış takma ad
olarak okunur ve süreç başına bir kez uyarılır; kullanıcının mevcut dosyası bozulmaz.

`sandbox.enabled` açma anahtarıdır: `true` → `runtime.shell_sandbox: write_root`,
`false` → `off`. İkisi birden yazılmışsa Claude adı kazanır. Claude'un `network` nesnesi
yazıldığında ağ, Claude'daki gibi proxy'den geçer (`allowlist`; boş liste = dış ağ kapalı).
"""

from __future__ import annotations

import logging

from ..core.errors import ConfigError

__all__ = ["migrate_to_claude_names", "normalize_claude_sandbox", "warn_legacy_switch"]

_LOGGER = logging.getLogger(__name__)

#: Kök düzeyindeki Claude adı → Fusion iç alanı.
_TOP_LEVEL = {
    "autoAllowBashIfSandboxed": "auto_allow",
    "excludedCommands": "excluded_commands",
    "allowUnsandboxedCommands": "allow_unsandboxed",
    "failIfUnavailable": "fail_if_unavailable",
}
#: `sandbox.filesystem.*` → Fusion iç alanı.
_FILESYSTEM = {"allowWrite": "allow_write", "denyRead": "deny_read", "allowRead": "allow_read"}
#: `sandbox.network.*` → Fusion iç alanı.
_NETWORK = {
    "allowedDomains": "allowed_domains",
    "deniedDomains": "denied_domains",
    "strictAllowlist": "strict_allowlist",
}
#: Fusion'ın eski adları → Claude'daki karşılığı (uyarı metni için).
_LEGACY_NAMES = {
    "allow_write": "sandbox.filesystem.allowWrite",
    "deny_read": "sandbox.filesystem.denyRead",
    "allow_read": "sandbox.filesystem.allowRead",
    "allowed_domains": "sandbox.network.allowedDomains",
    "denied_domains": "sandbox.network.deniedDomains",
    "auto_allow": "sandbox.autoAllowBashIfSandboxed",
    "excluded_commands": "sandbox.excludedCommands",
    "allow_unsandboxed": "sandbox.allowUnsandboxedCommands",
    "fail_if_unavailable": "sandbox.failIfUnavailable",
}
#: Claude'da olmayan Fusion uzantısı: `sandbox.network.mode` (`open` | `allowlist`).
NETWORK_MODE_KEY = "mode"
_WARNED: set[str] = set()


def _warn_once(old: str, new: str) -> None:
    if old in _WARNED:
        return
    _WARNED.add(old)
    _LOGGER.warning("%s kullanımdan kalkıyor; Claude Code adı %s kullanılmalı.", old, new)


def warn_legacy_switch() -> None:
    """`runtime.shell_sandbox` eski açma anahtarıdır; bir kez uyar (#321)."""
    _warn_once("runtime.shell_sandbox", "sandbox.enabled")


def _section(raw: object, where: str) -> dict[str, object]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ConfigError(f"{where} bir eşleme olmalı.")
    return dict(raw)


def _move(source: dict[str, object], names: dict[str, str], target: dict[str, object]) -> None:
    """Claude adlarını iç adlara taşı; Claude adı eski adın üzerine yazar (birincil)."""
    for claude_name, internal in names.items():
        if claude_name in source:
            target[internal] = source.pop(claude_name)


def _network(raw: object, result: dict[str, object]) -> list[str]:
    """`network` eski kip metni (`open`/`allowlist`) ya da Claude nesnesi olabilir.

    Desteklenmeyen Claude ağ anahtarlarının adlarını döndürür.
    """
    if raw is None:
        return []
    if isinstance(raw, str):
        _warn_once("sandbox.network: <kip>", "sandbox.network.allowedDomains")
        result["network"] = raw
        return []
    network = _section(raw, "sandbox.network")
    _move(network, _NETWORK, result)
    # Claude: sandbox içindeki komutun doğrudan çıkışı yok, trafik proxy'den geçer. Fusion'ın
    # eski kısıtsız ağı (`open`) geçiş süresince `network.mode` uzantısıyla korunur.
    result["network"] = network.pop(NETWORK_MODE_KEY, "allowlist")
    if result["network"] == "open":
        _warn_once("sandbox.network.mode: open", "sandbox.network.allowedDomains (proxy)")
    return [f"network.{key}" for key in network]


def _credential_entries(raw: object, where: str, key: str) -> list[str]:
    """`[{<key>: ..., mode: deny|mask}]`; `mask` Fusion'da `deny`'a düşer (bir kez uyarılır)."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ConfigError(f"{where} bir liste olmalı.")
    values: list[str] = []
    for entry in raw:
        if not isinstance(entry, dict) or not isinstance(entry.get(key), str):
            raise ConfigError(f"{where}: her girdi {{{key}: ..., mode: deny|mask}} olmalı.")
        mode = entry.get("mode", "deny")
        if mode not in ("deny", "mask"):
            raise ConfigError(f"{where}: mode deny ya da mask olmalı: {mode!r}")
        if mode == "mask":
            _warn_once(f"{where} mode: mask", f"{where} mode: deny (Fusion maskelemez)")
        values.append(str(entry[key]))
    return values


def _credentials(raw: object, result: dict[str, object]) -> list[str]:
    """Claude `sandbox.credentials` (#368): `envVars` ortamdan çıkar, `files` okunamaz."""
    if raw is None:
        return []
    section = _section(raw, "sandbox.credentials")
    result["credential_env"] = _credential_entries(
        section.pop("envVars", None), "sandbox.credentials.envVars", "name"
    )
    result["credential_files"] = _credential_entries(
        section.pop("files", None), "sandbox.credentials.files", "path"
    )
    return [f"credentials.{key}" for key in section]


def normalize_claude_sandbox(section: object) -> tuple[dict[str, object], bool | None]:
    """Kullanıcının `sandbox:` bölümünü iç adlara çevir; `enabled` değerini ayrı döndür.

    Dönen sözlük `SandboxConfig` alanlarını taşır. Desteklenmeyen Claude anahtarları
    (`filesystem.denyWrite`, `network.allowUnixSockets`…) sessizce yok sayılmaz: bir kez
    uyarılır ve dışarıda bırakılır.
    """
    data = _section(section, "sandbox")
    enabled = data.pop("enabled", None)
    if enabled is not None and not isinstance(enabled, bool):
        raise ConfigError("sandbox.enabled true ya da false olmalı.")
    result: dict[str, object] = {}
    for old, new in _LEGACY_NAMES.items():
        if old in data:
            _warn_once(f"sandbox.{old}", new)
            result[old] = data.pop(old)
    filesystem = _section(data.pop("filesystem", None), "sandbox.filesystem")
    _move(filesystem, _FILESYSTEM, result)
    unsupported = [f"filesystem.{key}" for key in filesystem]
    unsupported += _network(data.pop("network", None), result)
    unsupported += _credentials(data.pop("credentials", None), result)
    _move(data, _TOP_LEVEL, result)
    for key in unsupported:
        _warn_once(f"sandbox.{key}", "(henüz desteklenmiyor; yok sayıldı)")
    result.update(data)  # kalan (bilinmeyen ya da iç) anahtarlar doğrulamaya bırakılır
    return result, enabled


def _claude_path(internal: str) -> tuple[str, ...]:
    """İç alan adının Claude yolu (`allow_write` → `filesystem.allowWrite`)."""
    for names, parent in ((_FILESYSTEM, "filesystem"), (_NETWORK, "network")):
        for claude_name, name in names.items():
            if name == internal:
                return (parent, claude_name)
    for claude_name, name in _TOP_LEVEL.items():
        if name == internal:
            return (claude_name,)
    return (internal,)


def migrate_to_claude_names(data: dict[str, object]) -> dict[str, object]:
    """Kullanıcı dosyasındaki eski sandbox adlarını Claude adlarına taşı (yeni sözlük döner).

    `/sandbox` ve `fusion sandbox` yazdıktan sonra çağrılır: dosyada aynı ayarın hem eski
    hem Claude adı kalmasın, Claude adı birincil olduğundan yazılan değer kaybolmasın.
    `runtime.shell_sandbox` → `sandbox.enabled`; `network: open` → `network.mode: open`.
    """
    result = dict(data)
    raw_section = result.get("sandbox")
    section = dict(raw_section) if isinstance(raw_section, dict) else {}
    runtime = result.get("runtime")
    if isinstance(runtime, dict) and "shell_sandbox" in runtime:
        runtime = dict(runtime)
        section["enabled"] = runtime.pop("shell_sandbox") == "write_root"
        result["runtime"] = runtime
    if isinstance(section.get("network"), str):
        section["network"] = {NETWORK_MODE_KEY: section["network"]}
    for internal in list(_LEGACY_NAMES):
        if internal not in section:
            continue
        value = section.pop(internal)
        path = _claude_path(internal)
        if len(path) == 1:
            section[path[0]] = value
            continue
        parent = section.get(path[0])
        nested = dict(parent) if isinstance(parent, dict) else {}
        nested[path[1]] = value
        section[path[0]] = nested
    if section:
        result["sandbox"] = section
    return result
