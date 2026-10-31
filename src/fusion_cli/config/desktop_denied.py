"""Uygulamayı `desktop.denied_apps`'e ekle: onay kartı ve terminal "Her zaman reddet" (P-007).

Masaüstü (`bilgisayar.uygulama_reddet`, kart), TUI ve düz terminal aynı yazımı kullanır;
doğrulama `settings_access.write_setting` ile `fusion config set desktop.denied_apps` aynıdır.
"""

from __future__ import annotations

from ..core.errors import ConfigError
from .models import Config
from .settings_access import write_setting

DENIED_ADDED = "{app} reddedilen uygulamalara eklendi (Ayarlar › Bu bilgisayar)."
DENIED_EXISTS = "{app} zaten reddedilenlerde."
DENIED_INVALID = "Uygulama adı boş ya da virgüllü olamaz."


def with_denied_app(config: Config, app: str) -> tuple[Config, str]:
    """Güncel yapılandırma ve kullanıcı metni; ad geçersiz ya da yazılamazsa `ConfigError`."""
    name = app.strip()
    if not name or "," in name:
        raise ConfigError(DENIED_INVALID)
    current = config.desktop.denied_apps
    if any(item.strip().casefold() == name.casefold() for item in current):
        return config, DENIED_EXISTS.format(app=name)
    try:
        updated, _path = write_setting(config, "desktop.denied_apps", ",".join([*current, name]))
    except OSError as error:
        raise ConfigError(f"Ret listesi yazılamadı: {error}") from error
    return updated, DENIED_ADDED.format(app=name)
