"""`/sandbox` — kabuk sandbox'ının durumu ve ayarları (P-010; Claude Code `/sandbox`).

    /sandbox                      panel (Kip · Geçersiz kılmalar · Yapılandırma · Bağımlılıklar);
                                  etkileşimsiz ortamda durum metni
    /sandbox on|off               runtime.shell_sandbox = write_root | off
    /sandbox ag open|allowlist    ağ kipi
    /sandbox izin github.com      izinli alan adı ekle (ağ kipi allowlist'e geçer)
    /sandbox engelle x.com        yasak alan adı · /sandbox kaldir x.com
    /sandbox oto|zorunlu|disari|sir|localhost on|off
        auto_allow · fail_if_unavailable · allow_unsandboxed · hide_secret_env · allow_localhost

Değişiklik oturuma uygulanır ve kullanıcı dosyasına yazılır (`/config` ile aynı yol).
"""

from __future__ import annotations

import sys

from ...config.sandbox_admin import apply_sandbox_action, sandbox_status
from ...core.errors import ConfigError
from ..sandbox_view import format_change, format_status, parse_action
from .state import ReplState


def sandbox_command(state: ReplState, argument: str) -> str:
    """Slash komut işleyicisi; Türkçe sonuç metni döndürür.

    Argümansız ve etkileşimli terminalde Claude gibi panel açılır (`sandbox_panel`, #352);
    etkileşimsiz ortamda durum metni basılır.
    """
    try:
        parsed = parse_action(argument)
        if parsed is None and sys.stdin.isatty():
            from ...ui.picker import pick
            from .sandbox_panel import sandbox_panel

            result = sandbox_panel(state.config, state.root, picker=pick)
            state.config = result.config
            return result.message
        if parsed is None:
            return format_status(sandbox_status(state.config, state.root))
        change = apply_sandbox_action(state.config, *parsed, root=state.root, local=True)
    except ConfigError as error:
        return str(error)
    state.config = change.config
    return format_change(change)
