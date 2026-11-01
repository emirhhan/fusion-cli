"""CLI'de Chrome bağlantısının kullanıcıya ait tercihleri (#421).

Claude Code: `/chrome` › **Enabled by default** CLI ve VS Code'un paylaştığı TEK ayardır;
"Claude in Chrome extension detected" başlangıç sorusunun cevabı bu ayarı değiştirir; ilk
`--chrome` açılışındaki tanıtım bir kez gösterilir; "Claude wants to use your browser"
istemindeki **Don't ask again** sonraki oturumlarda istemi kapatır.

Kayıt kullanıcının yapılandırma dizinindedir (`chrome-cli.json`); proje dosyası Chrome'u
açamaz (Claude: "a project can't turn on Claude in Chrome").
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from ..core.errors import ConfigError
from .paths import user_config_dir

STORE_NAME = "chrome-cli.json"


@dataclasses.dataclass(frozen=True)
class ChromeCliPrefs:
    #: `None`: kullanıcı henüz seçmedi (başlangıç sorusu sorulabilir).
    enabled_by_default: bool | None = None
    #: Kurulum istemi "Bir daha sorma" ile kapatıldı.
    dont_ask_install: bool = False
    #: İlk `--chrome` tanıtımı gösterildi.
    intro_seen: bool = False


_KEYS = {
    "enabledByDefault": "enabled_by_default",
    "dontAskInstall": "dont_ask_install",
    "introSeen": "intro_seen",
}


def store_path() -> Path:
    return user_config_dir() / STORE_NAME


def load(path: Path | None = None) -> ChromeCliPrefs:
    """Tercihleri oku; dosya yoksa ya da bozuksa varsayılanlar."""
    target = store_path() if path is None else path
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ChromeCliPrefs()
    if not isinstance(payload, dict):
        return ChromeCliPrefs()
    values = {
        field: payload[key] for key, field in _KEYS.items() if isinstance(payload.get(key), bool)
    }
    return ChromeCliPrefs(**values)


def save(prefs: ChromeCliPrefs, path: Path | None = None) -> None:
    """Tercihleri yaz; yazılamazsa `ConfigError` (Türkçe)."""
    target = store_path() if path is None else path
    body = {key: getattr(prefs, field) for key, field in _KEYS.items()}
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as error:
        raise ConfigError(f"Chrome tercihi yazılamadı: {error}") from None


def update(path: Path | None = None, **changes: bool | None) -> ChromeCliPrefs:
    """Okuyup değiştirilmiş KOPYAYI yaz ve döndür."""
    # Alan adları `_KEYS` ile sınırlı; değerler bool (enabled_by_default None olabilir).
    updated = dataclasses.replace(load(path), **changes)  # type: ignore[arg-type]
    save(updated, path)
    return updated
