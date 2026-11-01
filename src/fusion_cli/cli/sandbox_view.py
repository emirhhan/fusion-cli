"""Sandbox durumunun düz metin görünümü ve eylem ayrıştırıcısı (P-010).

`/sandbox` (REPL) ve `fusion sandbox durum` aynı metni basar; argüman ayrıştırması da
ortaktır: REPL `/sandbox izin github.com`, CLI `fusion sandbox izin github.com`.
"""

from __future__ import annotations

from ..config.sandbox_admin import SandboxChange, SandboxStatus
from ..core.errors import ConfigError
from ..ui import messages

__all__ = ["format_change", "format_status", "parse_action"]

#: Kullanıcının yazdığı eylem adı → kanonik eylem (`config.sandbox_admin.SANDBOX_ACTIONS`).
_ALIASES = {
    "on": "ac",
    "ac": "ac",
    "aç": "ac",
    "enable": "ac",
    "off": "kapat",
    "kapat": "kapat",
    "disable": "kapat",
    "ag": "ag",
    "ağ": "ag",
    "network": "ag",
    "izin": "izin",
    "allow": "izin",
    "engelle": "engelle",
    "deny": "engelle",
    "kaldir": "kaldir",
    "kaldır": "kaldir",
    "remove": "kaldir",
    "oto": "oto",
    "auto": "oto",
    "zorunlu": "zorunlu",
    "strict": "zorunlu",
    "disari": "disari",
    "dışarı": "disari",
    "sir": "sir",
    "sır": "sir",
    "secrets": "sir",
    "localhost": "localhost",
}
_NEEDS_VALUE = frozenset(
    {"ag", "izin", "engelle", "kaldir", "oto", "zorunlu", "disari", "sir", "localhost"}
)


def parse_action(argument: str) -> tuple[str, str] | None:
    """`izin github.com` → ("izin", "github.com"); boş argüman → None (durum)."""
    words = argument.split()
    if not words:
        return None
    action = _ALIASES.get(words[0].casefold())
    value = " ".join(words[1:])
    if action is None or (action in _NEEDS_VALUE and not value):
        raise ConfigError(messages.SANDBOX_USAGE)
    return action, value


def _on_off(value: bool) -> str:
    return "açık" if value else "kapalı"


def format_status(status: SandboxStatus) -> str:
    availability = (
        messages.SANDBOX_AVAILABLE
        if status.available
        else messages.SANDBOX_UNAVAILABLE.format(reason=status.reason)
    )
    extra = f", {', '.join(status.allow_write)}" if status.allow_write else ""
    lines = [
        messages.SANDBOX_TITLE.format(
            state=messages.SANDBOX_STATE_ON if status.enabled else messages.SANDBOX_STATE_OFF
        ),
        messages.SANDBOX_PLATFORM.format(platform=status.platform, availability=availability),
        messages.SANDBOX_WRITE.format(extra=extra),
        messages.SANDBOX_READ.format(paths=", ".join(status.deny_read) or "—"),
    ]
    if status.allow_read:
        lines.append(messages.SANDBOX_READ_OPENED.format(paths=", ".join(status.allow_read)))
    if status.network == "allowlist":
        denied = f"; yasak: {', '.join(status.denied_domains)}" if status.denied_domains else ""
        lines.append(
            messages.SANDBOX_NETWORK_ALLOWLIST.format(
                allowed=", ".join(status.allowed_domains) or messages.SANDBOX_NETWORK_NONE,
                denied=denied,
                localhost=_on_off(status.allow_localhost),
            )
        )
    else:
        lines.append(messages.SANDBOX_NETWORK_OPEN)
    if status.debug_ports:
        lines.append(messages.SANDBOX_DEBUG_PORTS.format(guard=status.debug_ports))
    lines.append(
        messages.SANDBOX_FLAGS.format(
            outside="onaylı" if status.allow_unsandboxed else "reddedilir",
            auto=_on_off(status.auto_allow),
            fail="çalıştırma" if status.fail_if_unavailable else "uyar ve sandbox'sız çalıştır",
            secrets="gizli" if status.hide_secret_env else "açık",
        )
    )
    if status.excluded_commands:
        lines.append(messages.SANDBOX_EXCLUDED.format(commands=", ".join(status.excluded_commands)))
    lines.extend(f"  · {item}" for item in getattr(status, "extras", ()))
    lines.append(messages.SANDBOX_HINT)
    return "\n".join(lines)


def format_change(change: SandboxChange) -> str:
    text = messages.SANDBOX_CHANGED.format(
        setting=change.setting, value=change.value, path=change.path
    )
    return "\n".join((text, *change.notes))
