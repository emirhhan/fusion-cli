"""`bilgisayar.*` RPC'leri — Ayarlar › Bu bilgisayar ekranının arka ucu (P-006).

Claude Desktop "Settings › This computer" karşılığı: computer use anahtarı, kademe tavanı,
kategori tablosu, reddedilen uygulamalar, uygulama başına kademe ve tur davranışı. Değerler
`desktop:` bölümüne `settings_access.write_setting` ile yazılır (CLI'deki `fusion config set
desktop.<alan>` ile aynı doğrulama); yanıt güncel `Config`'i de döndürür ki oturum değişikliği
bir sonraki turda yeniden açılış gerektirmeden kullansın.

Hatalar `{"ok": False, "metin": …}` ile Türkçe döner; iz basılmaz.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping

from ..config.desktop_denied import with_denied_app
from ..config.models import Config
from ..config.settings_access import format_value, write_setting
from ..core.desktop_settings import DEPRECATED_KEYS, DesktopLevel, DesktopSettings
from ..core.errors import ConfigError
from ..tools.desktop import running_app_names
from ..tools.desktop_permissions import platform_name

COMPUTER_ROUTES = frozenset(
    {
        "bilgisayar.ayarlar",
        "bilgisayar.ayar_yaz",
        "bilgisayar.uygulamalar",
        "bilgisayar.uygulama_reddet",
    }
)
#: Arayüzden yazılabilen alanlar: `DesktopSettings`'in kullanımdan kalkmamış alanları (#424).
SETTING_KEYS = tuple(
    field.name for field in dataclasses.fields(DesktopSettings) if field.name not in DEPRECATED_KEYS
)


def settings_view(config: Config) -> dict[str, object]:
    """`bilgisayar.ayarlar`: ayarların düz görünümü + kademe seçenekleri."""
    desktop = config.desktop
    return {
        "ok": True,
        "platform": platform_name(),
        "ayarlar": {
            name: (
                list(value)
                if isinstance(value, tuple)
                else value.value
                if isinstance(value, DesktopLevel)
                else value
            )
            for name, value in ((key, getattr(desktop, key)) for key in SETTING_KEYS)
        },
        "kademeler": [{"deger": level.value, "etiket": level.label} for level in DesktopLevel],
    }


def _raw(value: object) -> str | None:
    """Arayüz değerini `write_setting`in beklediği metne çevir (liste → virgüllü)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return value
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return ",".join(item.strip() for item in value if item.strip())
    return None


def write(config: Config, data: Mapping[str, object]) -> tuple[dict[str, object], Config]:
    """`bilgisayar.ayar_yaz{anahtar, deger}`: tek alanı doğrula, yaz, güncel ayarı döndür."""
    key = str(data.get("anahtar") or "")
    if key not in SETTING_KEYS:
        return {"ok": False, "metin": f"Bilinmeyen bilgisayar ayarı: {key or '(boş)'}."}, config
    raw = _raw(data.get("deger"))
    if raw is None:
        return {"ok": False, "metin": f"desktop.{key} için değer biçimi geçersiz."}, config
    try:
        updated, _path = write_setting(config, f"desktop.{key}", raw)
    except (ConfigError, OSError) as error:
        return {"ok": False, "metin": str(error)}, config
    shown = format_value(getattr(updated.desktop, key))
    return {**settings_view(updated), "metin": f"desktop.{key} = {shown}"}, updated


def deny_app(config: Config, app: str) -> tuple[dict[str, object], Config]:
    """`bilgisayar.uygulama_reddet{uygulama}`: uygulamayı kalıcı ret listesine ekle.

    Onay kartındaki "Her zaman reddet" de bunu kullanır (P-007); TUI/terminal aynı yazımı
    `config.desktop_denied` üzerinden yapar.
    """
    try:
        updated, text = with_denied_app(config, app)
    except ConfigError as error:
        return {"ok": False, "metin": str(error)}, config
    return {**settings_view(updated), "metin": text}, updated


def running_apps() -> dict[str, object]:
    """`bilgisayar.uygulamalar`: ret listesine eklenebilecek çalışan uygulamalar."""
    names = running_app_names()
    if isinstance(names, str):
        return {"ok": False, "metin": names, "uygulamalar": []}
    return {"ok": True, "uygulamalar": sorted(set(names), key=str.casefold)}


def dispatch(
    config: Config, name: str, data: Mapping[str, object]
) -> tuple[dict[str, object], Config]:
    """Yönlendirici: yanıt + (yazma olduysa) güncel yapılandırma."""
    if name == "bilgisayar.ayarlar":
        return settings_view(config), config
    if name == "bilgisayar.ayar_yaz":
        return write(config, data)
    if name == "bilgisayar.uygulama_reddet":
        return deny_app(config, str(data.get("uygulama") or ""))
    if name == "bilgisayar.uygulamalar":
        return running_apps(), config
    return {"ok": False, "metin": f"Bilinmeyen bilgisayar isteği: {name}"}, config
