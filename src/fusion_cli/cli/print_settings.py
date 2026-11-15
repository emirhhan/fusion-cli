"""`--settings` içindeki Claude ayar anahtarlarının oturuma uygulanması (#296).

Claude'da `--settings <dosya|json>` bu oturum için settings.json anahtarlarını ezer. Fusion'da
karşılığı olan anahtarlar:

- `model` → oturum modeli (`--model` önceliklidir),
- `permissions.allow/ask/deny` → oturumluk izin kuralları,
- `permissions.defaultMode` → başlangıç kipi (`--permission-mode` önceliklidir),
- `permissions.additionalDirectories` → ek erişim kökleri (`--add-dir` gibi),
- `env` → koşunun ortam değişkenleri,
- `disableAllHooks: true` → kancalar kapalı.

`--setting-sources user,project,local` değerleri doğrulanır (geçersiz kaynak hatadır) ve
yalnız adı geçen katmanlar yüklenir (bkz. `config/setting_sources.py`).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

from ..config.models import Config
from ..config.setting_sources import set_setting_sources
from ..ui import print_messages as texts

SETTING_SOURCES = ("user", "project", "local")


@dataclass(frozen=True, slots=True)
class SessionSettings:
    """`--settings` anahtarlarından türeyen oturum değerleri."""

    default_mode: str | None = None
    add_dirs: tuple[Path, ...] = ()
    env: tuple[tuple[str, str], ...] = ()
    disable_hooks: bool = False


def read_settings(settings: dict[str, object]) -> SessionSettings:
    block = settings.get("permissions")
    permissions = block if isinstance(block, dict) else {}
    mode = permissions.get("defaultMode")
    dirs = permissions.get("additionalDirectories")
    env = settings.get("env")
    return SessionSettings(
        default_mode=mode if isinstance(mode, str) and mode.strip() else None,
        add_dirs=tuple(
            Path(item).expanduser() for item in dirs if isinstance(item, str) and item.strip()
        )
        if isinstance(dirs, list)
        else (),
        env=tuple((str(k), str(v)) for k, v in env.items() if isinstance(k, str))
        if isinstance(env, dict)
        else (),
        disable_hooks=settings.get("disableAllHooks") is True,
    )


def apply_settings(config: Config, session: SessionSettings) -> Config:
    """Ortamı ve kanca kapatmayı uygula (ortam bu süreç için ayarlanır)."""
    for key, value in session.env:
        os.environ[key] = value
    if session.disable_hooks:
        config = replace(config, runtime=replace(config.runtime, hooks_enabled=False))
    return config


def check_setting_sources(raw: str | None) -> tuple[str, ...] | None:
    """`--setting-sources` virgüllü listesi; bilinmeyen kaynak `ValueError`."""
    if raw is None:
        return None
    items = tuple(item.strip().lower() for item in raw.split(",") if item.strip())
    unknown = [item for item in items if item not in SETTING_SOURCES]
    if unknown:
        raise ValueError(texts.PRINT_SETTING_SOURCES_INVALID.format(given=", ".join(unknown)))
    return items


def apply_setting_sources(raw: str | None) -> None:
    """`--setting-sources` doğrula ve bu süreç için uygula (verilmezse dokunma)."""
    sources = check_setting_sources(raw)
    if sources is not None:
        set_setting_sources(sources)


def root_settings(
    config: Config, raw: str | None, model_flag: str | None
) -> tuple[Config, tuple[Path, ...]]:
    """Kök komut `--settings`: `model` (`--model` öncelikli), `env`, `disableAllHooks`,
    `permissions.additionalDirectories`, `permissions.defaultMode` (başlangıç kipi) ve
    `permissions.allow/ask/deny` (oturumluk kural katmanı, `config/flag_settings.py`).
    """
    from ..config.flag_settings import set_flag_permissions
    from ..config.flag_settings_anchor import record_settings_flag
    from .print_options import apply_model, load_settings, parse_permission_mode

    record_settings_flag(raw)  # `/x` kalıbı `--settings` dosyasının dizinine bağlanır (#45)
    settings = load_settings(raw)
    if not settings:
        return config, ()
    session = read_settings(settings)
    model = settings.get("model")
    if not model_flag and isinstance(model, str) and model.strip():
        config = apply_model(config, model, None)
    block = settings.get("permissions")
    set_flag_permissions(block if isinstance(block, dict) else None)
    if session.default_mode is not None:
        mode = parse_permission_mode(session.default_mode, skip_permissions=False)
        config = replace(config, runtime=replace(config.runtime, approval_mode=mode.value))
    return apply_settings(config, session), session.add_dirs
