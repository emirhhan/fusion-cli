"""Nokta yoluyla ayar okuma/yazma (P-029): `fusion config get/set/list`, `/config`, `-c`.

Claude Code `/config key=value` ve Codex `-c key=value` davranışının Fusion karşılığı.
Yol `bölüm.alan` biçimindedir (`runtime.max_tokens`, `embedding.provider`); tip
doğrulaması dataclass alan tiplerinden türetilir: boolean, tam sayı, ondalık, metin,
Enum ve metin/sayı listesi (virgülle). Model rolleri (`agent`, `judge`, `candidates`)
buradan yazılmaz — onların kendi akışları ve yazıcıları var (`/model`, `/level`).

Oturum içi uygulama (`apply_setting`) ile kalıcı yazım (`write_setting`) ayrıdır:
`-c key=value` yalnız oturuma uygulanır, `/config key=value` ikisini de yapar.
"""

from __future__ import annotations

import dataclasses
from dataclasses import replace
from enum import Enum
from pathlib import Path
from types import UnionType
from typing import Union, get_args, get_origin, get_type_hints

from ..core.errors import ConfigError
from .models import Config, EmbeddingConfig, RuntimeConfig

#: Nokta yoluyla erişilebilen bölümler (ad → dataclass tipi).
SETTING_SECTIONS: dict[str, type] = {"runtime": RuntimeConfig, "embedding": EmbeddingConfig}

#: Serbest metin görünen ama yalnız belirli değerleri anlamlı olan alanlar (31 Ekim: `mavi`
#: 'tamam' deyip çalışma anında sessizce varsayılana düşüyordu). `ui.theme.PALETTES` ve
#: `view_commands.TUI_MODES` ile aynı tutulur; test_settings_access bunu denetler (config katmanı
#: ui'yi içe aktaramaz).
SETTING_CHOICES: dict[str, tuple[str, ...]] = {
    "runtime.terminal_theme": ("koyu", "acik", "ansi", "daltonizm"),
    "runtime.tui": ("fullscreen", "inline"),
}

_TRUE = frozenset({"true", "1", "yes", "on", "evet", "açık", "acik", "aç", "ac"})
_FALSE = frozenset({"false", "0", "no", "off", "hayır", "hayir", "kapalı", "kapali", "kapat"})


@dataclasses.dataclass(frozen=True, slots=True)
class Setting:
    """Listelemede tek satır: yol, görünen değer ve tip adı."""

    path: str
    value: str
    kind: str


def _field_type(section: str, name: str) -> object:
    cls = SETTING_SECTIONS.get(section)
    if cls is None:
        raise ConfigError(
            f"Bilinmeyen ayar bölümü: '{section}'. Bölümler: {', '.join(SETTING_SECTIONS)}"
        )
    hints = get_type_hints(cls)
    if name not in hints:
        raise ConfigError(
            f"Bilinmeyen ayar: '{section}.{name}'. Liste için: fusion config list {section}"
        )
    return hints[name]


def split_path(path: str) -> tuple[str, str]:
    section, dot, name = path.strip().partition(".")
    if not dot or not name or not section:
        raise ConfigError(
            f"Ayar yolu 'bölüm.alan' biçiminde olmalı (ör. runtime.max_tokens): {path}"
        )
    return section, name


def _inner(target: object) -> tuple[object, bool]:
    """`X | None` → (X, True); değilse (target, False)."""
    if get_origin(target) in (UnionType, Union):
        members = [arg for arg in get_args(target) if arg is not type(None)]
        if len(members) == 1:
            return members[0], True
    return target, False


def kind_name(target: object) -> str:
    inner, optional = _inner(target)
    if isinstance(inner, type) and issubclass(inner, Enum):
        name = "|".join(str(member.value) for member in inner)
    elif get_origin(inner) is tuple:
        (item, *_) = get_args(inner)
        name = f"liste[{kind_name(item)}]"
    elif get_origin(inner) is dict:
        name = "sözlük"
    elif inner is bool:
        name = "boolean"
    elif inner is int:
        name = "tam sayı"
    elif inner is float:
        name = "sayı"
    elif inner is str:
        name = "metin"
    else:
        name = getattr(inner, "__name__", str(inner))
    return f"{name}|null" if optional else name


