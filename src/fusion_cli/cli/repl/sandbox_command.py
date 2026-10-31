"""`/sandbox` — kabuk sandbox'ının durumu ve ayarları (P-010; Claude Code `/sandbox`).

    /sandbox                      durum: platform, kurulabilirlik, yazma/okuma/ağ kuralları
    /sandbox on|off               runtime.shell_sandbox = write_root | off
    /sandbox ag open|allowlist    ağ kipi
    /sandbox izin github.com      izinli alan adı ekle (ağ kipi allowlist'e geçer)
    /sandbox engelle x.com        yasak alan adı · /sandbox kaldir x.com
    /sandbox oto|zorunlu|disari|sir|localhost on|off
        auto_allow · fail_if_unavailable · allow_unsandboxed · hide_secret_env · allow_localhost

Değişiklik oturuma uygulanır ve kullanıcı dosyasına yazılır (`/config` ile aynı yol).
"""

from __future__ import annotations

from ...config.sandbox_admin import apply_sandbox_action, sandbox_status
from ...core.errors import ConfigError
from ..sandbox_view import format_change, format_status, parse_action
from .state import ReplState


def sandbox_command(state: ReplState, argument: str) -> str:
    """Slash komut işleyicisi; Türkçe sonuç metni döndürür."""
    try:
        parsed = parse_action(argument)
        if parsed is None:
            return format_status(sandbox_status(state.config, state.root))
        change = apply_sandbox_action(state.config, *parsed, root=state.root)
    except ConfigError as error:
        return str(error)
    state.config = change.config
    return format_change(change)
