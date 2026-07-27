"""Seçilen modelleri kullanıcı `config.yaml`'ına yaz.

`/level` ve `/development` ile yapılan seçim yalnızca oturum boyunca yaşarsa
kullanıcı her açılışta aynı seçimi tekrar yapmak zorunda kalır. Bu modül seçimi
kalıcılaştırır.

İki kural yazımı belirler:

1. **Yalnızca model rolleri yazılır** (`agent`, `judge`, `candidates`). Dosyadaki
   diğer bölümler (`runtime`, `embedding`, `extra_candidates`…) okunup aynen geri
   yazılır; kullanıcının elle ayarladığı hiçbir şey kaybolmaz. `tiers` de
   yazılmaz: kademe tanımları `defaults.yaml`'ın işidir, kopyalanırsa iki kaynak
   oluşur ve zamanla ayrışır.

2. **Yazım atomiktir.** Önce geçici dosyaya yazılır, sonra yerine taşınır. Yarım
   yazımda kullanıcının yapılandırması bozulmaz — bir sonraki açılışta uygulama
   hiç açılmazdı.

YAML yorumları KORUNMAZ: `yaml.safe_load` yorumları düşürür. Kullanıcının kendi
yorumları varsa yeniden yazımda silinir; bunun alternatifi yorum-koruyan bir
ayrıştırıcıya (ruamel) bağımlılık eklemekti, seçimi kalıcılaştırmak için ağır.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import asdict
from pathlib import Path

import yaml

from ..core.errors import ConfigError
from ..core.types import ModelSpec
from .models import Config
from .paths import user_config_candidates, user_config_dir

#: Bu modülün yazdığı bölümler. Dosyadaki geri kalan her şeye dokunulmaz.
#:
#: `task_model_map` listeye DAHİLDİR ve olmak zorundadır: harita yalnızca tanımlı
#: bir aday adını işaret edebilir. Aday havuzu yazılıp harita eski hâlinde
#: bırakılsaydı dosya yükleme anında "adlı aday tanımlı değil" hatası verir ve
#: uygulama bir daha hiç açılmazdı.
MODEL_SECTIONS = ("agent", "judge", "candidates", "task_model_map")


def write_model_section(config: Config, path: Path | None = None) -> Path:
    """Etkin model rollerini kullanıcı yapılandırmasına yaz; yazılan yolu döndür.

    `path` verilmezse mevcut kullanıcı dosyası kullanılır; hiç yoksa kullanıcı
    yapılandırma dizininde yeni bir `config.yaml` oluşturulur.
    """
    target = path or _target_path(config)
    existing = _read_existing(target)
    existing.update(
        {
            "agent": _spec_to_dict(config.agent),
            "judge": _spec_to_dict(config.judge),
            "candidates": [_spec_to_dict(spec) for spec in config.candidates],
            "task_model_map": dict(config.task_model_map),
        }
    )
    _atomic_write(target, existing)
    return target


def write_verification_commands(
    config: Config, commands: tuple[str, ...], path: Path | None = None
) -> Path:
    """Doğrulama komutlarını `runtime:` altına yaz; yazılan yolu döndür.

    Yalnızca bu anahtar güncellenir, `runtime`'ın diğer ayarları korunur: kullanıcı
    orada zaman aşımı ya da adım sınırı değiştirmiş olabilir ve bir kapı planını
    onaylamak onları sıfırlamamalıdır.
    """
    target = path or _target_path(config)
    existing = _read_existing(target)
    runtime = existing.get("runtime")
    updated = dict(runtime) if isinstance(runtime, dict) else {}
    updated["verification_commands"] = list(commands)
    existing["runtime"] = updated
    _atomic_write(target, existing)
    return target


def write_provider(config: Config, provider: str, path: Path | None = None) -> Path:
    """Sağlayıcı tercihini `runtime:` altına yaz; yazılan yolu döndür.

    Yalnızca bu anahtar güncellenir; `runtime`ın diğer ayarları korunur.
    """
    target = path or _target_path(config)
    existing = _read_existing(target)
    runtime = existing.get("runtime")
    updated = dict(runtime) if isinstance(runtime, dict) else {}
    updated["provider"] = provider
    existing["runtime"] = updated
    _atomic_write(target, existing)
    return target


def _target_path(config: Config) -> Path:
    """Yazılacak dosya: yapılandırmanın geldiği dosya, yoksa kullanıcı dizini."""
    if config.source is not None:
        return config.source
    existing = next((item for item in user_config_candidates() if item.is_file()), None)
    return existing or user_config_dir() / "config.yaml"


def _read_existing(path: Path) -> dict[str, object]:
    """Dosyadaki mevcut ayarları oku. Yoksa boş sözlük."""
    if not path.is_file():
        return {}
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"Yapılandırma okunamadı ({path}): {exc}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(
            f"Yapılandırma geçerli YAML değil ({path}): {exc}. "
            "Seçim kaydedilmedi; dosyayı düzelt ya da sil."
        ) from exc
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ConfigError(f"Yapılandırma kökü sözlük olmalı ({path}).")
    return raw


def _spec_to_dict(spec: ModelSpec) -> dict[str, object]:
    """`ModelSpec`'i YAML'a yazılabilir sözlüğe çevir.

    Boş alanlar (etiketsiz model, yedeksiz model) yazılmaz: dosyada `tags: []`
    satırları gürültüden başka bir şey değildir.

    Ölçüt "boş mu" DEĞİL "tanımsız mı": sayısal bir alanda `0` geçerli ve anlamlı
    bir değer olabilir. Doğruluk/yanlışlık ölçütü kullanılsaydı sessizce atılır,
    yükleyici varsayılana düşer ve kullanıcının açıkça yazdığı tercih tersine dönerdi.
    """
    data = asdict(spec)
    return {
        key: (list(value) if isinstance(value, tuple) else value)
        for key, value in data.items()
        if value is not None and value != () and value != ""
    }


def _atomic_write(path: Path, data: dict[str, object]) -> None:
    """Geçici dosyaya yaz, sonra yerine taşı: yarım yazım config'i bozamaz."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    # Geçici dosya HEDEFLE AYNI DİZİNDE açılır: `os.replace` yalnızca aynı dosya
    # sisteminde atomiktir, /tmp başka bir bağlama noktası olabilir.
    handle, name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    temporary = Path(name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(text)
        temporary.replace(path)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise ConfigError(f"Yapılandırma yazılamadı ({path}): {exc}") from exc
