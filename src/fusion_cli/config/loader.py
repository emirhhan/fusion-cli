"""Yapılandırma yükleyici: gömülü varsayılanlar + kullanıcı dosyası → tiplenmiş `Config`.

Akış:
1. `.env` dosyaları yüklenir (yalnızca açık çağrıyla — import anında iş yapılmaz).
2. Pakete gömülü `defaults.yaml` okunur; varsayılanların TEK kaynağıdır.
3. Bulunan ilk kullanıcı yapılandırması bunun üzerine DERİN birleştirilir.
4. Sonuç tiplenmiş dataclass'lara dönüştürülür; bilinmeyen anahtar ya da yanlış tip
   sessizce yutulmaz, anlaşılır bir `ConfigError` verir.

Dönüştürme jeneriktir: dataclass alanlarından türetilir. Yeni bir ayar eklemek için
`defaults.yaml`'a bir satır ve dataclass'a bir alan eklemek yeterlidir; bu dosyaya
dokunulmaz.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any, TypeVar, get_args, get_origin, get_type_hints

import yaml
from dotenv import load_dotenv

from ..core.errors import ConfigError
from ..core.types import ModelSpec
from .models import Config, EmbeddingConfig, RuntimeConfig, TierSpec
from .paths import bundled_defaults, env_file_candidates, memory_dir, user_config_candidates

#: Yapılandırmanın en üst düzeyinde izin verilen bölümler.
_SECTIONS = (
    "agent",
    "candidates",
    "extra_candidates",
    "judge",
    "vision",
    "task_model_map",
    "runtime",
    "embedding",
    "tiers",
)

# PEP 695 sözdizimi yerine TypeVar: paket Python 3.11'i de destekler.
T = TypeVar("T")


def load_environment() -> None:
    """`.env` dosyalarını sırayla yükle. Önce yüklenen kazanır; mevcut ortam ezilmez."""
    for candidate in env_file_candidates():
        if candidate.is_file():
            load_dotenv(candidate)


def load_config(path: str | Path | None = None) -> Config:
    """Yapılandırmayı yükle ve doğrula.

    `path` verilirse yalnızca o dosya kullanıcı yapılandırması sayılır.
    """
    load_environment()

    defaults = _read_yaml(bundled_defaults())
    source = Path(path) if path is not None else _first_existing(user_config_candidates())
    if source is not None:
        if not source.is_file():
            raise ConfigError(f"Yapılandırma dosyası bulunamadı: {source}")
        user = _read_yaml(source)
        _reject_removed(user)
        merged = _deep_merge(defaults, _apply_renames(user))
    else:
        merged = defaults

    try:
        return _assemble(merged, source)
    except ConfigError as exc:
        # Hangi dosyanın suçlu olduğu söylenmezse kullanıcı aramak zorunda kalıyor;
        # dosya birden çok yerde olabiliyor (FUSION_CONFIG, ./, kullanıcı dizini).
        if source is None:
            raise
        raise ConfigError(f"{exc} (dosya: {source})") from exc


def _assemble(merged: dict[str, object], source: Path | None) -> Config:
    """Birleştirilmiş sözlüğü doğrulayıp `Config` kur."""
    _reject_unknown(merged, _SECTIONS, "yapılandırma kökü")
    return Config(
        agent=_build(ModelSpec, merged["agent"], "agent"),
        candidates=_build_candidates(merged["candidates"], merged.get("extra_candidates")),
        judge=_build(ModelSpec, merged["judge"], "judge"),
        # Görme opsiyoneldir: tanımlı değilse görsel kapı hiç kurulmaz.
        vision=_build(ModelSpec, merged["vision"], "vision") if merged.get("vision") else None,
        task_model_map=_build_task_map(merged["task_model_map"], merged["candidates"]),
        runtime=_build(RuntimeConfig, merged["runtime"], "runtime"),
        embedding=_build(EmbeddingConfig, merged["embedding"], "embedding"),
        memory_dir=memory_dir(),
        source=source,
        tiers=_build_tiers(merged["tiers"]),
    )


def _build_tiers(raw: object) -> tuple[TierSpec, ...]:
    """Kademe listesini doğrula: boş olamaz, adlar benzersiz ve küçük harf olmalı.

    Ad benzersizliği şart: `tier_by_name` ilk eşleşeni döndürür, bir ad iki kez
    yazılırsa ikincisi sessizce ölü tanım olurdu.
    """
    if not isinstance(raw, list) or not raw:
        raise ConfigError("tiers: en az bir kademe tanımlı olmalı.")
    specs = tuple(_build(TierSpec, item, f"tiers[{index}]") for index, item in enumerate(raw))
    for spec in specs:
        if spec.name != spec.name.lower():
            raise ConfigError(f"tiers: kademe adı küçük harf olmalı, gelen: '{spec.name}'")
        if not spec.candidates:
            raise ConfigError(f"tiers.{spec.name}: en az bir aday tanımlı olmalı.")
    names = [spec.name for spec in specs]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ConfigError(
            f"tiers: kademe adları benzersiz olmalı, tekrar eden: {', '.join(duplicates)}"
        )
    return specs


def _build_candidates(raw: object, extra: object = None) -> tuple[ModelSpec, ...]:
    """Aday listesini doğrula: boş olamaz, adlar benzersiz olmalı.

    `extra_candidates` havuza EKLER, yerini almaz. Derin birleştirmede bir liste
    tamamen değiştirilir; varsayılanları koruyup yanına yerel bir model (Ollama,
    vLLM) eklemek isteyen kullanıcı için ekleyici bir bölüm gereklidir.
    """
    if not isinstance(raw, list) or not raw:
        raise ConfigError("candidates: en az bir aday tanımlı olmalı.")
    specs = tuple(_build(ModelSpec, item, f"candidates[{index}]") for index, item in enumerate(raw))
    if extra is not None:
        if not isinstance(extra, list):
            raise ConfigError("extra_candidates: liste bekleniyordu.")
        specs += tuple(
            _build(ModelSpec, item, f"extra_candidates[{index}]")
            for index, item in enumerate(extra)
        )
    names = [spec.name for spec in specs]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ConfigError(
            f"candidates: aday adları benzersiz olmalı, tekrar eden: {', '.join(duplicates)}"
        )
    return specs


def _build_task_map(raw: object, candidates: object) -> dict[str, str]:
    """Görev tipi eşlemesi var olmayan bir adayı işaret edemez."""
    if not isinstance(raw, dict):
        raise ConfigError(f"task_model_map: sözlük bekleniyordu, gelen: {type(raw).__name__}")
    known = {
        item.get("name")
        for item in (candidates if isinstance(candidates, list) else [])
        if isinstance(item, dict)
    }
    mapping: dict[str, str] = {}
    for task_type, name in raw.items():
        if not isinstance(name, str):
            raise ConfigError(f"task_model_map.{task_type}: metin bekleniyordu.")
        if name not in known:
            raise ConfigError(
                f"task_model_map.{task_type}: '{name}' adlı aday tanımlı değil. "
                f"Tanımlı adaylar: {', '.join(sorted(str(k) for k in known))}"
            )
        mapping[str(task_type)] = name
    return mapping


# --------------------------------------------------------------------------- #
# Okuma ve birleştirme
# --------------------------------------------------------------------------- #

# YAML doğası gereği tipsizdir; `Any` yalnızca bu sınırda kullanılır ve aşağıdaki
# `_build` çağrısında tiplenmiş dataclass'lara dönüştürülerek katmanlara öyle geçer.
YamlMapping = dict[str, Any]


def _read_yaml(path: Path) -> YamlMapping:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"Yapılandırma okunamadı ({path}): {exc}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"Yapılandırma geçerli YAML değil ({path}): {exc}") from exc
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ConfigError(f"Yapılandırma kökü sözlük olmalı ({path}), gelen: {type(raw).__name__}")
    return raw


#: Taşıma sırasında ADI DEĞİŞEN ayarlar: eski ad → yeni ad.
#: Kullanıcının elindeki config'in yeniden adlandırma yüzünden patlaması,
#: davranışın korunduğu bir taşımada kabul edilebilir değil.
RENAMED_KEYS = {
    "runtime": {"agent_max_iterations": "agent_max_steps"},
}

#: Taşınmayan ayarlar: neden yok olduklarını söyleyebilmek için. Sessizce
#: yutulmazlar — kullanıcı bir şey ayarladığını sanıp beklentiye girmesin.
REMOVED_KEYS = {
    "runtime": {"live_input": "tur sürerken canlı giriş henüz taşınmadı"},
}


def _apply_renames(data: YamlMapping) -> YamlMapping:
    """Eski adla yazılmış ayarları yeni adlarına taşı."""
    result = dict(data)
    for section, renames in RENAMED_KEYS.items():
        raw = result.get(section)
        if not isinstance(raw, dict):
            continue
        section_data = dict(raw)
        for old, new in renames.items():
            if old in section_data:
                # Yeni ad da yazılmışsa kullanıcının açık tercihi odur.
                section_data.setdefault(new, section_data[old])
                del section_data[old]
        result[section] = section_data
    return result


def _reject_removed(data: YamlMapping) -> None:
    """Taşınmamış ayarlar için genel liste yerine sebebini söyleyen hata ver."""
    for section, removed in REMOVED_KEYS.items():
        raw = data.get(section)
        if not isinstance(raw, dict):
            continue
        for key, reason in removed.items():
            if key in raw:
                raise ConfigError(f"{section}.{key}: bu ayar artık yok — {reason}. Satırı sil.")


def _first_existing(candidates: tuple[Path, ...]) -> Path | None:
    return next((candidate for candidate in candidates if candidate.is_file()), None)


def _deep_merge(base: YamlMapping, overlay: YamlMapping) -> YamlMapping:
    """`overlay`'i `base` üzerine derin birleştir. Liste değerleri değiştirilir, eklenmez."""
    merged: YamlMapping = dict(base)
    for key, value in overlay.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = _deep_merge(current, value)
        else:
            merged[key] = value
    return merged