def parse_value(raw: str, target: object, where: str) -> object:
    """Kullanıcının yazdığı metni alan tipine çevir; uymuyorsa `ConfigError`."""
    inner, optional = _inner(target)
    text = raw.strip()
    if optional and text.lower() in ("null", "none", "yok", ""):
        return None
    if inner is bool:
        if text.lower() in _TRUE:
            return True
        if text.lower() in _FALSE:
            return False
        raise ConfigError(f"{where}: true/false bekleniyordu, gelen: {raw!r}")
    if inner is int:
        try:
            return int(text)
        except ValueError:
            raise ConfigError(f"{where}: tam sayı bekleniyordu, gelen: {raw!r}") from None
    if inner is float:
        try:
            return float(text)
        except ValueError:
            raise ConfigError(f"{where}: sayı bekleniyordu, gelen: {raw!r}") from None
    if inner is str:
        choices = SETTING_CHOICES.get(where)
        if choices and text.lower() not in choices:
            raise ConfigError(
                f"{where}: geçersiz değer '{text}'. İzin verilen: {', '.join(choices)}"
            )
        return text.lower() if choices else text
    if isinstance(inner, type) and issubclass(inner, Enum):
        try:
            return inner(text.lower())
        except ValueError:
            allowed = ", ".join(str(member.value) for member in inner)
            raise ConfigError(
                f"{where}: geçersiz değer '{text}'. İzin verilen: {allowed}"
            ) from None
    if get_origin(inner) is tuple:
        (item, *_) = get_args(inner)
        parts = [part.strip() for part in text.split(",") if part.strip()]
        return tuple(parse_value(part, item, where) for part in parts)
    raise ConfigError(f"{where}: bu ayar komut satırından değiştirilemez (tip: {kind_name(inner)})")


def format_value(value: object) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (tuple, list)):
        return ", ".join(format_value(item) for item in value) or "(boş)"
    if isinstance(value, dict):
        return ", ".join(f"{key}={format_value(item)}" for key, item in value.items()) or "(boş)"
    return str(value)


def yaml_value(value: object) -> object:
    """Dosyaya yazılacak düz değer: Enum → değer, demet → liste."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [yaml_value(item) for item in value]
    return value


def read_setting(config: Config, path: str) -> str:
    section, name = split_path(path)
    _field_type(section, name)
    return format_value(getattr(getattr(config, section), name))


def list_settings(config: Config, filter_text: str = "") -> list[Setting]:
    """Tüm erişilebilir ayarlar (isteğe bağlı alt dizi süzgeci, büyük/küçük duyarsız)."""
    needle = filter_text.strip().casefold()
    rows: list[Setting] = []
    for section, cls in SETTING_SECTIONS.items():
        hints = get_type_hints(cls)
        holder = getattr(config, section)
        for field in dataclasses.fields(cls):
            path = f"{section}.{field.name}"
            if needle and needle not in path.casefold():
                continue
            choices = SETTING_CHOICES.get(path)
            kind = "|".join(choices) if choices else kind_name(hints[field.name])
            rows.append(Setting(path, format_value(getattr(holder, field.name)), kind))
    return rows


def apply_setting(config: Config, path: str, raw: str) -> Config:
    """Ayarı yalnız bu `Config` nesnesine uygula (oturumluk); doğrulanmış kopya döner."""
    section, name = split_path(path)
    value = parse_value(raw, _field_type(section, name), path)
    holder = getattr(config, section)
    return replace(config, **{section: replace(holder, **{name: value})})


def parse_override(pair: str) -> tuple[str, str]:
    """`-c yol=değer` çiftini ayır."""
    path, equals, raw = pair.partition("=")
    if not equals or not path.strip():
        raise ConfigError(f"Geçersiz geçersiz kılma: {pair!r} — biçim: bölüm.alan=değer")
    return path.strip(), raw


def apply_overrides(config: Config, pairs: tuple[str, ...]) -> Config:
    for pair in pairs:
        path, raw = parse_override(pair)
        config = apply_setting(config, path, raw)
    return config


def write_setting(
    config: Config, path: str, raw: str, file: Path | None = None
) -> tuple[Config, Path]:
    """Ayarı doğrula, kullanıcı dosyasına yaz ve güncellenmiş `Config` ile yolu döndür."""
    from . import writer

    section, name = split_path(path)
    value = parse_value(raw, _field_type(section, name), path)
    updated = replace(config, **{section: replace(getattr(config, section), **{name: value})})
    target = writer.write_section_value(config, section, name, yaml_value(value), file)
    return updated, target