# --------------------------------------------------------------------------- #
# Doğrulama ve dönüştürme
# --------------------------------------------------------------------------- #


def _reject_unknown(data: YamlMapping, allowed: tuple[str, ...], where: str) -> None:
    unknown = sorted(set(data) - set(allowed))
    if unknown:
        raise ConfigError(
            f"{where}: bilinmeyen anahtar {', '.join(unknown)}. "
            f"Beklenenler: {', '.join(sorted(allowed))}"
            "\nYalnızca DEĞİŞTİRMEK istediğin anahtarları yaz; gerisi zaten varsayılan."
        )


def _build(cls: type[T], data: object, where: str) -> T:
    """Bir sözlüğü dataclass'a dönüştür; eksik/fazla/yanlış tipli alanı hata yap."""
    if not isinstance(data, dict):
        raise ConfigError(f"{where}: sözlük bekleniyordu, gelen: {type(data).__name__}")

    hints = get_type_hints(cls)
    fields = {field.name: field for field in dataclasses.fields(cls)}  # type: ignore[arg-type]
    _reject_unknown(data, tuple(fields), where)

    values: dict[str, object] = {}
    for name, field in fields.items():
        if name in data:
            values[name] = _convert(data[name], hints[name], f"{where}.{name}")
        elif _has_default(field):
            continue
        else:
            raise ConfigError(
                f"{where}: '{name}' alanı eksik. Varsayılanı `defaults.yaml` içinde tanımlı olmalı."
            )
    return cls(**values)


def _has_default(field: dataclasses.Field[Any]) -> bool:
    return (
        field.default is not dataclasses.MISSING or field.default_factory is not dataclasses.MISSING
    )


def _convert(value: object, target: object, where: str) -> object:
    """Ham YAML değerini hedef tipe çevir; uymuyorsa anlaşılır hata ver."""
    if dataclasses.is_dataclass(target) and isinstance(target, type):
        return _build(target, value, where)

    if get_origin(target) is tuple:
        return _convert_tuple(value, target, where)

    if target is bool:
        return _expect(value, bool, "boolean", where)
    if target is int:
        # `bool` Python'da `int` alt tipidir; ayarlarda sayı beklenen yere True sızmasın.
        if isinstance(value, bool):
            raise ConfigError(f"{where}: tam sayı bekleniyordu, gelen: boolean")
        return _expect(value, int, "tam sayı", where)
    if target is float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ConfigError(f"{where}: sayı bekleniyordu, gelen: {type(value).__name__}")
        return float(value)
    if target is str:
        return _expect(value, str, "metin", where)

    raise ConfigError(f"{where}: desteklenmeyen ayar tipi: {target!r}")


def _convert_tuple(value: object, target: object, where: str) -> tuple[object, ...]:
    (item_type, *_) = get_args(target)
    # Metin listesi beklenen yere yazılan TEK metin, tek elemanlı liste sayılır.
    # Önceki sürüm `fallback: str | list[str]` kabul ediyordu; kullanıcıların
    # elindeki `fallback: bir/model` yazan config'ler yükleme anında patlamasın.
    # Belirsizlik yok: metin listesinde tek metnin başka anlamı olamaz.
    if item_type is str and isinstance(value, str):
        return (value,)
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise ConfigError(f"{where}: liste bekleniyordu, gelen: {type(value).__name__}")
    return tuple(_convert(item, item_type, f"{where}[{index}]") for index, item in enumerate(value))


def _expect(value: object, target: type[T], label: str, where: str) -> T:
    if not isinstance(value, target):
        raise ConfigError(f"{where}: {label} bekleniyordu, gelen: {type(value).__name__}")
    return value
